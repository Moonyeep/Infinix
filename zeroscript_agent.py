#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agent_core.events import EventLog
from agent_core.policy import PolicyBroker
from agent_core.session import SessionStore
from agent_core.tools import ToolRegistry
from agent_core.workspace import Workspace


def build(root: Path):
    state = root / ".zeroscript"
    events = EventLog(state / "events.jsonl")
    sessions = SessionStore(state / "sessions.db")
    extra_roots = [Path(x.strip()) for x in os.environ.get("ZS_AGENT_WORKSPACE_ROOTS", "").split(os.pathsep) if x.strip()]
    workspace = Workspace(root, allowed_roots=extra_roots)
    registry = ToolRegistry(workspace, PolicyBroker(), events)
    return registry, sessions


def main() -> int:
    parser = argparse.ArgumentParser(prog="infinix-agent", description="Infinix local agent core")
    parser.add_argument("--workspace", default=".", help="workspace root")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("tools")
    read = sub.add_parser("read")
    read.add_argument("path")
    create = sub.add_parser("create")
    create.add_argument("path")
    create.add_argument("content")
    create.add_argument("--approve", action="store_true")
    write = sub.add_parser("write")
    write.add_argument("path")
    write.add_argument("content")
    write.add_argument("--approve", action="store_true")
    patch = sub.add_parser("patch")
    patch.add_argument("path")
    patch.add_argument("old_text")
    patch.add_argument("new_text")
    patch.add_argument("--approve", action="store_true")
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    registry, sessions = build(root)
    sid = sessions.create({"action": args.action})
    sessions.set_state(sid, "RUNNING")
    try:
        if args.action == "tools":
            print(json.dumps(registry.manifest(), indent=2, ensure_ascii=False))
        elif args.action == "read":
            result = registry.call("file.read", {"path": args.path})
            print(json.dumps(result, ensure_ascii=False))
        elif args.action == "create":
            result = registry.call("file.create", {"path": args.path, "content": args.content}, approved=args.approve)
            sessions.checkpoint(sid, "create-result", result)
            print(json.dumps(result, ensure_ascii=False))
        elif args.action == "write":
            result = registry.call("file.write", {"path": args.path, "content": args.content}, approved=args.approve)
            sessions.checkpoint(sid, "write-result", result)
            print(json.dumps(result, ensure_ascii=False))
        elif args.action == "patch":
            result = registry.call("file.patch", {"path": args.path, "old_text": args.old_text, "new_text": args.new_text}, approved=args.approve)
            sessions.checkpoint(sid, "patch-result", result)
            print(json.dumps(result, ensure_ascii=False))
        sessions.set_state(sid, "SUCCEEDED")
        return 0
    except Exception as exc:
        sessions.set_state(sid, "FAILED")
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
