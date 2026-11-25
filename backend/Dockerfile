# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim AS deps
WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python3.12
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

FROM deps AS model
RUN /opt/venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/models')"

FROM python:3.12-slim-bookworm AS runtime
RUN groupadd -g 10001 app && useradd -u 10001 -g app -m app \
    && mkdir -p /data/raw /srv && chown -R app:app /data /srv
WORKDIR /srv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/srv HF_HUB_OFFLINE=1
COPY --from=deps /opt/venv /opt/venv
COPY --from=model --chown=app:app /opt/models /opt/models
COPY backend/alembic.ini backend/start.sh ./
COPY backend/app ./app
COPY evals ./evals
USER app
EXPOSE 8000
CMD ["sh", "/srv/start.sh"]

FROM deps AS testdeps
RUN uv sync --frozen --no-cache

FROM runtime AS test
USER root
COPY --from=testdeps /opt/venv /opt/venv
COPY backend/pyproject.toml ./
COPY backend/tests ./tests
RUN chown -R app:app /srv
USER app
CMD ["pytest"]
