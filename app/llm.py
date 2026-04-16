from __future__ import annotations

import logging
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from app.config import Settings

logger = logging.getLogger(__name__)

_FREE_CHAT_SYSTEM = """You are a careful, honest assistant aligned with the user's intent.

Rules:
1) The user's LAST message is the main request. Older turns are context only for clear follow-ups (pronouns, "same as before", "and for X?"). If the latest message starts a new topic or does not clearly continue the previous one, answer it on its own — do not force unrelated history into the reply.
2) They may digress, widen the discussion, or switch to an unrelated subject; follow that shift naturally instead of pulling them back to an earlier theme unless they return to it themselves.
3) Stay consistent: do not contradict what you said earlier in this conversation unless you correct a mistake explicitly.
4) If the request is ambiguous or missing what you need to answer (scope, format, reference), ask ONE short clarifying question before giving a detailed answer.
5) Reply in the same language as the user's latest message. Be concise unless they ask for detail.
6) Do not invent facts; say clearly when you do not know."""

# Suite de conversation sans nouvelle requête sur les fichiers (décision déjà prise en amont).
DATASET_CONTINUATION_EXTRA = """

Additional context for this turn:
- They may continue the prior exchange, but they may also change subject, digress, or broaden the talk; prioritize what their latest message is actually asking now.
- Their uploaded materials may be about any subject; follow the thread and their wording, without guessing a document type.
- When they clearly refer to content you already produced, draw from YOUR last message in this thread; if they have moved on, answer the new direction without forcing file context.
- Do not state new factual claims from files that you have not already given in this conversation. If they need information that only the files can provide, they should ask in a way that triggers a new lookup.
- Do not mention implementation details (queries, retrieval, “snippets”)."""

# Alias rétrocompat (même texte).
PDF_REVISION_CONTINUATION_EXTRA = DATASET_CONTINUATION_EXTRA


