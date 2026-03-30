from __future__ import annotations

import csv
import uuid
from io import StringIO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from app.config import ensure_data_directories, get_settings
from app.services.data_cache import clear_process_cache


class CsvIngestionService:
    async def upload(self, file: UploadFile) -> JSONResponse:
        ensure_data_directories()
        filename = file.filename or "upload.csv"
        if not filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

        s = get_settings()
        process_id = str(uuid.uuid4())
        tmp_path = s.tmp_dir / f"{process_id}.csv"

        content = await file.read()
        try:
            tmp_path.write_bytes(content)
            sep = _detect_separator(content)
            rows = CSVLoader(file_path=str(tmp_path), csv_args={"delimiter": sep}).load()
            emb = OpenAIEmbeddings(model=s.embedding_model)
            FAISS.from_documents(rows, emb).save_local(str(s.vectorstore_dir / process_id))

            df = pd.read_csv(StringIO(content.decode("latin-1")), sep=sep)
            pq.write_table(pa.Table.from_pandas(df), s.parquet_dir / f"{process_id}.parquet")
            clear_process_cache(process_id)

            return JSONResponse(
                status_code=200,
                content={
                    "message": "File uploaded successfully",
                    "file_id": process_id,
                    "file_name": filename,
                    "separator": sep,
                },
            )
        except (csv.Error, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
            return JSONResponse(status_code=400, content={"message": f"CSV parsing error: {exc}"})
        except Exception as exc:
            return JSONResponse(status_code=500, content={"message": str(exc)})
        finally:
            tmp_path.unlink(missing_ok=True)


def _detect_separator(sample: bytes) -> str:
    return csv.Sniffer().sniff(sample.decode("latin-1")).delimiter
