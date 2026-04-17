from __future__ import annotations

import json
from dataclasses import dataclass
import re
from pathlib import Path

import duckdb
import sqlparse
from fastapi import HTTPException
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from cachetools import TTLCache

from app.config import get_settings
from app.llm import LLMError, coerce_to_llm_error, get_chat_llm
from app.services.datasets import tabular_db_path


@dataclass(frozen=True)
class SQLAnswer:
    sql: str
    answer: str


_RE_QUOTED = re.compile(r"[\"“”'‘’]([^\"“”'‘’]{2,80})[\"“”'‘’]")
_RE_SEARCH_HINT = re.compile(r"\b(contient|containing|contains|inclut|include|includes|cherche|search|find)\b", re.IGNORECASE)

_PROFILE_CACHE: TTLCache[str, tuple[float, str]] = TTLCache(maxsize=256, ttl=600)
_SIGNALS_CACHE: TTLCache[str, tuple[float, str]] = TTLCache(maxsize=256, ttl=600)


def _db_mtime(p: Path) -> float:
    try:
        return float(p.stat().st_mtime)
    except Exception:
        return 0.0


def _sources_key(allowed_sources: list[str] | None) -> str:
    if allowed_sources is None:
        return "*"
    return ",".join(sorted(str(x) for x in allowed_sources))


_PROMPT_FILTERED = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a careful data assistant. Generate a single DuckDB SQL SELECT query.\n"
            "Rows may describe any kind of real-world or abstract data; use only the provided column names and the user’s question — do not assume what the table is “about” beyond that.\n"
            "If a conversation context block appears, use it ONLY to resolve follow-ups (pronouns, « same », etc.). "
            "The line after « Question actuelle : » is authoritative.\n"
            "The user may shift or widen the topic; map SQL only to what « Question actuelle » asks about this table, not to earlier themes they abandoned.\n"
            "Interpret that current question; do not assume extra filters or aggregates they did not ask for.\n"
            "If the question is too vague to map to one meaningful query (missing column, condition, or scope), "
            "output JSON with:\n"
            '- "answer": ONE short clarifying question in the SAME language as the user.\n'
            '- "sql": a valid SELECT that returns no rows but still obeys all rules below, e.g. '
            "`SELECT * FROM items WHERE __source_file IN ({allowed_sources}) AND 1=0 LIMIT 1`.\n"
            "Otherwise output a normal analytical query.\n"
            "Rules:\n"
            "- Output strictly valid JSON with keys: sql, answer.\n"
            "- The SQL must be a single SELECT statement querying the table `items`.\n"
            "- Do not use INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/ATTACH/PRAGMA.\n"
            "- Add a LIMIT 100 unless the user explicitly asks for all rows.\n"
            "- Use only the provided columns.\n"
            "- The column `__source_file` identifies which imported file each row comes from.\n"
            "- You MUST include: WHERE __source_file IN ({allowed_sources}) (combine with AND if other predicates).\n"
            "- Check column profiles for data types. If a column is VARCHAR/text but the question asks for numeric/date calculations, try using LIKE pattern matching as an alternative instead of giving up.\n"
            "- For date-related questions on text columns, try filtering with LIKE for year patterns (e.g., LIKE '%1943%' for year 1943) instead of date calculations.\n"
            '- The "answer" field must summarize what the SQL result shows; if the result is empty, say so clearly.\n'
            '- The "answer" text must be in the same language as the user\'s question (the « Question actuelle » line).\n'
            "Columns:\n{columns}\n"
            "Column profiles (types + examples):\n{profiles}\n"
            "Search signals (optional hints):\n{signals}\n",
        ),
        ("human", "{question}"),
    ]
)

