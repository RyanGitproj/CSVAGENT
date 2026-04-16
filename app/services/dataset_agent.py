from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm import LLMError, _message_content_text, get_chat_llm
from app.services.pdf_rag import PdfRagService, _manifest_path as pdf_manifest_path
from app.services.sql_qa import SQLQAService, tabular_schema_text
from app.services.workspace_files import tabular_manifest_path

logger = logging.getLogger(__name__)


class AgentToolsUnsupported(Exception):
    """Le modèle / fournisseur n’expose pas d’outils exploitables."""


_AGENT_SYSTEM = """You are a capable assistant. Your priority is the user's intent, but you must keep factual claims grounded in the user's uploaded files when they are available.

Their workspace may include indexed text documents (PDFs) and/or tabular data (spreadsheets). You have TOOLS to read those when needed. Tools are helpers to answer using their files, not optional for substantive questions:
- Do not call tools for greetings, thanks, short reactions, meta-requests about your previous message, rephrasing what you already said, or clearly general chit-chat.
- If the user asks for anything that should be based on their PDFs/tables/documents (e.g. “inside my PDF”, “selon le document”, “dedans”, “reference with my file”, “pose moi des questions dedans”, “dans le document fourni”, “my data”, “the table”, “the file”), call tools and use the results.
- If the requested facts are not supported by tool results (or no relevant excerpts are found), say it briefly (not found in the provided files) and then answer the user's question with a best-effort general answer.
- Clearly label the general part as « hors du document » (not verified by the uploaded text/table).
- You may call no tools, one tool, or several; combine results into one clear answer.
- After tool output, synthesize in the user's language; do not mention “tools”, “RAG”, or “SQL” unless they asked how it works.
- If a tool returns nothing useful, say so briefly and continue helpfully without inventing file content."""


class EmptyToolInput(BaseModel):
    unused: str = Field(default="", description="Leave empty; not used.")


class PdfSearchArgs(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=900,
        description="Focused search phrase (user’s language) to retrieve relevant passages from indexed PDFs.",
    )


class SqlRefineArgs(BaseModel):
    refinement: str = Field(
        default="",
        max_length=800,
        description="Optional short addition to narrow the table question. Leave empty to use the main user message as-is.",
    )


def _workspace_files_summary(dataset_id: str) -> str:
    lines: list[str] = []
    pm = pdf_manifest_path(dataset_id)
    if pm.exists():
        try:
            for r in json.loads(pm.read_text(encoding="utf-8")):
                kind = str(r.get("kind", "pdf"))
                orig = str(r.get("original_name", "?"))
                lines.append(f"- {kind}: {orig}")
        except Exception:
            lines.append("- (PDF manifest unreadable)")
    tm = tabular_manifest_path(dataset_id)
    if tm.exists():
        try:
            for r in json.loads(tm.read_text(encoding="utf-8")):
                orig = str(r.get("original_name", "?"))
                lines.append(f"- tabular: {orig}")
        except Exception:
            lines.append("- (tabular manifest unreadable)")
    return "\n".join(lines) if lines else "No files listed in this workspace."


