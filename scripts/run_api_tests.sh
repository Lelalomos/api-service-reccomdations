#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_SUFFIX="$(date +%s%N)"
API_TEST_ENV="${TMPDIR:-/tmp}/api-test-${RUN_SUFFIX}.env"
POSTGRES_TEST_ENV="${TMPDIR:-/tmp}/api-postgres-test-${RUN_SUFFIX}.env"
RABBITMQ_TEST_ENV="${TMPDIR:-/tmp}/api-rabbitmq-test-${RUN_SUFFIX}.env"
QDRANT_TEST_ENV="${TMPDIR:-/tmp}/api-qdrant-test-${RUN_SUFFIX}.env"
WORKER_TEST_ENV="${TMPDIR:-/tmp}/api-worker-test-${RUN_SUFFIX}.env"
API_PROJECT_NAME="api_test_${RUN_SUFFIX}"
POSTGRES_PROJECT_NAME="api_postgres_${RUN_SUFFIX}"
RABBITMQ_PROJECT_NAME="api_rabbitmq_${RUN_SUFFIX}"
QDRANT_PROJECT_NAME="api_qdrant_${RUN_SUFFIX}"
WORKER_PROJECT_NAME="api_worker_${RUN_SUFFIX}"
SHARED_NETWORK_NAME="api-test-backend-${RUN_SUFFIX}"

wait_for_service() {
  local project_name="$1"
  local env_file="$2"
  local compose_file="$3"
  local service_name="$4"
  local expected_state="$5"
  local attempt=0
  local container_id=""
  local current_state=""

  while [ "$attempt" -lt 60 ]; do
    container_id="$(docker compose -p "$project_name" --env-file "$env_file" -f "$compose_file" ps -q "$service_name" 2>/dev/null || true)"
    if [ -n "$container_id" ]; then
      current_state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      if [ "$current_state" = "$expected_state" ]; then
        return 0
      fi
    fi
    attempt=$((attempt + 1))
    sleep 2
  done

  echo "Service '$service_name' did not reach state '$expected_state'." >&2
  docker compose -p "$project_name" --env-file "$env_file" -f "$compose_file" ps >&2 || true
  return 1
}

cleanup() {
  docker compose -p "$API_PROJECT_NAME" --env-file "$API_TEST_ENV" -f "$ROOT_DIR/api-service/docker-compose.yml" down -v >/dev/null 2>&1 || true
  docker compose -p "$POSTGRES_PROJECT_NAME" --env-file "$POSTGRES_TEST_ENV" -f "$ROOT_DIR/postgresql/docker-compose.yml" down -v >/dev/null 2>&1 || true
  docker compose -p "$WORKER_PROJECT_NAME" --env-file "$WORKER_TEST_ENV" -f "$ROOT_DIR/worker/docker-compose.yml" down -v >/dev/null 2>&1 || true
  docker compose -p "$RABBITMQ_PROJECT_NAME" --env-file "$RABBITMQ_TEST_ENV" -f "$ROOT_DIR/rabbitmq/docker-compose.yml" down -v >/dev/null 2>&1 || true
  docker compose -p "$QDRANT_PROJECT_NAME" --env-file "$QDRANT_TEST_ENV" -f "$ROOT_DIR/vector_db/docker-compose.yml" down -v >/dev/null 2>&1 || true
  docker ps -aq --filter "label=com.docker.compose.project=$API_PROJECT_NAME" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker ps -aq --filter "label=com.docker.compose.project=$POSTGRES_PROJECT_NAME" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker ps -aq --filter "label=com.docker.compose.project=$WORKER_PROJECT_NAME" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker ps -aq --filter "label=com.docker.compose.project=$RABBITMQ_PROJECT_NAME" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker ps -aq --filter "label=com.docker.compose.project=$QDRANT_PROJECT_NAME" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker volume ls -q --filter "label=com.docker.compose.project=$API_PROJECT_NAME" | xargs -r docker volume rm >/dev/null 2>&1 || true
  docker volume ls -q --filter "label=com.docker.compose.project=$POSTGRES_PROJECT_NAME" | xargs -r docker volume rm >/dev/null 2>&1 || true
  docker volume ls -q --filter "label=com.docker.compose.project=$WORKER_PROJECT_NAME" | xargs -r docker volume rm >/dev/null 2>&1 || true
  docker volume ls -q --filter "label=com.docker.compose.project=$RABBITMQ_PROJECT_NAME" | xargs -r docker volume rm >/dev/null 2>&1 || true
  docker volume ls -q --filter "label=com.docker.compose.project=$QDRANT_PROJECT_NAME" | xargs -r docker volume rm >/dev/null 2>&1 || true
  docker network ls -q --filter "label=com.docker.compose.project=$API_PROJECT_NAME" | xargs -r docker network rm >/dev/null 2>&1 || true
  docker network ls -q --filter "label=com.docker.compose.project=$POSTGRES_PROJECT_NAME" | xargs -r docker network rm >/dev/null 2>&1 || true
  docker network ls -q --filter "label=com.docker.compose.project=$WORKER_PROJECT_NAME" | xargs -r docker network rm >/dev/null 2>&1 || true
  docker network ls -q --filter "label=com.docker.compose.project=$RABBITMQ_PROJECT_NAME" | xargs -r docker network rm >/dev/null 2>&1 || true
  docker network ls -q --filter "label=com.docker.compose.project=$QDRANT_PROJECT_NAME" | xargs -r docker network rm >/dev/null 2>&1 || true
  docker network rm "$SHARED_NETWORK_NAME" >/dev/null 2>&1 || true
  rm -f "$API_TEST_ENV" "$POSTGRES_TEST_ENV" "$RABBITMQ_TEST_ENV" "$QDRANT_TEST_ENV" "$WORKER_TEST_ENV"
}

