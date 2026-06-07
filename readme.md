# API Service Guide

This document explains how to configure, start, and test the FastAPI service in this project.

## Files

- `api-service/docker-compose.yml`: Docker services for the API and the API test runner
- `api-service/.env`: configurable values for API ports, container names, auth secret, token expiry, shared network name, and the path to the PostgreSQL env file
- `api-service/api_service/main.py`: FastAPI routes for health, login, and recommendations
- `api-service/api_service/rpc.py`: RabbitMQ RPC request and reply helper for recommendations
- `api-service/api_service/auth.py`: password hash verification, JWT creation, and bearer token validation
- `api-service/requirements-api.txt`: Python dependencies for the API service
- `api-service/Dockerfile`: shared image for the API service and the API tests
- `api-service/scripts/build_api_docker.sh`: builds the API Docker image
- `api-service/scripts/start_api_compose.sh`: starts the API Docker Compose stack
- `api-service/scripts/api_client.py`: one configurable Python script that can call all API routes
- `api-service/scripts/run_api_unit_tests.sh`: Docker-based unit and API tests
- `api-service/scripts/run_api_tests.sh`: Docker-based end-to-end API test script
- `tests/test_api_unit.py`: unit tests for the FastAPI app without external network calls
- `tests/test_api_service.py`: route and token tests
- `tests/test_api_auth.py`: password hash and token helper tests

## Configuration

The API Docker setup reads values from `api-service/.env`.

Current variables:

- `API_CONTAINER_NAME`: Docker container name for the FastAPI service
- `API_TESTS_CONTAINER_NAME`: Docker container name for the API test runner
- `API_HOST_PORT`: host port mapped to API port `8000`
- `API_HOST`: API hostname used by the test container
- `API_PORT`: API port used by the test container
- `API_SECRET_KEY`: signing key for JWT access tokens
- `API_ACCESS_TOKEN_EXPIRE_MINUTES`: access token lifetime in minutes
- `API_RPC_TIMEOUT_SECONDS`: maximum time the API waits for the worker RPC reply
- `POSTGRES_ENV_FILE`: path to the PostgreSQL env file from `postgresql/`
- `SHARED_NETWORK_NAME`: Docker network name shared with the PostgreSQL stack
- `RABBITMQ_HOST`: RabbitMQ hostname used by the API
- `RABBITMQ_PORT`: RabbitMQ port used by the API
- `RABBITMQ_USER`: RabbitMQ username
- `RABBITMQ_PASSWORD`: RabbitMQ password
- `RABBITMQ_QUEUE`: request queue name for recommendation RPC

## Logging

The API now writes application logs to stdout.

What is logged:

- registration success and failure
- login success and failure
- request completion with path, status code, and duration
- recommendation request start and completion
- RPC send, reply, timeout, and worker error events

Safety rules:

- passwords are not logged
- bearer tokens are not logged
- Docker log rotation is enabled with `max-size=10m` and `max-file=3`

## Authentication

This service uses:

- username and password registration at `POST /api/v1/auth/register`
- username and password login at `POST /api/v1/auth/token`
- bearer token auth for protected routes
- JWT access tokens with expiry
- password verification against PostgreSQL table `user_account`
- new API-created users are stored with PBKDF2-SHA256 password hashes
- imported workbook users may still use SHA-256 hex password hashes stored in `user_account.password`

Important note:

- the API does not start its own PostgreSQL service
- the API reads PostgreSQL connection values from the env file in `postgresql/`
- the API reads users from PostgreSQL startup-imported data
- `user_account.password` is expected to be a SHA-256 hex string

## Start The API

Start the PostgreSQL stack first:

```bash
bash postgresql/scripts/start_postgres_compose.sh
```

Then start the API stack:

```bash
docker compose --env-file api-service/.env -f api-service/docker-compose.yml up --build -d
```

Helper scripts:

```bash
bash api-service/scripts/build_api_docker.sh
bash api-service/scripts/start_api_compose.sh
python3 api-service/scripts/api_client.py
```

What happens on startup:

- the PostgreSQL stack from `postgresql/` owns `postgres` and `postgres-import`
- the API stack joins the shared backend network
- the API connects to the PostgreSQL service from the PostgreSQL stack
- the API service uses `restart: unless-stopped`, so Docker starts it again after host reboot unless you stopped it manually

Check running services:

```bash
docker compose --env-file api-service/.env -f api-service/docker-compose.yml ps
```

Health check:

```text
http://localhost:8001/health
```

Single API client script:

- file: `api-service/scripts/api_client.py`
- change config at the top of the file or override with env vars
- `API_ACTION=health`
- `API_ACTION=register`
- `API_ACTION=login`
- `API_ACTION=recommendations`

Examples:

```bash
python3 api-service/scripts/api_client.py
API_ACTION=register API_USERNAME=roza API_PASSWORD=secret python3 api-service/scripts/api_client.py
API_ACTION=login API_USERNAME=roza API_PASSWORD=secret python3 api-service/scripts/api_client.py
API_ACTION=recommendations API_USERNAME=roza API_PASSWORD=secret API_TITLE="Iron Man" python3 api-service/scripts/api_client.py
```

## Routes

- `GET /health`: returns service liveness
- `POST /api/v1/auth/register`: accepts JSON `username` and `password`, creates a new user, rejects duplicate usernames
- `POST /api/v1/auth/token`: accepts form `username` and `password`, returns bearer token and expiry
- `POST /api/v1/recommendations`: protected route, accepts `username` and `title`, rejects username mismatch, sends an RPC request to RabbitMQ, waits for the worker result, and returns the worker reply

## Run Tests

Run the API test suite with Docker:

```bash
bash api-service/scripts/run_api_unit_tests.sh
```

Run the API test suite after starting the service:

```bash
bash api-service/scripts/run_api_tests.sh
```

What the tests cover:

- unit checks for app routes with FastAPI `TestClient`
- health route
- registration success and duplicate username rejection
- login success and failure against PostgreSQL `user_account`
- bearer token protection
- token expiry handling
- recommendation route RPC response
- recommendation request username validation against the authenticated token user
- password hash verification helpers for PBKDF2 and SHA-256 hex

Important note:

- the API end-to-end test script starts isolated PostgreSQL, RabbitMQ, Qdrant, and worker stacks
- the API test scripts use isolated temporary Docker Compose projects and remove them after the test run, so they do not leave exited project test containers behind

## Stop Services

Stop the containers:

```bash
docker compose --env-file api-service/.env -f api-service/docker-compose.yml down
```