def run_dataset_agent(
    settings: Settings,
    *,
    dataset_id: str,
    augmented_user_message: str,
    pdf_search_seed: str,
    has_pdf: bool,
    has_tab: bool,
    pdf_sel: list[str] | None,
    tab_sel: list[str] | None,
    provider_override: str | None,
    model_override: str | None,
    max_steps: int = 6,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """
    Retourne (réponse, sources accumulées, noms d’outils invoqués avec succès).
    """
    sources_acc: list[dict[str, Any]] = []
    tools_used: list[str] = []
    deadline = time.monotonic() + float(settings.dataset_agent_wall_seconds)
    repeat_limit = settings.dataset_agent_repeat_tool_limit
    recent_sigs: list[str] = []

    def tool_list_files(unused: str = "") -> str:
        return _workspace_files_summary(dataset_id)

    def tool_tabular_schema(unused: str = "") -> str:
        if not has_tab:
            return "No tabular data in this workspace."
        return tabular_schema_text(dataset_id)

    def tool_search_pdf(query: str) -> str:
        if not has_pdf:
            return "No indexed PDFs in this workspace."
        q = (query or "").strip() or pdf_search_seed
        try:
            ctx, srcs = PdfRagService().retrieve_excerpts(
                dataset_id,
                q,
                active_pdf_files=pdf_sel,
            )
            for s in srcs:
                sources_acc.append(dict(s))
            return ctx
        except HTTPException as e:
            return f"PDF tool error: {e.detail}"
        except Exception as exc:
            logger.warning("tool_search_pdf: %s", exc)
            return f"PDF tool failed: {exc!s}"

    def tool_query_spreadsheet(refinement: str = "") -> str:
        if not has_tab:
            return "No tabular data in this workspace."
        q = augmented_user_message.strip()
        if (refinement or "").strip():
            q = f"{q}\n(Précision pour la requête tableur : {refinement.strip()})"
        try:
            answer, sql, preview = SQLQAService().answer(
                dataset_id,
                q,
                provider=provider_override,
                model=model_override,
                active_tabular_files=tab_sel,
            )
            sources_acc.append({"kind": "sql", "sql": sql, "preview_rows": preview})
            prev_txt = json.dumps(preview[:8], ensure_ascii=False) if preview else "[]"
            return f"{answer}\n\n(aperçu lignes JSON court: {prev_txt})"
        except HTTPException as e:
            return f"Spreadsheet tool error: {e.detail}"
        except LLMError as e:
            return f"Spreadsheet tool error: {e.detail}"
        except Exception as exc:
            logger.warning("tool_query_spreadsheet: %s", exc)
            return f"Spreadsheet tool failed: {exc!s}"

    tools: list[StructuredTool] = [
        StructuredTool.from_function(
            name="list_workspace_files",
            description="List uploaded files in this workspace. Use when the user asks what is loaded or which documents exist.",
            func=tool_list_files,
            args_schema=EmptyToolInput,
        ),
    ]

    if has_tab:
        tools.append(
            StructuredTool.from_function(
                name="describe_tabular_schema",
                description="List column names for ingested spreadsheet data. Use when you need the table shape before querying.",
                func=tool_tabular_schema,
                args_schema=EmptyToolInput,
            )
        )
        tools.append(
            StructuredTool.from_function(
                name="query_spreadsheet_data",
                description="Answer a question over spreadsheet rows (counts, filters, aggregates). Use when numeric/tabular facts from the user’s tables are needed.",
                func=tool_query_spreadsheet,
                args_schema=SqlRefineArgs,
            )
        )

    if has_pdf:
        tools.append(
            StructuredTool.from_function(
                name="search_document_excerpts",
                description="Retrieve text excerpts from indexed documents. Use when factual content from the user’s PDFs is needed.",
                func=tool_search_pdf,
                args_schema=PdfSearchArgs,
            )
        )

    llm = get_chat_llm(settings, provider_override=provider_override, model_override=model_override)
    if not hasattr(llm, "bind_tools"):
        raise AgentToolsUnsupported("bind_tools not available for this model class")

    try:
        llm_t = llm.bind_tools(tools)
    except LLMError:
        raise
    except Exception as exc:
        raise AgentToolsUnsupported(str(exc)) from exc

    tool_map = {t.name: t for t in tools}
    messages: list[Any] = [
        SystemMessage(content=_AGENT_SYSTEM),
        HumanMessage(content=augmented_user_message),
    ]

    for step in range(max(1, max_steps)):
        if time.monotonic() > deadline:
            msg = "Délai agent dépassé — réponse interrompue pour limiter la durée."
            logger.warning("dataset_agent wall time exceeded (dataset_id=%s)", dataset_id)
            return msg, sources_acc, tools_used

        try:
            resp = llm_t.invoke(messages)
        except LLMError:
            raise
        except Exception as exc:
            raise AgentToolsUnsupported(str(exc)) from exc

        messages.append(resp)
        if not isinstance(resp, AIMessage):
            continue

        tcs = list(resp.tool_calls or [])
        if not tcs:
            text = _message_content_text(resp)
            return (text or "Aucune réponse.").strip(), sources_acc, tools_used

        for tc in tcs:
            tid = tc.get("id") or f"call_{step}"
            name = tc.get("name") or ""
            args = tc.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
            sig = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
            recent_sigs.append(sig)
            if len(recent_sigs) >= repeat_limit and len(set(recent_sigs[-repeat_limit:])) == 1:
                logger.warning("dataset_agent repeat tool loop detected: %s", name)
                return (
                    "Je m’arrête : le même outil a été sollicité trop de fois de suite sans progression.",
                    sources_acc,
                    tools_used,
                )

            tool = tool_map.get(name)
            if tool is None:
                messages.append(
                    ToolMessage(content=f"Unknown tool: {name}", tool_call_id=str(tid))
                )
                continue
            try:
                out = tool.invoke(args)
            except Exception as exc:
                out = f"Tool error: {exc!s}"
            else:
                if name:
                    tools_used.append(name)
            messages.append(ToolMessage(content=str(out)[:12_000], tool_call_id=str(tid)))

    last = messages[-1]
    if isinstance(last, AIMessage):
        return (_message_content_text(last) or "Limite d’étapes atteinte.").strip(), sources_acc, tools_used
    return "Limite d’étapes atteinte.", sources_acc, tools_used
