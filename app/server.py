from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import apply_env_from_settings, ensure_data_directories
from app.schemas import Messages
from app.services import CsvChatService, CsvIngestionService


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    apply_env_from_settings()
    ensure_data_directories()
    yield


app = FastAPI(
    title="AskCSV API",
    description="Upload CSV files, index them for retrieval, and query with a LangChain agent + sandboxed pandas.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.post("/parquet/upload_file")
async def upload_csv(file: UploadFile = File(...)) -> JSONResponse:
    return await CsvIngestionService().upload(file)


@app.post("/askcsv/double/{process_id}")
async def ask_csv(process_id: str, messages: Messages) -> JSONResponse:
    return await CsvChatService(process_id).answer(messages)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
