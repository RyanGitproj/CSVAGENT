from __future__ import annotations

from langchain_core.pydantic_v1 import BaseModel, Field, validator

from app.security.repl_validation import validate_python_repl_query


class Message(BaseModel):
    role: str = Field(default="human")
    content: str | None = None


class Messages(BaseModel):
    messages: list[Message]


class PythonInputs(BaseModel):
    query: str = Field(description="Code snippet to run against `df`")

    @validator("query")
    def sandbox(cls, v: str) -> str:  # noqa: N805
        validate_python_repl_query(v)
        return v