trap cleanup EXIT

python - <<'PY' "$ROOT_DIR/postgresql/.env" "$POSTGRES_TEST_ENV" "$RUN_SUFFIX" "$SHARED_NETWORK_NAME"
from pathlib import Path
import sys

base_env = Path(sys.argv[1]).read_text()
run_suffix = sys.argv[3]
replacements = {
    "POSTGRES_CONTAINER_NAME=dsassignment-postgres": f"POSTGRES_CONTAINER_NAME=dsassignment-postgres-{run_suffix}",
    "POSTGRES_UI_CONTAINER_NAME=dsassignment-adminer": f"POSTGRES_UI_CONTAINER_NAME=dsassignment-adminer-{run_suffix}",
    "POSTGRES_TESTS_CONTAINER_NAME=dsassignment-postgres-tests": f"POSTGRES_TESTS_CONTAINER_NAME=dsassignment-postgres-tests-{run_suffix}",
    "POSTGRES_HOST_PORT=5433": f"POSTGRES_HOST_PORT={5600 + (int(run_suffix) % 100)}",
    "POSTGRES_UI_PORT=8085": f"POSTGRES_UI_PORT={8300 + (int(run_suffix) % 100)}",
    "SHARED_NETWORK_NAME=dsassignment-backend": f"SHARED_NETWORK_NAME={sys.argv[4]}",
}

for old, new in replacements.items():
    base_env = base_env.replace(old, new)

Path(sys.argv[2]).write_text(base_env)
PY

python - <<'PY' "$ROOT_DIR/rabbitmq/.env" "$RABBITMQ_TEST_ENV" "$RUN_SUFFIX" "$SHARED_NETWORK_NAME"
from pathlib import Path
import sys

base_env = Path(sys.argv[1]).read_text()
run_suffix = sys.argv[3]
replacements = {
    "RABBITMQ_CONTAINER_NAME=dsassignment-rabbitmq": f"RABBITMQ_CONTAINER_NAME=dsassignment-rabbitmq-{run_suffix}",
    "RABBITMQ_WORKER_CONTAINER_NAME=dsassignment-rabbitmq-worker": f"RABBITMQ_WORKER_CONTAINER_NAME=dsassignment-rabbitmq-worker-{run_suffix}",
    "RABBITMQ_TESTS_CONTAINER_NAME=dsassignment-rabbitmq-tests": f"RABBITMQ_TESTS_CONTAINER_NAME=dsassignment-rabbitmq-tests-{run_suffix}",
    "RABBITMQ_AMQP_PORT=5673": f"RABBITMQ_AMQP_PORT={5700 + (int(run_suffix) % 100)}",
    "RABBITMQ_MANAGEMENT_PORT=15673": f"RABBITMQ_MANAGEMENT_PORT={15700 + (int(run_suffix) % 100)}",
    "RABBITMQ_WORKER_MODE=loop": "RABBITMQ_WORKER_MODE=oneshot",
    "SHARED_NETWORK_NAME=dsassignment-backend": f"SHARED_NETWORK_NAME={sys.argv[4]}",
}

for old, new in replacements.items():
    base_env = base_env.replace(old, new)

Path(sys.argv[2]).write_text(base_env)
PY

python - <<'PY' "$ROOT_DIR/vector_db/.env" "$QDRANT_TEST_ENV" "$RUN_SUFFIX" "$SHARED_NETWORK_NAME"
from pathlib import Path
import sys

