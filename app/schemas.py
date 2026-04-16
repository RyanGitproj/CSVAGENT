from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="Display name for this dataset")


class DatasetInfo(BaseModel):
    id: str
    name: str
    created_at: str


class IngestTabularResult(BaseModel):
    dataset_id: str
    table_name: str
    rows: int
    columns: list[str]


class IngestPdfResult(BaseModel):
    dataset_id: str
    files: list[str]
    chunks: int


class AskMode(str):
    pass


AskModeLiteral = Literal["tabular", "docs", "auto", "agent"]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: AskModeLiteral = "auto"
    provider: Literal["ollama", "gemini", "groq"] | None = None
    conversation_id: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    # Noms de fichiers stockés (stored_name) à interroger. None = tous. Liste vide = erreur.
    active_files: list[str] | None = None


class DatasetFileDelete(BaseModel):
    stored_name: str = Field(min_length=1, max_length=500)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class FreeAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    provider: Literal["ollama", "gemini", "groq"] | None = None
    conversation_id: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1, max_length=200)


class SourceSQL(BaseModel):
    kind: Literal["sql"] = "sql"
    sql: str
    preview_rows: list[dict]


class SourceDoc(BaseModel):
    kind: Literal["doc"] = "doc"
    source: str
    page: int | None = None
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceSQL | SourceDoc] = Field(default_factory=list)
    tools_used: list[str] = Field(
        default_factory=list,
        description="Outils agent invoqués pour ce tour (vide hors mode agent / auto).",
    )


class DatasetIngestStatus(BaseModel):
    dataset_id: str
    has_tabular: bool
    has_pdf: bool


class DatasetFileItem(BaseModel):
    kind: Literal["tabular", "pdf"]
    original_name: str
    stored_name: str
    uploaded_at: str


class DatasetFilesResponse(BaseModel):
    dataset_id: str
    files: list[DatasetFileItem] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: str
    message_count: int


class ChatMessageOut(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str | None = None


class ConversationMessagesResponse(BaseModel):
    conversation_id: str
    messages: list[ChatMessageOut] = Field(default_factory=list)


class PdfPreviewPage(BaseModel):
    page: int
    text: str


class FilePreviewPdf(BaseModel):
    kind: Literal["pdf"] = "pdf"
    original_name: str
    stored_name: str
    page_count: int
    pages: list[PdfPreviewPage]
    truncated: bool


class FilePreviewTabular(BaseModel):
    kind: Literal["tabular"] = "tabular"
    original_name: str
    stored_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows_estimate: int
    truncated: bool
