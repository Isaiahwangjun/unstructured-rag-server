"""Runtime configuration loaded from environment / .env.

Kept dead simple: read once at import time, expose as constants.
The MCP server and the ingest CLI both pick these up.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # no-op if .env doesn't exist

CHROMA_DIR: Path = Path(os.getenv("CHROMA_DIR", ".chroma")).resolve()
COLLECTION: str = os.getenv("COLLECTION", "rag_kit")
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")

# Hosting platforms (Zeabur, Render, Fly, Heroku) inject PORT and
# expect the app to bind 0.0.0.0:$PORT. If we see PORT, we honour
# that contract; otherwise we fall back to a local-friendly default.
_PLATFORM_PORT = os.getenv("PORT")
MCP_HOST: str = os.getenv("MCP_HOST", "0.0.0.0" if _PLATFORM_PORT else "127.0.0.1")
MCP_PORT: int = int(os.getenv("MCP_PORT", _PLATFORM_PORT or "8765"))
MCP_PATH: str = os.getenv("MCP_PATH", "/mcp")


def _csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


# FastMCP enforces an allow-list on Host and Origin headers as
# DNS-rebinding protection. The library default is localhost-only,
# which 421s any request from a real hostname (e.g. behind Render
# / Zeabur / a reverse proxy). Default to "*" so the deployed image
# works out of the box; tighten this in production by listing the
# real hostname(s).
MCP_ALLOWED_HOSTS: list[str] = _csv(os.getenv("MCP_ALLOWED_HOSTS"), ["*"])
MCP_ALLOWED_ORIGINS: list[str] = _csv(os.getenv("MCP_ALLOWED_ORIGINS"), ["*"])

# Embeddings are sent to an OpenAI-compatible HTTP API. By default
# we hit OpenAI directly; users behind an OpenAI-compatible gateway
# (Azure, LiteLLM, internal proxies) can override the base URL and
# key without changing code.
OPENAI_BASE_URL: str | None = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")


def require_openai_key() -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and "
            "fill in your key, or export it directly. If you're using "
            "an OpenAI-compatible gateway, also set OPENAI_BASE_URL."
        )