base_env = Path(sys.argv[1]).read_text()
run_suffix = sys.argv[3]
replacements = {
    "QDRANT_CONTAINER_NAME=dsassignment-qdrant": f"QDRANT_CONTAINER_NAME=dsassignment-qdrant-{run_suffix}",
    "QDRANT_HTTP_PORT=6333": f"QDRANT_HTTP_PORT={6400 + (int(run_suffix) % 100)}",
    "QDRANT_GRPC_PORT=6334": f"QDRANT_GRPC_PORT={6500 + (int(run_suffix) % 100)}",
    "SHARED_NETWORK_NAME=dsassignment-backend": f"SHARED_NETWORK_NAME={sys.argv[4]}",
}

for old, new in replacements.items():
    base_env = base_env.replace(old, new)

Path(sys.argv[2]).write_text(base_env)
PY

python - <<'PY' "$ROOT_DIR/worker/.env" "$WORKER_TEST_ENV" "$SHARED_NETWORK_NAME"
from pathlib import Path
import sys

base_env = Path(sys.argv[1]).read_text()
base_env = base_env.replace(
    "SHARED_NETWORK_NAME=dsassignment-backend",
    f"SHARED_NETWORK_NAME={sys.argv[3]}",
)
Path(sys.argv[2]).write_text(base_env)
PY

python - <<'PY' "$ROOT_DIR/api-service/.env" "$API_TEST_ENV" "$RUN_SUFFIX" "$POSTGRES_TEST_ENV" "$SHARED_NETWORK_NAME"
from pathlib import Path
import sys

base_env = Path(sys.argv[1]).read_text()
run_suffix = sys.argv[3]
replacements = {
    "API_CONTAINER_NAME=dsassignment-api-service": f"API_CONTAINER_NAME=dsassignment-api-service-{run_suffix}",
    "API_TESTS_CONTAINER_NAME=dsassignment-api-tests": f"API_TESTS_CONTAINER_NAME=dsassignment-api-tests-{run_suffix}",
    "API_HOST_PORT=8001": f"API_HOST_PORT={8100 + (int(run_suffix) % 100)}",
    "POSTGRES_ENV_FILE=../postgresql/.env": f"POSTGRES_ENV_FILE={sys.argv[4]}",
    "SHARED_NETWORK_NAME=dsassignment-backend": f"SHARED_NETWORK_NAME={sys.argv[5]}",
}

for old, new in replacements.items():
    base_env = base_env.replace(old, new)

Path(sys.argv[2]).write_text(base_env)
PY

docker compose -p "$POSTGRES_PROJECT_NAME" --env-file "$POSTGRES_TEST_ENV" -f "$ROOT_DIR/postgresql/docker-compose.yml" up --build -d
docker compose -p "$RABBITMQ_PROJECT_NAME" --env-file "$RABBITMQ_TEST_ENV" -f "$ROOT_DIR/rabbitmq/docker-compose.yml" up --build -d rabbitmq
docker compose -p "$QDRANT_PROJECT_NAME" --env-file "$QDRANT_TEST_ENV" -f "$ROOT_DIR/vector_db/docker-compose.yml" up --build -d
wait_for_service "$POSTGRES_PROJECT_NAME" "$POSTGRES_TEST_ENV" "$ROOT_DIR/postgresql/docker-compose.yml" postgres healthy
wait_for_service "$POSTGRES_PROJECT_NAME" "$POSTGRES_TEST_ENV" "$ROOT_DIR/postgresql/docker-compose.yml" postgres-import healthy
wait_for_service "$RABBITMQ_PROJECT_NAME" "$RABBITMQ_TEST_ENV" "$ROOT_DIR/rabbitmq/docker-compose.yml" rabbitmq healthy
wait_for_service "$QDRANT_PROJECT_NAME" "$QDRANT_TEST_ENV" "$ROOT_DIR/vector_db/docker-compose.yml" qdrant healthy
wait_for_service "$QDRANT_PROJECT_NAME" "$QDRANT_TEST_ENV" "$ROOT_DIR/vector_db/docker-compose.yml" qdrant-import healthy
docker compose -p "$WORKER_PROJECT_NAME" --env-file "$WORKER_TEST_ENV" -f "$ROOT_DIR/worker/docker-compose.yml" up --build -d worker
wait_for_service "$WORKER_PROJECT_NAME" "$WORKER_TEST_ENV" "$ROOT_DIR/worker/docker-compose.yml" worker running
docker compose -p "$API_PROJECT_NAME" --env-file "$API_TEST_ENV" -f "$ROOT_DIR/api-service/docker-compose.yml" up --build -d api
wait_for_service "$API_PROJECT_NAME" "$API_TEST_ENV" "$ROOT_DIR/api-service/docker-compose.yml" api healthy
docker compose -p "$API_PROJECT_NAME" --env-file "$API_TEST_ENV" -f "$ROOT_DIR/api-service/docker-compose.yml" run --rm api-tests pytest -q tests/test_api_unit.py tests/test_api_service.py tests/test_api_auth.py tests/test_api_scripts.py
