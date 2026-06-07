#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib import error, parse, request


ROOT_DIR = Path(__file__).resolve().parents[2]
API_ENV_FILE = ROOT_DIR / "api-service/.env"
POSTGRES_ENV_FILE = ROOT_DIR / "postgresql/.env"
RABBITMQ_ENV_FILE = ROOT_DIR / "rabbitmq/.env"
QDRANT_ENV_FILE = ROOT_DIR / "vector_db/.env"
WORKER_ENV_FILE = ROOT_DIR / "worker/.env"

# Configure everything here or override with environment variables.
ACTION = os.getenv("API_ACTION", "health")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")
USERNAME = os.getenv("API_USERNAME", "lelalomos")
PASSWORD = os.getenv("API_PASSWORD", "lelalomos")
TITLE = os.getenv("API_TITLE", "Wednesday")
TOKEN = os.getenv("API_TOKEN", "")
AUTO_LOGIN_FOR_RECOMMENDATIONS = os.getenv("API_AUTO_LOGIN_FOR_RECOMMENDATIONS", "1") == "1"


def service_is_running(env_file: Path, compose_file: Path, service_name: str) -> bool:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "ps",
            service_name,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and re.search(r"\bUp\b", result.stdout) is not None


def require_service(env_file: Path, compose_file: Path, service_name: str, start_command: str) -> None:
    if service_is_running(env_file, compose_file, service_name):
        return
    raise SystemExit(f"{service_name} service is not running. Start it first with {start_command}")


def require_core_services() -> None:
    require_service(
        API_ENV_FILE,
        ROOT_DIR / "api-service/docker-compose.yml",
        "api",
        "bash api-service/scripts/start_api_compose.sh",
    )
    require_service(
        POSTGRES_ENV_FILE,
        ROOT_DIR / "postgresql/docker-compose.yml",
        "postgres",
        "bash postgresql/scripts/start_postgres_compose.sh",
    )


def require_recommendation_services() -> None:
    require_core_services()
    require_service(
        RABBITMQ_ENV_FILE,
        ROOT_DIR / "rabbitmq/docker-compose.yml",
        "rabbitmq",
        "bash rabbitmq/scripts/start_rabbitmq_compose.sh",
    )
    require_service(
        QDRANT_ENV_FILE,
        ROOT_DIR / "vector_db/docker-compose.yml",
        "qdrant",
        "bash vector_db/scripts/start_qdrant_compose.sh",
    )
    require_service(
        WORKER_ENV_FILE,
        ROOT_DIR / "worker/docker-compose.yml",
        "worker",
        "bash worker/scripts/start_worker_compose.sh",
    )


def send_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> str:
    req = request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with request.urlopen(req) as response:
            return response.read().decode("utf-8")
    except error.HTTPError as exc:
        print(exc.read().decode("utf-8"), file=sys.stderr)
        raise SystemExit(exc.code) from exc


def call_health() -> str:
    require_core_services()
    return send_request(f"{API_BASE_URL}/health")


def call_register() -> str:
    require_core_services()
    payload = json.dumps({"username": USERNAME, "password": PASSWORD}).encode("utf-8")
    return send_request(
        f"{API_BASE_URL}/api/v1/auth/register",
        method="POST",
        headers={"Content-Type": "application/json"},
        body=payload,
    )


def call_login() -> str:
    require_core_services()
    payload = parse.urlencode({"username": USERNAME, "password": PASSWORD}).encode("utf-8")
    return send_request(
        f"{API_BASE_URL}/api/v1/auth/token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=payload,
    )


def call_recommendations() -> str:
    bearer_token = TOKEN
    require_recommendation_services()

    if not bearer_token and AUTO_LOGIN_FOR_RECOMMENDATIONS:
        bearer_token = json.loads(call_login())["access_token"]

    if not bearer_token:
        raise SystemExit("API_TOKEN is required when API_AUTO_LOGIN_FOR_RECOMMENDATIONS is not 1.")

    payload = json.dumps({"username": USERNAME, "title": TITLE}).encode("utf-8")
    return send_request(
        f"{API_BASE_URL}/api/v1/recommendations",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        },
        body=payload,
    )


def main() -> None:
    actions = {
        "health": call_health,
        "register": call_register,
        "login": call_login,
        "recommendations": call_recommendations,
    }
    if ACTION not in actions:
        raise SystemExit(
            f"Unknown API_ACTION: {ACTION}\nSupported values: health, register, login, recommendations"
        )
    print(actions[ACTION]())


if __name__ == "__main__":
    main()
