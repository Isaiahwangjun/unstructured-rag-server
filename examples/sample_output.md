# Sample output — verifiable end-to-end

This file captures real `mcp_client_demo.py` runs against the live
deployment at `https://unstructured-rag-server.onrender.com/mcp`.

The hits below were retrieved via the canonical MCP handshake
(`initialize` → `list_tools` → `call_tool`), against a Chroma
collection holding 53 chunks (51 from a Chinese intrusion-detection
master's thesis + 2 from a small PPTX deck).

For readability `body` is truncated to ~250 chars in this file. The
demo client prints full bodies on stdout — re-run any of the
commands below to see them.

---

## Query 1 — English query → CJK thesis

```bash
$ MCP_URL=https://unstructured-rag-server.onrender.com/mcp \
    uv run python scripts/mcp_client_demo.py "supervised learning" 3
```

**stderr (handshake + summary):**

```
# connecting to https://unstructured-rag-server.onrender.com/mcp
# tools: ['list_sources', 'search']
# indexed sources: ['edge_case_deck', 'thesis']
# search query='supervised learning' k=3
OK: 3 hits, schema valid
```

**stdout (top hits):**

```json
[
  {
    "id": "thesis::c_0012",
    "source": "thesis",
    "body": "研究 [55] 使用隨機森林 、 k 近鄰演算法及邏輯迴歸 (logistic regression) 訓練出不同的分類器 ， 再用支援向量機綜合三種分類器的結果 。 結果表明 ， 在 UNSW-NB15 資料集上 ， 堆疊法準確率達 94 % 且誤報率僅",
    "headings": ["2.2.1 監督式學習"],
    "page_start": 20,
    "page_end": 20,
    "score": 0.4791063070297241
  },
  {
    "id": "thesis::c_0014",
    "source": "thesis",
    "body": "…監督式學習的缺點是需花費大量人力標記資料 ， 而非監督式學習雖然不用標記資料 …(truncated)",
    "headings": ["2.2.4 強化學習"],
    "page_start": 22,
    "page_end": 22,
    "score": 0.4897957444190979
  },
  {
    "id": "thesis::c_0010",
    "source": "thesis",
    "body": "…機器學習大致可分為四種 ： 監督式學習 (supervised learning) … …(truncated)",
    "headings": ["2.2.1 監督式學習"],
    "page_start": 19,
    "page_end": 20,
    "score": 0.5459222793579102
  }
]
```

**Exit code:** `0` (schema valid, hits returned).

What this demonstrates:
- Cross-lingual retrieval works: the English query lands on the
  matching Chinese section "2.2.1 監督式學習".
- Heading chain and page range come back correctly, so a downstream
  agent can cite "page 20, section 2.2.1".

---

## Query 2 — English query → PPTX hit

```bash
$ MCP_URL=https://unstructured-rag-server.onrender.com/mcp \
    uv run python scripts/mcp_client_demo.py "Q4 revenue by segment" 3
```

**stderr:**

```
# connecting to https://unstructured-rag-server.onrender.com/mcp
# tools: ['list_sources', 'search']
# indexed sources: ['edge_case_deck', 'thesis']
# search query='Q4 revenue by segment' k=3
OK: 3 hits, schema valid
```

**stdout (top hit only — full output has 3):**

```json
[
  {
    "id": "edge_case_deck::c_0001",
    "source": "edge_case_deck",
    "body": "2026 Product Roadmap — 產品藍圖. Title slide for the 'Rad-IC Take-Home Demo' presentation. The bilingual title pairs the English '2026 Product Roadmap' with the Chinese translation 產品藍圖 …(truncated)",
    "headings": [],
    "page_start": 1,
    "page_end": 5,
    "score": 0.5585677623748779
  }
]
```

What this demonstrates:
- Both the PDF (parse-pdf) and PPTX (parse-pptx) ingest paths land
  in the same MCP-served collection, queryable through the same
  `search` tool.
- The slide range that contains the Q4 revenue table (slides 1–5)
  is the top result.

---

## Query 3 — Chinese query → CJK thesis

```bash
$ MCP_URL=https://unstructured-rag-server.onrender.com/mcp \
    uv run python scripts/mcp_client_demo.py "資料擴增 SMOTE" 3
```

**stderr:**

```
# connecting to https://unstructured-rag-server.onrender.com/mcp
# tools: ['list_sources', 'search']
# indexed sources: ['edge_case_deck', 'thesis']
# search query='資料擴增 SMOTE' k=3
OK: 3 hits, schema valid
```

**stdout (top hits):**

```json
[
  {
    "id": "thesis::c_0031",
    "source": "thesis",
    "body": "…採用 one-hot 編碼 … …(truncated)",
    "headings": ["4.2 前處理"],
    "page_start": 44,
    "page_end": 45,
    "score": 0.5005
  },
  {
    "id": "thesis::c_0032",
    "source": "thesis",
    "body": "找出 k 個最近鄰居 … SMOTE 與 ADASYN 的差別為 ， SMOTE 針對樣本數量少的類別進行擴增 … …(truncated)",
    "headings": ["4.2 前處理"],
    "page_start": 45,
    "page_end": 45,
    "score": 0.5189
  },
  {
    "id": "thesis::c_0034",
    "source": "thesis",
    "body": "本論文將比較原始資料 、 SMOTE 及 ADASYN 擴增資料所訓練出的模型 … …(truncated)",
    "headings": ["4.3.2 資料擴增實驗"],
    "page_start": 48,
    "page_end": 49,
    "score": 0.5463
  }
]
```

What this demonstrates: a Chinese-only query lands on the data-
augmentation pre-processing chunks (`4.2 前處理`, including the
SMOTE/ADASYN formula description) and the experimental result
chunk (`4.3.2 資料擴增實驗`) that compares them — a common RAG
failure mode (mixed-language corpora) handled cleanly because
chunk-text upstream attaches a context header in English that
includes the document identity, anchoring both languages in the
same embedding space.

---

## Source filter (`source` argument on `search`)

The `search` tool accepts an optional `source=...` argument to
restrict results to one document basename. Demonstration script
calls `search` with each source in turn, both with the same query:

```python
async with streamablehttp_client(URL) as (r,w,_):
    async with ClientSession(r,w) as s:
        await s.initialize()
        for src in ["thesis", "edge_case_deck"]:
            resp = await s.call_tool(
                "search",
                {"query": "next steps", "k": 2, "source": src},
            )
            ...
```

**stderr (per-source summary):**

```
# connecting to https://unstructured-rag-server.onrender.com/mcp

# source='thesis'  k=2  -> 2 hits
  thesis::c_0029  pages=40-41  score=0.807
  thesis::c_0028  pages=39-39  score=0.820

# source='edge_case_deck'  k=2  -> 2 hits
  edge_case_deck::c_0002  pages=5-8  score=0.631
  edge_case_deck::c_0001  pages=1-5  score=0.685
```

What this demonstrates:
- The `source` filter actually scopes to the requested document; no
  cross-contamination from the other source in the collection.
- Same query yields different hits per source — useful when the
  caller wants to ground an answer in *this* document specifically.

---

## Server boot log (Render container, first start)

Captured from Render's deployment log on the first cold start:

```
==> Running 'uv run --no-sync rag-server'
Starting MCP server on http://0.0.0.0:10000/mcp
  Chroma dir: /app/.chroma
  Collection: rag_kit
  Sources indexed: ['edge_case_deck', 'thesis']
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO     StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
==> Your service is live 🎉
```

Two things to note:

1. `Sources indexed: ['edge_case_deck', 'thesis']` — confirms the
   pre-built `.chroma/` shipped with the repo was loaded at boot,
   so the deployment is queryable on the very first request without
   any ingest step.
2. `Uvicorn running on http://0.0.0.0:10000` — Render injects `PORT`
   env var; `config.py` honours that and binds 0.0.0.0 instead of
   the local-default 127.0.0.1. Same image, different env.

---

## Reproducing this file

The exact commands above against the live URL will produce
equivalent output (chunks and scores are deterministic given a
fixed embedder + index). To re-verify locally, replace `MCP_URL`
with `http://127.0.0.1:8765/mcp` and start the server with
`uv run rag-server`.
