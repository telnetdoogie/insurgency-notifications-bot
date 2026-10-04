FROM python:3.12-slim

WORKDIR /app
COPY insurgency_bot /app/insurgency_bot

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    USERS_FILE=/config/users.json \
    DOCKER_SOCKET=/var/run/docker.sock \
    CONTAINER_NAME=insurgency-sandstorm

CMD ["python", "-m", "insurgency_bot"]
