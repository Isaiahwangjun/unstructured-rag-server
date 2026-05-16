"""Chroma persistent-client wrapper.

We use Chroma's PersistentClient (on-disk, no separate server). The
collection holds one entry per chunk: id, embedding, document body,
metadata (source / headings / page range).

Cosine distance is the default in Chroma — we leave that as is. Lower
score = closer match.
"""

from __future__ import annotations

import json
from typing import Any

import chromadb
from chromadb.config import Settings

from . import config

_client: chromadb.api.ClientAPI | None = None


def _get_client() -> chromadb.api.ClientAPI:
    global _client
    if _client is None:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def _get_collection() -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=config.COLLECTION,
        # Embeddings are computed externally (we pass them in directly),
        # so disable Chroma's default embedding function.
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )


def upsert(
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    """Idempotent insert. Re-running with the same ids overwrites."""
    if not ids:
        return
    coll = _get_collection()
    coll.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=[_normalise_metadata(m) for m in metadatas],
    )


def _normalise_metadata(m: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata values must be primitives. Lists and dicts get
    JSON-encoded so we can round-trip headings + anything else later."""
    out: dict[str, Any] = {}
    for k, v in m.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = json.dumps(v, ensure_ascii=False)
    return out


def query(
    embedding: list[float],
    k: int = 5,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Top-k nearest neighbours. Optional `source_filter` restricts to
    one document basename (e.g. "thesis")."""
    coll = _get_collection()
    where = {"source": source_filter} if source_filter else None
    res = coll.query(
        query_embeddings=[embedding],
        n_results=k,
        where=where,
    )
    hits: list[dict[str, Any]] = []
    ids = res.get("ids", [[]])[0] or []
    docs = res.get("documents", [[]])[0] or []
    metas = res.get("metadatas", [[]])[0] or []
    distances = res.get("distances", [[]])[0] or []
    for i, _id in enumerate(ids):
        meta = dict(metas[i] or {})
        # Decode JSON-encoded list/dict fields back into Python objects.
        if isinstance(meta.get("headings"), str):
            try:
                meta["headings"] = json.loads(meta["headings"])
            except (ValueError, TypeError):
                meta["headings"] = []
        hits.append(
            {
                "id": _id,
                "body": docs[i] if i < len(docs) else "",
                "score": float(distances[i]) if i < len(distances) else 0.0,
                **meta,
            }
        )
    return hits


def list_sources() -> list[str]:
    """Distinct `source` metadata values currently in the collection."""
    coll = _get_collection()
    # Chroma doesn't have DISTINCT — `get` with limit None returns all
    # metadata, which we dedupe in Python. Fine at this scale.
    res = coll.get(include=["metadatas"])
    seen: set[str] = set()
    for m in res.get("metadatas") or []:
        s = (m or {}).get("source")
        if isinstance(s, str):
            seen.add(s)
    return sorted(seen)


def _reset_for_tests() -> None:
    """Used by tests to start from a clean slate."""
    global _client
    if _client is not None:
        try:
            _client.delete_collection(config.COLLECTION)
        except Exception:  # noqa: BLE001
            pass
    _client = None
