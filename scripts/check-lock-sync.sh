#!/usr/bin/env bash
# Verify that the engine's lock files are in sync with their requirements
# files.
#
# Compares pinned versions only: upstream can add wheels (and so hashes) to
# an existing release, which changes the hash lists of a regenerated lock
# without changing what gets installed. Regenerates the locks in place via
# scripts/lock-deps.sh, so a contributor who sees a failure can just commit
# the result.
#
# Usage:
#   ./scripts/check-lock-sync.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

LOCKS=(requirements.lock requirements-ml.lock requirements-dev.lock)

pins() { grep -E '^[A-Za-z0-9_.-]+==' "$1" | sed -E 's/ *\\$//'; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for f in "${LOCKS[@]}"; do
    pins "engine/$f" > "$WORK/$f.committed"
done

scripts/lock-deps.sh

status=0
for f in "${LOCKS[@]}"; do
    if ! diff -u "$WORK/$f.committed" <(pins "engine/$f"); then
        if [ -n "${GITHUB_ACTIONS:-}" ]; then
            echo "::error file=engine/$f::$f is out of date. Run scripts/lock-deps.sh and commit the result."
        else
            echo "ERROR: engine/$f is out of date. Run scripts/lock-deps.sh and commit the result." >&2
        fi
        status=1
    fi
done

exit $status
