from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.llm import LLMError, _message_content_text, get_chat_llm
from app.services.chat_memory import ChatMemoryStore

logger = logging.getLogger(__name__)

_SUMMARY_SYS = """You compress a chat transcript into a short running summary for context in later turns.
Output only the summary text, no title. Same language as most of the transcript. Be factual and compact."""


def maybe_refresh_conversation_summary(
    settings: Settings,
    mem: ChatMemoryStore,
    conversation_id: str,
    *,
    provider_override: str | None,
    model_override: str | None,
) -> None:
    if not settings.conversation_summary_enabled:
        return
    n = mem.message_count(conversation_id)
    every = settings.conversation_summary_every_n_messages
    if n < every or n % every != 0:
        return
    rows = mem.messages_for_conversation(conversation_id)
    tail = rows[-36:] if len(rows) > 36 else rows
    lines: list[str] = []
    for role, content, _ts in tail:
        c = (content or "").strip().replace("\n", " ")
        if len(c) > 400:
            c = c[:399] + "…"
        lines.append(f"{role.upper()}: {c}")
    blob = "\n".join(lines)
    if not blob.strip():
        return
    human = (
        f"Max length: {settings.conversation_summary_max_chars} characters.\n\nTranscript:\n{blob}"
    )
    try:
        llm = get_chat_llm(settings, provider_override=provider_override, model_override=model_override)
        out = llm.invoke(
            [
                SystemMessage(content=_SUMMARY_SYS),
                HumanMessage(content=human),
            ]
        )
        text = _message_content_text(out).strip()
        if not text:
            return
        if len(text) > settings.conversation_summary_max_chars:
            text = text[: settings.conversation_summary_max_chars - 1] + "…"
        mem.set_conversation_summary(conversation_id, text)
    except LLMError as exc:
        logger.warning("conversation summary skipped: %s", exc.detail)
    except Exception as exc:
        logger.warning("conversation summary failed: %s", exc)
