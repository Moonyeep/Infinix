from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class SessionStore:
    """Small resumable state store; payloads are JSON and never treated as policy."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, state TEXT NOT NULL, created_at REAL NOT NULL,
              updated_at REAL NOT NULL, metadata TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, created_at REAL NOT NULL,
              label TEXT NOT NULL, payload TEXT NOT NULL,
              FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, metadata: dict[str, Any] | None = None) -> str:
        sid = str(uuid.uuid4())
        now = time.time()
        with self._db() as db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)", (sid, "IDLE", now, now, json.dumps(metadata or {})))
        return sid

    def set_state(self, session_id: str, state: str) -> None:
        with self._db() as db:
            db.execute("UPDATE sessions SET state=?, updated_at=? WHERE id=?", (state, time.time(), session_id))

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def checkpoint(self, session_id: str, label: str, payload: dict[str, Any]) -> str:
        cid = str(uuid.uuid4())
        with self._db() as db:
            db.execute("INSERT INTO checkpoints VALUES (?, ?, ?, ?, ?)", (cid, session_id, time.time(), label, json.dumps(payload, ensure_ascii=False)))
        return cid

    def latest_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM checkpoints WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (session_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result
