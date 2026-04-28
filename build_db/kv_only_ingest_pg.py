import asyncio
import json
import os
from pathlib import Path

import numpy as np
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc


FIXED_JSON_PATH = Path(r"C:\Users\doant\Downloads\custom_kg_full.json")
FIXED_WORKSPACE = "legal_ai_platform"
FIXED_BATCH_SIZE = 500
SKIP_FULL_DOCS = False

FIXED_POSTGRES_HOST = "localhost"
FIXED_POSTGRES_PORT = "5432"
FIXED_POSTGRES_USER = "admin"
FIXED_POSTGRES_PASSWORD = "supersecretpassword"
FIXED_POSTGRES_DATABASE = "legal_ai_audit"
FIXED_POSTGRES_ENABLE_VECTOR = "false"


def _batched_items(data: dict, batch_size: int):
    items = list(data.items())
    for i in range(0, len(items), batch_size):
        yield dict(items[i : i + batch_size])


def _resolve_json_path() -> Path:
    candidates = []

    env_path = os.getenv("LIGHTRAG_KV_JSON_PATH")
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            FIXED_JSON_PATH,
            Path(__file__).resolve().parent / "custom_kg_full.json",
        ]
    )

    for path in candidates:
        if path.exists():
            return path

    searched = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(f"JSON not found. Searched:\n{searched}")


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_chunks_dict(custom_kg: dict, tokenizer) -> dict[str, dict]:
    chunks_dict: dict[str, dict] = {}
    for chunk in custom_kg.get("chunks", []):
        source_id = chunk.get("source_id")
        if not source_id:
            continue

        content = chunk.get("content", "") or ""
        file_path = chunk.get("file_path", "unknown_source")
        tokens = chunk.get("tokens")
        if not isinstance(tokens, int) or tokens < 0:
            tokens = len(tokenizer.encode(content)) if content else 0

        chunks_dict[source_id] = {
            "content": content,
            "source_id": source_id,
            "file_path": file_path,
            "full_doc_id": chunk.get("full_doc_id", file_path),
            "chunk_order_index": _safe_int(chunk.get("chunk_order_index", 0)),
            "tokens": tokens,
            "llm_cache_list": chunk.get("llm_cache_list", []),
        }
    return chunks_dict


def _build_full_docs_dict(chunks_dict: dict[str, dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for chunk in chunks_dict.values():
        doc_id = chunk.get("full_doc_id") or chunk.get("file_path") or "unknown_doc"
        grouped.setdefault(doc_id, []).append(chunk)

    full_docs: dict[str, dict] = {}
    for doc_id, doc_chunks in grouped.items():
        doc_chunks_sorted = sorted(doc_chunks, key=lambda c: c.get("chunk_order_index", 0))
        merged_content = "\n\n".join(c.get("content", "") for c in doc_chunks_sorted if c.get("content"))
        full_docs[doc_id] = {
            "content": merged_content,
            "file_path": doc_id,
        }
    return full_docs


async def _dummy_embed(texts: list[str], **kwargs) -> np.ndarray:
    return np.zeros((len(texts), 8), dtype=np.float32)


async def _dummy_llm(prompt: str, system_prompt: str | None = None, history_messages=None, **kwargs):
    return ""


async def main():
    json_path = _resolve_json_path()

    # PGKV reads PostgreSQL connection settings from these environment variables.
    os.environ.setdefault("POSTGRES_HOST", FIXED_POSTGRES_HOST)
    os.environ.setdefault("POSTGRES_PORT", FIXED_POSTGRES_PORT)
    os.environ.setdefault("POSTGRES_USER", FIXED_POSTGRES_USER)
    os.environ.setdefault("POSTGRES_PASSWORD", FIXED_POSTGRES_PASSWORD)
    os.environ.setdefault("POSTGRES_DATABASE", FIXED_POSTGRES_DATABASE)
    os.environ.setdefault("POSTGRES_ENABLE_VECTOR", FIXED_POSTGRES_ENABLE_VECTOR)

    # PGKV uses POSTGRES_WORKSPACE for namespace isolation.
    os.environ.setdefault("POSTGRES_WORKSPACE", FIXED_WORKSPACE)

    with json_path.open("r", encoding="utf-8-sig") as f:
        custom_kg = json.load(f)

    work_dir = Path(
        os.getenv(
            "LIGHTRAG_KV_WORKDIR",
            Path(__file__).resolve().parent / "target_kv_only",
        )
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    rag = LightRAG(
        working_dir=str(work_dir),
        llm_model_func=_dummy_llm,
        embedding_func=EmbeddingFunc(
            embedding_dim=8,
            max_token_size=64,
            func=_dummy_embed,
        ),
        kv_storage="PGKVStorage",
        doc_status_storage="PGDocStatusStorage",
        vector_storage="NanoVectorDBStorage",
        graph_storage="NetworkXStorage",
    )

    chunks_dict = _build_chunks_dict(custom_kg, rag.tokenizer)
    if not chunks_dict:
        raise ValueError("No chunks found in JSON input.")

    full_docs_dict = _build_full_docs_dict(chunks_dict)

    print(f"Using JSON source: {json_path}")
    print(f"Using working_dir: {work_dir}")
    print(f"Using PG workspace: {os.environ['POSTGRES_WORKSPACE']}")

    await rag.initialize_storages()

    print(f"[KV] Upserting text_chunks: {len(chunks_dict)}")
    for batch in _batched_items(chunks_dict, FIXED_BATCH_SIZE):
        await rag.text_chunks.upsert(batch)

    if not SKIP_FULL_DOCS:
        print(f"[KV] Upserting full_docs: {len(full_docs_dict)}")
        for batch in _batched_items(full_docs_dict, FIXED_BATCH_SIZE):
            await rag.full_docs.upsert(batch)

    print("Done. PGKV backfill completed.")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
