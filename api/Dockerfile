# syntax=docker/dockerfile:1.7
# --------------------------------------------------------------------------
# Stage 1 — builder: install into an isolated venv we can copy verbatim.
# --------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build

# Build context is the repository root (not api/) so the image can bundle
# both api/app and worker/, which live as siblings in the repo. CI must pass
# `context: .` and `file: api/Dockerfile` — see .github/workflows/deploy.yml.
# Copy metadata + source together; setuptools needs both to build the wheel.
COPY api/pyproject.toml api/README.md* ./
COPY api/app ./app

RUN pip install --upgrade pip \
    && pip install -e . \
    && find /opt/venv -type d \( -name __pycache__ -o -name '*.dist-info' -prune -false \) -prune -exec rm -rf {} + \
    || true

# Strip caches — a second pass because the -prune trick above bails on empties.
RUN find /opt/venv -type d -name __pycache__ -exec rm -rf {} + \
    && find /opt/venv -type f -name '*.pyc' -delete

# --------------------------------------------------------------------------
# Stage 2 — runtime: minimal image, non-root, health-checked.
# --------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# libpq for psycopg's C extension; curl for HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# App source. Keep the copy list narrow so image rebuilds are cache-friendly.
COPY api/app ./app
COPY api/alembic ./alembic
COPY api/alembic.ini ./alembic.ini
COPY api/entrypoint.sh /app/entrypoint.sh

# S14a.3b: scheduler workers (worker.alert_scheduler, worker.notification_sender,
# worker.renewals_scheduler, worker.audit_export, worker.hubspot_intake,
# worker.hubspot_writeback) share this image with the API. They're invoked as
# `python -m worker.<name>` from EventBridge-triggered ECS run-task
# overrides (see infra-tf/modules/schedulers). worker/ is a plain module tree
# (not a wheel package); `python -m` adds the WORKDIR (/app) to sys.path so
# `worker.<name>` resolves without needing an install.
COPY worker ./worker

RUN chmod +x /app/entrypoint.sh \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["/app/entrypoint.sh"]
