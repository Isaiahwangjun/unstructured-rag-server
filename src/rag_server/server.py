"""FastMCP server exposing two tools over streamable-HTTP transport.

Tools:
  - search(query, k=5, source=None): semantic search over the
    Chroma collection populated by `rag-ingest`.
  - list_sources(): which document basenames are currently indexed.

Run:
  uv run rag-server
  # listens on http://127.0.0.1:8000/mcp by default

Connect from Claude Desktop / Claude Code as a remote MCP server
(see README for config snippets).
"""

from __future__ import annotations

import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

from . import config, embed, store


# DNS-rebinding protection. FastMCP defaults to enabling this with
# a localhost-only allow-list, which 421s every request once we
# deploy behind a real hostname (Render, Zeabur, any reverse proxy).
#
# DNS rebinding attacks matter when a server has cookie/auth state a
# malicious browser script could hijack — this server has none, so
# we disable the check by default. Operators who want it can list
# explicit hostnames via MCP_ALLOWED_HOSTS (the SDK does not honour
# a "*" wildcard; it only accepts exact matches or "<host>:*" port
# wildcards).
if config.MCP_ALLOWED_HOSTS:
    _security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=config.MCP_ALLOWED_HOSTS,
        allowed_origins=config.MCP_ALLOWED_ORIGINS or ["*"],
    )
else:
    _security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )

mcp = FastMCP("unstructured-rag-server", transport_security=_security)


class Hit(BaseModel):
    """One semantic-search result. `score` is cosine distance — lower
    is more relevant."""

    id: str = Field(description="Namespaced chunk id, e.g. 'thesis::c_0017'")
    source: str = Field(description="Document basename this chunk came from")
    body: str = Field(description="Original chunk body, no context-header prefix")
    headings: list[str] = Field(
        default_factory=list,
        description="Section heading chain leading to this chunk",
    )
    page_start: Optional[int] = Field(default=None, description="First page (or slide) the chunk draws from")
    page_end: Optional[int] = Field(default=None, description="Last page (or slide) the chunk draws from")
    score: float = Field(description="Cosine distance; lower means closer match")


@mcp.tool()
def search(query: str, k: int = 5, source: str | None = None) -> list[Hit]:
    """Semantic search over the indexed chunks.

    Args:
        query: Natural-language question or phrase.
        k: Number of hits to return (default 5).
        source: Optional document basename to restrict to (e.g. "thesis"
                — without the .pdf extension). Use list_sources() to
                see what's available.
    """
    embedding = embed.embed_texts([query])[0]
    raw_hits = store.query(embedding, k=k, source_filter=source)
    return [
        Hit(
            id=h["id"],
            source=h.get("source", ""),
            body=h.get("body", ""),
            headings=h.get("headings") or [],
            page_start=h.get("page_start"),
            page_end=h.get("page_end"),
            score=h.get("score", 0.0),
        )
        for h in raw_hits
    ]


@mcp.tool()
def list_sources() -> list[str]:
    """Return distinct document basenames currently indexed.

    Useful for the model to discover which corpora exist before
    issuing a `search` call with `source=...`.
    """
    return store.list_sources()


def main() -> int:
    """Entry point for `uv run rag-server`."""
    print(
        f"Starting MCP server on http://{config.MCP_HOST}:{config.MCP_PORT}{config.MCP_PATH}",
        file=sys.stderr,
    )
    print(f"  Chroma dir: {config.CHROMA_DIR}", file=sys.stderr)
    print(f"  Collection: {config.COLLECTION}", file=sys.stderr)
    print(f"  Sources indexed: {store.list_sources() or '(none — run rag-ingest first)'}", file=sys.stderr)
    mcp.settings.host = config.MCP_HOST
    mcp.settings.port = config.MCP_PORT
    mcp.settings.streamable_http_path = config.MCP_PATH
    mcp.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    sys.exit(main())
