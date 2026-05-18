# Base on the official Python slim image from Docker Hub. We
# previously used ghcr.io/astral-sh/uv but GHCR's intermittent 502s
# break Render builds; Docker Hub is the more reliable source for an
# unattended PaaS pipeline. uv installs into the image in one
# `pip install` step.
FROM python:3.13-slim-bookworm

# uv is installed into /usr/local so it lands on PATH for every step.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first (cached layer) — copy only the manifest
# files so source-only changes don't bust this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Now copy the rest of the project. README is needed by the build
# (hatchling reads it for the wheel metadata).
COPY README.md ./
COPY src ./src
COPY scripts ./scripts
COPY fixtures ./fixtures
COPY .chroma ./.chroma

# Install the project itself into the venv so `rag-server` resolves.
RUN uv sync --frozen --no-dev

# Hosting platforms inject PORT; config.py bridges that to MCP_PORT
# and binds 0.0.0.0 automatically. Default to 8765 for plain
# `docker run` without -e PORT.
ENV PORT=8765
EXPOSE 8765

# stderr is unbuffered so PaaS log streaming shows the boot lines
# the moment they happen.
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "--no-sync", "rag-server"]