class LLMError(Exception):
    """Erreur liée au fournisseur LLM ou au modèle (mappée vers une réponse HTTP côté API)."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def normalize_model_id(model: str | None) -> str | None:
    if model is None:
        return None
    t = model.strip()
    return t if t else None


def coerce_to_llm_error(exc: BaseException) -> LLMError:
    if isinstance(exc, LLMError):
        return exc
    msg = str(exc).strip() or exc.__class__.__name__
    lower = msg.lower()

    if "429" in msg or "rate limit" in lower or "too many requests" in lower:
        return LLMError(
            "Limite de débit du fournisseur atteinte. Réessaie dans quelques instants ou change de modèle.",
            status_code=429,
        )
    if (
        "401" in msg
        or "403" in msg
        or "unauthorized" in lower
        or "permission denied" in lower
        or ("api key" in lower and ("invalid" in lower or "missing" in lower or "incorrect" in lower))
    ):
        return LLMError(
            "Clé API refusée ou manquante. Vérifie les variables d’environnement (GROQ_API_KEY, GEMINI_API_KEY) dans .env.",
            status_code=401,
        )
    if (
        "model" in lower
        and ("not found" in lower or "does not exist" in lower or "invalid model" in lower or "unsupported" in lower)
    ) or ("model" in lower and "404" in msg):
        return LLMError(
            f"Modèle indisponible ou inconnu pour ce fournisseur. Détail : {msg[:300]}",
            status_code=400,
        )
    if "timeout" in lower or "timed out" in lower or isinstance(exc, TimeoutError):
        return LLMError(
            "Délai dépassé : le modèle n’a pas répondu à temps. Réessaie, augmente LLM_REQUEST_TIMEOUT, ou choisis un modèle plus rapide.",
            status_code=504,
        )
    if (
        "connection" in lower
        or "refused" in lower
        or "econnrefused" in lower
        or "name or service not known" in lower
        or "failed to resolve" in lower
    ):
        return LLMError(
            "Impossible de joindre le service LLM (réseau, URL Ollama, ou service distant). Vérifie qu’Ollama tourne si tu l’utilises.",
            status_code=503,
        )
    if isinstance(exc, ValueError):
        return LLMError(msg[:500], status_code=400)

    return LLMError(f"Échec de l’appel au modèle : {msg[:400]}", status_code=502)


def get_chat_llm(
    settings: Settings,
    provider_override: str | None = None,
    model_override: str | None = None,
    *,
    temperature_override: float | None = None,
    max_output_tokens_override: int | None = None,
) -> BaseChatModel:
    provider = (provider_override or settings.llm_provider or "").strip().lower()
    model_override = normalize_model_id(model_override)
    temp = settings.chat_temperature if temperature_override is None else float(temperature_override)
    max_out = max_output_tokens_override

    if provider == "ollama":
        model = model_override or settings.ollama_chat_model
        if not (model or "").strip():
            raise LLMError("Aucun modèle Ollama défini. Choisis un modèle dans l’interface ou OLLAMA_MODEL dans .env.", status_code=400)
        ollama_kw: dict = {}
        if max_out is not None:
            ollama_kw["num_predict"] = int(max_out)
        oa = dict(
            base_url=settings.ollama_base_url,
            model=model,
            temperature=temp,
        )
        if ollama_kw:
            oa["model_kwargs"] = ollama_kw
        return ChatOllama(**oa)

    if provider == "groq":
        key = (settings.groq_api_key or "").strip()
        if not key:
            raise LLMError(
                "Clé API Groq absente : définissez GROQ_API_KEY dans .env (https://console.groq.com/keys).",
                status_code=400,
            )
        groq_kw: dict = {
            "model": model_override or settings.groq_chat_model,
            "temperature": temp,
            "groq_api_key": key,
            "timeout": settings.llm_request_timeout_seconds,
            "max_retries": settings.llm_max_retries,
        }
        if max_out is not None:
            groq_kw["max_tokens"] = int(max_out)
        return ChatGroq(**groq_kw)

    if provider == "gemini":
        key = (settings.gemini_api_key or "").strip()
        if not key:
            raise LLMError(
                "Clé API Gemini absente : définissez GEMINI_API_KEY dans .env (https://aistudio.google.com/apikey).",
                status_code=400,
            )
        gem_kw: dict = {
            "model": model_override or settings.gemini_chat_model,
            "temperature": temp,
            "google_api_key": key,
            "timeout": settings.llm_request_timeout_seconds,
            "max_retries": settings.llm_max_retries,
        }
        if max_out is not None:
            gem_kw["max_output_tokens"] = int(max_out)
        return ChatGoogleGenerativeAI(**gem_kw)

    raise LLMError(f"Fournisseur LLM non pris en charge : {provider!r}. Utilise groq, gemini ou ollama.", status_code=400)


def _build_messages(
    history: list[tuple[Literal["user", "assistant"], str]],
    question: str,
    *,
    extra_system_instructions: str | None = None,
) -> list[BaseMessage]:
    system = _FREE_CHAT_SYSTEM
    if extra_system_instructions:
        system = f"{system}{extra_system_instructions}"
    msgs: list[BaseMessage] = [SystemMessage(content=system)]
    for role, content in history:
        if role == "user":
            msgs.append(HumanMessage(content=content))
        else:
            msgs.append(AIMessage(content=content))
    msgs.append(HumanMessage(content=question))
    return msgs


def _message_content_text(result: object) -> str:
    content = getattr(result, "content", "")
    if isinstance(content, list):
        content = " ".join(str(x) for x in content)
    return str(content).strip()


def invoke_free_chat(
    settings: Settings,
    *,
    provider_override: str | None,
    model_override: str | None,
    history: list[tuple[Literal["user", "assistant"], str]],
    question: str,
    extra_system_instructions: str | None = None,
) -> str:
    try:
        llm = get_chat_llm(settings, provider_override=provider_override, model_override=model_override)
        messages = _build_messages(
            history,
            question,
            extra_system_instructions=extra_system_instructions,
        )
        result = llm.invoke(messages)
        text = _message_content_text(result)
        return text or "Aucune réponse renvoyée par le modèle."
    except LLMError:
        raise
    except Exception as exc:
        logger.warning("invoke_free_chat failure: %s", exc, exc_info=True)
        raise coerce_to_llm_error(exc) from exc
