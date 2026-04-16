from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import json
import logging
import mimetypes
from pathlib import Path
from typing import Literal, cast

import httpx
from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from app.config import apply_env_from_settings, ensure_data_directories, get_settings
from app.llm import DATASET_CONTINUATION_EXTRA, LLMError, invoke_free_chat
from app.schemas import (
    AskRequest,
    AskResponse,
    ChatMessageOut,
    ConversationMessagesResponse,
    ConversationSummary,
    DatasetCreate,
    DatasetFileDelete,
    DatasetFilesResponse,
    DatasetInfo,
    DatasetIngestStatus,
    DatasetFileItem,
    FilePreviewPdf,
    FilePreviewTabular,
    FreeAskRequest,
    IngestPdfResult,
    IngestTabularResult,
    SourceDoc,
    SourceSQL,
)
from fastapi import HTTPException

from app.services import DatasetRegistry, PdfRagService, SQLQAService, TabularIngestionService
from app.services.workspace_files import delete_dataset_file
from app.services.chat_memory import ChatMemoryStore
from app.services.datasets import dataset_dir, docs_dir, pdf_index_dir, tabular_db_path
from app.services.ask_quota import check_and_consume_ask_units
from app.services.conversation_context import augment_question_for_dataset
from app.services.conversation_summary import maybe_refresh_conversation_summary
from app.services.dataset_agent import AgentToolsUnsupported, run_dataset_agent
from app.services.doc_preview import build_preview_payload, resolve_workspace_file
from app.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


def _sources_from_agent_dicts(raw: list[dict]) -> list[SourceDoc | SourceSQL]:
    out: list[SourceDoc | SourceSQL] = []
    for r in raw:
        k = r.get("kind")
        if k == "doc":
            p = r.get("page")
            try:
                pi = int(p) if p is not None else None
            except (TypeError, ValueError):
                pi = None
            out.append(
                SourceDoc(
                    source=str(r.get("source") or "document"),
                    page=pi,
                    excerpt=str(r.get("excerpt") or ""),
                )
            )
        elif k == "sql":
            out.append(
                SourceSQL(
                    sql=str(r.get("sql") or ""),
                    preview_rows=list(r.get("preview_rows") or []),
                )
            )
    return out


def _ask_quota_units_for_mode(mode: str) -> int:
    return 2 if mode in ("auto", "agent") else 1


def _finalize_dataset_ask_turn(
    dataset_id: str,
    payload: AskRequest,
    mem: ChatMemoryStore,
    s,
    conversation_id: str,
    mode: str,
    out: AskResponse,
) -> AskResponse:
    mem.append_turn(conversation_id, payload.question, out.answer)
    mem.prune(conversation_id, keep_last=60)
    maybe_refresh_conversation_summary(
        s,
        mem,
        conversation_id,
        provider_override=payload.provider,
        model_override=payload.model,
    )
    if s.ask_request_log_enabled:
        logger.info(
            "ask",
            extra={
                "dataset_id": dataset_id,
                "conversation_id": conversation_id,
                "mode": mode,
                "tools_used": list(out.tools_used),
            },
        )
    return out