_PROMPT_LEGACY = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a careful data assistant. Generate a single DuckDB SQL SELECT query.\n"
            "If a conversation context block appears, only the « Question actuelle » line is authoritative.\n"
            "Interpret that question; do not assume unstated filters.\n"
            "If the question is too vague to map to one meaningful query, output JSON with:\n"
            '- "answer": ONE short clarifying question in the user\'s language.\n'
            '- "sql": `SELECT * FROM items WHERE 1=0 LIMIT 1` (no rows).\n'
            "Otherwise output a normal query.\n"
            "Rules:\n"
            "- Output strictly valid JSON with keys: sql, answer.\n"
            "- The SQL must be a single SELECT statement querying the table `items`.\n"
            "- Do not use INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/ATTACH/PRAGMA.\n"
            "- Add a LIMIT 100 unless the user explicitly asks for all rows.\n"
            "- Use only the provided columns.\n"
            '- The "answer" field must summarize the SQL result; if empty, say so.\n'
            '- The "answer" must be in the same language as the user\'s latest question.\n'
            "Columns:\n{columns}\n"
            "Column profiles (types + examples):\n{profiles}\n"
            "Search signals (optional hints):\n{signals}\n",
        ),
        ("human", "{question}"),
    ]
)


def _escape_column_names(sql: str, columns: list[str]) -> str:
    """
    Échappe automatiquement les noms de colonnes qui contiennent des espaces ou caractères spéciaux.
    Cette fonction post-processe le SQL généré par le LLM pour corriger les noms de colonnes.
    """
    if not sql or not columns:
        return sql

    result = sql
    for col in columns:
        if not col:
            continue
        # Si le nom contient des espaces ou caractères non-alphanumériques (sauf underscore)
        if any(c.isspace() or not (c.isalnum() or c == '_') for c in col):
            # Remplacer les backticks par des guillemets doubles
            result = result.replace(f'`{col}`', f'"{col}"')
            # Remplacer les versions normalisées avec underscores
            normalized = col.replace(' ', '_').replace('-', '_')
            result = result.replace(f'`{normalized}`', f'"{col}"')
            result = result.replace(normalized, f'"{col}"')
            # Remplacer le nom original non-échappé par la version échappée
            # Utiliser une approche plus robuste avec regex pour éviter de remplacer dans les chaînes littérales
            import re
            # Pattern: mot qui n'est pas déjà entre guillemets doubles
            pattern = r'\b' + re.escape(col) + r'\b(?=(?:[^"]*"[^"]*")*[^"]*$)'
            result = re.sub(pattern, f'"{col}"', result)

    return result


def _validate_sql(sql: str) -> str:
    s = (sql or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="Empty SQL generated.")
    if ";" in s:
        raise HTTPException(status_code=400, detail="SQL must not contain semicolons.")

    parsed = sqlparse.parse(s)
    if len(parsed) != 1:
        raise HTTPException(status_code=400, detail="SQL must be a single statement.")

    stmt = parsed[0]
    stype = (stmt.get_type() or "").upper()
    if stype != "SELECT":
        raise HTTPException(status_code=400, detail="Only SELECT statements are allowed.")

    upper = s.upper()
    blocked = ["PRAGMA", "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT", "INSTALL", "LOAD"]
    if any(b in upper for b in blocked):
        raise HTTPException(status_code=400, detail="Disallowed SQL keyword detected.")

    # Basic safety: cap result size unless the model already did.
    if "LIMIT" not in upper:
        s = f"SELECT * FROM ({s}) AS _q LIMIT 100"

    return s


def _ensure_source_file_column(dataset_id: str) -> None:
    db_path = tabular_db_path(dataset_id)
    if not db_path.exists():
        return
    con = duckdb.connect(str(db_path))
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info('items')").fetchall()]
        if "__source_file" in cols:
            return
        con.execute("ALTER TABLE items ADD COLUMN __source_file VARCHAR")
        con.execute("UPDATE items SET __source_file = 'legacy' WHERE __source_file IS NULL")
    finally:
        con.close()


def _get_columns(dataset_id: str) -> list[str]:
    db_path = tabular_db_path(dataset_id)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="No tabular data found. Ingest CSV/Excel first.")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("PRAGMA threads=4")
        rows = con.execute("PRAGMA table_info('items')").fetchall()
    finally:
        con.close()

    # pragma table_info returns: cid, name, type, notnull, dflt_value, pk
    return [r[1] for r in rows]


def _table_info(dataset_id: str) -> list[tuple]:
    db_path = tabular_db_path(dataset_id)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("PRAGMA threads=4")
        return con.execute("PRAGMA table_info('items')").fetchall()
    finally:
        con.close()


