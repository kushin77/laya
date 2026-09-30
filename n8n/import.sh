#!/usr/bin/env bash
# Import Laya n8n workflows via the n8n REST API.
# Usage: ./n8n/import.sh [N8N_URL]
set -euo pipefail

N8N_URL="${1:-http://localhost:45678}"
WORKFLOW_DIR="$(cd "$(dirname "$0")/workflows" && pwd)"

echo "Importing Laya workflows into n8n at $N8N_URL..."

for workflow_file in "$WORKFLOW_DIR"/*.json; do
    name=$(basename "$workflow_file" .json)
    echo "  Importing $name..."
    response=$(curl -s -w "\n%{http_code}" -X POST "$N8N_URL/api/v1/workflows" \
        -H "Content-Type: application/json" \
        -d @"$workflow_file") || true
    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
        echo "    OK"
    elif [ "$http_code" = "409" ] || echo "$body" | grep -qi "already exists"; then
        # n8n has no live instance to verify against here; based on its public API docs a
        # duplicate workflow name returns 409, and some versions return 400 with an
        # "already exists" message in the body instead. Treat either as a no-op, not a failure,
        # so re-running this script is safe. If your n8n version reports duplicates differently,
        # adjust this check.
        echo "    Already imported, skipping"
    else
        echo "    ERROR: HTTP $http_code importing $name — $body" >&2
        echo "    You may need to set an API key or import manually via the n8n UI" >&2
    fi
done

echo ""
echo "Done. Activate workflows in the n8n UI at $N8N_URL."
echo "Note: You will need to configure credentials (Jira, Slack, Gmail, Bitbucket, Calendar) in n8n."
