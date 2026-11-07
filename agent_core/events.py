from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"(api[_-]?key|token|secret|password|authorization|cookie)", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "[REDACTED]" if _SECRET_KEY.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str) and len(value) > 2048:
        return value[:2048] + "...[TRUNCATED]"
    return value


class EventLog:
    """Append-only JSONL event log with correlation IDs and conservative redaction."""

    def __init__(self, path: Path, session_id: str | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or str(uuid.uuid4())

    def emit(self, event: str, **data: Any) -> dict[str, Any]:
        record = {
            "ts": time.time(),
            "session_id": self.session_id,
            "event_id": str(uuid.uuid4()),
            "event": event,
            "data": redact(data),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record