def _profile_text(dataset_id: str, *, allowed_sources: list[str] | None) -> str:
    """
    Profiling léger pour guider le LLM (gros gain de qualité SQL).
    - types
    - null%
    - quelques exemples de valeurs distinctes
    - min/max pour numériques / dates quand possible
    """
    s = get_settings()
    if not s.tabular_profile_enabled:
        return "(profiles disabled)"
    db_path = tabular_db_path(dataset_id)
    mode = (s.tabular_profile_mode or "light").strip().lower()
    ttl = int(s.tabular_profile_ttl_seconds)
    key = f"{dataset_id}\x00{_sources_key(allowed_sources)}\x00{mode}"
    mtime = _db_mtime(db_path)
    if ttl > 0:
        hit = _PROFILE_CACHE.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("PRAGMA threads=4")
        info = con.execute("PRAGMA table_info('items')").fetchall()
        cols = [(r[1], str(r[2] or "")) for r in info if r[1] != "__source_file"]
        where = ""
        params: list[object] = []
        if allowed_sources is not None:
            where = "WHERE __source_file IN (" + ", ".join(["?"] * len(allowed_sources)) + ")"
            params = list(allowed_sources)
        # total rows (for null ratios)
        total = con.execute(f"SELECT COUNT(*) FROM items {where}", params).fetchone()[0] or 0
        total = int(total)
        lines: list[str] = []
        cap = 50 if mode == "light" else 100
        for name, typ in cols[:cap]:
            # null count
            nulls = con.execute(
                f"SELECT COUNT(*) FROM items {where} AND {duckdb.escape_identifier(name)} IS NULL" if where else f"SELECT COUNT(*) FROM items WHERE {duckdb.escape_identifier(name)} IS NULL",
                params,
            ).fetchone()[0]
            nulls_i = int(nulls or 0)
            null_pct = (nulls_i / total * 100.0) if total > 0 else 0.0

            examples_lim = 3 if mode == "light" else 5
            examples = con.execute(
                f"SELECT DISTINCT {duckdb.escape_identifier(name)} FROM items {where} AND {duckdb.escape_identifier(name)} IS NOT NULL LIMIT {examples_lim}"
                if where
                else f"SELECT DISTINCT {duckdb.escape_identifier(name)} FROM items WHERE {duckdb.escape_identifier(name)} IS NOT NULL LIMIT {examples_lim}",
                params,
            ).fetchall()
            ex = [str(r[0])[:40] for r in examples if r and r[0] is not None]
            ex_txt = ", ".join(ex) if ex else "-"

            mm_txt = ""
            t_upper = typ.upper()
            if any(k in t_upper for k in ["INT", "DEC", "NUM", "DOUBLE", "FLOAT", "REAL", "BIGINT", "SMALLINT", "TINYINT"]):
                row = con.execute(
                    f"SELECT MIN({duckdb.escape_identifier(name)}), MAX({duckdb.escape_identifier(name)}) FROM items {where}",
                    params,
                ).fetchone()
                if row:
                    mm_txt = f" min={row[0]} max={row[1]}"
            elif "DATE" in t_upper or "TIMESTAMP" in t_upper:
                row = con.execute(
                    f"SELECT MIN({duckdb.escape_identifier(name)}), MAX({duckdb.escape_identifier(name)}) FROM items {where}",
                    params,
                ).fetchone()
                if row:
                    mm_txt = f" min={row[0]} max={row[1]}"

            lines.append(f"- {name} ({typ}) nulls≈{null_pct:.1f}% examples: {ex_txt}{mm_txt}")
        out = "\n".join(lines) if lines else "(no columns)"
        if ttl > 0:
            _PROFILE_CACHE[key] = (mtime, out)
        return out
    except Exception:
        return "(profiles unavailable)"
    finally:
        con.close()


def _extract_search_terms(question: str) -> list[str]:
    q = (question or "").strip()
    if not q:
        return []
    out: list[str] = []
    for m in _RE_QUOTED.findall(q):
        t = (m or "").strip()
        if 2 <= len(t) <= 80:
            out.append(t)
        if len(out) >= 3:
            break
    return out


