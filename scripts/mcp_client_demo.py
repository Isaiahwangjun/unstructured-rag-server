#!/usr/bin/env python3
"""End-to-end MCP client demo.

Connects to the running rag-server over streamable HTTP, runs the
canonical MCP handshake (initialize → list_tools → call_tool), and
prints results as JSON.

Exits:
  0 — every check passed: server reachable, both tools listed,
       at least one source indexed, search returned at least one hit
       with the expected schema.
  1 — any check failed (collection empty, missing tool, malformed
       hit, etc.).

This shape — pass/fail exit codes wrapped around a real MCP
handshake — is what the JD calls a "verifiable output". A reviewer
can run it manually and read the JSON, or wire it into CI.

Usage:
    uv run python scripts/mcp_client_demo.py "<query>" [<k>]

    The endpoint defaults to MCP_HOST:MCP_PORT from the running
    server's config (.env). Override with MCP_URL=... if needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


load_dotenv()


def _server_url() -> str:
    explicit = os.getenv("MCP_URL")
    if explicit:
        return explicit
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = os.getenv("MCP_PORT", "8765")
    path = os.getenv("MCP_PATH", "/mcp")
    return f"http://{host}:{port}{path}"


REQUIRED_TOOLS = {"search", "list_sources"}
REQUIRED_HIT_FIELDS = {"id", "source", "body", "headings", "score"}


async def run(query: str, k: int) -> int:
    url = _server_url()
    print(f"# connecting to {url}", file=sys.stderr)

    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            print(f"# tools: {sorted(tool_names)}", file=sys.stderr)
            missing = REQUIRED_TOOLS - tool_names
            if missing:
                print(f"FAIL: server missing tools {sorted(missing)}", file=sys.stderr)
                return 1

            sources_resp = await session.call_tool("list_sources", {})
            sources = _extract_payload(sources_resp) or []
            print(f"# indexed sources: {sources}", file=sys.stderr)
            if not sources:
                print(
                    "FAIL: collection is empty. Run `rag-ingest <chunks.json>` first.",
                    file=sys.stderr,
                )
                return 1

            print(f"# search query={query!r} k={k}", file=sys.stderr)
            search_resp = await session.call_tool("search", {"query": query, "k": k})
            payload = _extract_payload(search_resp)
            hits: list = payload if isinstance(payload, list) else (payload or {}).get("result", [])

    print(json.dumps(hits, ensure_ascii=False, indent=2))

    if not hits:
        print("FAIL: search returned zero hits", file=sys.stderr)
        return 1

    bad = [h for h in hits if not REQUIRED_HIT_FIELDS.issubset(h.keys())]
    if bad:
        print(
            f"FAIL: {len(bad)} hit(s) missing required fields {REQUIRED_HIT_FIELDS}",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(hits)} hits, schema valid", file=sys.stderr)
    return 0


def _extract_payload(resp):
    """FastMCP returns content blocks. For tools that return structured
    output (Pydantic / list / dict), the parsed value lands in
    `structuredContent`. We fall back to JSON-decoding the first text
    block if that isn't present."""
    sc = getattr(resp, "structuredContent", None)
    if sc is not None:
        # Tools whose return type is a bare list have their value
        # wrapped under "result" by the SDK.
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    # Fallback: parse first text content block.
    for block in getattr(resp, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: mcp_client_demo.py <query> [<k>]", file=sys.stderr)
        return 2
    query = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) >= 3 else 5
    return asyncio.run(run(query, k))


if __name__ == "__main__":
    sys.exit(main())
