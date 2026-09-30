# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""n8n workflow provisioning for platform connections.

Handles creating n8n credentials and cloning/activating bundled workflow
templates for a connection, and tearing both down on removal. Extracted out
of ``egress/connections.py`` so the connection broker only orchestrates the
steps (validate → keychain → provision → record) without owning n8n's
credential/workflow mechanics.
"""

from __future__ import annotations

import copy
import json
import uuid

import structlog

from laya.db.sqlite import get_db
from laya.integrations.platforms import PLATFORMS

log = structlog.get_logger()


class _BlankOnMissing(dict):
    """format_map source that resolves missing template fields to ""."""

    def __missing__(self, key: str) -> str:
        return ""


async def provision_to_n8n(
    platform: str, name: str, credentials: dict
) -> str | None:
    """Create a credential in n8n and return its ID."""
    platform_config = PLATFORMS.get(platform)
    if not platform_config:
        return None

    try:
        from laya.integrations.n8n_client import create_credential

        # Merge any n8n-specific defaults (e.g. server URL)
        source = {**platform_config.get("n8n_defaults", {}), **credentials}

        # Platforms whose n8n credential schema differs from our stored fields
        # (e.g. bitbucket_server: httpHeaderAuth wants {name, value}, we store
        # {server, accessToken}) declare a declarative n8n_credential_template —
        # string values are str.format templates over the connection's fields.
        template = platform_config.get("n8n_credential_template")
        if template:
            cred_data = {
                k: v.format_map(_BlankOnMissing(source)) if isinstance(v, str) else v
                for k, v in template.items()
            }
        else:
            cred_data = source

        result = await create_credential(
            name=name,
            n8n_type=platform_config["n8n_type"],
            data=cred_data,
            # node_type feeds the (deprecated, ignored-by-n8n-v1) nodesAccess
            # field; generic-HTTP platforms have no native node, so fall back to
            # the httpRequest node type rather than sending an empty string.
            node_type=platform_config["n8n_node"] or "n8n-nodes-base.httpRequest",
        )
        return str(result.get("id", ""))
    except Exception as e:
        log.error("n8n_provision_failed", platform=platform, error=str(e))
        return None


async def clone_workflows_for_connection(
    platform: str,
    connection_id: str,
    connection_name: str,
    n8n_credential_id: str,
    get_from_keychain,
    space_id: str | None = None,
) -> tuple[int, list[str]]:
    """Clone bundled workflow templates for a specific connection.

    Idempotent — skips if sources already exist for this connection_id.

    For each template workflow (e.g., "Laya - Gmail Ingestion"):
    1. Read the bundled JSON template
    2. Rename to include connection display name
    3. Update webhook paths to be connection-specific
    4. Inject the connection's n8n credential into matching nodes
    5. Create as a new workflow in n8n via POST
    6. Register as a source with connection_id
    7. Activate the workflow

    ``get_from_keychain`` is the connection broker's cached credential reader
    (``connections._get_from_keychain``), injected to avoid a keychain-layer
    import cycle back into ``connections``.

    Returns (activated_count, error_messages).
    """
    from laya.integrations.n8n_bootstrap import (
        WORKFLOWS_DIR,
        _get_error_handler_id,
        _load_deployed_versions,
        _save_deployed_versions,
    )
    from laya.integrations.n8n_client import activate_workflow

    # Idempotency: skip if sources already exist for this connection
    db = await get_db()
    existing = await db.execute_fetchall(
        "SELECT source_id FROM sources WHERE connection_id = ?",
        (connection_id,),
    )
    if existing:
        log.debug("clone_already_exists", connection_id=connection_id, count=len(existing))
        return len(existing), []

    platform_config = PLATFORMS.get(platform, {})
    template_names = platform_config.get("workflows", [])
    if not template_names:
        return 0, []

    n8n_type = platform_config.get("n8n_type", "")
    n8n_node = platform_config.get("n8n_node", "")
    activated = 0
    errors: list[str] = []

    # Build a map of template name → JSON file
    template_files: dict[str, dict] = {}
    if WORKFLOWS_DIR.exists():
        for wf_file in WORKFLOWS_DIR.glob("*.json"):
            try:
                data = json.loads(wf_file.read_text(encoding="utf-8"))
                template_files[data.get("name", "")] = data
            except Exception:
                continue

    api_key = None
    try:
        from laya.security.keychain import get_api_key
        api_key = get_api_key("n8n")
    except Exception:
        pass

    if not api_key:
        return 0, ["n8n API key not configured"]

    from laya.config import get_n8n_config
    from laya.http_client import get_client
    base_url = get_n8n_config()["base_url"].rstrip("/")
    headers = {"X-N8N-API-KEY": api_key, "Content-Type": "application/json"}

    short_id = connection_id.replace("conn_", "")
    platform_label = platform_config.get("label", platform.title())

    # Snapshot the declared non-secret runtime config fields once (credentials
    # were stored in the keychain in create_connection step 2, so the cached
    # read is cheap). URL-ish values lose their trailing slash so workflow
    # expressions can concatenate paths without double slashes.
    workflow_config: dict | None = None
    config_fields = platform_config.get("workflow_config_fields") or []
    if config_fields:
        creds = get_from_keychain(connection_id, platform) or {}
        workflow_config = {
            k: (creds.get(k).rstrip("/") if isinstance(creds.get(k), str) else creds.get(k))
            for k in config_fields
        }

    # Fetch existing n8n workflows to prevent creating duplicates.
    # Without this check, restarts or retries can create orphan workflows
    # in n8n that the engine doesn't track, leading to double-ingestion.
    from laya.integrations.n8n_bootstrap import _get_existing_workflows
    existing_n8n_workflows = await _get_existing_workflows(base_url, api_key) or {}

    # The shared error handler's workflow ID is written into each ingestion
    # clone's settings.errorWorkflow so node failures route back to the engine.
    # Executor clones don't get wired (egress failures surface through
    # action_cards.last_error).
    error_handler_id = _get_error_handler_id()

    for template_name in template_names:
        template_data = template_files.get(template_name)
        if not template_data:
            errors.append(f"Template \"{template_name}\" not found in bundled workflows")
            continue

        wf_data = copy.deepcopy(template_data)

        # 1. Build workflow name: "Laya Gmail - Personal (Ingestion)"
        wf_type = "Executor" if "executor" in template_name.lower() else "Ingestion"
        if connection_name:
            wf_data["name"] = f"Laya {platform_label} - {connection_name} ({wf_type})"
        else:
            wf_data["name"] = f"Laya {platform_label} - {short_id} ({wf_type})"

        # Wire ingestion clones to the shared error handler so any node failure
        # (bad creds, API rate limit, code exception, engine POST failure) lands
        # in ingestion_errors on the engine.
        if error_handler_id and wf_type == "Ingestion":
            wf_data.setdefault("settings", {})["errorWorkflow"] = error_handler_id

        # 2. Update webhook paths and inject credentials
        for node in wf_data.get("nodes", []):
            # Update primary webhook path to be connection-specific
            if (node.get("type") == "n8n-nodes-base.webhook"
                    and node.get("parameters", {}).get("httpMethod")):
                old_path = node["parameters"].get("path", "")
                if old_path:
                    node["parameters"]["path"] = f"{old_path}-{short_id}"

            # Inject credential into matching nodes
            node_creds = node.get("credentials", {})
            params = node.get("parameters", {})
            node_type = node.get("type", "")
            node_cred_type = params.get("nodeCredentialType")
            # HTTP Request nodes (e.g. Gmail archive/star/mark_read) bind the
            # credential under the key named by nodeCredentialType, which can
            # differ from the platform's native n8n_type — Gmail's native type
            # is "gmailOAuth2" but its HTTP nodes use "gmailOAuth2Api".  Match
            # on the HTTP cred type for this platform and inject under that key,
            # otherwise n8n can't resolve the credential at runtime and the
            # node fails with "Credentials not found".
            from laya.egress.oauth import _PLATFORM_HTTP_CRED_TYPES
            http_cred_type = _PLATFORM_HTTP_CRED_TYPES.get(platform)
            is_http_match = (
                http_cred_type is not None
                and node_type == "n8n-nodes-base.httpRequest"
                and node_cred_type == http_cred_type
            )
            is_native_match = (
                n8n_type in node_creds
                # n8n_node may be "" for generic-HTTP platforms (bitbucket_server);
                # unguarded startswith("") would match EVERY node and spray the
                # credential across the whole workflow.
                or (bool(n8n_node) and (
                    node_type == n8n_node
                    or node_type.startswith(n8n_node)  # matches gmailTrigger, googleCalendarTrigger, etc.
                ))
                or node_cred_type == n8n_type
            )
            if is_http_match or is_native_match:
                if "credentials" not in node:
                    node["credentials"] = {}
                cred_key = http_cred_type if is_http_match else n8n_type
                node["credentials"][cred_key] = {
                    "id": n8n_credential_id,
                    "name": connection_name,
                }

        # 3. Create workflow in n8n (or reuse existing if same name already exists)
        target_name = wf_data["name"]
        existing_wf = existing_n8n_workflows.get(target_name)
        if existing_wf:
            # Workflow with this name already exists in n8n — reuse it
            wf_id = str(existing_wf["id"])
            log.info("workflow_clone_reused_existing",
                     name=target_name, id=wf_id, connection_id=connection_id)
        else:
            create_fields = {"name", "nodes", "connections", "settings", "staticData", "tags"}
            create_data = {k: v for k, v in wf_data.items() if k in create_fields}
            try:
                resp = await get_client().post(
                    f"{base_url}/api/v1/workflows",
                    headers=headers,
                    json=create_data,
                    timeout=10.0,
                )
                if resp.status_code not in (200, 201):
                    errors.append(f"Failed to create \"{target_name}\": HTTP {resp.status_code}")
                    continue
                created_wf = resp.json()
                wf_id = str(created_wf.get("id", ""))
            except Exception as e:
                errors.append(f"Failed to create \"{target_name}\": {e}")
                continue

        # 4. Activate. The client-side call occasionally raises even when the
        # server-side activation succeeded (observed on Windows: httpx errors
        # with empty `str(e)`). Verify via GET before surfacing a failure to
        # the user.
        try:
            await activate_workflow(wf_id, active=True)
            activated += 1
            log.info("workflow_cloned_and_activated",
                     name=wf_data["name"], id=wf_id, connection_id=connection_id)
        except Exception as e:
            err_detail = str(e) or f"{type(e).__name__}: {e!r}"

            try:
                verify_resp = await get_client().get(
                    f"{base_url}/api/v1/workflows/{wf_id}",
                    headers=headers,
                    timeout=10.0,
                )
                is_active = (
                    verify_resp.status_code == 200
                    and bool(verify_resp.json().get("active"))
                )
            except Exception:
                is_active = False

            if is_active:
                activated += 1
                log.info("workflow_cloned_and_activated",
                         name=wf_data["name"], id=wf_id, connection_id=connection_id)
            else:
                errors.append(f"Failed to activate \"{wf_data['name']}\": {err_detail}")
                log.warning("workflow_clone_activate_failed",
                            name=wf_data["name"], id=wf_id, error=err_detail)

        # 5. Register as source with connection_id
        is_executor = "executor" in template_name.lower()
        source_type = "executor" if is_executor else "ingestion"
        webhook_path = None
        if is_executor:
            for node in wf_data.get("nodes", []):
                if (node.get("type") == "n8n-nodes-base.webhook"
                        and node.get("parameters", {}).get("httpMethod")):
                    webhook_path = node["parameters"].get("path")
                    break

        db = await get_db()
        source_id = f"src_{uuid.uuid4().hex[:12]}"
        await db.execute(
            """INSERT INTO sources
               (source_id, name, platform, workflow_id, space_id,
                source_type, webhook_path, connection_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_id, wf_data["name"], platform, wf_id,
             space_id or "default", source_type, webhook_path, connection_id),
        )
        await db.commit()

        # Per-clone runtime config: platforms may declare non-secret credential
        # fields (workflow_config_fields) their workflows need at runtime — e.g.
        # bitbucket_server's server base URL, which the ingestion clone reads via
        # GET /metadata/{platform}-config:{{ $workflow.id }} to build REST URLs
        # and the /repos?host= filter (same per-clone pattern as slack-channels).
        # Always written under space 'default': workflow ids are globally unique
        # and the metadata GET the workflow performs defaults to that space.
        if workflow_config:
            await db.execute(
                """INSERT INTO metadata (key, value, space_id)
                   VALUES (?, ?, 'default')
                   ON CONFLICT (key, space_id) DO UPDATE SET value = excluded.value""",
                (f"{platform}-config:{wf_id}", json.dumps(workflow_config)),
            )
            await db.commit()

        # Track deployed version for this template
        bundled_version = (template_data.get("meta") or {}).get("laya_version")
        if bundled_version:
            deployed_versions = _load_deployed_versions()
            deployed_versions[template_name] = bundled_version
            _save_deployed_versions(deployed_versions)

    return activated, errors


