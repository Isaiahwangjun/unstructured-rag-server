"""Ingest CLI — read a chunks.json from unstructured-rag-kit, embed
each chunk's `text`, upsert into Chroma.

ID namespacing is the load-bearing detail: every chunks.json starts
fresh from `c_0001`, so two unnamespaced ingests would silently
overwrite each other. We prefix each id with the source basename
(`thesis::c_0001`) so the same Chroma collection can hold many
documents without collisions.

Usage:
    uv run rag-ingest path/to/chunks.json [more.json ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import embed, store


def _basename_from_source(source: str | None, fallback_path: Path) -> str:
    """The 'source' in chunks.json carries the original filename
    (e.g. 'thesis.pdf'). Strip the extension. If missing, use the
    json file's stem."""
    if source:
        return Path(source).stem
    return fallback_path.stem


def ingest_file(path: Path) -> int:
    """Embed and upsert every chunk in `path`. Returns chunk count."""
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks = data.get("chunks") or []
    if not chunks:
        print(f"  warning: {path} has zero chunks — nothing to ingest", file=sys.stderr)
        return 0

    basename = _basename_from_source(data.get("source"), path)

    ids = [f"{basename}::{c['id']}" for c in chunks]
    documents = [c.get("body") or c.get("text") or "" for c in chunks]
    texts_to_embed = [c.get("text") or c.get("body") or "" for c in chunks]
    metadatas = [
        {
            "source": basename,
            "source_filename": data.get("source") or "",
            "headings": c.get("headings") or [],
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
            "context_header": c.get("context_header") or "",
        }
        for c in chunks
    ]

    embeddings = embed.embed_texts(texts_to_embed)
    store.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    return len(chunks)


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("Usage: rag-ingest <chunks.json> [<chunks.json> ...]", file=sys.stderr)
        return 1

    total = 0
    for raw in args:
        path = Path(raw)
        if not path.exists():
            print(f"Error: {path} not found", file=sys.stderr)
            return 1
        n = ingest_file(path)
        basename = _basename_from_source(
            json.loads(path.read_text(encoding="utf-8")).get("source"), path
        )
        print(f"ingested {n} chunks from {basename}", file=sys.stderr)
        total += n

    print(f"Done. Total chunks ingested: {total}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
