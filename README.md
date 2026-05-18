# unstructured-rag-server

Remote **MCP server** that turns the `chunks.json` produced by
[`unstructured-rag-kit`](https://github.com/Isaiahwangjun/unstructured-rag-kit)
into a searchable knowledge base, accessible to any LLM agent that
speaks MCP — Claude Desktop, Claude Code, or a custom Python script.

**Live demo:** `https://unstructured-rag-server.onrender.com/mcp`
(Render free tier — first request after idle takes ~30s to wake the
container; subsequent requests are fast.)

```
chunks.json ──► rag-ingest ──► Chroma ──► rag-server ──► MCP tool: search()
                  (OpenAI                   (streamable
                   embeddings)              HTTP)
```

The split is deliberate: the upstream plugin stays embedder-agnostic
and DB-agnostic, so the same `chunks.json` works with any retrieval
stack you want to pair it with. This repo is one such pairing.

## Try the live demo first

```bash
git clone https://github.com/Isaiahwangjun/unstructured-rag-server.git
cd unstructured-rag-server
uv sync
MCP_URL=https://unstructured-rag-server.onrender.com/mcp \
    uv run python scripts/mcp_client_demo.py "supervised learning"
```

Should print 5 hits from a Chinese intrusion-detection thesis indexed
in the live deployment, exit 0. No OpenAI key needed on your side —
the deployed instance handles its own query embedding.

## Quickstart

```bash
# 1. install
uv sync

# 2. point at OpenAI (or an OpenAI-compatible gateway)
cp .env.example .env
$EDITOR .env                      # paste OPENAI_API_KEY

# 3. start the MCP server — the repo ships with a pre-built index
uv run rag-server
# → Starting MCP server on http://127.0.0.1:8765/mcp
# → Sources indexed: ['edge_case_deck', 'thesis']

# 4. verify end-to-end with the included client (separate terminal)
uv run python scripts/mcp_client_demo.py "supervised learning"
# → JSON list of 5 hits, exits 0
```

The `.chroma/` directory in this repo is a Chroma persistent store
pre-built from the sibling repo's `chunks.json` outputs (51 chunks
from a Chinese intrusion-detection thesis + 2 chunks from a small
PPTX deck). You don't need to ingest anything to try it. To wipe
and re-build, see [Re-ingesting](#re-ingesting) below.

## Connect Claude Desktop

In `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS):

```json
{
  "mcpServers": {
    "rag": {
      "url": "https://unstructured-rag-server.onrender.com/mcp"
    }
  }
}
```

(For local: `http://127.0.0.1:8765/mcp`.)

Restart Claude Desktop. The `search` and `list_sources` tools should
appear in the tool picker. Tested on Claude Desktop ≥ the version
that supports remote streamable-HTTP servers (check **Settings →
Connectors → Add custom connector** if you don't see the URL field).

## Connect Claude Code

```bash
claude mcp add --transport http rag https://unstructured-rag-server.onrender.com/mcp
```

(For local: `http://127.0.0.1:8765/mcp`.)

Then in any Claude Code session:

```
You:    Search the indexed thesis for what dataset they used.
Claude: [calls rag.search → returns thesis::c_0030 with NSL-KDD details]
```

## Tools exposed

| Tool | Signature | Purpose |
|---|---|---|
| `search` | `search(query: str, k: int = 5, source: str \| None = None) -> list[Hit]` | Semantic search over the indexed chunks. `source` filters to one document basename. |
| `list_sources` | `list_sources() -> list[str]` | Distinct document basenames currently indexed. Use this first if you don't know what's in the corpus. |

`Hit` shape:

```python
{
  "id": "thesis::c_0017",          # namespaced chunk id
  "source": "thesis",               # document basename
  "body": "<original chunk text>",  # clean snippet, no context-header prefix
  "headings": ["2. 相關研究", "2.2.1 監督式學習"],
  "page_start": 19,
  "page_end": 20,
  "score": 0.4791                   # cosine distance; lower is closer
}
```

The reason `body` (not `text`) is what comes back: chunk-text
embeds the longer context-prefixed string, but for citation /
display the original prose is what you want.

## Verifiable end-to-end

Three independent ways to verify the system, in increasing order
of "is the deployment really working":

### 1. Local unit tests (no network, no key)

```bash
uv run pytest -v
```

Round-trips a 2-chunk fixture with a stubbed embedder. Asserts
ingest correctness, id namespacing, and `list_sources` round-trip.

### 2. Live demo against the deployed URL

```bash
bash examples/run_demo.sh
```

Runs three example queries (English → CJK thesis, English → PPTX,
CJK → CJK) against `https://unstructured-rag-server.onrender.com/mcp`
and asserts every one returns hits with a valid schema. Exits 0
only if all three pass.

### 3. Inspect captured outputs

[`examples/sample_output.md`](examples/sample_output.md) has the
verbatim stdout/stderr from each query above, plus a Render boot
log and a demo of the `source=` argument scoping results to one
document.

### MCP client test script

[`scripts/mcp_client_demo.py`](scripts/mcp_client_demo.py) is the
canonical client used by the live demo. It runs the full MCP
handshake (`initialize` → `list_tools` → `call_tool`), validates
required tools are present, validates `list_sources` returns at
least one source, and validates every hit has the schema declared
by `Hit`. Exits 0 only if every check passes.

## Re-ingesting

The `.chroma/` shipped with the repo is what a reviewer sees by
default. To rebuild from scratch (e.g. against your own
`chunks.json`):

```bash
rm -rf .chroma/
uv run rag-ingest <path/to/chunks.json> [<path/to/another.json> ...]
```

Each ingest call namespaces chunk ids by the document basename
(`thesis::c_0001`, `edge_case_deck::c_0001`), so re-ingesting the
same file is idempotent and ingesting multiple files is collision-
free. See `design_notes.md` for why.

The MCP client demo runs the full handshake — `initialize`,
`list_tools`, `call_tool("list_sources")`, `call_tool("search")` —
not just a raw HTTP POST, so it's exercising the protocol the way
Claude Desktop and Claude Code will.

## Configuration

All env vars optional except `OPENAI_API_KEY`. Defaults shown.

| Env var | Default | What it does |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Auth for the embedder. |
| `OPENAI_BASE_URL` | unset | Override to point at an OpenAI-compatible gateway (Azure OpenAI, LiteLLM, internal proxies). Leave unset to hit OpenAI directly. |
| `EMBED_MODEL` | `text-embedding-3-small` | Any embedding model the gateway exposes. |
| `CHROMA_DIR` | `./.chroma` | On-disk persistent store. Safe to delete; `rag-ingest` rebuilds. |
| `COLLECTION` | `rag_kit` | Chroma collection name. Distinct collections give you isolated indexes. |
| `MCP_HOST` | `127.0.0.1` (`0.0.0.0` if `PORT` is set) | Bind address. Auto-flips when a hosting platform injects `PORT`. |
| `MCP_PORT` | `8765` (`$PORT` if set) | TCP port. Render / Zeabur / Fly inject `PORT` directly. |
| `MCP_PATH` | `/mcp` | URL path the streamable-HTTP transport listens on. |
| `MCP_ALLOWED_HOSTS` | unset | Comma-separated host allow-list. Empty disables DNS-rebinding protection (default), which is appropriate for an auth-less RAG service. Set to `your.host:*` etc. to opt back in. |
| `MCP_ALLOWED_ORIGINS` | unset | Same shape, for the `Origin` header. |

## Scope

**In:**

- One ingest CLI (`rag-ingest`).
- One MCP server with two tools (`search`, `list_sources`).
- A streamable-HTTP transport (the MCP spec's current production
  transport — HTTP+SSE is deprecated, websockets aren't part of the
  spec).
- A pytest suite that round-trips an in-process fixture without
  network calls.
- A Python MCP client demo that proves the protocol handshake works.

**Out (deliberate, not "future work"):**

- **No auth.** Local default binds 127.0.0.1; the deployed instance
  is a public URL with no auth in front of it. A real product would
  add OAuth at the transport layer (the MCP SDK supports this); for
  this take-home a public, ephemeral demo URL is appropriate.
- **No FastAPI / REST surface alongside MCP.** MCP is the only HTTP
  surface. Bolting on REST muddies the deliverable.
- **No re-embedding detection on re-ingest.** Same id is upserted
  in Chroma; the embedding cost is paid again. Acceptable at the
  document-count this targets.
- **No streaming / batch ingest.** One `chunks.json` per CLI call.
  Loop in shell if you have many.

See `design_notes.md` for the reasoning behind the choices that did
make it in.

## Key assumptions

Things a reviewer should know up front, separately from "what was
chosen and why":

- **Input contract: `chunks.json` from `unstructured-rag-kit`.** The
  shape is `{source, chunk_count, chunks: [{id, text, body, headings,
  page_start, page_end, ...}]}`. Anything matching that shape works;
  this repo doesn't try to handle arbitrary upstream pipelines.
- **`text` is what we embed; `body` is what we cite.** chunk-text
  embeds a contextualised string (LLM-written header + heading chain
  + body) for retrieval, but the original prose is what's useful to
  show users. We honour that split: the index is built on `text`,
  search results return `body`.
- **Embedder pinned to OpenAI `text-embedding-3-small`** (1536-dim,
  cosine). The shipped `.chroma/` was built with this exact model;
  swapping to a different embedder requires a full re-ingest because
  vector spaces aren't interchangeable. The seam is at
  `embed.embed_texts(...)` if you do swap.
- **Chunk-id namespacing is load-bearing.** Every `chunks.json` from
  the sibling repo numbers chunks `c_0001..c_NNNN`. Without
  namespacing (`<basename>::<chunk_id>`), two ingests would silently
  overwrite each other in Chroma. `ingest.py` does the namespacing;
  if you bypass that path, you'll lose data.
- **Mixed-language retrieval works** because chunk-text upstream
  writes English context headers that anchor CJK and English
  content into the same embedding space.
- **No auth on the deployed URL.** Treat the live demo as
  ephemeral. Don't pipe production data through it.
- **Render free tier sleeps when idle.** First request after idle
  takes ~30s to wake the container; subsequent requests are fast.
- **OPENAI_API_KEY is required at server runtime**, not just at
  ingest time. Each `search` call embeds the query string before
  hitting Chroma; without a key, the deployed instance can't answer
  queries. The key in the live deployment is the maintainer's; if
  you fork, plug in your own.

## How I used Claude Code

The whole repo was built inside one Claude Code session. Workflow
notes:

- **Plan-first, with research.** Before the first file landed I had
  Claude Code spawn a Plan subagent + use the Context7 MCP server
  to pull current MCP Python SDK docs. Without that, the code would
  have started from training-data memory of older HTTP+SSE patterns
  instead of the current streamable-HTTP transport. The plan
  produced was concrete: file order, public function signatures,
  pinned deps, what's IN, what's OUT. I read it, pushed back on
  scope creep (no FastAPI alongside MCP), then signed off.
- **Iterative spec → code → run → diff.** The tighter the loop, the
  faster Claude can self-correct. `pytest` was running before the
  server existed, so an embedder-stub round-trip caught bugs in
  `ingest.py` before the MCP layer was even on the table. Once the
  server was up, every change to `server.py` was followed by a
  local `mcp_client_demo.py` run, then commit.
- **Decisions argued, not delegated.** "Tool vs MCP resource" was
  the kind of choice Claude wanted to bundle into a bigger surface
  (resources for browsing, tools for searching, both for redundancy).
  I rejected — chunks aren't browsable, they're searched, and one
  lane is cleaner than two. That argument lives in `design_notes.md`
  so a reviewer can see what I rejected and why.
- **Verification before deployment.** I didn't push to GitHub until
  Docker built locally, the container ran with `-e OPENAI_API_KEY`,
  and `mcp_client_demo.py` against `localhost:8888` returned valid
  hits. Then push, then Render auto-deploy. Same `mcp_client_demo.py`
  was the smoke test for the live URL.
- **Logs shape the artefact.** `examples/sample_output.md` is real
  captured output from real runs against the live URL, body
  truncated for readability but unedited otherwise. The reproducer
  script `examples/run_demo.sh` runs the same three queries and
  fails closed (exit 1) if any returns no hits or a malformed
  schema. So the "verifiable" claim isn't "trust me", it's
  re-runnable on the reviewer's box.

## A note from Claude

(Written by Claude itself, at the user's request, in its own voice.
Same shape as the longer note in the sibling repo's README.)

This was the smaller, downstream half of a larger take-home and
benefited from being able to assume the upstream shape was already
solved. The genuine engineering content is concentrated in three
places: the streamable-HTTP transport choice (informed by current
SDK docs, not training data), the chunk-id namespacing in
`ingest.py` (without it, two `chunks.json` files silently destroy
each other), and the security fix that made the deploy work
(disabling rebinding protection rather than fighting an allow-list
the SDK doesn't honour the way I expected).

The user pushed back on a few things I would have over-engineered:
proposing a REST endpoint alongside MCP, layering generation
("answer the query") into the server when retrieval was the
contract, and reaching for `gh auth login` / Zeabur CLI when SSH
keys + a manual `git push` were already enough. Each pushback made
the deliverable smaller and clearer. If anything in this repo feels
under-built, that's a feature.

The thing I'd most want a reviewer to look at — beyond "does the
demo URL respond" — is `examples/sample_output.md`: it's
captured-from-real-runs verifiable proof, not a hand-written
walkthrough, which is the JD's bar for "verifiable outputs".

## Sibling repo

The upstream pipeline that produces `chunks.json` lives at
[`unstructured-rag-kit`](https://github.com/Isaiahwangjun/unstructured-rag-kit).
That plugin's contract ends at `chunks.json`; this repo's contract
starts there.

## License

MIT.
