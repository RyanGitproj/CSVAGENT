from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    created_at: str


class ChatMemoryStore:
    def __init__(self) -> None:
        s = get_settings()
        self._db_path: Path = s.data_dir / "chat_memory.sqlite3"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self._db_path))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        return con

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        con = self._connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conv_time "
                "ON messages(conversation_id, created_at)"
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    conversation_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            con.commit()
        finally:
            con.close()

    def append_turn(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO messages(id, conversation_id, role, content, created_at) VALUES(?,?,?,?,?)",
                (str(uuid.uuid4()), conversation_id, "user", user_text, now),
            )
            con.execute(
                "INSERT INTO messages(id, conversation_id, role, content, created_at) VALUES(?,?,?,?,?)",
                (str(uuid.uuid4()), conversation_id, "assistant", assistant_text, now),
            )
            con.commit()
        finally:
            con.close()

    def recent_history(self, conversation_id: str, max_messages: int = 12) -> list[tuple[str, str]]:
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT role, content FROM (
                  SELECT role, content, created_at
                  FROM messages
                  WHERE conversation_id = ?
                  ORDER BY created_at DESC
                  LIMIT ?
                ) ORDER BY created_at ASC
                """,
                (conversation_id, max_messages),
            ).fetchall()
        finally:
            con.close()
        return [(str(r["role"]), str(r["content"])) for r in rows]

    def message_count(self, conversation_id: str) -> int:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        finally:
            con.close()
        return int(row["n"]) if row else 0

    def get_conversation_summary(self, conversation_id: str) -> str | None:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT summary FROM conversation_summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        finally:
            con.close()
        if not row:
            return None
        t = (row["summary"] or "").strip()
        return t or None

    def set_conversation_summary(self, conversation_id: str, summary: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        con = self._connect()
        try:
            con.execute(
                """
                INSERT INTO conversation_summaries(conversation_id, summary, updated_at)
                VALUES(?,?,?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                  summary = excluded.summary,
                  updated_at = excluded.updated_at
                """,
                (conversation_id, summary, now),
            )
            con.commit()
        finally:
            con.close()

    def prune(self, conversation_id: str, keep_last: int = 60) -> None:
        con = self._connect()
        try:
            con.execute(
                """
                DELETE FROM messages
                WHERE conversation_id = ?
                AND id NOT IN (
                  SELECT id
                  FROM messages
                  WHERE conversation_id = ?
                  ORDER BY created_at DESC
                  LIMIT ?
                )
                """,
                (conversation_id, conversation_id, keep_last),
            )
            con.commit()
        finally:
            con.close()

    def list_conversations(self, *, limit: int = 60) -> list[dict[str, str | int]]:
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT
                  t.conversation_id AS id,
                  t.updated_at AS updated_at,
                  (
                    SELECT COUNT(*) FROM messages c WHERE c.conversation_id = t.conversation_id
                  ) AS message_count,
                  (
                    SELECT content FROM messages u
                    WHERE u.conversation_id = t.conversation_id AND u.role = 'user'
                    ORDER BY u.created_at ASC
                    LIMIT 1
                  ) AS first_user_text
                FROM (
                  SELECT conversation_id, MAX(created_at) AS updated_at
                  FROM messages
                  GROUP BY conversation_id
                ) AS t
                ORDER BY t.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            con.close()

        out: list[dict[str, str | int]] = []
        for r in rows:
            raw_title = (r["first_user_text"] or "").strip() or "(discussion vide)"
            if len(raw_title) > 52:
                raw_title = raw_title[:49] + "…"
            out.append(
                {
                    "id": str(r["id"]),
                    "title": raw_title,
                    "updated_at": str(r["updated_at"]),
                    "message_count": int(r["message_count"] or 0),
                }
            )
        return out

    def messages_for_conversation(self, conversation_id: str) -> list[tuple[str, str, str]]:
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()
        finally:
            con.close()
        out: list[tuple[str, str, str]] = []
        for r in rows:
            ts = r["created_at"]
            out.append((str(r["role"]), str(r["content"]), str(ts) if ts is not None else ""))
        return out

    def delete_conversation(self, conversation_id: str) -> int:
        con = self._connect()
        try:
            con.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (conversation_id,))
            cur = con.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            con.commit()
            return int(cur.rowcount or 0)
        finally:
            con.close()