def _dataset_ask_sync(dataset_id: str, payload: AskRequest) -> AskResponse:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id. Create a dataset first.")
    if payload.active_files is not None and len(payload.active_files) == 0:
        raise HTTPException(
            status_code=400,
            detail="Sélectionnez au moins un fichier à utiliser pour l’interrogation.",
        )
    pdf_set, tab_set = _manifest_kind_sets(dataset_id)
    pdf_sel, tab_sel = _resolve_active_file_lists(payload.active_files, pdf_set, tab_set)

    mode = payload.mode
    conversation_id = payload.conversation_id or f"dataset:{dataset_id}"
    check_and_consume_ask_units(conversation_id, _ask_quota_units_for_mode(mode))
    mem = ChatMemoryStore()
    s = get_settings()
    ctx = augment_question_for_dataset(
        conversation_id,
        payload.question,
        s,
        provider_override=payload.provider,
        model_override=payload.model,
    )
    has_tab = tabular_db_path(dataset_id).exists()
    has_pdf = pdf_index_dir(dataset_id).exists()

    def _history_for_continuation() -> list[tuple[Literal["user", "assistant"], str]]:
        cap = max(s.chat_history_max_messages, s.conversation_context_max_messages)
        return cast(
            list[tuple[Literal["user", "assistant"], str]],
            mem.recent_history(conversation_id, max_messages=cap),
        )

    if mode == "docs":
        if not has_pdf:
            raise HTTPException(status_code=404, detail="No PDF index found. Ingest PDF first.")
        if pdf_sel is not None and len(pdf_sel) == 0:
            raise HTTPException(status_code=400, detail="Aucun fichier PDF sélectionné pour la requête.")
        if ctx.skip_dataset_lookup:
            answer = invoke_free_chat(
                s,
                provider_override=payload.provider,
                model_override=payload.model,
                history=_history_for_continuation(),
                question=payload.question,
                extra_system_instructions=DATASET_CONTINUATION_EXTRA,
            )
            out = AskResponse(answer=answer, sources=[], tools_used=[])
        else:
            answer, sources = PdfRagService().answer(
                dataset_id,
                ctx.pdf_search_question,
                provider=payload.provider,
                model=payload.model,
                active_pdf_files=pdf_sel,
                llm_question=ctx.llm_question,
            )
            out = AskResponse(answer=answer, sources=[SourceDoc(**x) for x in sources], tools_used=[])
        return _finalize_dataset_ask_turn(dataset_id, payload, mem, s, conversation_id, mode, out)

    if mode == "tabular":
        if not has_tab:
            raise HTTPException(status_code=404, detail="No tabular data found. Ingest CSV/Excel first.")
        if tab_sel is not None and len(tab_sel) == 0:
            raise HTTPException(status_code=400, detail="Aucun fichier tableur sélectionné pour la requête.")
        if ctx.skip_dataset_lookup:
            answer = invoke_free_chat(
                s,
                provider_override=payload.provider,
                model_override=payload.model,
                history=_history_for_continuation(),
                question=payload.question,
                extra_system_instructions=DATASET_CONTINUATION_EXTRA,
            )
            out = AskResponse(answer=answer, sources=[], tools_used=[])
        else:
            answer, sql, preview = SQLQAService().answer(
                dataset_id,
                ctx.llm_question,
                provider=payload.provider,
                model=payload.model,
                active_tabular_files=tab_sel,
            )
            out = AskResponse(answer=answer, sources=[SourceSQL(sql=sql, preview_rows=preview)], tools_used=[])
        return _finalize_dataset_ask_turn(dataset_id, payload, mem, s, conversation_id, mode, out)

    try_tab = has_tab and (tab_sel is None or len(tab_sel) > 0)
    try_pdf = has_pdf and (pdf_sel is None or len(pdf_sel) > 0)
    if not try_tab and not try_pdf:
        raise HTTPException(
            status_code=400,
            detail="Aucun fichier utilisable pour cette question (sélection ou données manquantes).",
        )

    if ctx.skip_dataset_lookup:
        answer = invoke_free_chat(
            s,
            provider_override=payload.provider,
            model_override=payload.model,
            history=_history_for_continuation(),
            question=payload.question,
            extra_system_instructions=DATASET_CONTINUATION_EXTRA,
        )
        out = AskResponse(answer=answer, sources=[], tools_used=[])
        return _finalize_dataset_ask_turn(dataset_id, payload, mem, s, conversation_id, mode, out)

    try:
        ans, raw_src, tools_used = run_dataset_agent(
            s,
            dataset_id=dataset_id,
            augmented_user_message=ctx.llm_question,
            pdf_search_seed=ctx.pdf_search_question,
            has_pdf=try_pdf,
            has_tab=try_tab,
            pdf_sel=pdf_sel,
            tab_sel=tab_sel,
            provider_override=payload.provider,
            model_override=payload.model,
            max_steps=s.dataset_agent_max_steps,
        )
        out = AskResponse(answer=ans, sources=_sources_from_agent_dicts(raw_src), tools_used=tools_used)
        return _finalize_dataset_ask_turn(dataset_id, payload, mem, s, conversation_id, mode, out)
    except AgentToolsUnsupported:
        logger.info("Dataset agent indisponible pour ce modèle — routage auto classique.")
    except LLMError:
        raise

    if try_tab:
        try:
            answer, sql, preview = SQLQAService().answer(
                dataset_id,
                ctx.llm_question,
                provider=payload.provider,
                model=payload.model,
                active_tabular_files=tab_sel,
            )
            out = AskResponse(answer=answer, sources=[SourceSQL(sql=sql, preview_rows=preview)], tools_used=[])
            return _finalize_dataset_ask_turn(dataset_id, payload, mem, s, conversation_id, mode, out)
        except LLMError:
            raise
        except HTTPException:
            raise
        except Exception:
            if not try_pdf:
                raise
    if try_pdf:
        answer, sources = PdfRagService().answer(
            dataset_id,
            ctx.pdf_search_question,
            provider=payload.provider,
            model=payload.model,
            active_pdf_files=pdf_sel,
            llm_question=ctx.llm_question,
        )
        out = AskResponse(answer=answer, sources=[SourceDoc(**x) for x in sources], tools_used=[])
        return _finalize_dataset_ask_turn(dataset_id, payload, mem, s, conversation_id, mode, out)

    raise HTTPException(
        status_code=400,
        detail="Aucun fichier utilisable pour cette question (sélection ou données manquantes).",
    )