def _search_signals(dataset_id: str, *, question: str, allowed_sources: list[str] | None) -> str:
    """
    Heuristique : si la question ressemble à une recherche "contient X",
    on scanne rapidement les colonnes texte pour compter où X apparaît.
    """
    s = get_settings()
    if not s.tabular_search_signals_enabled:
        return "(signals disabled)"
    q = (question or "").strip()
    if not q or not _RE_SEARCH_HINT.search(q):
        return "(none)"
    terms = _extract_search_terms(q)
    if not terms:
        return "(none)"
    db_path = tabular_db_path(dataset_id)
    ttl = int(s.tabular_search_signals_ttl_seconds)
    mtime = _db_mtime(db_path)
    qk = "|".join(terms[:3])
    key = f"{dataset_id}\x00{_sources_key(allowed_sources)}\x00{qk}"
    if ttl > 0:
        hit = _SIGNALS_CACHE.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("PRAGMA threads=4")
        info = con.execute("PRAGMA table_info('items')").fetchall()
        text_cols = [r[1] for r in info if r[1] != "__source_file" and "CHAR" in str(r[2] or "").upper() or "TEXT" in str(r[2] or "").upper() or "VARCHAR" in str(r[2] or "").upper()]
        if not text_cols:
            return "(none)"
        where = ""
        params: list[object] = []
        if allowed_sources is not None:
            where = "WHERE __source_file IN (" + ", ".join(["?"] * len(allowed_sources)) + ")"
            params = list(allowed_sources)
        lines: list[str] = []
        for term in terms:
            tparam = f"%{term}%"
            best: list[tuple[str, int]] = []
            for c in text_cols[:120]:
                q_sql = (
                    f"SELECT COUNT(*) FROM items {where} AND CAST({duckdb.escape_identifier(c)} AS VARCHAR) ILIKE ?"
                    if where
                    else f"SELECT COUNT(*) FROM items WHERE CAST({duckdb.escape_identifier(c)} AS VARCHAR) ILIKE ?"
                )
                cnt = con.execute(q_sql, params + [tparam]).fetchone()[0]
                ci = int(cnt or 0)
                if ci:
                    best.append((c, ci))
            best.sort(key=lambda x: x[1], reverse=True)
            if best:
                top = ", ".join(f"{c}:{n}" for c, n in best[:6])
                lines.append(f"- term {term!r}: matches in {top}")
        out = "\n".join(lines) if lines else "(none)"
        if ttl > 0:
            _SIGNALS_CACHE[key] = (mtime, out)
        return out
    except Exception:
        return "(none)"
    finally:
        con.close()


def tabular_schema_text(dataset_id: str) -> str:
    """Résumé de schéma pour l’agent (ne lève pas d’exception si la DB est absente)."""
    if not tabular_db_path(dataset_id).exists():
        return "No tabular database in this workspace."
    try:
        cols = _get_columns(dataset_id)
    except Exception:
        return "Tabular database exists but columns could not be read."
    return "Table `items` columns:\n" + "\n".join(f"- {c}" for c in cols)


def _sql_list_literals(values: list[str]) -> str:
    out: list[str] = []
    for v in values:
        esc = (v or "").replace("'", "''")
        out.append(f"'{esc}'")
    return ", ".join(out) if out else "''"


