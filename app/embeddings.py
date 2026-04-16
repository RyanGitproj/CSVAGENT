from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import Settings

_emb_cache: dict[tuple, Embeddings] = {}


def clear_embeddings_cache() -> None:
    _emb_cache.clear()


def _emb_key(s: Settings) -> tuple:
    return (
        (s.embeddings_provider or "").lower(),
        s.embeddings_model,
        s.ollama_base_url,
        s.gemini_api_key,
    )


def _build_embeddings(settings: Settings) -> Embeddings:
    provider = (settings.embeddings_provider or "").lower()

    if provider in ("sentence_transformers", "sentence-transformers", "huggingface"):
        return HuggingFaceEmbeddings(model_name=settings.embeddings_model)

    if provider == "ollama":
        return OllamaEmbeddings(
            base_url=settings.ollama_base_url,
            model=settings.embeddings_model,
        )

    if provider == "gemini":
        return GoogleGenerativeAIEmbeddings(
            model=settings.embeddings_model or "text-embedding-004",
            google_api_key=settings.gemini_api_key,
        )

    raise ValueError(f"Unsupported embeddings provider: {settings.embeddings_provider!r}")


def get_embeddings(settings: Settings) -> Embeddings:
    k = _emb_key(settings)
    if k not in _emb_cache:
        _emb_cache[k] = _build_embeddings(settings)
    return _emb_cache[k]
