#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agent_core.improvement import improve_once


SUCCESS_STATES = {
    "audit_complete",
    "review_required",
    "no_change",
    "source_upload_not_authorized",
    "driver_unconfigured",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Infinix or generate an isolated self-improvement candidate")
    parser.add_argument("--repo", default=".", help="project directory (Git checkout or extracted source package)")
    parser.add_argument("--mode", choices=("audit", "propose"), default="audit")
    parser.add_argument("--allow-source-upload", action="store_true", help="request remote proposal; also requires persistent ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1")
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("ZS_IMPROVE_TIMEOUT", str(4 * 60 * 60))))
    args = parser.parse_args()
    try:
        result = improve_once(
            Path(args.repo),
            timeout=args.timeout,
            mode=args.mode,
            allow_source_upload=args.allow_source_upload,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in SUCCESS_STATES else 1


if __name__ == "__main__":
    raise SystemExit(main())
