#!/usr/bin/env sh
set -eu

compose_command="docker compose"

echo "Building and starting API, dashboard, and MCP services..."
$compose_command up --build -d

wait_for_http() {
  url="$1"
  service="$2"
  attempt=0
  until curl --fail --silent "$url" >/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 40 ]; then
      echo "$service did not become healthy. Inspect logs with: docker compose logs $service"
      exit 1
    fi
    sleep 2
  done
}

echo "Waiting for the API and dashboard health endpoints..."
wait_for_http "http://localhost:${API_PORT:-8000}/health" "api"
wait_for_http "http://localhost:${DASHBOARD_PORT:-8501}/_stcore/health" "dashboard"

attempt=0
until [ "$($compose_command ps --status running --services mcp)" = "mcp" ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 20 ]; then
    echo "MCP service is not running. Inspect logs with: docker compose logs mcp"
    exit 1
  fi
  sleep 1
done

echo "Demo is ready."
echo "Dashboard: http://localhost:${DASHBOARD_PORT:-8501}"
echo "API docs: http://localhost:${API_PORT:-8000}/docs"
echo "MCP endpoint: http://localhost:${MCP_PORT:-8001}/mcp"
echo "Follow docs/demo-script.md for the 3-5 minute walkthrough."
echo "Stop with: docker compose down"
