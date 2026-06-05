from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from personal_secretary.config import SecretaryConfig
from personal_secretary.models import ClassifiedFile, IngestedFile


class SecretaryStorage:
    def __init__(self, config: SecretaryConfig) -> None:
        self.config = config
        self.base = config.data_dir
        self.inbox = self.base / "inbox"
        self.organized = self.base / "organized"
        self.reports = self.base / "reports"
        self.state_file = self.base / "state.json"
        self.db_path = self.base / "secretary.db"

        self.inbox.mkdir(parents=True, exist_ok=True)
        self.organized.mkdir(parents=True, exist_ok=True)
        self.reports.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    project TEXT,
                    category TEXT,
                    created_at TEXT NOT NULL,
                    sender TEXT,
                    subject TEXT,
                    extracted_text TEXT,
                    target_path TEXT,
                    UNIQUE(source, source_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    attachments_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_expense_overrides (
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (source, source_id)
                )
                """
            )

    def load_state(self) -> dict:
        if not self.state_file.exists():
            return {}
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save_state(self, state: dict) -> None:
        self.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def has_source_item(self, source: str, source_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM files WHERE source=? AND source_id=? LIMIT 1", (source, source_id)
            ).fetchone()
            return row is not None

    def register_ingested(self, item: IngestedFile) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO files
                (source, source_id, file_name, local_path, created_at, sender, subject)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.source,
                    item.source_id,
                    item.file_name,
                    str(item.local_path),
                    item.created_at,
                    item.sender,
                    item.subject,
                ),
            )

    def register_classified(self, item: ClassifiedFile) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE files
                SET project=?, category=?, extracted_text=?, target_path=?
                WHERE source=? AND source_id=?
                """,
                (
                    item.project,
                    item.category,
                    item.extracted_text[:50000],
                    str(item.target_path),
                    item.ingested.source,
                    item.ingested.source_id,
                ),
            )

    def all_indexed_files(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    f.source,
                    f.source_id,
                    f.file_name,
                    f.local_path,
                    f.project,
                    f.category,
                    f.created_at,
                    f.sender,
                    f.subject,
                    f.extracted_text,
                    f.target_path,
                    CASE WHEN mo.source_id IS NOT NULL THEN 1 ELSE 0 END AS manual_expense_override,
                    COALESCE(mo.category, '') AS manual_expense_category
                FROM files f
                LEFT JOIN manual_expense_overrides mo
                    ON mo.source = f.source AND mo.source_id = f.source_id
                ORDER BY f.created_at DESC
                """
            ).fetchall()
        keys = [
            "source",
            "source_id",
            "file_name",
            "local_path",
            "project",
            "category",
            "created_at",
            "sender",
            "subject",
            "extracted_text",
            "target_path",
            "manual_expense_override",
            "manual_expense_category",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def set_manual_expense_override(self, source: str, source_id: str, category: str, note: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO manual_expense_overrides (source, source_id, category, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source, source_id)
                DO UPDATE SET category=excluded.category, note=excluded.note, created_at=excluded.created_at
                """,
                (source, source_id, category, note, datetime.utcnow().isoformat()),
            )

    def clear_manual_expense_override(self, source: str, source_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM manual_expense_overrides WHERE source=? AND source_id=?",
                (source, source_id),
            )

    def save_report(self, payload: dict) -> None:
        now = datetime.utcnow().isoformat()
        payload_file = self.reports / f"report_{now.replace(':', '-').replace('.', '-')}.json"
        payload_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with self._conn() as conn:
            conn.execute(
                "INSERT INTO reports (created_at, payload_json) VALUES (?, ?)",
                (now, json.dumps(payload, ensure_ascii=False)),
            )

    def latest_report(self) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload_json FROM reports ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return {}
        return json.loads(row[0])

    def save_chat_message(self, role: str, content: str, attachments: list[str] | None = None) -> None:
        payload = json.dumps(attachments or [], ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (created_at, role, content, attachments_json)
                VALUES (?, ?, ?, ?)
                """,
                (datetime.utcnow().isoformat(), role, content, payload),
            )

    def recent_chat_messages(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT created_at, role, content, attachments_json
                FROM chat_messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        result: list[dict] = []
        for created_at, role, content, attachments_json in reversed(rows):
            try:
                attachments = json.loads(attachments_json)
            except json.JSONDecodeError:
                attachments = []
            result.append(
                {
                    "created_at": created_at,
                    "role": role,
                    "content": content,
                    "attachments": attachments,
                }
            )
        return result

    def save_agent_run(self, payload: dict) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agent_runs (created_at, payload_json) VALUES (?, ?)",
                (now, json.dumps(payload, ensure_ascii=False)),
            )

    def latest_agent_run(self) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return {}
        return json.loads(row[0])

    def list_agent_runs(self, limit: int = 30) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, payload_json
                FROM agent_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        result: list[dict] = []
        for run_id, created_at, payload_json in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                payload = {}
            result.append(
                {
                    "id": run_id,
                    "created_at": created_at,
                    "payload": payload,
                }
            )
        return result

    def get_agent_run(self, run_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, created_at, payload_json FROM agent_runs WHERE id=? LIMIT 1",
                (run_id,),
            ).fetchone()
        if not row:
            return {}

        raw_id, created_at, payload_json = row
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            payload = {}

        return {
            "id": raw_id,
            "created_at": created_at,
            "payload": payload,
        }

    def outlook_attachment_stats(self, recent_days: int = 14) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT created_at FROM files WHERE source='outlook'"
            ).fetchall()

        total = len(rows)
        recent = 0
        last_sync_iso = ""
        cutoff = datetime.utcnow() - timedelta(days=max(1, recent_days))
        last_sync_dt: datetime | None = None

        for (created_at_raw,) in rows:
            dt = self._parse_datetime(str(created_at_raw or ""))
            if not dt:
                continue
            if dt >= cutoff:
                recent += 1
            if last_sync_dt is None or dt > last_sync_dt:
                last_sync_dt = dt

        if last_sync_dt:
            last_sync_iso = last_sync_dt.isoformat()

        return {
            "total": total,
            "recent": recent,
            "recent_days": max(1, recent_days),
            "last_sync": last_sync_iso,
        }

    @staticmethod
    def _parse_datetime(raw: str) -> datetime | None:
        text = raw.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is not None:
                return dt.replace(tzinfo=None)
            return dt
        except Exception:
            return None
