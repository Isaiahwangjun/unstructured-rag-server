#!/usr/bin/env bash
# Reproduce the queries documented in examples/sample_output.md
# against the live deployment. No OpenAI key needed on your side —
# the deployed instance handles its own embedding for incoming
# queries.
#
# Override MCP_URL to point at a different deployment or your own
# local server.
set -euo pipefail

MCP_URL="${MCP_URL:-https://unstructured-rag-server.onrender.com/mcp}"
export MCP_URL
echo "# MCP_URL=$MCP_URL"
echo

cd "$(dirname "$0")/.."

queries=(
  "supervised learning"
  "Q4 revenue by segment"
  "資料擴增 SMOTE"
)

failed=0
for q in "${queries[@]}"; do
  echo "===================="
  echo "Query: $q"
  echo "===================="
  if uv run python scripts/mcp_client_demo.py "$q" 3; then
    echo "[OK]"
  else
    echo "[FAIL] exit=$?"
    failed=$((failed + 1))
  fi
  echo
done

if [ "$failed" -gt 0 ]; then
  echo "$failed of ${#queries[@]} queries failed."
  exit 1
fi
echo "All ${#queries[@]} queries returned valid hits."
