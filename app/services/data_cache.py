from __future__ import annotations

from cachetools import TTLCache
import pandas as pd
import pyarrow.parquet as pq
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

from app.config import get_settings

_cache: TTLCache[str, object] = TTLCache(maxsize=64, ttl=1200)


def get_dataframe(process_id: str) -> pd.DataFrame:
    key = f"df:{process_id}"
    hit = _cache.get(key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    path = get_settings().parquet_dir / f"{process_id}.parquet"
    df = pq.read_table(path).to_pandas()
    _cache[key] = df
    return df


def get_faiss(process_id: str) -> FAISS:
    key = f"faiss:{process_id}"
    hit = _cache.get(key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    s = get_settings()
    emb = OpenAIEmbeddings(model=s.embedding_model)
    db = FAISS.load_local(
        str(s.vectorstore_dir / process_id),
        emb,
        allow_dangerous_deserialization=True,
    )
    _cache[key] = db
    return db


def clear_process_cache(process_id: str) -> None:
    _cache.pop(f"df:{process_id}", None)
    _cache.pop(f"faiss:{process_id}", None)
