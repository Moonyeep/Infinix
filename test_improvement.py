import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from agent_core.improvement import _bump_candidate_version, _generate_patch, _is_protected, _patch_paths, improve_once


class ImprovementTests(unittest.TestCase):
    def make_git_repo(self, root: Path) -> Path:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / "README.md").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "init"],
            cwd=root,
            check=True,
        )
        return root

    def test_dirty_tracked_worktree_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self.make_git_repo(Path(td))
            (repo / "README.md").write_text("dirty", encoding="utf-8")
            result = improve_once(repo)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("untracked changes", result["reason"])

    def test_untracked_files_also_block_git_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self.make_git_repo(Path(td))
            (repo / "untracked.py").write_text("pass\n", encoding="utf-8")
            result = improve_once(repo)
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(result["source_status"])

    def test_extracted_zip_directory_can_run_local_audit_and_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "extracted"
            repo.mkdir()
            (repo / "README.md").write_text("Infinix test source\n", encoding="utf-8")
            result = improve_once(repo, mode="audit", timeout=60)
            self.assertEqual(result["status"], "audit_complete")
            self.assertFalse(result["source_uploaded"])
            self.assertTrue(Path(result["report_path"]).is_file())
            saved = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "audit_complete")

    def test_proposal_refuses_source_upload_without_explicit_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "source"
            repo.mkdir()
            (repo / "README.md").write_text("local source\n", encoding="utf-8")
            result = improve_once(repo, mode="propose", allow_source_upload=False, timeout=60)
            self.assertEqual(result["status"], "source_upload_not_authorized")
            self.assertFalse(result["source_uploaded"])
            self.assertFalse(result["candidate_installed"])

    def test_proposal_needs_one_time_persistent_upload_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "source"
            repo.mkdir()
            (repo / "README.md").write_text("local source\n", encoding="utf-8")
            with patch.dict(os.environ, {"ZS_IMPROVE_ALLOW_SOURCE_UPLOAD": "0"}), patch(
                "agent_core.improvement._generate_patch"
            ) as generate:
                result = improve_once(repo, mode="propose", allow_source_upload=True, timeout=60)
            self.assertEqual(result["status"], "source_upload_not_authorized")
            self.assertFalse(result["source_uploaded"])
            generate.assert_not_called()

    def test_protected_source_files_cannot_be_patched(self):
        patch = "diff --git a/agent_core/policy.py b/agent_core/policy.py\n--- a/agent_core/policy.py\n+++ b/agent_core/policy.py\n"
        self.assertIn("agent_core/policy.py", _patch_paths(patch))
        self.assertTrue(_is_protected("agent_core/policy.py"))
        self.assertTrue(_is_protected("schedules/zeroscript-self-improve.service"))
        self.assertFalse(_is_protected("zeroscript-extension/core/main.js"))

    def test_patch_paths_reject_traversal(self):
        patch = "diff --git a/../../outside.py b/../../outside.py\n--- a/../../outside.py\n+++ b/../../outside.py\n"
        with self.assertRaises(ValueError):
            _patch_paths(patch)

    def test_patch_paths_reject_quoted_or_ambiguous_paths(self):
        patch = 'diff --git "a/file with spaces.py" "b/file with spaces.py"\n'
        with self.assertRaises(ValueError):
            _patch_paths(patch)

    def test_candidate_version_bump_updates_manifest_and_bridge_together(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            extension = root / "zeroscript-extension"
            extension.mkdir()
            (extension / "manifest.json").write_text('{"version":"1.6.15"}\n', encoding="utf-8")
            (root / "bridge.py").write_text('BRIDGE_VERSION = "1.6.15"\n', encoding="utf-8")
            self.assertEqual(_bump_candidate_version(root), "1.6.16")
            self.assertEqual(json.loads((extension / "manifest.json").read_text(encoding="utf-8"))["version"], "1.6.16")
            self.assertIn('BRIDGE_VERSION = "1.6.16"', (root / "bridge.py").read_text(encoding="utf-8"))

    def test_proposal_creates_versioned_candidate_zip_without_touching_active_source(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "source"
            extension = repo / "zeroscript-extension"
            extension.mkdir(parents=True)
            (repo / "README.md").write_text("old text\n", encoding="utf-8")
            (repo / "bridge.py").write_text('BRIDGE_VERSION = "1.6.15"\n', encoding="utf-8")
            (extension / "manifest.json").write_text('{"version":"1.6.15"}\n', encoding="utf-8")
            diff = (
                "diff --git a/README.md b/README.md\n"
                "--- a/README.md\n+++ b/README.md\n"
                "@@ -1 +1 @@\n-old text\n+improved text\n"
            )
            with patch.dict(os.environ, {"ZS_IMPROVE_ALLOW_SOURCE_UPLOAD": "1"}), patch(
                "agent_core.improvement._api_settings", return_value={"base": "http://localhost:1234/v1", "model": "test", "key": ""}
            ), patch("agent_core.improvement._generate_patch", return_value=(diff, {"model": "test", "no_change": False})):
                result = improve_once(repo, mode="propose", allow_source_upload=True, timeout=60)
            self.assertEqual(result["status"], "review_required")
            self.assertEqual(result["candidate_version"], "1.6.16")
            self.assertTrue(Path(result["candidate_zip"]).is_file())
            self.assertEqual((repo / "README.md").read_text(encoding="utf-8"), "old text\n")
            self.assertEqual(json.loads((extension / "manifest.json").read_text(encoding="utf-8"))["version"], "1.6.15")

    def test_openai_compatible_driver_uses_local_endpoint_and_sanitized_context(self):
        class Handler(BaseHTTPRequestHandler):
            payload = None

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                self.__class__.payload = json.loads(self.rfile.read(length))
                body = json.dumps({"choices": [{"message": {"content": "NO_CHANGE"}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                pass

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "README.md").write_text('api_key = "sk-' + "A" * 28 + '"\nordinary documentation\n', encoding="utf-8")
            server = HTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/v1"
                patch_text, info = _generate_patch(root, {"base": base, "model": "local-test", "key": ""}, 5)
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
            self.assertEqual(patch_text, "")
            self.assertTrue(info["no_change"])
            sent = json.dumps(Handler.payload)
            self.assertNotIn("A" * 28, sent)
            self.assertIn("[REDACTED]", sent)


if __name__ == "__main__":
    unittest.main()