class SQLQAService:
    def answer(
        self,
        dataset_id: str,
        question: str,
        provider: str | None = None,
        model: str | None = None,
        active_tabular_files: list[str] | None = None,
    ) -> tuple[str, str, list[dict]]:
        settings = get_settings()
        _ensure_source_file_column(dataset_id)
        cols = _get_columns(dataset_id)
        has_source = "__source_file" in cols
        allowed = active_tabular_files
        if has_source and allowed is not None and len(allowed) == 0:
            raise HTTPException(status_code=400, detail="Aucun fichier tableur sélectionné pour la requête.")
        allowed_list: list[str] | None = None
        allowed_sql = ""
        if has_source:
            if allowed is None:
                db_path = tabular_db_path(dataset_id)
                con = duckdb.connect(str(db_path), read_only=True)
                try:
                    con.execute("PRAGMA threads=4")
                    rows = con.execute(
                        "SELECT DISTINCT __source_file FROM items WHERE __source_file IS NOT NULL"
                    ).fetchall()
                finally:
                    con.close()
                allowed_list = [str(r[0]) for r in rows if r[0] is not None]
            else:
                allowed_list = list(allowed)
            if len(allowed_list) == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Aucune donnée tableur pour la sélection actuelle.",
                )
            allowed_sql = _sql_list_literals(allowed_list)

        try:
            llm = get_chat_llm(settings, provider_override=provider, model_override=model)
            profiles = _profile_text(dataset_id, allowed_sources=allowed_list if has_source else None)
            signals = _search_signals(dataset_id, question=question, allowed_sources=allowed_list if has_source else None)
            if has_source and allowed_list is not None:
                chain = _PROMPT_FILTERED | llm | StrOutputParser()
                raw = chain.invoke(
                    {
                        "question": question,
                        "columns": "\n".join(f"- {c}" for c in cols),
                        "allowed_sources": allowed_sql,
                        "profiles": profiles,
                        "signals": signals,
                    }
                )
            else:
                chain = _PROMPT_LEGACY | llm | StrOutputParser()
                raw = chain.invoke(
                    {
                        "question": question,
                        "columns": "\n".join(f"- {c}" for c in cols),
                        "profiles": profiles,
                        "signals": signals,
                    }
                )
        except LLMError:
            raise
        except Exception as exc:
            raise coerce_to_llm_error(exc) from exc

        try:
            # Nettoyer la réponse: enlever blocs markdown ```json ... ```
            cleaned = (raw or "").strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()
            # Chercher le premier objet JSON dans la réponse
            json_start = cleaned.find("{")
            json_end = cleaned.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                cleaned = cleaned[json_start:json_end]
            if not cleaned:
                raise ValueError("LLM a retourné une réponse vide")
            obj = json.loads(cleaned)
            sql = obj.get("sql", "")
            # Échapper automatiquement les noms de colonnes avec espaces/caractères spéciaux
            sql = _escape_column_names(sql, cols)
            sql = _validate_sql(sql)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"LLM output parsing error: {exc}") from exc

        # Exécuter le SQL d'abord
        db_path = tabular_db_path(dataset_id)
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            con.execute("PRAGMA threads=4")
            cur = con.execute(sql)
            colnames = [d[0] for d in cur.description]
            rows = cur.fetchmany(100)
        except Exception as sql_exc:
            con.close()
            # Log pour déboguer
            print(f"[SQL ERROR] Question: {question}")
            print(f"[SQL ERROR] Generated SQL: {sql}")
            print(f"[SQL ERROR] Error: {sql_exc}")
            # Retourner une réponse explicite sur l'erreur SQL
            error_msg = str(sql_exc)
            if "Parser Error" in error_msg or "syntax error" in error_msg:
                return "Erreur de syntaxe SQL. Le format des données ne permet pas cette requête.", "", []
            elif "Conversion Error" in error_msg:
                return "Erreur de conversion: les données ne sont pas dans le bon format pour ce calcul.", "", []
            else:
                return f"Erreur SQL: {error_msg[:100]}", "", []
        finally:
            con.close()

        preview = [dict(zip(colnames, r, strict=False)) for r in rows]

        # Générer la réponse basée sur les résultats réels
        try:
            answer_prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful data assistant. Based on the SQL query results, answer the user's question in a clear and direct way. Use the same language as the user's question. If there are no results, explicitly state that no results were found."),
                ("human", "Question: {question}\n\nSQL Results:\n{results}\n\nAnswer the question based on these results.")
            ])
            
            results_text = "\n".join(
                f"Row {i+1}: " + ", ".join(f"{k}={v}" for k, v in row.items())
                for i, row in enumerate(preview[:10])
            )
            if not preview:
                results_text = "No results found. The query returned 0 rows."
            
            answer_chain = answer_prompt | llm | StrOutputParser()
            answer = answer_chain.invoke({
                "question": question,
                "results": results_text
            }).strip()
            
            if not answer:
                answer = "Aucun résultat trouvé." if not preview else f"{len(preview)} résultat(s) trouvé(s)."
        except Exception:
            # Fallback: utiliser la réponse originale si le second appel échoue
            answer = str(obj.get("answer", "")).strip() or "OK."

        return answer, sql, preview