async def remove_connection_workflows(connection_id: str) -> None:
    """Deactivate and delete all cloned n8n workflows owned by a connection."""
    from laya.integrations.n8n_client import activate_workflow

    from laya.config import get_n8n_config
    from laya.http_client import get_client
    from laya.security.keychain import get_api_key

    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT workflow_id FROM sources WHERE connection_id = ?",
        (connection_id,),
    )
    if not rows:
        return

    # Clean up per-clone metadata keyed by workflow_id (Slack channel config,
    # per-platform workflow config written at clone time).
    for row in rows:
        wf_id = row["workflow_id"]
        if wf_id:
            await db.execute(
                "DELETE FROM metadata WHERE key = ?",
                (f"slack-channels:{wf_id}",),
            )
            await db.execute(
                "DELETE FROM metadata WHERE key LIKE ?",
                (f"%-config:{wf_id}",),
            )
    await db.commit()

    api_key = get_api_key("n8n")
    if not api_key:
        return
    base_url = get_n8n_config()["base_url"].rstrip("/")
    headers = {"X-N8N-API-KEY": api_key}

    for row in rows:
        wf_id = row["workflow_id"]
        if not wf_id:
            continue
        # Deactivate then delete
        try:
            await activate_workflow(wf_id, active=False)
        except Exception:
            pass
        try:
            await get_client().delete(
                f"{base_url}/api/v1/workflows/{wf_id}",
                headers=headers,
                timeout=10.0,
            )
            log.info("workflow_clone_deleted", workflow_id=wf_id,
                     connection_id=connection_id)
        except Exception as e:
            log.warning("workflow_clone_delete_failed",
                        workflow_id=wf_id, error=str(e))

    # Remove source rows
    await db.execute(
        "DELETE FROM sources WHERE connection_id = ?",
        (connection_id,),
    )
    await db.commit()
