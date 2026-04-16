from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    datasets_dir: Path
    tmp_dir: Path

    # Local LLM (Ollama)
    llm_provider: str
    ollama_base_url: str
    ollama_chat_model: str
    groq_api_key: str
    groq_chat_model: str
    gemini_api_key: str
    gemini_chat_model: str
    chat_temperature: float
    # Nombre de messages (user+assistant) récents passés au chat libre (réduit le mélange de sujets).
    chat_history_max_messages: int
    # Historique injecté avant la question pour SQL / réponse PDF (cohérence des suites).
    conversation_context_max_messages: int
    conversation_context_max_chars_per_message: int
    # Gemini client: default 6 retries + no timeout can feel "stuck" for minutes
    llm_request_timeout_seconds: float
    llm_max_retries: int

    # Embeddings
    embeddings_provider: str
    embeddings_model: str

    # Guardrails
    max_upload_mb: int
    max_table_rows: int
    max_workspace_files: int
    rate_limit_enabled: bool
    rate_limit_per_minute: int

    # Aperçu fichiers (UI)
    preview_max_pdf_pages: int
    preview_max_chars_per_pdf_page: int
    preview_max_tabular_rows: int

    # Routeur CHAT vs LOOKUP avant SQL/RAG (1 petit appel LLM si activé)
    dataset_tool_router_enabled: bool
    dataset_router_snippet_chars: int
    dataset_router_max_output_tokens: int
    dataset_agent_max_steps: int
    dataset_agent_wall_seconds: float
    dataset_agent_repeat_tool_limit: int
    dataset_router_model: str
    dataset_ask_quota_per_conversation_per_minute: int
    pdf_retrieval_cache_ttl_seconds: int
    pdf_ocr_enabled: bool
    pdf_ocr_max_pages: int
    conversation_summary_enabled: bool
    conversation_summary_every_n_messages: int
    conversation_summary_max_chars: int
    ask_request_log_enabled: bool

    # Tabular SQL guidance (profiling + lexical hints)
    tabular_profile_enabled: bool
    tabular_profile_mode: str
    tabular_profile_ttl_seconds: int
    tabular_search_signals_enabled: bool
    tabular_search_signals_ttl_seconds: int


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@lru_cache
def get_settings() -> Settings:
    root = _project_root()
    data_dir = Path(os.getenv("DATA_DIR", str(root / "data")))
    return Settings(
        project_root=root,
        data_dir=data_dir,
        datasets_dir=(data_dir / "datasets"),
        tmp_dir=data_dir / "tmp",
        llm_provider=os.getenv("LLM_PROVIDER", "groq"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_chat_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        groq_chat_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_chat_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        chat_temperature=float(os.getenv("CHAT_TEMPERATURE", "0.15")),
        chat_history_max_messages=max(2, min(40, int(os.getenv("CHAT_HISTORY_MAX_MESSAGES", "12")))),
        conversation_context_max_messages=max(2, min(40, int(os.getenv("CONVERSATION_CONTEXT_MAX_MESSAGES", "16")))),
        conversation_context_max_chars_per_message=max(100, min(4000, int(os.getenv("CONVERSATION_CONTEXT_MAX_CHARS", "450")))),
        llm_request_timeout_seconds=float(os.getenv("LLM_REQUEST_TIMEOUT", "90")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        embeddings_provider=os.getenv("EMBEDDINGS_PROVIDER", "sentence_transformers"),
        embeddings_model=os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "25")),
        max_table_rows=int(os.getenv("MAX_TABLE_ROWS", "20000")),
        max_workspace_files=max(1, min(50, int(os.getenv("MAX_WORKSPACE_FILES", "3")))),
        rate_limit_enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("1", "true", "yes"),
        rate_limit_per_minute=max(10, min(10_000, int(os.getenv("RATE_LIMIT_PER_MINUTE", "180")))),
        preview_max_pdf_pages=max(1, min(30, int(os.getenv("PREVIEW_MAX_PDF_PAGES", "8")))),
        preview_max_chars_per_pdf_page=max(500, min(50_000, int(os.getenv("PREVIEW_MAX_CHARS_PDF_PAGE", "5000")))),
        preview_max_tabular_rows=max(10, min(500, int(os.getenv("PREVIEW_MAX_TABULAR_ROWS", "150")))),
        dataset_tool_router_enabled=(
            os.getenv("DATASET_TOOL_ROUTER_ENABLED", "true").lower() in ("1", "true", "yes")
        ),
        dataset_router_snippet_chars=max(
            1_200,
            min(8_000, int(os.getenv("DATASET_ROUTER_SNIPPET_CHARS", "2600"))),
        ),
        dataset_router_max_output_tokens=max(
            4,
            min(128, int(os.getenv("DATASET_ROUTER_MAX_OUTPUT_TOKENS", "16"))),
        ),
        dataset_agent_max_steps=max(2, min(24, int(os.getenv("DATASET_AGENT_MAX_STEPS", "6")))),
        dataset_agent_wall_seconds=float(
            os.getenv("DATASET_AGENT_WALL_SECONDS", "120"),
        ),
        dataset_agent_repeat_tool_limit=max(
            2,
            min(12, int(os.getenv("DATASET_AGENT_REPEAT_TOOL_LIMIT", "3"))),
        ),
        dataset_router_model=(os.getenv("DATASET_ROUTER_MODEL", "") or "").strip(),
        dataset_ask_quota_per_conversation_per_minute=max(
            5,
            min(500, int(os.getenv("DATASET_ASK_QUOTA_PER_CONV_PER_MIN", "40"))),
        ),
        pdf_retrieval_cache_ttl_seconds=max(
            0,
            min(600, int(os.getenv("PDF_RETRIEVAL_CACHE_TTL_SECONDS", "90"))),
        ),
        pdf_ocr_enabled=os.getenv("PDF_OCR_ENABLED", "false").lower() in ("1", "true", "yes"),
        pdf_ocr_max_pages=max(1, min(30, int(os.getenv("PDF_OCR_MAX_PAGES", "8")))),
        conversation_summary_enabled=os.getenv("CONVERSATION_SUMMARY_ENABLED", "true").lower()
        in ("1", "true", "yes"),
        conversation_summary_every_n_messages=max(
            8,
            min(80, int(os.getenv("CONVERSATION_SUMMARY_EVERY_N", "24"))),
        ),
        conversation_summary_max_chars=max(
            200,
            min(2000, int(os.getenv("CONVERSATION_SUMMARY_MAX_CHARS", "600"))),
        ),
        ask_request_log_enabled=os.getenv("ASK_REQUEST_LOG_ENABLED", "true").lower()
        in ("1", "true", "yes"),

        tabular_profile_enabled=os.getenv("TABULAR_PROFILE_ENABLED", "true").lower() in ("1", "true", "yes"),
        tabular_profile_mode=(os.getenv("TABULAR_PROFILE_MODE", "light") or "light").strip().lower(),
        tabular_profile_ttl_seconds=max(
            0,
            min(3600, int(os.getenv("TABULAR_PROFILE_TTL_SECONDS", "120"))),
        ),
        tabular_search_signals_enabled=os.getenv("TABULAR_SEARCH_SIGNALS_ENABLED", "true").lower()
        in ("1", "true", "yes"),
        tabular_search_signals_ttl_seconds=max(
            0,
            min(3600, int(os.getenv("TABULAR_SEARCH_SIGNALS_TTL_SECONDS", "120"))),
        ),
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
    try:
        from app.embeddings import clear_embeddings_cache

        clear_embeddings_cache()
    except Exception:
        pass


def apply_env_from_settings() -> None:
    # Kept for backward compatibility; most settings are read directly.
    # We intentionally do not set any remote-provider API keys here.
    return None


def ensure_data_directories() -> None:
    s = get_settings()
    s.tmp_dir.mkdir(parents=True, exist_ok=True)
    s.datasets_dir.mkdir(parents=True, exist_ok=True)
