#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

docker build -f "$ROOT_DIR/api-service/Dockerfile" -t dsassignment-api-service:latest "$ROOT_DIR"
