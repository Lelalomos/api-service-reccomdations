#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_SUFFIX="$(date +%s%N)"
TEST_ENV="${TMPDIR:-/tmp}/api-test-${RUN_SUFFIX}.env"
PROJECT_NAME="api_test_${RUN_SUFFIX}"

cleanup() {
  docker compose -p "$PROJECT_NAME" --env-file "$TEST_ENV" -f "$ROOT_DIR/api-service/docker-compose.yml" down -v >/dev/null 2>&1 || true
  docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME" | xargs -r docker volume rm >/dev/null 2>&1 || true
  docker network ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME" | xargs -r docker network rm >/dev/null 2>&1 || true
  rm -f "$TEST_ENV"
}

trap cleanup EXIT

python - <<'PY' "$ROOT_DIR/api-service/.env" "$TEST_ENV" "$RUN_SUFFIX"
from pathlib import Path
import sys

base_env = Path(sys.argv[1]).read_text()
run_suffix = sys.argv[3]
replacements = {
    "API_CONTAINER_NAME=dsassignment-api-service": f"API_CONTAINER_NAME=dsassignment-api-service-{run_suffix}",
    "API_TESTS_CONTAINER_NAME=dsassignment-api-tests": f"API_TESTS_CONTAINER_NAME=dsassignment-api-tests-{run_suffix}",
    "API_HOST_PORT=8001": f"API_HOST_PORT={8100 + (int(run_suffix) % 100)}",
    "POSTGRES_CONTAINER_NAME=dsassignment-api-postgres": f"POSTGRES_CONTAINER_NAME=dsassignment-api-postgres-{run_suffix}",
    "POSTGRES_HOST_PORT=5434": f"POSTGRES_HOST_PORT={5600 + (int(run_suffix) % 100)}",
}

for old, new in replacements.items():
    base_env = base_env.replace(old, new)

Path(sys.argv[2]).write_text(base_env)
PY

docker compose -p "$PROJECT_NAME" --env-file "$TEST_ENV" -f "$ROOT_DIR/api-service/docker-compose.yml" run --build --rm api-tests pytest -q tests/test_api_unit.py tests/test_api_auth.py tests/test_api_scripts.py
