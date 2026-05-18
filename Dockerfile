# Slim Python 3.13 image — Chroma + mcp + openai install cleanly here.
# We install uv from the official base image so dep resolution and the
# project layout match local dev exactly.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

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

# stderr is unbuffered so Zeabur log streaming shows the boot lines
# the moment they happen.
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "--no-sync", "rag-server"]
