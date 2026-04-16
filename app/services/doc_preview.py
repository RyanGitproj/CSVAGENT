from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi import HTTPException
from pypdf import PdfReader

from app.config import get_settings
from app.services.datasets import dataset_dir, docs_dir, tabular_db_path
from app.services.workspace_files import tabular_manifest_path


def _safe_stored_name(stored_name: str) -> str:
    if not stored_name or len(stored_name) > 500:
        raise HTTPException(status_code=400, detail="Nom de fichier stocké invalide.")
    if ".." in stored_name or "/" in stored_name or "\\" in stored_name:
        raise HTTPException(status_code=400, detail="Nom de fichier stocké invalide.")
    base = Path(stored_name).name
    if base != stored_name.strip():
        raise HTTPException(status_code=400, detail="Nom de fichier stocké invalide.")
    return base


def _manifest_rows(dataset_id: str) -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    for manifest in (
        docs_dir(dataset_id) / "manifest.json",
        tabular_manifest_path(dataset_id),
    ):
        if not manifest.exists():
            continue
        for r in json.loads(manifest.read_text(encoding="utf-8")):
            sn = str(r.get("stored_name", ""))
            if not sn or sn in seen:
                continue
            seen.add(sn)
            rows.append(r)
    return rows


def resolve_workspace_file(dataset_id: str, stored_name: str) -> tuple[str, str, Path]:
    """
    Retourne (kind, original_name, chemin absolu du fichier sur disque).
    kind: 'pdf' | 'tabular'
    """
    sn = _safe_stored_name(stored_name)
    for r in _manifest_rows(dataset_id):
        if str(r.get("stored_name", "")) != sn:
            continue
        kind = str(r.get("kind", ""))
        original = str(r.get("original_name", sn))
        if kind == "pdf":
            p = docs_dir(dataset_id) / sn
            if p.is_file():
                return "pdf", original, p
        elif kind == "tabular":
            p = dataset_dir(dataset_id) / "imports" / sn
            if p.is_file():
                return "tabular", original, p
    raise HTTPException(status_code=404, detail="Fichier introuvable dans cet espace.")


def preview_pdf_text(path: Path, *, max_pages: int, max_chars_per_page: int) -> tuple[int, list[dict], bool]:
    reader = PdfReader(str(path))
    n_pages = len(reader.pages)
    pages_out: list[dict] = []
    truncated = False
    for i in range(min(max_pages, n_pages)):
        page_no = i + 1
        text = (reader.pages[i].extract_text() or "").strip()
        if len(text) > max_chars_per_page:
            text = text[:max_chars_per_page] + "…"
            truncated = True
        pages_out.append({"page": page_no, "text": text})
    if n_pages > max_pages:
        truncated = True
    return n_pages, pages_out, truncated


def preview_tabular_rows(dataset_id: str, stored_name: str, *, limit: int) -> dict:
    db_path = tabular_db_path(dataset_id)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Aucune donnée tableur pour cet espace.")
    lim = max(1, min(limit, 500))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("PRAGMA threads=4")
        info = con.execute("PRAGMA table_info('items')").fetchall()
        colnames = [r[1] for r in info]
        has_source = "__source_file" in colnames
        if has_source:
            total = con.execute(
                "SELECT COUNT(*) FROM items WHERE __source_file = ?",
                [stored_name],
            ).fetchone()[0]
            cur = con.execute(
                f"SELECT * FROM items WHERE __source_file = ? LIMIT {lim}",
                [stored_name],
            )
        else:
            total = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            cur = con.execute(f"SELECT * FROM items LIMIT {lim}")
        desc = cur.description
        keys = [d[0] for d in desc] if desc else []
        raw_rows = cur.fetchall()
    finally:
        con.close()

    rows = [dict(zip(keys, row, strict=False)) for row in raw_rows]
    for r in rows:
        if "__source_file" in r:
            del r["__source_file"]
    return {
        "columns": [c for c in keys if c != "__source_file"],
        "rows": rows,
        "total_rows_estimate": int(total),
        "truncated": int(total) > len(rows),
    }


def build_preview_payload(dataset_id: str, stored_name: str) -> dict:
    s = get_settings()
    sn = _safe_stored_name(stored_name)
    kind, original, path = resolve_workspace_file(dataset_id, sn)
    if kind == "pdf":
        n_pages, pages, truncated = preview_pdf_text(
            path,
            max_pages=s.preview_max_pdf_pages,
            max_chars_per_page=s.preview_max_chars_per_pdf_page,
        )
        return {
            "kind": "pdf",
            "original_name": original,
            "stored_name": sn,
            "page_count": n_pages,
            "pages": pages,
            "truncated": truncated,
        }
    data = preview_tabular_rows(dataset_id, sn, limit=s.preview_max_tabular_rows)
    return {
        "kind": "tabular",
        "original_name": original,
        "stored_name": sn,
        **data,
    }
