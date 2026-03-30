from __future__ import annotations

import asyncio

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from langchain.agents import AgentExecutor
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.tools.retriever import create_retriever_tool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_experimental.tools import PythonAstREPLTool
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.schemas import Messages, PythonInputs
from app.services.data_cache import get_dataframe, get_faiss

_AGENT_SYSTEM = """You are working with a pandas DataFrame named `df` in Python.

Schema and sample (from `df.head().to_markdown()`):
<df>
{dhead}
</df>

Use this workflow:
1. If the question is ambiguous, ask which columns or filters matter.
2. Use `data_search` first to align with real column names and example values.
3. Use `python_repl` for read-only pandas analysis (filter, groupby, aggregates).
4. If results look wrong, revisit `data_search` before writing more code.
5. Keep answers concise and grounded in the data.

Both tools use the same in-memory `df`. Do not assume columns that you have not seen via tools or the preview above.
"""


def _history_messages(payload: Messages) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for m in payload.messages[:-1]:
        role = (m.role or "").lower()
        text = m.content or ""
        if role in ("human", "user"):
            out.append(HumanMessage(content=text))
        elif role in ("ai", "assistant"):
            out.append(AIMessage(content=text))
    return out


class CsvChatService:
    def __init__(self, process_id: str) -> None:
        self._process_id = process_id
        self._settings = get_settings()
        self._executor: AgentExecutor | None = None

    def _executor_or_build(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = self._build_executor()
        return self._executor

    def _build_executor(self) -> AgentExecutor:
        df = get_dataframe(self._process_id)
        system = _AGENT_SYSTEM.format(dhead=df.head().to_markdown())
        db = get_faiss(self._process_id)

        retriever_tool = create_retriever_tool(
            db.as_retriever(),
            "data_search",
            "Semantic search over ingested CSV rows",
        )
        repl = PythonAstREPLTool(
            locals={"df": df},
            name="python_repl",
            description="Run read-only pandas code against `df`",
            args_schema=PythonInputs,
        )
        tools = [retriever_tool, repl]

        llm = ChatOpenAI(
            model=self._settings.chat_model,
            temperature=self._settings.chat_temperature,
        ).bind_tools(tools)

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        agent = (
            {
                "input": lambda x: x["input"],
                "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
                "chat_history": lambda x: x["chat_history"],
            }
            | prompt
            | llm
            | OpenAIToolsAgentOutputParser()
        )

        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=self._settings.chat_agent_verbose,
        )

    async def answer(self, payload: Messages) -> JSONResponse:
        if not payload.messages:
            raise HTTPException(status_code=400, detail="`messages` must not be empty.")

        last = payload.messages[-1]
        if (last.role or "").lower() not in ("human", "user"):
            raise HTTPException(status_code=400, detail="The last message must be from the user.")

        user_text = last.content or ""
        history = _history_messages(payload)

        try:
            executor = self._executor_or_build()
            result = await asyncio.to_thread(
                executor.invoke,
                {"input": user_text, "chat_history": history},
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"No dataset found for process_id={self._process_id}. Upload a CSV first.",
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return JSONResponse(
            status_code=200,
            content={"messages": [{"role": "assistant", "content": result["output"]}]},
        )
