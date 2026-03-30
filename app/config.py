from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    langchain_api_key: str | None
    langchain_tracing_v2: str
    project_root: Path
    parquet_dir: Path
    vectorstore_dir: Path
    tmp_dir: Path
    embedding_model: str
    chat_model: str
    chat_temperature: float
    chat_agent_verbose: bool


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@lru_cache
def get_settings() -> Settings:
    root = _project_root()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        langchain_api_key=os.getenv("LANGCHAIN_API_KEY"),
        langchain_tracing_v2=os.getenv("LANGCHAIN_TRACING_V2", "false"),
        project_root=root,
        parquet_dir=root / "parquet",
        vectorstore_dir=root / "vectorestore",
        tmp_dir=root / "tmp",
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002"),
        chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo"),
        chat_temperature=float(os.getenv("OPENAI_CHAT_TEMPERATURE", "0.6")),
        chat_agent_verbose=os.getenv("CHAT_AGENT_VERBOSE", "false").lower() == "true",
    )


def apply_env_from_settings() -> None:
    s = get_settings()
    if s.openai_api_key:
        os.environ["OPENAI_API_KEY"] = s.openai_api_key
    if s.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = s.langchain_api_key
    os.environ["LANGCHAIN_TRACING_V2"] = s.langchain_tracing_v2


def ensure_data_directories() -> None:
    s = get_settings()
    s.parquet_dir.mkdir(parents=True, exist_ok=True)
    s.vectorstore_dir.mkdir(parents=True, exist_ok=True)
    s.tmp_dir.mkdir(parents=True, exist_ok=True)
