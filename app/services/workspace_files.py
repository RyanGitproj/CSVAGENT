from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi import HTTPException

from app.services.datasets import dataset_dir, docs_dir, tabular_db_path
from app.services.pdf_rag import _manifest_path as pdf_manifest_path, rebuild_pdf_index_from_manifest


def tabular_manifest_path(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "imports" / "manifest.json"


def delete_dataset_file(dataset_id: str, stored_name: str) -> None:
    pdf_m = pdf_manifest_path(dataset_id)
    if pdf_m.exists():
        rows = json.loads(pdf_m.read_text(encoding="utf-8"))
        new_rows = [r for r in rows if str(r.get("stored_name", "")) != stored_name]
        if len(new_rows) < len(rows):
            pdf_m.write_text(json.dumps(new_rows, ensure_ascii=False, indent=2), encoding="utf-8")
            p = docs_dir(dataset_id) / stored_name
            if p.exists():
                p.unlink()
            rebuild_pdf_index_from_manifest(dataset_id)
            return

    tm = tabular_manifest_path(dataset_id)
    if tm.exists():
        rows = json.loads(tm.read_text(encoding="utf-8"))
        new_rows = [r for r in rows if str(r.get("stored_name", "")) != stored_name]
        if len(new_rows) < len(rows):
            tm.write_text(json.dumps(new_rows, ensure_ascii=False, indent=2), encoding="utf-8")
            p = dataset_dir(dataset_id) / "imports" / stored_name
            if p.exists():
                p.unlink()
            db_path = tabular_db_path(dataset_id)
            if db_path.exists():
                con = duckdb.connect(str(db_path))
                try:
                    cols = [r[1] for r in con.execute("PRAGMA table_info('items')").fetchall()]
                    if "__source_file" in cols:
                        con.execute("DELETE FROM items WHERE __source_file = ?", [stored_name])
                    else:
                        con.execute("DROP TABLE IF EXISTS items")
                finally:
                    con.close()
            return

    raise HTTPException(status_code=404, detail="Fichier inconnu dans cet espace.")
