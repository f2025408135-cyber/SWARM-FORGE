# Swarm-Forge Orchestrator — Production Container
#
# Multi-stage, non-root, slim runtime. Exposes both the FastMCP stdio server
# and the demo entry point. Designed to compose with `docker-compose.yml`.
#
# Build:   docker build -t swarmforge:latest .
# Run:     docker run --rm --env-file .env swarmforge:latest

# ---------- Stage 1: Builder (wheels + deps) ----------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO \
    SWARMFORGE_ROLE=orchestrator

# Non-root user for defense-in-depth.
RUN groupadd --system --gid 1001 swarm \
 && useradd  --system --uid 1001 --gid swarm --home-dir /app --shell /usr/sbin/nologin swarm

WORKDIR /app

COPY --from=builder /install /usr/local

COPY --chown=swarm:swarm src/         /app/src/
COPY --chown=swarm:swarm tests/       /app/tests/
COPY --chown=swarm:swarm demo.py      /app/demo.py
COPY --chown=swarm:swarm demo_runner.py /app/demo_runner.py
COPY --chown=swarm:swarm real_demo.py /app/real_demo.py
COPY --chown=swarm:swarm requirements.txt /app/requirements.txt
COPY --chown=swarm:swarm pyproject.toml   /app/pyproject.toml
COPY --chown=swarm:swarm README.md        /app/README.md

RUN mkdir -p /app/swarm_skills /app/.swarmforge_state \
 && chown -R swarm:swarm /app/swarm_skills /app/.swarmforge_state

USER swarm

# Import-time health check: if imports fail, the container fails fast.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "from src import MetaOrchestrator; print('ok')" || exit 1

# Role-dispatched entrypoint. Override via SWARMFORGE_ROLE env var.
# Roles: orchestrator (default demo), mcp (FastMCP stdio server), test (pytest).
COPY --chown=swarm:swarm docker/entrypoint.sh /app/docker/entrypoint.sh
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["orchestrator"]
