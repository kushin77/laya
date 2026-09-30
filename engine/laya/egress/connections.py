# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Connection Broker — single pane of glass for all platform credentials.

Users interact with Laya Settings only. The broker handles:
1. Receiving credentials (API keys, OAuth tokens, SMTP configs)
2. Validating them (test API call to the platform, via the Platform registry)
3. Provisioning to wherever backends need them (n8n, OS keychain)
4. Tracking connection health

Credential validation and n8n workflow provisioning live elsewhere:
- ``egress/platforms/<name>.py`` — each platform's ``Platform.validate_credentials``.
- ``egress/provisioning.py`` — n8n credential/workflow provisioning and teardown.
"""

from __future__ import annotations

import json
import time
import uuid

import structlog

from laya.db.sqlite import get_db
from laya.db.timeutil import db_now
from laya.egress import provisioning
from laya.egress.models import Connection, ConnectionResult
from laya.egress.platforms import credential_validators
from laya.egress.registry import get_capabilities
from laya.integrations.platforms import PLATFORMS
from laya.security.keychain import (
    delete_egress_secret,
    get_egress_secret,
    set_egress_secret,
)

log = structlog.get_logger()

EGRESS_KEYCHAIN_SERVICE = "laya-egress"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_connection(
    platform: str,
    credentials: dict,
    name: str | None = None,
    space_id: str | None = None,
) -> ConnectionResult:
    """Create a new platform connection.

    Steps:
    1. Validate credentials with a test API call
    2. Store in OS keychain (source of truth)
    3. Provision to n8n (create credential via n8n REST API)
    4. Record in SQLite metadata table
    """
    if platform not in PLATFORMS and platform != "smtp":
        return ConnectionResult(status="failed", error=f"Unknown platform: {platform}")

    connection_id = f"conn_{uuid.uuid4().hex[:12]}"
    display_name = name or f"Laya - {PLATFORMS.get(platform, {}).get('label', platform)}"

    # Step 1: Validate
    valid, error = await _validate_credentials(platform, credentials)
    if not valid:
        return ConnectionResult(status="failed", error=error)

    # Step 2: Store in keychain
    if not _store_in_keychain(connection_id, platform, credentials):
        return ConnectionResult(status="failed", error="Failed to store credentials in keychain")

    # Step 3: Provision to n8n (skip for SMTP — handled by SMTP backend directly)
    n8n_credential_id = None
    provision_error = None
    if platform != "smtp":
        n8n_credential_id = await provisioning.provision_to_n8n(platform, display_name, credentials)
        if n8n_credential_id is None:
            provision_error = f"Failed to create n8n credential for {platform}"
            log.warning("n8n_provision_failed", platform=platform, name=display_name)

    # Step 4: Clone and activate workflows for this connection
    workflow_errors: list[str] = []
    if n8n_credential_id:
        try:
            activated, workflow_errors = await provisioning.clone_workflows_for_connection(
                platform, connection_id, display_name, n8n_credential_id,
                _get_from_keychain, space_id=space_id,
            )
            log.info("workflows_cloned", platform=platform, count=activated,
                     connection_id=connection_id)
        except Exception as e:
            workflow_errors = [str(e)]
            log.warning("workflow_clone_failed", platform=platform, error=str(e))

    # Determine final status
    all_errors = []
    if provision_error:
        all_errors.append(provision_error)
    all_errors.extend(workflow_errors)

    status = "error" if all_errors else "connected"
    error_message = "; ".join(all_errors) if all_errors else None

    # Step 5: Record in SQLite
    capabilities = [c.action_type for c in get_capabilities(platform)]
    now = db_now()

    db = await get_db()
    await db.execute(
        """INSERT INTO egress_connections
           (connection_id, platform, name, n8n_credential_id, space_id,
            status, capabilities, error_message, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            connection_id,
            platform,
            display_name,
            n8n_credential_id,
            space_id,
            status,
            json.dumps(capabilities),
            error_message,
            now,
            now,
        ),
    )
    await db.commit()

    log.info(
        "connection_created",
        connection_id=connection_id,
        platform=platform,
        n8n_credential_id=n8n_credential_id,
        status=status,
    )

    return ConnectionResult(
        status=status,
        connection_id=connection_id,
        capabilities=capabilities,
        error=error_message,
    )


async def remove_connection(connection_id: str) -> None:
    """Remove a platform connection — clean up keychain, n8n, and SQLite."""
    # Virtual executor-source connections — remove the source row
    if connection_id.startswith("exec_"):
        source_id = connection_id.removeprefix("exec_")
        db = await get_db()
        await db.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))
        await db.commit()
        log.info("executor_source_removed", source_id=source_id)
        return

    db = await get_db()

    rows = await db.execute_fetchall(
        "SELECT platform, n8n_credential_id FROM egress_connections WHERE connection_id = ?",
        (connection_id,),
    )
    if not rows:
        return

    row = rows[0]
    platform = row["platform"]
    n8n_cred_id = row["n8n_credential_id"]

    # Remove from keychain
    _remove_from_keychain(connection_id, platform)

    # Deactivate and delete cloned workflows for this connection
    await provisioning.remove_connection_workflows(connection_id)

    # Remove n8n credential
    if n8n_cred_id:
        try:
            from laya.integrations.n8n_client import delete_credential

            await delete_credential(n8n_cred_id)
        except Exception as e:
            log.warning("n8n_credential_delete_failed", error=str(e))

    # Remove from SQLite
    await db.execute(
        "DELETE FROM egress_connections WHERE connection_id = ?",
        (connection_id,),
    )
    await db.commit()

    log.info("connection_removed", connection_id=connection_id, platform=platform)


