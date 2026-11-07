"""Bridge-owned message bus for authorized supervisor/worker task trees."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

_SESSION_RE = re.compile(r"^(?:tab:[0-9]{1,12}|team:[a-f0-9]{16,64}:tab:[0-9]{1,12})$", re.I)
_TASK_RE = re.compile(r"^task_[a-fA-F0-9-]{20,80}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,100}$")
_TERMINAL = {"completed", "failed", "stopped", "cancelled"}
_MAX_TASKS = 256
_MAX_INBOX = 100
_MAX_MESSAGES = 1024
_MAX_STATE_BYTES = 8 * 1024 * 1024


def _session(value: Any) -> str:
    text = str(value or "")
    return text if _SESSION_RE.fullmatch(text) else ""


def _task(value: Any) -> str:
    text = str(value or "")
    return text if _TASK_RE.fullmatch(text) else ""


class TeamMessageBus:
    """Small, bounded, restart-safe bus for direct supervisor/worker messages.

    ToolRegistry session IDs authenticate the requesting tab at the extension
    boundary. The bridge stores only task relationships and bounded messages;
    it never executes message contents.
    """

    def __init__(self, state_path: str | os.PathLike[str] | None = None):
        self.state_path = Path(state_path) if state_path else None
        self._lock = threading.RLock()
        self.tasks: dict[str, dict[str, Any]] = {}
        self.session_tasks: dict[str, str] = {}
        self.supervisors: set[str] = set()
        self.inboxes: dict[str, list[dict[str, Any]]] = {}
        self.sequences: dict[str, int] = {}
        self.message_ids: dict[str, tuple[str, int]] = {}
        self._load()

    def _load(self) -> None:
        path = self.state_path
        if not path:
            return
        try:
            if not path.is_file() or path.stat().st_size > _MAX_STATE_BYTES:
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            tasks = data.get("tasks", {})
            if isinstance(tasks, dict):
                for task_id, item in tasks.items():
                    if not _task(task_id) or not isinstance(item, dict):
                        continue
                    sid, parent_sid = _session(item.get("session_id")), _session(item.get("parent_session_id"))
                    parent_id = _task(item.get("parent_task_id")) if item.get("parent_task_id") else ""
                    depth, state = item.get("depth"), item.get("state")
                    if not sid or not parent_sid or sid == parent_sid or not isinstance(depth, int) or not 1 <= depth <= 3:
                        continue
                    if state not in {"starting", "running", *_TERMINAL}:
                        state = "starting"
                    safe = {
                        "task_id": task_id, "session_id": sid, "parent_session_id": parent_sid,
                        "parent_task_id": parent_id, "provider": str(item.get("provider", ""))[:40],
                        "depth": depth, "allow_children": item.get("allow_children") is True,
                        "state": state, "created_at": int(item.get("created_at", 0) or 0),
                        "updated_at": int(item.get("updated_at", 0) or 0),
                    }
                    self.tasks[task_id] = safe
                    self.session_tasks[sid] = task_id
                    self.supervisors.add(parent_sid)
            stored_sequences = data.get("sequences", {})
            if isinstance(stored_sequences, dict):
                for sid, sequence in stored_sequences.items():
                    sid = _session(sid)
                    if sid and isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 0:
                        self.sequences[sid] = sequence
            inboxes = data.get("inboxes", {})
            if isinstance(inboxes, dict):
                for sid, items in inboxes.items():
                    sid = _session(sid)
                    if not sid or not isinstance(items, list):
                        continue
                    safe_items = []
                    for item in items[-_MAX_INBOX:]:
                        if not isinstance(item, dict):
                            continue
                        mid = str(item.get("message_id", ""))
                        text = item.get("text")
                        seq = item.get("sequence")
                        if not _ID_RE.fullmatch(mid) or not isinstance(text, str) or not 1 <= len(text) <= 4000 or not isinstance(seq, int) or seq < 1:
                            continue
                        safe_items.append({
                            "message_id": mid, "sequence": seq,
                            "from_task_id": str(item.get("from_task_id", ""))[:90],
                            "direction": item.get("direction") if item.get("direction") in {"from_supervisor", "from_child"} else "from_supervisor",
                            "text": text, "created_at": int(item.get("created_at", 0) or 0),
                        })
                        self.message_ids[mid] = (sid, seq)
                    if safe_items:
                        self.inboxes[sid] = safe_items
                        self.sequences[sid] = max(self.sequences.get(sid, 0), *(x["sequence"] for x in safe_items))
            self._trim_locked()
        except Exception:
            # Corrupt/stale state is ignored; it must never stop bridge startup.
            self.tasks.clear(); self.session_tasks.clear(); self.supervisors.clear()
            self.inboxes.clear(); self.sequences.clear(); self.message_ids.clear()

    def _persist_locked(self) -> None:
        if not self.state_path:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps({
                "version": 1,
                "tasks": self.tasks,
                "inboxes": self.inboxes,
                "sequences": self.sequences,
            }, ensure_ascii=False, separators=(",", ":"))
            if len(payload.encode("utf-8")) > _MAX_STATE_BYTES:
                self._trim_locked()
                payload = json.dumps({"version": 1, "tasks": self.tasks, "inboxes": self.inboxes, "sequences": self.sequences}, ensure_ascii=False, separators=(",", ":"))
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.state_path.parent, prefix="team-bus-", suffix=".tmp", delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, self.state_path)
        except Exception:
            # Persistence is best-effort; in-memory messaging remains available.
            try:
                if "temp_path" in locals() and temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

    def _trim_locked(self) -> None:
        while sum(len(items) for items in self.inboxes.values()) > _MAX_MESSAGES:
            oldest_sid = ""
            oldest_time = float("inf")
            oldest_message = None
            for sid, items in self.inboxes.items():
                if items and items[0].get("created_at", 0) < oldest_time:
                    oldest_sid, oldest_time, oldest_message = sid, items[0].get("created_at", 0), items[0]
            if not oldest_message:
                break
            self.inboxes[oldest_sid].pop(0)
            self.message_ids.pop(oldest_message["message_id"], None)
        if len(self.tasks) > _MAX_TASKS:
            referenced_parents = {item["parent_task_id"] for item in self.tasks.values() if item.get("parent_task_id")}
            removable = sorted((item for item in self.tasks.values()
                                if item["state"] in _TERMINAL and item["task_id"] not in referenced_parents),
                               key=lambda x: x["updated_at"])
            for item in removable[:len(self.tasks) - _MAX_TASKS]:
                self.tasks.pop(item["task_id"], None)
                self.session_tasks.pop(item["session_id"], None)
            self.supervisors = {item["parent_session_id"] for item in self.tasks.values()}

    def register(self, *, task_id: Any, session_id: Any, parent_session_id: Any,
                 parent_task_id: Any = "", provider: Any = "", depth: Any = 1,
                 allow_children: Any = False) -> dict[str, Any]:
        tid, sid, parent_sid = _task(task_id), _session(session_id), _session(parent_session_id)
        raw_parent_tid = str(parent_task_id or "").strip()
        parent_tid = _task(raw_parent_tid) if raw_parent_tid else ""
        if raw_parent_tid and not parent_tid:
            return {"ok": False, "error": "invalid parent task ID"}
        if not tid or not sid or not parent_sid or sid == parent_sid:
            return {"ok": False, "error": "invalid task or tab session identity"}
        if not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= 3:
            return {"ok": False, "error": "team depth must be between one and three"}
        now = int(time.time() * 1000)
        with self._lock:
            existing = self.tasks.get(tid)
            if existing:
                same = (existing["session_id"] == sid and existing["parent_session_id"] == parent_sid and existing["parent_task_id"] == parent_tid)
                return {"ok": same, "duplicate": same, "error": None if same else "task ID is already bound to another session"}
            if sid in self.session_tasks:
                return {"ok": False, "error": "worker session is already bound to another team task"}
            self._trim_locked()
            if len(self.tasks) >= _MAX_TASKS:
                referenced = {item["parent_task_id"] for item in self.tasks.values() if item.get("parent_task_id")}
                removable = sorted((item for item in self.tasks.values()
                                    if item["state"] in _TERMINAL and item["task_id"] not in referenced),
                                   key=lambda item: item["updated_at"])
                if removable:
                    victim = removable[0]
                    self.tasks.pop(victim["task_id"], None)
                    self.session_tasks.pop(victim["session_id"], None)
                    self.supervisors = {item["parent_session_id"] for item in self.tasks.values()}
            if len(self.tasks) >= _MAX_TASKS:
                return {"ok": False, "error": "team task capacity reached; no unreferenced completed task can be retired"}
            if parent_tid:
                parent = self.tasks.get(parent_tid)
                if not parent or parent["session_id"] != parent_sid or not parent["allow_children"]:
                    return {"ok": False, "error": "parent task is missing or not authorized to delegate"}
                if parent["state"] != "running" or depth != parent["depth"] + 1:
                    return {"ok": False, "error": "child task does not match the authorized parent depth/state"}
            elif depth != 1:
                return {"ok": False, "error": "root workers must have depth one"}
            self.tasks[tid] = {
                "task_id": tid, "session_id": sid, "parent_session_id": parent_sid,
                "parent_task_id": parent_tid, "provider": str(provider or "")[:40],
                "depth": depth, "allow_children": allow_children is True,
                "state": "starting", "created_at": now, "updated_at": now,
            }
            self.session_tasks[sid] = tid
            self.supervisors.add(parent_sid)
            self._trim_locked(); self._persist_locked()
            return {"ok": True, "state": "starting", "duplicate": False}

    def update(self, *, session_id: Any, task_id: Any, state: Any,
               result: Any = "", error: Any = "") -> dict[str, Any]:
        sid, tid = _session(session_id), _task(task_id)
        if state not in {"starting", "running", *_TERMINAL}:
            return {"ok": False, "error": "invalid worker state"}
        with self._lock:
            item = self.tasks.get(tid)
            if not item or item["session_id"] != sid or self.session_tasks.get(sid) != tid:
                return {"ok": False, "error": "session does not own this team task"}
            current = item["state"]
            if current in _TERMINAL and state != current:
                return {"ok": False, "error": "terminal task state cannot be changed"}
            if current == "running" and state == "starting":
                return {"ok": False, "error": "running task cannot move back to starting"}
            item["state"] = state
            item["updated_at"] = int(time.time() * 1000)
            self._persist_locked()
            return {"ok": True, "state": state}

    def send_message(self, *, session_id: Any, target_task_id: Any,
                     message_id: Any, text: Any) -> dict[str, Any]:
        sid = _session(session_id)
        target_id = str(target_task_id or "")
        mid = str(message_id or "")
        body = str(text or "").strip()
        if not sid or not _ID_RE.fullmatch(mid):
            return {"ok": False, "error": "valid tab session and message ID are required"}
        if not body or len(body) > 4000:
            return {"ok": False, "error": "message must contain 1-4000 characters"}
        with self._lock:
            source_id = self.session_tasks.get(sid, "")
            source = self.tasks.get(source_id) if source_id else None
            if target_id == "supervisor":
                if not source:
                    return {"ok": False, "error": "only a registered worker can message its supervisor"}
                recipient_sid = source["parent_session_id"]
                direction, from_id = "from_child", source_id
            else:
                target = self.tasks.get(_task(target_id))
                if not target or target["parent_session_id"] != sid:
                    return {"ok": False, "error": "messages may only be sent to a direct child task"}
                if source:
                    if target["parent_task_id"] != source_id:
                        return {"ok": False, "error": "messages may only be sent to a direct child task"}
                elif sid not in self.supervisors or target["parent_task_id"]:
                    return {"ok": False, "error": "session is not the authorized supervisor of this worker"}
                recipient_sid = target["session_id"]
                direction, from_id = "from_supervisor", source_id or "supervisor"
            previous = self.message_ids.get(mid)
            if previous:
                if previous[0] != recipient_sid:
                    return {"ok": False, "error": "message ID was already used for another recipient"}
                original = next((item for item in self.inboxes.get(recipient_sid, [])
                                 if item.get("message_id") == mid), None)
                if original and (original.get("from_task_id") == from_id and
                                 original.get("direction") == direction and original.get("text") == body):
                    return {"ok": True, "duplicate": True, "sequence": previous[1], "message_id": mid}
                return {"ok": False, "error": "message ID was reused with different sender or content"}
            sequence = self.sequences.get(recipient_sid, 0) + 1
            item = {"message_id": mid, "sequence": sequence, "from_task_id": from_id,
                    "direction": direction, "text": body, "created_at": int(time.time() * 1000)}
            inbox = self.inboxes.setdefault(recipient_sid, [])
            inbox.append(item)
            if len(inbox) > _MAX_INBOX:
                removed = inbox.pop(0)
                self.message_ids.pop(removed["message_id"], None)
            self.sequences[recipient_sid] = sequence
            self.message_ids[mid] = (recipient_sid, sequence)
            self._trim_locked(); self._persist_locked()
            delivered = "supervisor" if target_id == "supervisor" else target_id
            return {"ok": True, "duplicate": False, "delivered_to": delivered, "sequence": sequence, "message_id": mid}

    def inbox(self, *, session_id: Any, after_sequence: Any = 0,
              limit: Any = 50) -> dict[str, Any]:
        sid = _session(session_id)
        if not sid:
            return {"ok": False, "error": "valid tab session is required"}
        try:
            after = max(0, int(after_sequence))
            cap = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid inbox cursor or limit"}
        with self._lock:
            task_id = self.session_tasks.get(sid)
            if not task_id and sid not in self.supervisors:
                # A newly started supervisor can safely see an empty inbox before
                # its first worker is registered; no unlinked messages are exposed.
                return {"ok": True, "task_id": None, "messages": [], "next_sequence": after}
            items = [dict(item) for item in self.inboxes.get(sid, []) if item["sequence"] > after]
            items = items[-cap:]
            return {"ok": True, "task_id": task_id, "messages": items,
                    "next_sequence": items[-1]["sequence"] if items else after}