_ollama_tags_cache: TTLCache[str, tuple[list[str], str | None]] = TTLCache(maxsize=8, ttl=2.5)
_httpx_sync: httpx.Client | None = None


def _http_sync() -> httpx.Client:
    global _httpx_sync
    if _httpx_sync is None:
        _httpx_sync = httpx.Client(
            timeout=httpx.Timeout(2.5, connect=2.0),
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        )
    return _httpx_sync


def _max_workspace_files() -> int:
    return get_settings().max_workspace_files


def _ollama_model_tags(base_url: str, timeout: float = 2.5) -> tuple[list[str], str | None]:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return [], "OLLAMA_BASE_URL est vide."
    if base in _ollama_tags_cache:
        return _ollama_tags_cache[base]
    try:
        r = _http_sync().get(f"{base}/api/tags", timeout=timeout)
        r.raise_for_status()
        data = r.json()
        names = [str(m.get("name", "")) for m in data.get("models", []) if m.get("name")]
        if not names:
            out: tuple[list[str], str | None] = (
                [],
                "Ollama répond mais aucun modèle n’est installé (`ollama pull <nom>`).",
            )
        else:
            out = (names, None)
    except httpx.TimeoutException:
        out = ([], "Ollama ne répond pas à temps. Lance `ollama serve` ou vérifie OLLAMA_BASE_URL.")
    except Exception as exc:
        out = ([], f"Ollama injoignable : {str(exc)[:160]}")
    _ollama_tags_cache[base] = out
    return out


def _manifest_kind_sets(dataset_id: str) -> tuple[set[str], set[str]]:
    pdf: set[str] = set()
    tab: set[str] = set()
    for manifest in (
        docs_dir(dataset_id) / "manifest.json",
        dataset_dir(dataset_id) / "imports" / "manifest.json",
    ):
        if not manifest.exists():
            continue
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        for r in rows:
            k = str(r.get("kind", ""))
            sn = str(r.get("stored_name", ""))
            if not sn:
                continue
            if k == "pdf":
                pdf.add(sn)
            elif k == "tabular":
                tab.add(sn)
    return pdf, tab


def _resolve_active_file_lists(
    active_files: list[str] | None,
    pdf_set: set[str],
    tab_set: set[str],
) -> tuple[list[str] | None, list[str] | None]:
    if active_files is None:
        return None, None
    pdf_sel = [a for a in active_files if a in pdf_set]
    tab_sel = [a for a in active_files if a in tab_set]
    return pdf_sel, tab_sel


def _workspace_file_count(dataset_id: str) -> int:
    pdf_set, tab_set = _manifest_kind_sets(dataset_id)
    return len(pdf_set) + len(tab_set)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    apply_env_from_settings()
    ensure_data_directories()
    yield
    global _httpx_sync
    if _httpx_sync is not None:
        _httpx_sync.close()
        _httpx_sync = None


app = FastAPI(
    title="AskNova Local API",
    description="Offline/local API: ingest CSV/Excel/PDF and answer questions via SQL-first + RAG (local models).",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=800)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:3000",
        "http://localhost:5173",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend standalone (externalisé pour déploiement séparé)
