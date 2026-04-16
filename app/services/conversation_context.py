from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import Settings
from app.services.chat_memory import ChatMemoryStore
from app.services.dataset_tool_router import needs_structured_file_lookup

# Accusés très courts : évite un appel routeur (pas une liste de « messages semblables »).
_ACK_PATTERNS = re.compile(
    r"^(merci|merci beaucoup|thanks|thank you|ok+|okay|d['’]accord|parfait|"
    r"super|génial|nickel|top|👍|🙏)\s*[!?.…]*$",
    re.IGNORECASE,
)

_CONTEXT_HEADER = (
    "[Fil récent — pronoms, suites, digressions possibles. "
    "La ligne « Question actuelle » prime sur le reste.]\n"
)


@dataclass(frozen=True)
class DatasetTurnContext:
    """Contexte pour une question sur un dataset (fichiers tabulaires et/ou texte indexé)."""

    llm_question: str
    pdf_search_question: str
    skip_dataset_lookup: bool


def _looks_like_short_ack(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    return bool(_ACK_PATTERNS.match(t))


def should_skip_dataset_lookup(
    history: list[tuple[str, str]],
    current_user_message: str,
    settings: Settings,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> bool:
    """
    True = pas de SQL ni RAG ce tour (réponse type chat, ``sources`` vides).

    Décision générique : petit appel LLM « CHAT vs LOOKUP » (pas de catalogue de phrases).
    Désactiver avec ``DATASET_TOOL_ROUTER_ENABLED=false`` : seuls les accusés très courts
    court-circuitent encore le routeur.
    """
    q = (current_user_message or "").strip()
    if not history or not q:
        return False

    if _looks_like_short_ack(q):
        return True

    if history[-1][0] != "assistant":
        return False

    if not settings.dataset_tool_router_enabled:
        return False

    return not needs_structured_file_lookup(
        settings,
        history=history,
        user_message=q,
        provider_override=provider_override,
        model_override=model_override,
    )


should_skip_pdf_retrieval = should_skip_dataset_lookup


def build_pdf_search_query(
    history: list[tuple[str, str]],
    current_question: str,
    *,
    max_chars: int = 900,
) -> str:
    cur = (current_question or "").strip()
    if not history:
        return cur

    parts: list[str] = [cur]
    users_seen = 0
    for role, content in reversed(history):
        if role != "user":
            continue
        c = (content or "").strip()
        if not c or c == cur:
            continue
        parts.append(c)
        users_seen += 1
        if users_seen >= 2:
            break

    merged = " · ".join(reversed(parts))
    if len(merged) <= max_chars:
        return merged
    return merged[: max_chars - 1] + "…"


def _thread_anchor_line(
    history: list[tuple[str, str]],
    *,
    max_chars: int = 120,
) -> str | None:
    for role, content in history:
        if role != "user":
            continue
        t = (content or "").strip().replace("\n", " ")
        if not t:
            continue
        if len(t) > max_chars:
            t = t[: max_chars - 1] + "…"
        return f"Entrée dans le fil : {t}\n"
    return None


def augment_question_for_dataset(
    conversation_id: str,
    current_question: str,
    settings: Settings,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> DatasetTurnContext:
    q = (current_question or "").strip()
    if not q:
        return DatasetTurnContext(llm_question=q, pdf_search_question=q, skip_dataset_lookup=False)

    max_msg = settings.conversation_context_max_messages
    max_chars = settings.conversation_context_max_chars_per_message

    mem = ChatMemoryStore()
    hist = mem.recent_history(conversation_id, max_messages=max_msg)
    pdf_q = build_pdf_search_query(hist, q)

    if not hist:
        return DatasetTurnContext(llm_question=q, pdf_search_question=pdf_q, skip_dataset_lookup=False)

    anchor = _thread_anchor_line(hist)
    lines: list[str] = []
    for role, content in hist:
        c = (content or "").strip()
        if len(c) > max_chars:
            c = c[: max_chars - 1] + "…"
        prefix = "U" if role == "user" else "A"
        lines.append(f"{prefix}: {c}")

    block = "\n".join(lines)
    sum_prefix = ""
    if settings.conversation_summary_enabled:
        sl = mem.get_conversation_summary(conversation_id)
        if sl:
            t = sl.strip()
            if len(t) > settings.conversation_summary_max_chars:
                t = t[: settings.conversation_summary_max_chars - 1] + "…"
            sum_prefix = f"[Résumé fil : {t}]\n"
    aug = f"{_CONTEXT_HEADER}{sum_prefix}{anchor or ''}{block}\n---\nQuestion actuelle :\n{q}"
    router_model = (settings.dataset_router_model or "").strip() or model_override
    skip = should_skip_dataset_lookup(
        hist,
        q,
        settings,
        provider_override=provider_override,
        model_override=router_model,
    )
    return DatasetTurnContext(llm_question=aug, pdf_search_question=pdf_q, skip_dataset_lookup=skip)
