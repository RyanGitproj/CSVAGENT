from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import ensure_data_directories, get_settings


@dataclass(frozen=True)
class DatasetRecord:
    id: str
    name: str
    created_at: str


class DatasetRegistry:
    def __init__(self) -> None:
        ensure_data_directories()
        s = get_settings()
        self._path: Path = s.data_dir / "datasets.json"

    def _read_all(self) -> list[DatasetRecord]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        out: list[DatasetRecord] = []
        for x in raw:
            out.append(DatasetRecord(id=x["id"], name=x["name"], created_at=x["created_at"]))
        return out

    def _write_all(self, rows: list[DatasetRecord]) -> None:
        self._path.write_text(
            json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create(self, name: str) -> DatasetRecord:
        rows = self._read_all()
        now = datetime.now(timezone.utc).isoformat()
        rec = DatasetRecord(id=str(uuid.uuid4()), name=name, created_at=now)
        rows.append(rec)
        self._write_all(rows)
        return rec

    def get(self, dataset_id: str) -> DatasetRecord | None:
        for r in self._read_all():
            if r.id == dataset_id:
                return r
        return None

    def list(self) -> list[DatasetRecord]:
        return self._read_all()


def dataset_dir(dataset_id: str) -> Path:
    s = get_settings()
    return s.datasets_dir / dataset_id


def tabular_db_path(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "tabular.duckdb"


def docs_dir(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "docs"


def pdf_index_dir(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "pdf_index"

