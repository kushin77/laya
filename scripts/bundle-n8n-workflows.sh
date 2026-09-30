#!/usr/bin/env bash
# Bundle n8n workflows into Tauri resources (imported into n8n on first run).
# Used by both build.sh (local builds) and CI (GitHub Actions).
#
# Usage:
#   ./scripts/bundle-n8n-workflows.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES_DIR="$REPO_ROOT/ui/src-tauri/resources"
ENGINE_BUNDLE="$RESOURCES_DIR/engine"
N8N_WORKFLOWS_DEST="$ENGINE_BUNDLE/n8n_workflows"

echo "── Bundling n8n workflows ──"

mkdir -p "$ENGINE_BUNDLE"

rm -rf "$N8N_WORKFLOWS_DEST"

if [ -d "$REPO_ROOT/n8n/workflows" ]; then
    cp -R "$REPO_ROOT/n8n/workflows" "$N8N_WORKFLOWS_DEST"
    echo "  $(ls "$N8N_WORKFLOWS_DEST" | wc -l | tr -d ' ') n8n workflows bundled"
else
    echo "  No n8n/workflows directory found, skipping"
fi
