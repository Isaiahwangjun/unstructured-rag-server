# unstructured-rag-server — design notes

Reader: a repo reviewer who wants to know *why* this looks the way
it does. Not loaded at runtime — that's `README.md`.

## What this repo is, and isn't

This is the second half of the take-home. The first half (parse →
clean → chunk) lives in `unstructured-rag-kit`. The contract
between them is `chunks.json`: a flat JSON file with embedding-ready
text, original body, headings, and page ranges per chunk. This repo
ingests that file and exposes it over MCP.

It is **not** a general retrieval framework, multi-tenant search
service, or production deployment. It's exactly enough code to prove
the JD's "remote MCP server, queryable by an LLM agent" requirement.

## Transport: streamable HTTP

The JD says "remote MCP". MCP currently has three transports:

- **stdio** — local subprocess. Not remote.
- **HTTP + SSE** — the original remote transport. Deprecated in the
  current spec.
- **streamable HTTP** — single endpoint (`POST/GET /mcp`), bidirectional
  via SSE-over-POST framing. The spec's current recommendation, what
  Claude Desktop and Claude Code both speak.
- **websockets** — not part of the spec.

So: streamable HTTP. The FastMCP `transport="streamable-http"` flag
gets us there with one line. The matching client primitive is
`mcp.client.streamable_http.streamablehttp_client`.

## Why two tools, no resources

MCP exposes both **tools** (model invokes) and **resources** (user
selects). For RAG search the obvious shape is one tool: `search(query, k)`.

I considered also exposing each indexed document as an MCP resource
(`rag://thesis`, `rag://deck`) so the user could "attach" a corpus
to a conversation. Rejected because:

1. **Chunks aren't browsable** — they're searched. Resources work
   well when the user knows what they want to read; that's a poor
   model for retrieval.
2. **Claude Desktop's resource UX requires user-side selection** per
   call, while tools auto-route from the model. For an LLM agent
   answering arbitrary questions, tools are what we want.
3. **It would duplicate the index** with a worse access pattern.

I did add a second tool, `list_sources()`, so the model can discover
which corpora exist before issuing a `search` with `source=...`.
That's lightweight and removes the need for the user to type
basenames blind.

## Why id namespacing is load-bearing

Every `chunks.json` from the sibling repo restarts ids at `c_0001`.
Two ingest calls with the same id space would silently overwrite
each other in Chroma — the second `c_0001` clobbers the first.

`ingest.py` namespaces every id as `f"{source_basename}::{chunk_id}"`
(e.g. `thesis::c_0001`). The basename comes from the chunks.json's
own `source` field (`thesis.pdf` → `thesis`), with a fallback to
the JSON file's stem.

This is the only piece of glue logic that's not obvious from the
file shapes. Worth recording so future-me doesn't accidentally
remove it.

## Why no auth

JD says "remote MCP", not "public MCP". The reviewer is going to
run this on their own machine; binding `127.0.0.1` and pointing
Claude Desktop at `localhost:8765` is the simplest deployment that
satisfies "remote".

Auth on top of streamable HTTP is real work — OAuth flows, token
verification, the `mcp-auth` library — and adds nothing to the
demonstrable behaviour the JD asks for. If this ever ships beyond
a single user, the auth piece is bolted on at the transport layer
(reverse proxy, OAuth) rather than rewritten into the server.

## Why no FastAPI alongside MCP

Tempting addition: a `/search` REST endpoint for non-MCP clients.
Skipped because:

- **The JD asks for MCP**, not "MCP and REST". Adding REST without
  it being asked for muddies the deliverable.
- **Two surfaces means two test paths.** The MCP client demo
  exercises the protocol the way real LLM agents will; a REST
  endpoint is just `requests.post`. Doubling the surface area for
  no reviewer benefit.
- **MCP can already be hit from non-LLM code** — see
  `scripts/mcp_client_demo.py`. The "I just want curl access"
  argument doesn't survive 30 lines of Python.

## Embedder choice

OpenAI `text-embedding-3-small`:

- 1536-dim, ~62M parameters' worth of capacity.
- Strong on English; adequate on CJK (the test corpus is a Chinese
  thesis with English citations interleaved).
- Cheap: $0.02 per million input tokens. A 51-chunk thesis costs
  fractions of a cent to index.
- The JD mentions "OpenAI SDK" specifically; using it answers that
  prompt without ceremony.

The embedding seam is `embed.embed_texts(texts) -> list[list[float]]`.
Swapping in another embedder is a one-function rewrite if needed.

The OpenAI client takes an optional `OPENAI_BASE_URL` so the same
code works against any OpenAI-compatible gateway (Azure OpenAI,
LiteLLM, internal AI gateways). I tested against an internal gateway
during development; the README points reviewers at the public OpenAI
endpoint by default.

## Chroma vs alternatives

Chroma's persistent client (on-disk, no server) wins for this use
case because:

- **Zero ops.** A `PersistentClient(path=...)` is enough. No Docker,
  no separate process, no client/server pairing.
- **Sufficient at scale.** Tens of thousands of chunks fit
  comfortably; the entire test corpus is 51.
- **Cosine distance is the default**, which matches what the
  context-prefixed embeddings expect.

I considered FAISS (no metadata layer of its own — would need a
separate sidecar JSON), Qdrant (heavier, real server), and SQLite +
sqlite-vec (interesting but young). None of them earn their cost
at this size. If the consumer ever wants Qdrant later, the swap
point is `store.py` — the rest of the code doesn't care.

## Test strategy

`tests/test_ingest.py` round-trips a tiny fixture without hitting
the network. The OpenAI embedder is monkey-patched to a deterministic
function that emits 3-dim vectors based on substring matching, so
the assertions are about ordering ("the dog query returns the dog
chunk first"), not about embedding fidelity.

This is enough to catch the regressions that matter most:
- Chunks.json schema drifting (id, body, headings, page_start).
- ID namespacing breaking on re-ingest of two files with overlapping
  ids.
- Chroma metadata round-tripping the headings list correctly.

End-to-end against the real OpenAI API is what `mcp_client_demo.py`
proves; pytest doesn't try to duplicate it.

## What `mcp_client_demo.py` is actually testing

The JD asks for "verifiable outputs (e.g., an MCP client test
script)". The demo client:

1. Connects to the running server via `streamablehttp_client`.
2. Runs the canonical MCP handshake: `initialize`, `list_tools`,
   `call_tool`.
3. Validates that both required tools are exposed.
4. Validates that the collection isn't empty (`list_sources` returns
   at least one source).
5. Validates that `search` returns hits whose schema matches what
   `Hit` declares (id / source / body / headings / score).

Exit code 0 only if all five pass. Exit 1 with a `FAIL: <reason>`
on stderr otherwise. That makes it usable both as a manual demo and
as a CI-shaped check.

The bar I set: a reviewer can clone, ingest, run the server, run
the demo, and have a single binary signal — green or red — that
says whether the system is wired correctly. If they want to see
*what* came back, the JSON is on stdout.
