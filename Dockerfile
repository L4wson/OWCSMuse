# The HTTP API (python -m owcsmuse serve). Stateless: everything it answers comes from Postgres (DATABASE_URL).
#
#   docker build -t owcsmuse-api .
#   docker run -e DATABASE_URL=... -p 8000:8000 owcsmuse-api
#   docker run -e DATABASE_URL=... owcsmuse-api python -m owcsmuse migrate     # the release step, before serving
#
# The image carries migrations/ and scope/ so `migrate` (and its competition-name load) runs from it as the
# release command. It carries no tests, no frontend and no dev tools, and never a .env (see .dockerignore).

# The base image: the official one through Amazon ECR Public's mirror of Docker Hub, which Fly's builder pulls. CI passes
# its own GHCR copy (`--build-arg BASE_IMAGE=...`, .github/workflows/mirror-images.yml): anonymous pulls from a shared
# runner hit ECR Public's per-IP data limit.
ARG BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim

# ---------------------------------------------------------------- build: the package and the api extra, in a venv
FROM ${BASE_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
COPY pyproject.toml ./
COPY owcsmuse ./owcsmuse
# a regular (non-editable) install: the runtime image needs the venv only, not /src
RUN pip install ".[api]"

# ---------------------------------------------------------------- runtime: the venv, migrations and scope, non-root
FROM ${BASE_IMAGE}
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OWCS_LOG_FORMAT=json \
    PORT=8000
RUN groupadd --system --gid 10001 owcs && useradd --system --uid 10001 --gid owcs --no-create-home owcs
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
# migrate reads migrations/ and scope/competition_names.json relative to the working directory
COPY migrations ./migrations
COPY scope ./scope
USER owcs
EXPOSE 8000
# /healthz is liveness plus a database round trip: 503 when Postgres is unreachable
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/healthz', timeout=4)"
# sh -c so a host's $PORT is honoured; exec so uvicorn is PID 1 and receives SIGTERM
CMD ["sh", "-c", "exec python -m owcsmuse serve --host 0.0.0.0 --port \"${PORT:-8000}\""]
