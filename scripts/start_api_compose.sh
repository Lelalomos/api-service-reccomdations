#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

docker compose --env-file "$ROOT_DIR/api-service/.env" -f "$ROOT_DIR/api-service/docker-compose.yml" up --build -d
