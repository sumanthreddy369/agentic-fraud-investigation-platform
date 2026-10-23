FROM ghcr.io/astral-sh/uv:0.12.21 AS uv
FROM python:3.11-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
ARG INSTALL_AGENTS=false
RUN case "$INSTALL_AGENTS" in \
      true) uv sync --frozen --no-dev --extra onnx-cpu --extra agents --no-cache ;; \
      false) uv sync --frozen --no-dev --extra onnx-cpu --no-cache ;; \
      *) echo "INSTALL_AGENTS must be true or false" >&2; exit 1 ;; \
    esac \
    && useradd --uid 10001 --create-home risk
COPY alembic.ini ./
COPY migrations ./migrations
USER 10001:10001
EXPOSE 8000
CMD ["/opt/venv/bin/uvicorn", "risk_platform.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-server-header", "--no-access-log"]