# Désactivé pour déploiement API-only sur Render
# Le frontend sera servi par Vercel
# Fallback gardé pour développement local si nécessaire
# frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
# if frontend_dir.exists():
#     app.mount("/web", StaticFiles(directory=str(frontend_dir), html=True), name="web")
# else:
#     # Fallback vers l'ancien frontend intégré
#     web_dir = Path(__file__).resolve().parent / "web"
#     app.mount("/web", StaticFiles(directory=str(web_dir), html=True), name="web")


@app.exception_handler(LLMError)
async def _handle_llm_error(_request, exc: LLMError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/limits")
async def limits() -> dict[str, int | bool | float | str]:
    s = get_settings()
    return {
        "max_upload_mb": s.max_upload_mb,
        "max_table_rows": s.max_table_rows,
        "max_workspace_files": s.max_workspace_files,
        "rate_limit_enabled": s.rate_limit_enabled,
        "rate_limit_per_minute": s.rate_limit_per_minute,
        "preview_max_pdf_pages": s.preview_max_pdf_pages,
        "preview_max_tabular_rows": s.preview_max_tabular_rows,
        "chat_history_max_messages": s.chat_history_max_messages,
        "conversation_context_max_messages": s.conversation_context_max_messages,
        "conversation_context_max_chars_per_message": s.conversation_context_max_chars_per_message,
        "dataset_tool_router_enabled": s.dataset_tool_router_enabled,
        "dataset_router_snippet_chars": s.dataset_router_snippet_chars,
        "dataset_router_max_output_tokens": s.dataset_router_max_output_tokens,
        "dataset_agent_max_steps": s.dataset_agent_max_steps,
        "dataset_agent_wall_seconds": s.dataset_agent_wall_seconds,
        "dataset_agent_repeat_tool_limit": s.dataset_agent_repeat_tool_limit,
        "dataset_router_model": (s.dataset_router_model or "").strip(),
        "dataset_ask_quota_per_conversation_per_minute": s.dataset_ask_quota_per_conversation_per_minute,
        "pdf_retrieval_cache_ttl_seconds": s.pdf_retrieval_cache_ttl_seconds,
        "pdf_ocr_enabled": s.pdf_ocr_enabled,
        "conversation_summary_enabled": s.conversation_summary_enabled,
        "conversation_summary_every_n_messages": s.conversation_summary_every_n_messages,
        "conversation_summary_max_chars": s.conversation_summary_max_chars,
        "ask_request_log_enabled": s.ask_request_log_enabled,
    }


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse("/web")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/llm/options")
async def llm_options() -> dict:
    try:
        s = get_settings()
        ollama_models, ollama_hint = _ollama_model_tags(s.ollama_base_url)
        groq_ok = bool((s.groq_api_key or "").strip())
        gem_ok = bool((s.gemini_api_key or "").strip())
        return {
            "default_provider": "groq",
            "groq_api_key_configured": groq_ok,
            "gemini_api_key_configured": gem_ok,
            "llm_request_timeout_seconds": s.llm_request_timeout_seconds,
            "llm_max_retries": s.llm_max_retries,
            "providers": [
                {
                    "id": "groq",
                    "label": "Groq (rapide, quota gratuit)",
                    "default_model": s.groq_chat_model,
                    "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
                    "available": groq_ok,
                    "hint": None
                    if groq_ok
                    else "Définis GROQ_API_KEY dans .env pour appeler Groq.",
                },
                {
                    "id": "gemini",
                    "label": "Google Gemini",
                    "default_model": s.gemini_chat_model,
                    "models": ["gemini-2.0-flash", "gemini-2.5-flash"],
                    "available": gem_ok,
                    "hint": None if gem_ok else "Définis GEMINI_API_KEY dans .env pour appeler Gemini.",
                },
                {
                    "id": "ollama",
                    "label": "Ollama (local)",
                    "default_model": s.ollama_chat_model,
                    "models": ollama_models,
                    "available": bool(ollama_models),
                    "hint": ollama_hint,
                },
            ],
        }
    except Exception:
        logger.exception("llm_options: échec de construction de la réponse")
        return {
            "default_provider": "groq",
            "groq_api_key_configured": False,
            "gemini_api_key_configured": False,
            "llm_request_timeout_seconds": 90,
            "llm_max_retries": 2,
            "options_error": "Impossible de charger les options LLM. Le serveur reste disponible ; réessaie.",
            "providers": [
                {
                    "id": "groq",
                    "label": "Groq",
                    "default_model": "llama-3.3-70b-versatile",
                    "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
                    "available": False,
                    "hint": None,
                },
                {
                    "id": "gemini",
                    "label": "Google Gemini",
                    "default_model": "gemini-2.0-flash",
                    "models": ["gemini-2.0-flash", "gemini-2.5-flash"],
                    "available": False,
                    "hint": None,
                },
                {
                    "id": "ollama",
                    "label": "Ollama (local)",
                    "default_model": "qwen2.5:7b",
                    "models": [],
                    "available": False,
                    "hint": None,
                },
            ],
        }


@app.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations() -> list[ConversationSummary]:
    rows = ChatMemoryStore().list_conversations(limit=80)
    return [ConversationSummary(**r) for r in rows]


@app.get("/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def conversation_messages(conversation_id: str) -> ConversationMessagesResponse:
    if len(conversation_id) > 120:
        raise HTTPException(status_code=400, detail="Identifiant de discussion trop long.")
    pairs = ChatMemoryStore().messages_for_conversation(conversation_id)
    messages = [ChatMessageOut(role=r, content=c, created_at=ts or None) for r, c, ts in pairs]
    return ConversationMessagesResponse(conversation_id=conversation_id, messages=messages)


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict[str, bool]:
    if len(conversation_id) > 120:
        raise HTTPException(status_code=400, detail="Identifiant de discussion trop long.")
    ChatMemoryStore().delete_conversation(conversation_id)
    return {"ok": True}


@app.post("/ask/free", response_model=AskResponse)
async def ask_free(payload: FreeAskRequest) -> AskResponse:
    s = get_settings()
    conversation_id = payload.conversation_id or "global"
    mem = ChatMemoryStore()
    hist = mem.recent_history(conversation_id, max_messages=s.chat_history_max_messages)
    hist.extend((t.role, t.content) for t in payload.history)
    answer = invoke_free_chat(
        s,
        provider_override=payload.provider,
        model_override=payload.model,
        history=hist,
        question=payload.question,
    )
    mem.append_turn(conversation_id, payload.question, answer)
    mem.prune(conversation_id, keep_last=60)
    return AskResponse(answer=answer, sources=[])


@app.post("/datasets", response_model=DatasetInfo)
async def create_dataset(payload: DatasetCreate) -> DatasetInfo:
    rec = DatasetRegistry().create(payload.name)
    return DatasetInfo(id=rec.id, name=rec.name, created_at=rec.created_at)


@app.get("/datasets", response_model=list[DatasetInfo])
async def list_datasets() -> list[DatasetInfo]:
    rows = DatasetRegistry().list()
    return [DatasetInfo(id=r.id, name=r.name, created_at=r.created_at) for r in rows]


@app.get("/datasets/{dataset_id}/ingest/status", response_model=DatasetIngestStatus)
async def dataset_ingest_status(dataset_id: str) -> DatasetIngestStatus:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id.")
    return DatasetIngestStatus(
        dataset_id=dataset_id,
        has_tabular=tabular_db_path(dataset_id).exists(),
        has_pdf=pdf_index_dir(dataset_id).exists(),
    )


@app.get("/datasets/{dataset_id}/files", response_model=DatasetFilesResponse)
async def dataset_files(dataset_id: str) -> DatasetFilesResponse:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id.")
    files: list[DatasetFileItem] = []
    for manifest in (
        (docs_dir(dataset_id) / "manifest.json"),
        (docs_dir(dataset_id).parent / "imports" / "manifest.json"),
    ):
        if not manifest.exists():
            continue
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        for r in rows:
            files.append(
                DatasetFileItem(
                    kind=str(r.get("kind", "pdf")),
                    original_name=str(r.get("original_name", "file")),
                    stored_name=str(r.get("stored_name", "")),
                    uploaded_at=str(r.get("uploaded_at", "")),
                )
            )
    files.sort(key=lambda x: x.uploaded_at, reverse=True)
    return DatasetFilesResponse(dataset_id=dataset_id, files=files)


@app.get("/datasets/{dataset_id}/files/{stored_name}/preview", response_model=FilePreviewPdf | FilePreviewTabular)
async def dataset_file_preview(dataset_id: str, stored_name: str) -> FilePreviewPdf | FilePreviewTabular:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id.")
    data = build_preview_payload(dataset_id, stored_name)
    if data["kind"] == "pdf":
        return FilePreviewPdf(**data)
    return FilePreviewTabular(**data)


@app.get("/datasets/{dataset_id}/files/{stored_name}/raw")
async def dataset_file_raw(dataset_id: str, stored_name: str) -> FileResponse:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id.")
    kind, original, path = resolve_workspace_file(dataset_id, stored_name)
    mt, _ = mimetypes.guess_type(original)
    if not mt:
        mt = "application/pdf" if kind == "pdf" else "application/octet-stream"
    return FileResponse(
        path,
        media_type=mt,
        filename=original,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=120"},
    )


@app.post("/datasets/{dataset_id}/ingest/tabular", response_model=IngestTabularResult)
async def ingest_tabular(dataset_id: str, file: UploadFile = File(...)) -> IngestTabularResult:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id. Create a dataset first.")
    if _workspace_file_count(dataset_id) >= _max_workspace_files():
        raise HTTPException(
            status_code=400,
            detail=f"Limite atteinte: maximum {_max_workspace_files()} fichiers dans le workspace.",
        )
    result = await TabularIngestionService().ingest(dataset_id, file)
    return IngestTabularResult(**result)


@app.post("/datasets/{dataset_id}/ingest/pdf", response_model=IngestPdfResult)
async def ingest_pdf(dataset_id: str, file: UploadFile = File(...)) -> IngestPdfResult:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id. Create a dataset first.")
    if _workspace_file_count(dataset_id) >= _max_workspace_files():
        raise HTTPException(
            status_code=400,
            detail=f"Limite atteinte: maximum {_max_workspace_files()} fichiers dans le workspace.",
        )
    result = await PdfRagService().ingest(dataset_id, file)
    return IngestPdfResult(**result)


@app.post("/datasets/{dataset_id}/ingest/auto")
async def ingest_auto(dataset_id: str, file: UploadFile = File(...)) -> dict:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id. Create a dataset first.")
    if _workspace_file_count(dataset_id) >= _max_workspace_files():
        raise HTTPException(
            status_code=400,
            detail=f"Limite atteinte: maximum {_max_workspace_files()} fichiers dans le workspace.",
        )
    filename = (file.filename or "").lower()
    if filename.endswith(".pdf"):
        result = await PdfRagService().ingest(dataset_id, file)
        return {"kind": "pdf", "result": result}
    if filename.endswith(".csv") or filename.endswith(".xls") or filename.endswith(".xlsx"):
        result = await TabularIngestionService().ingest(dataset_id, file)
        return {"kind": "tabular", "result": result}
    raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, CSV, XLS, XLSX.")


@app.delete("/datasets/{dataset_id}/files")
async def delete_workspace_file(dataset_id: str, payload: DatasetFileDelete) -> dict[str, bool]:
    if DatasetRegistry().get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id. Create a dataset first.")
    delete_dataset_file(dataset_id, payload.stored_name)
    return {"ok": True}


@app.post("/datasets/{dataset_id}/ask", response_model=AskResponse)
async def ask(dataset_id: str, payload: AskRequest) -> AskResponse:
    try:
        return await asyncio.to_thread(_dataset_ask_sync, dataset_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.post("/datasets/{dataset_id}/ask/stream")
async def ask_stream(dataset_id: str, payload: AskRequest) -> StreamingResponse:
    """NDJSON : une ligne ``meta``, puis ``done`` (payload JSON complet) ou ``error``."""

    async def gen():
        conv = payload.conversation_id or f"dataset:{dataset_id}"
        yield (
            json.dumps(
                {
                    "type": "meta",
                    "dataset_id": dataset_id,
                    "conversation_id": conv,
                    "mode": payload.mode,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        try:
            out = await asyncio.to_thread(_dataset_ask_sync, dataset_id, payload)
        except ValueError as exc:
            yield (
                json.dumps({"type": "error", "status": 429, "detail": str(exc)}, ensure_ascii=False)
                + "\n"
            )
            return
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            yield (
                json.dumps({"type": "error", "status": e.status_code, "detail": detail}, ensure_ascii=False)
                + "\n"
            )
            return
        except LLMError as e:
            yield (
                json.dumps({"type": "error", "status": e.status_code, "detail": e.detail}, ensure_ascii=False)
                + "\n"
            )
            return
        payload_dump = out.model_dump(mode="json")
        yield json.dumps({"type": "done", **payload_dump}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