async def list_all_connections() -> list[Connection]:
    """List all configured platform connections.

    Includes both explicit egress_connections AND executor sources from
    the sources table.  Executor sources are n8n workflows that can send
    emails / messages on behalf of the user but were never registered
    through the connection-broker flow.
    """
    db = await get_db()

    connections: list[Connection] = []

    # 1. Explicit egress connections
    rows = await db.execute_fetchall(
        """SELECT connection_id, platform, name, n8n_credential_id, space_id,
                  status, capabilities, error_message, last_validated_at,
                  created_at, updated_at
           FROM egress_connections
           ORDER BY created_at DESC""",
    )

    seen_platforms: set[str] = set()
    for r in rows:
        connections.append(
            Connection(
                connection_id=r["connection_id"],
                platform=r["platform"],
                name=r["name"],
                status=r["status"],
                capabilities=json.loads(r["capabilities"] or "[]"),
                n8n_credential_id=r["n8n_credential_id"],
                space_id=r["space_id"],
                error_message=r["error_message"],
                last_validated_at=r["last_validated_at"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
        )
        seen_platforms.add(r["platform"])

    # 2. Executor sources registered in the sources table (source_type =
    #    'executor' with a webhook_path, OR name containing "Executor" for
    #    auto-discovered entries that weren't tagged correctly).
    #    Exclude sources owned by a connection (those are managed by egress_connections).
    executor_rows = await db.execute_fetchall(
        """SELECT source_id, name, platform, workflow_id, space_id, created_at
           FROM sources
           WHERE connection_id IS NULL
             AND ((source_type = 'executor' AND webhook_path IS NOT NULL)
                  OR (name LIKE '%Executor%'))
           ORDER BY created_at DESC""",
    )

    for r in executor_rows:
        platform = r["platform"]
        caps = [c.action_type for c in get_capabilities(platform)]
        connections.append(
            Connection(
                connection_id=f"exec_{r['source_id']}",
                platform=platform,
                name=r["name"],
                status="connected",
                capabilities=caps,
                n8n_credential_id=None,
                space_id=r["space_id"],
                created_at=r["created_at"] or "",
            )
        )
        seen_platforms.add(platform)

    return connections


async def test_connection(connection_id: str) -> tuple[bool, str | None]:
    """Test if a connection's credentials are still valid."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT platform FROM egress_connections WHERE connection_id = ?",
        (connection_id,),
    )
    if not rows:
        return False, "Connection not found"

    platform = rows[0]["platform"]
    credentials = _get_from_keychain(connection_id, platform)
    if not credentials:
        return False, "Credentials not found in keychain"

    valid, error = await _validate_credentials(platform, credentials)

    # Update status
    now = db_now()
    new_status = "connected" if valid else "error"
    await db.execute(
        """UPDATE egress_connections
           SET status = ?, error_message = ?, last_validated_at = ?, updated_at = ?
           WHERE connection_id = ?""",
        (new_status, error, now, now, connection_id),
    )
    await db.commit()

    return valid, error


# ---------------------------------------------------------------------------
# Credential validation dispatch
# ---------------------------------------------------------------------------


async def _validate_credentials(platform: str, credentials: dict) -> tuple[bool, str | None]:
    """Test credentials against the platform's API via the Platform registry.

    Returns (True, None) on success or (False, error_message) on failure.
    Unknown platforms (no adapter registered) skip validation, matching the
    historical behavior.
    """
    adapter = credential_validators().get(platform)
    if adapter is None:
        return True, None
    try:
        return await adapter.validate_credentials(credentials)
    except Exception as e:
        return False, f"Validation error: {str(e)}"


# ---------------------------------------------------------------------------
# Keychain helpers
# ---------------------------------------------------------------------------


# Short TTL cache for connection credentials. _get_from_keychain is a blocking
# keyring syscall on the egress hot path (every Jira execution reads it) — this
# keeps it off the event loop for repeated reads (review §4 — P5-2). Writes and
# deletes update/invalidate the entry, so within-process reads stay correct.
_CRED_CACHE: dict[str, tuple[float, "dict | None"]] = {}
_CRED_CACHE_TTL = 60.0


def _store_in_keychain(connection_id: str, platform: str, credentials: dict) -> bool:
    """Store credentials in OS keychain."""
    key = f"{platform}:{connection_id}"
    ok = set_egress_secret(EGRESS_KEYCHAIN_SERVICE, key, json.dumps(credentials))
    if not ok:
        log.error("keychain_store_failed", connection_id=connection_id)
        return False
    _CRED_CACHE[key] = (time.monotonic(), dict(credentials))
    return True


def _get_from_keychain(connection_id: str, platform: str) -> dict | None:
    """Retrieve credentials from OS keychain (TTL-cached)."""
    key = f"{platform}:{connection_id}"
    entry = _CRED_CACHE.get(key)
    if entry is not None and (time.monotonic() - entry[0]) < _CRED_CACHE_TTL:
        # Copy so a caller mutating the result can't corrupt the cache.
        return dict(entry[1]) if entry[1] is not None else None
    raw = get_egress_secret(EGRESS_KEYCHAIN_SERVICE, key)
    try:
        val = json.loads(raw) if raw else None
    except Exception:
        return None
    _CRED_CACHE[key] = (time.monotonic(), val)
    return dict(val) if val is not None else None


def _remove_from_keychain(connection_id: str, platform: str) -> None:
    """Remove credentials from OS keychain."""
    key = f"{platform}:{connection_id}"
    if not delete_egress_secret(EGRESS_KEYCHAIN_SERVICE, key):
        log.warning("keychain_delete_failed", connection_id=connection_id)
        return
    _CRED_CACHE.pop(key, None)
