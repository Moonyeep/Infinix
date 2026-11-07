from __future__ import annotations

import difflib
import hashlib
import os
import subprocess
import shutil
import tempfile
from pathlib import Path


class WorkspaceError(ValueError):
    pass


class Workspace:
    def __init__(self, root: Path, backup_dir: Path | None = None, allowed_roots: list[Path] | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        configured = [Path(p).expanduser().resolve() for p in (allowed_roots or [])]
        self.allowed_roots = tuple(dict.fromkeys([self.root, *configured]))
        self.backup_dir = (backup_dir or self.root / ".zeroscript" / "backups").resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str) -> Path:
        raw = Path(str(relative)).expanduser()
        candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        if any(candidate == base or base in candidate.parents for base in self.allowed_roots):
            return candidate
        roots = ", ".join(str(p) for p in self.allowed_roots)
        raise WorkspaceError(f"path is outside allowed workspace roots: {relative} (allowed: {roots})")

    def read(self, relative: str, start_line: int = 1, line_count: int = 500, max_chars: int = 40000) -> str:
        """Read a bounded UTF-8 text excerpt; callers can page through long files."""
        path = self.resolve(relative)
        if not path.is_file():
            raise WorkspaceError(f"file not found: {relative}")
        if path.stat().st_size > 8 * 1024 * 1024:
            raise WorkspaceError("file exceeds the 8 MiB text-read safety limit")
        start = max(1, int(start_line))
        count = max(1, min(int(line_count), 2000))
        limit = max(100, min(int(max_chars), 100000))
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("file is not valid UTF-8 text") from exc
        selected = "".join(text.splitlines(keepends=True)[start - 1 : start - 1 + count])
        return selected[:limit]

    _SEARCH_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build", "coverage", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache", ".zeroscript"}
    _SEARCH_SKIP_FILES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json", "secrets.json"}

    def search(self, query: str, path: str = ".", glob: str = "*", limit: int = 50, context_chars: int = 160) -> dict[str, object]:
        """Literal case-insensitive source search, bounded and excluding secrets/generated trees."""
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            raise WorkspaceError("query must contain 1-1000 characters")
        if not isinstance(glob, str) or len(glob) > 200:
            raise WorkspaceError("glob must be a pattern up to 200 characters")
        base = self.resolve(path)
        if not base.is_dir():
            raise WorkspaceError(f"search path is not a directory: {path}")
        max_results = max(1, min(int(limit), 200))
        context = max(0, min(int(context_chars), 500))
        needle = query.casefold()
        results: list[dict[str, object]] = []
        files_scanned = 0
        for current, dirs, names in os.walk(base, followlinks=False):
            current_path = Path(current)
            dirs[:] = [name for name in dirs if name not in self._SEARCH_SKIP_DIRS and not (current_path / name).is_symlink()]
            for name in names:
                if name in self._SEARCH_SKIP_FILES or name.startswith(".env.") or name.lower().endswith((".pem", ".key", ".p12", ".pfx")):
                    continue
                file_path = current_path / name
                try:
                    resolved = file_path.resolve(strict=True)
                    resolved.relative_to(self.root)
                    if not resolved.is_file() or resolved.stat().st_size > 1_000_000:
                        continue
                    rel = file_path.relative_to(self.root).as_posix()
                    if not Path(rel).match(glob):
                        continue
                    raw = resolved.read_bytes()
                    if b"\x00" in raw[:8192]:
                        continue
                    text = raw.decode("utf-8")
                except (OSError, ValueError, UnicodeDecodeError):
                    continue
                files_scanned += 1
                for line_no, line in enumerate(text.splitlines(), 1):
                    column = line.casefold().find(needle)
                    if column < 0:
                        continue
                    lo, hi = max(0, column - context), min(len(line), column + len(query) + context)
                    results.append({"path": rel, "line": line_no, "column": column + 1, "text": line[lo:hi], "truncated": lo > 0 or hi < len(line)})
                    if len(results) >= max_results:
                        return {"query": query, "path": str(base), "files_scanned": files_scanned, "matches": results, "truncated": True}
        return {"query": query, "path": str(base), "files_scanned": files_scanned, "matches": results, "truncated": False}

    def git_status(self) -> dict[str, object]:
        return self._git_read(["status", "--short", "--branch", "--untracked-files=normal"])

    def git_diff(self, staged: bool = False, context_lines: int = 3) -> dict[str, object]:
        context = max(0, min(int(context_lines), 20))
        args = ["diff", "--no-ext-diff", "--no-textconv", "--no-color", f"--unified={context}"]
        if staged:
            args.append("--cached")
        args += ["--", ".", ":!.env", ":!.env.*", ":!*secret*", ":!*credential*"]
        result = self._git_read(args, output_limit=40000)
        return result

    def _git_read(self, args: list[str], output_limit: int = 12000) -> dict[str, object]:
        executable = shutil.which("git")
        if not executable:
            return {"available": False, "error": "git executable not found"}
        env = {"PATH": os.environ.get("PATH", ""), "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
        try:
            proc = subprocess.run([executable, "-C", str(self.root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, env=env, check=False)
        except subprocess.TimeoutExpired:
            return {"available": True, "error": "git inspection timed out"}
        output = proc.stdout or ""
        return {"available": True, "returncode": proc.returncode, "output": output[:output_limit], "truncated": len(output) > output_limit, "error": (proc.stderr or "")[-2000:] if proc.returncode else ""}

    def _atomic_write(self, path: Path, current: str, updated: str, create_only: bool = False) -> Path | None:
        if not path.parent.is_dir():
            raise WorkspaceError(f"parent directory does not exist: {path.parent}")
        backup = None
        if path.exists():
            digest = hashlib.sha256(current.encode()).hexdigest()[:16]
            backup = self.backup_dir / f"{path.name}.{digest}.bak"
            shutil.copy2(path, backup)
        fd, tmp_name = tempfile.mkstemp(prefix=".zs-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(updated)
                fh.flush()
                os.fsync(fh.fileno())
            if create_only:
                try:
                    os.link(tmp_name, path)
                except FileExistsError as exc:
                    raise WorkspaceError(f"file already exists: {path}") from exc
            else:
                os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return backup

    def create(self, relative: str, content: str) -> dict[str, str | int | bool]:
        path = self.resolve(relative)
        if not isinstance(content, str):
            raise WorkspaceError("content must be a string")
        if path.exists():
            raise WorkspaceError(f"file already exists: {relative}")
        self._atomic_write(path, "", content, create_only=True)
        diff = "".join(difflib.unified_diff([], content.splitlines(True), fromfile=relative, tofile=relative))
        return {"path": relative, "created": True, "diff": diff, "bytes": len(content.encode("utf-8"))}

    def write(self, relative: str, content: str) -> dict[str, str | int | bool]:
        path = self.resolve(relative)
        if not isinstance(content, str):
            raise WorkspaceError("content must be a string")
        if path.exists() and not path.is_file():
            raise WorkspaceError(f"not a file: {relative}")
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        backup = self._atomic_write(path, current, content)
        diff = "".join(difflib.unified_diff(current.splitlines(True), content.splitlines(True), fromfile=relative, tofile=relative))
        return {
            "path": relative,
            "backup": str(backup) if backup else "",
            "created": backup is None,
            "diff": diff,
            "bytes": len(content.encode("utf-8")),
        }

    def list(self, relative: str = ".", recursive: bool = False, max_depth: int = 2, limit: int = 200) -> dict[str, object]:
        """List entries without reading file contents, confined to allowed roots."""
        path = self.resolve(relative)
        if not path.exists():
            raise WorkspaceError(f"path not found: {relative}")
        if not path.is_dir():
            raise WorkspaceError(f"not a directory: {relative}")
        depth_limit = max(0, min(int(max_depth), 8))
        item_limit = max(1, min(int(limit), 1000))
        entries: list[dict[str, object]] = []
        base = path
        pending = [(path, 0)]
        while pending and len(entries) < item_limit:
            current, depth = pending.pop(0)
            try:
                children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError as exc:
                entries.append({"path": str(current), "error": str(exc)})
                continue
            for child in children:
                if len(entries) >= item_limit:
                    break
                rel = child.relative_to(base).as_posix() or "."
                is_dir = child.is_dir()
                item = {"path": rel, "name": child.name, "type": "directory" if is_dir else "file"}
                if not is_dir:
                    try: item["bytes"] = child.stat().st_size
                    except OSError: pass
                entries.append(item)
                if recursive and is_dir and depth < depth_limit:
                    pending.append((child, depth + 1))
        return {"path": str(path), "entries": entries, "truncated": bool(pending) or len(entries) >= item_limit}

    def patch(self, relative: str, old_text: str, new_text: str) -> dict[str, str | int]:
        path = self.resolve(relative)
        if path.exists() and not path.is_file():
            raise WorkspaceError(f"not a file: {relative}")
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if old_text and current.count(old_text) != 1:
            raise WorkspaceError("old_text must match exactly once")
        updated = current.replace(old_text, new_text, 1) if old_text else new_text
        backup = self._atomic_write(path, current, updated)
        diff = "".join(difflib.unified_diff(current.splitlines(True), updated.splitlines(True), fromfile=relative, tofile=relative))
        return {"path": relative, "backup": str(backup) if backup else "", "diff": diff, "bytes": len(updated.encode())}

    def rollback(self, backup: str) -> str:
        backup_path = Path(backup).resolve()
        if self.backup_dir not in backup_path.parents:
            raise WorkspaceError("backup is outside workspace backup directory")
        target_name = backup_path.name.rsplit(".", 2)[0]
        target = self.resolve(target_name)
        shutil.copy2(backup_path, target)
        return str(target)
