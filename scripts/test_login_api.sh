#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_ACTION=login \
API_USERNAME="${API_LOGIN_USERNAME:-lelalomos}" \
API_PASSWORD="${API_LOGIN_PASSWORD:-lelalomos}" \
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8001}" \
  python3 "$ROOT_DIR/api-service/scripts/api_client.py"
