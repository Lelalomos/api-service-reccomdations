FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace:/workspace/api-service

COPY api-service/requirements-api.txt /tmp/requirements-api.txt

RUN pip install --no-cache-dir -r /tmp/requirements-api.txt

COPY . /workspace

CMD ["pytest", "-q", "tests/test_api_unit.py", "tests/test_api_service.py", "tests/test_api_auth.py"]
