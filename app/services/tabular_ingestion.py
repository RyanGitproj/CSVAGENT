from __future__ import annotations

import csv
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import chardet
import pandas as pd
from fastapi import HTTPException, UploadFile

from app.config import get_settings
from app.services.datasets import dataset_dir, tabular_db_path


_RE_WS = re.compile(r"[ \t\f\v]+")


def _ensure_dataset_dirs(dataset_id: str) -> None:
    d = dataset_dir(dataset_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "imports").mkdir(parents=True, exist_ok=True)


def _too_large(content: bytes) -> bool:
    s = get_settings()
    return len(content) > (s.max_upload_mb * 1024 * 1024)


def _manifest_path(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "imports" / "manifest.json"


def _append_manifest(dataset_id: str, *, original_name: str, stored_name: str) -> None:
    path = _manifest_path(dataset_id)
    rows: list[dict] = []
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
    rows.append(
        {
            "kind": "tabular",
            "original_name": original_name,
            "stored_name": stored_name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _detect_encoding(content: bytes) -> str:
    """
    Détection encodage CSV (meilleure UX que utf-8/latin-1 seulement).
    Reste permissif: fallback sur utf-8 puis latin-1.
    """
    sample = content[:120_000]
    try:
        guess = chardet.detect(sample) or {}
        enc = str(guess.get("encoding") or "").strip()
        conf = float(guess.get("confidence") or 0.0)
        if enc and conf >= 0.55:
            return enc
    except Exception:
        pass
    return "utf-8"


def _sniff_csv_dialect(text_sample: str) -> tuple[str | None, str | None]:
    """
    Retourne (delimiter, quotechar) si détectable, sinon (None, None).
    """
    sample = (text_sample or "").strip()
    if not sample:
        return None, None
    try:
        d = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        delim = getattr(d, "delimiter", None)
        quote = getattr(d, "quotechar", None)
        return (delim if delim in [",", ";", "\t", "|"] else None), (quote if quote else None)
    except Exception:
        return None, None


def _read_csv_fast(file_path: Path, *, encoding: str, sep: str | None, quotechar: str | None) -> pd.DataFrame:
    try:
        return pd.read_csv(
            file_path,
            encoding=encoding,
            engine="c",
            sep=sep,
            quotechar=quotechar,
        )
    except Exception:
        return pd.read_csv(
            file_path,
            encoding=encoding,
            engine="python",
            sep=sep,
            quotechar=quotechar,
        )


def _normalize_col_name(name: str) -> str:
    t = unicodedata.normalize("NFKC", str(name or ""))
    t = t.replace("\u00a0", " ")
    t = _RE_WS.sub(" ", t).strip()
    if not t:
        return "col"
    return t


def _make_unique_columns(cols: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for c in cols:
        base = c
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append(base if n == 1 else f"{base}_{n}")
    return out


def _clean_text_cell(v: object) -> object:
    if v is None:
        return None
    if isinstance(v, str):
        t = unicodedata.normalize("NFKC", v)
        t = t.replace("\u00a0", " ")
        t = "".join(ch for ch in t if ch in ("\n", "\t") or unicodedata.category(ch)[0] != "C")
        t = _RE_WS.sub(" ", t).strip()
        return t
    return v


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    # Nettoyage safe des colonnes texte (ne touche pas aux nombres/dates).
    obj_cols = [c for c in df.columns if df[c].dtype == object]
    if obj_cols:
        for c in obj_cols:
            df[c] = df[c].map(_clean_text_cell)
    return df


def _read_tabular(file_path: Path) -> pd.DataFrame:
    name = file_path.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        # Default to first sheet; keep it simple for MVP.
        return pd.read_excel(file_path)

    if name.endswith(".csv"):
        # Détection encodage + séparateur.
        raw = file_path.read_bytes()
        enc = _detect_encoding(raw)
        # Sniff delimiter using decoded sample (fallbacks on decode errors).
        text_sample = ""
        for candidate in [enc, "utf-8", "latin-1"]:
            try:
                text_sample = raw[:80_000].decode(candidate, errors="replace")
                enc = candidate
                break
            except Exception:
                continue
        sep, quotechar = _sniff_csv_dialect(text_sample)
        # If sniff fails, try common default: auto for europe -> ';' often.
        if sep is None:
            sep = ";" if text_sample.count(";") > text_sample.count(",") else ","
        return _read_csv_fast(file_path, encoding=enc, sep=sep, quotechar=quotechar)

    raise HTTPException(
        status_code=400,
        detail="Formats acceptés : .csv, .xls, .xlsx uniquement.",
    )


class TabularIngestionService:
    TABLE_NAME = "items"

    async def ingest(self, dataset_id: str, file: UploadFile) -> dict:
        s = get_settings()
        _ensure_dataset_dirs(dataset_id)

        filename = file.filename or "upload"
        suffix = Path(filename).suffix.lower()
        if suffix not in (".csv", ".xls", ".xlsx"):
            raise HTTPException(
                status_code=400,
                detail="Formats acceptés : .csv, .xls, .xlsx uniquement.",
            )

        content = await file.read()
        if _too_large(content):
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux (max {s.max_upload_mb} Mo). Réduis la taille ou augmente MAX_UPLOAD_MB.",
            )

        import_id = str(uuid.uuid4())
        import_path = dataset_dir(dataset_id) / "imports" / f"{import_id}{suffix}"
        import_path.write_bytes(content)
        _append_manifest(dataset_id, original_name=filename, stored_name=import_path.name)

        try:
            df = _read_tabular(import_path)
        except HTTPException:
            raise
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Encodage du fichier illisible (CSV). Enregistre le fichier en UTF-8 ou Latin-1, "
                    "ou vérifie qu’il s’agit bien d’un CSV valide."
                ),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Lecture du tableur impossible : {exc}. "
                    "Vérifie le séparateur (virgule/point-virgule), les guillemets et qu’une seule feuille Excel contient les données."
                ),
            ) from exc

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="Le fichier ne contient aucune ligne de données (tableau vide).",
            )

        if len(df) > s.max_table_rows:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Trop de lignes ({len(df)}). Maximum autorisé : {s.max_table_rows}. "
                    "Filtre ou découpe le fichier, ou augmente MAX_TABLE_ROWS."
                ),
            )

        # Normalize + unique column names (avoid empty/duplicate names).
        df.columns = _make_unique_columns([_normalize_col_name(c) for c in df.columns])
        source_col = "__source_file"
        if source_col in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"A column named {source_col!r} is reserved; rename it in your file.",
            )
        df = _clean_dataframe(df)
        df[source_col] = import_path.name

        db_path = tabular_db_path(dataset_id)
        con = duckdb.connect(str(db_path))
        try:
            con.execute("PRAGMA threads=4")
            has_items = False
            try:
                con.execute(f"SELECT 1 FROM {self.TABLE_NAME} LIMIT 1")
                has_items = True
            except Exception:
                pass
            if not has_items:
                con.register("df", df)
                con.execute(f"CREATE TABLE {self.TABLE_NAME} AS SELECT * FROM df")
            else:
                info = con.execute(f"PRAGMA table_info('{self.TABLE_NAME}')").fetchall()
                existing_cols = [r[1] for r in info]
                if source_col not in existing_cols:
                    con.execute(
                        f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN {source_col} VARCHAR"
                    )
                    con.execute(
                        f"UPDATE {self.TABLE_NAME} SET {source_col} = 'legacy' WHERE {source_col} IS NULL"
                    )
                    existing_cols = [r[1] for r in con.execute(f"PRAGMA table_info('{self.TABLE_NAME}')").fetchall()]
                new_data_cols = [c for c in df.columns if c != source_col]
                old_data_cols = [c for c in existing_cols if c != source_col]
                if set(new_data_cols) != set(old_data_cols):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Les colonnes de ce fichier ne correspondent pas aux données déjà importées. "
                            "Supprimez les anciens fichiers tableur ou utilisez le même schéma."
                        ),
                    )
                con.execute(
                    f"DELETE FROM {self.TABLE_NAME} WHERE {source_col} = ?",
                    [import_path.name],
                )
                con.register("df", df)
                con.execute(f"INSERT INTO {self.TABLE_NAME} SELECT * FROM df")
            # Refresh stats for faster / more reliable query planning.
            try:
                con.execute(f"ANALYZE {self.TABLE_NAME}")
            except Exception:
                pass
        finally:
            con.close()

        return {
            "dataset_id": dataset_id,
            "table_name": self.TABLE_NAME,
            "rows": int(len(df)),
            "columns": [str(c) for c in df.columns if c != source_col],
        }

