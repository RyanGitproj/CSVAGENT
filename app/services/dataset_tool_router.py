from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.llm import LLMError, _message_content_text, get_chat_llm

logger = logging.getLogger(__name__)

# Principes généraux — pas d’exemples métier pour rester adaptatif à tout type de document.
_ROUTER_SYSTEM = """You route one user turn. The app may query user-uploaded files (search or structured queries). File topics are unknown and unconstrained — do not assume any domain.

Output exactly ONE word, uppercase, no punctuation: CHAT or LOOKUP.

CHAT — The reply can rely on the last assistant message and normal conversation alone (continuation, rewording, short reaction, general chat, digression, or a new topic that does not require reading their files). No new pass over file contents is required.

LOOKUP — Answering well requires reading, searching, or computing over uploaded material (including when they return to their data, ask a new factual question about it, or broaden into questions only the files can answer).

Rule: CHAT if their message is fully satisfiable without new file access; LOOKUP if it is not. Use any language the user uses.

Hard rule for file grounding: if the user explicitly asks to base the answer on uploaded files/documents (e.g. “dans le document”, “dedans”, “selon le PDF”, “référence au fichier”, “mes données”, “my data”, “the file/table”), then output LOOKUP.

Hard rule for off-document override: if the user explicitly asks to ignore the uploaded files (e.g. “sans référence au document”, “en général”, “hors du PDF”, “ignore the uploaded files”), then output CHAT.

If ambiguous: CHAT when they clearly build on the assistant’s latest reply with no file grounding; otherwise LOOKUP."""


def _assistant_snippet_for_router(text: str, *, max_chars: int, head_chars: int = 480) -> str:
    """Garde le début (listes en tête) et la fin (suites récentes) si le message est très long."""
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    h = min(head_chars, max_chars // 3)
    tail_budget = max_chars - h - 8
    if tail_budget < 400:
        return "…" + t[-(max_chars - 3) :]
    return t[:h] + "\n…\n" + t[-tail_budget:]


def parse_router_output_implies_file_lookup(raw: str) -> bool:
    """
    True = il faut exécuter SQL/RAG. Réponse attendue du modèle : CHAT ou LOOKUP.
    """
    line = (raw or "").strip().splitlines()[0] if (raw or "").strip() else ""
    u = line.upper()
    if u.startswith("CHAT"):
        return False
    if u.startswith("LOOKUP"):
        return True
    words = u.split()[:3]
    if "CHAT" in words:
        return False
    if "LOOKUP" in words:
        return True
    return True


def needs_structured_file_lookup(
    settings: Settings,
    *,
    history: list[tuple[str, str]],
    user_message: str,
    provider_override: str | None,
    model_override: str | None,
) -> bool:
    """
    True = exécuter SQL et/ou RAG pour ce tour.

    En cas d'erreur LLM, retourne True (comportement sûr).
    """
    if not history:
        return True
    last_role, last_assistant = history[-1]
    if last_role != "assistant":
        return True

    tail = _assistant_snippet_for_router(
        last_assistant,
        max_chars=settings.dataset_router_snippet_chars,
    )
    human = f"A (last):\n{tail}\n\nU:\n{(user_message or '').strip()}"

    try:
        llm = get_chat_llm(
            settings,
            provider_override=provider_override,
            model_override=model_override,
            temperature_override=0.0,
            max_output_tokens_override=settings.dataset_router_max_output_tokens,
        )
        out = llm.invoke(
            [
                SystemMessage(content=_ROUTER_SYSTEM),
                HumanMessage(content=human),
            ]
        )
        text = _message_content_text(out)
        need = parse_router_output_implies_file_lookup(text)
        if not need:
            logger.debug("dataset_tool_router: CHAT (skip structured lookup)")
        return need
    except LLMError as exc:
        logger.warning("dataset_tool_router LLM error, defaulting to LOOKUP: %s", exc.detail)
        return True
    except Exception as exc:
        logger.warning("dataset_tool_router failed, defaulting to LOOKUP: %s", exc)
        return True
