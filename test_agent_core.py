import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent_core.events import EventLog
from agent_core.policy import Decision, PolicyBroker
from agent_core.process import ProcessPolicyError, ProcessRunner
from agent_core.tools import ToolRegistry
from agent_core.workspace import Workspace, WorkspaceError


class AgentCoreTests(unittest.TestCase):
    def make(self, tmp_path: Path):
        root = tmp_path / "ws"
        root.mkdir()
        events = EventLog(root / ".zeroscript" / "events.jsonl", session_id="test")
        registry = ToolRegistry(Workspace(root), PolicyBroker(), events)
        registry.set_profile("development")
        return root, registry

    def test_read_is_allowed_and_confined(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            (root / "a.txt").write_text("hello", encoding="utf-8")
            self.assertEqual(tools.call("file.read", {"path": "a.txt"})["content"], "hello")
            with self.assertRaises(WorkspaceError):
                tools.call("file.read", {"path": "../outside.txt"})

    def test_file_read_supports_bounded_paging(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            (root / "long.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
            result = tools.call("file.read", {"path": "long.txt", "start_line": 2, "line_count": 2})
            self.assertEqual(result["content"], "two\nthree\n")
            self.assertEqual(result["start_line"], 2)

    def test_workspace_search_skips_generated_and_env_files(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            (root / "src").mkdir()
            (root / "src" / "logic.py").write_text("Needle in source\n", encoding="utf-8")
            (root / ".env.local").write_text("Needle=private\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "dep.js").write_text("Needle\n", encoding="utf-8")
            result = tools.call("workspace.search", {"query": "needle"})
            self.assertEqual([(item["path"], item["line"]) for item in result["matches"]], [("src/logic.py", 1)])

    def test_git_status_and_diff_are_available_read_only(self):
        import shutil, subprocess
        if not shutil.which("git"):
            self.skipTest("git is not installed")
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            def git(*args):
                subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
            git("init", "-q")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Test")
            target = root / "src.py"
            target.write_text("before\n", encoding="utf-8")
            git("add", "src.py"); git("commit", "-qm", "initial")
            target.write_text("after\n", encoding="utf-8")
            self.assertIn("src.py", tools.call("git.status", {})["output"])
            self.assertIn("-before", tools.call("git.diff", {})["output"])
            log = (root / ".zeroscript" / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("before", log)
            self.assertNotIn("after", log)

    def test_workspace_context_reads_standard_project_guidance(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            (root / "AGENTS.md").write_text("Use the existing style.", encoding="utf-8")
            ctx = tools.call("workspace.context", {})
            self.assertEqual(ctx["documents"][0]["path"], "AGENTS.md")
            self.assertIn("untrusted data", ctx["instructions_warning"])

    def test_browser_fill_value_is_not_written_to_event_log(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "ws"
            root.mkdir()
            events_path = root / ".zeroscript" / "events.jsonl"
            events = EventLog(events_path, session_id="browser-fill-test")
            browser = Mock()
            browser.fill.return_value = {"filled": True, "label": "Email", "characters": 18}
            tools = ToolRegistry(Workspace(root), PolicyBroker(), events, browser=browser)
            tools.set_profile("development")
            tools.call("browser.fill", {"label": "Email", "value": "private@example.com"}, approved=True)
            log_text = events_path.read_text(encoding="utf-8")
            self.assertNotIn("private@example.com", log_text)
            self.assertIn("omitted from local event log", log_text)

    def test_configured_extra_root_accepts_absolute_path(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "base"
            downloads = Path(td) / "Downloads"
            base.mkdir()
            downloads.mkdir()
            target = downloads / "test.txt"
            target.write_text("before", encoding="utf-8")
            events = EventLog(base / ".zeroscript" / "events.jsonl", session_id="extra-root")
            tools = ToolRegistry(Workspace(base, allowed_roots=[downloads]), PolicyBroker(), events)
            tools.set_profile("development")
            result = tools.call("file.patch", {"path": str(target), "old_text": "before", "new_text": "after"})
            self.assertEqual(target.read_text(encoding="utf-8"), "after")
            self.assertTrue(result["backup"])

    def test_list_directories_is_allowed_and_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            (root / "folder").mkdir()
            (root / "folder" / "a.txt").write_text("a", encoding="utf-8")
            result = tools.call("file.list", {"path": ".", "recursive": True, "max_depth": 2, "limit": 20})
            paths = {entry["path"] for entry in result["entries"]}
            self.assertIn("folder", paths)
            self.assertIn("folder/a.txt", paths)

    def test_patch_is_autonomous_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            (root / "a.txt").write_text("before", encoding="utf-8")
            result = tools.call("file.patch", {"path": "a.txt", "old_text": "before", "new_text": "after"})
            self.assertEqual((root / "a.txt").read_text(encoding="utf-8"), "after")
            self.assertTrue(result["backup"])
            log = (root / ".zeroscript" / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("before", log)
            self.assertNotIn("after", log)

    def test_file_write_creates_and_replaces_atomically_with_backup(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            created = tools.call("file.write", {"path": "new.txt", "content": "first"})
            self.assertTrue(created["created"])
            self.assertFalse(created["backup"])
            self.assertEqual((root / "new.txt").read_text(encoding="utf-8"), "first")
            replaced = tools.call("file.write", {"path": "new.txt", "content": "second"})
            self.assertFalse(replaced["created"])
            self.assertTrue(replaced["backup"])
            self.assertEqual(Path(replaced["backup"]).read_text(encoding="utf-8"), "first")
            self.assertEqual((root / "new.txt").read_text(encoding="utf-8"), "second")

    def test_file_write_obeys_basic_profile_approval_and_workspace_confinement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "ws"
            root.mkdir()
            tools = ToolRegistry(Workspace(root), PolicyBroker(), EventLog(root / ".zeroscript" / "events.jsonl"))
            args = {"path": "new.txt", "content": "safe"}
            self.assertEqual(tools.call("file.write", args)["status"], "approval_required")
            with self.assertRaises(WorkspaceError):
                tools.call("file.write", {"path": "../outside.txt", "content": "unsafe"}, approved=True)

    def test_file_create_never_overwrites_and_content_is_not_logged(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            created = tools.call("file.create", {"path": "new.txt", "content": "private-value"})
            self.assertTrue(created["created"])
            with self.assertRaises(WorkspaceError):
                tools.call("file.create", {"path": "new.txt", "content": "replacement"})
            self.assertEqual((root / "new.txt").read_text(encoding="utf-8"), "private-value")
            log = (root / ".zeroscript" / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("private-value", log)

    def test_policy_precedence(self):
        policy = PolicyBroker()
        policy.set_rule("workspace.write", Decision.ALLOW)
        self.assertEqual(policy.evaluate("workspace.write").decision, Decision.ALLOW)
        policy.set_rule("workspace.write", Decision.DENY)
        self.assertEqual(policy.evaluate("workspace.write").decision, Decision.DENY)

    def test_basic_profile_requires_approval_for_workspace_edits(self):
        policy = PolicyBroker()
        policy.set_profile("basic")
        self.assertEqual(policy.evaluate("workspace.read").decision, Decision.ALLOW)
        self.assertEqual(policy.evaluate("workspace.write").decision, Decision.ASK)
        with self.assertRaises(ValueError):
            policy.set_profile("unrestricted")

    def test_development_profile_allows_workspace_editing_but_not_process(self):
        policy = PolicyBroker()
        policy.set_profile("development")
        self.assertEqual(policy.evaluate("workspace.write").decision, Decision.ALLOW)
        self.assertEqual(policy.evaluate("process.exec", {"command": ["python3", "--version"]}).decision, Decision.ASK)

    def test_broad_profile_auto_allows_asked_capabilities_but_deny_wins(self):
        policy = PolicyBroker()
        policy.set_profile("broad")
        self.assertEqual(policy.evaluate("process.exec", {"command": ["python3", "--version"]}).decision, Decision.ALLOW)
        self.assertEqual(policy.evaluate("process.exec", {"shell": "powershell", "command": "Remove-Item test.tmp"}).decision, Decision.ALLOW)
        self.assertEqual(policy.evaluate("browser.control").decision, Decision.ALLOW)
        self.assertEqual(policy.evaluate("network.egress").decision, Decision.ALLOW)
        self.assertEqual(policy.evaluate("desktop.control").decision, Decision.ALLOW)
        policy.set_rule("process.exec", Decision.DENY)
        self.assertEqual(policy.evaluate("process.exec", {"command": ["python3", "--version"]}).decision, Decision.DENY)
        self.assertEqual(policy.evaluate("process.admin_exec").decision, Decision.DENY)

    def test_self_improve_runs_without_per_cycle_approval_in_all_profiles_but_deny_wins(self):
        policy = PolicyBroker()
        for profile in ("basic", "development", "broad"):
            policy.set_profile(profile)
            self.assertEqual(policy.evaluate("self_improve.run").decision, Decision.ALLOW)
        policy.set_rule("self_improve.run", Decision.DENY)
        self.assertEqual(policy.evaluate("self_improve.run").decision, Decision.DENY)

    def test_self_improve_tool_is_listed_and_runs_without_per_call_approval(self):
        with tempfile.TemporaryDirectory() as td:
            _, tools = self.make(Path(td))
            names = {tool["name"] for tool in tools.manifest()}
            self.assertIn("self_improve.run", names)
            tools.set_profile("broad")
            args = {"mode": "audit", "allow_source_upload": False}
            with patch("agent_core.improvement.improve_once", return_value={"status": "audit_complete"}) as run_cycle:
                result = tools.call("self_improve.run", args)
            self.assertEqual(result["status"], "audit_complete")
            run_cycle.assert_called_once()

    def test_events_redact_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "events.jsonl"
            EventLog(path, session_id="test").emit("x", api_key="secret", nested={"token": "hidden"})
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["data"]["api_key"], "[REDACTED]")
            self.assertEqual(record["data"]["nested"]["token"], "[REDACTED]")

    def test_process_test_requires_approval_and_runs_allowlisted_command(self):
        with tempfile.TemporaryDirectory() as td:
            _, tools = self.make(Path(td))
            args = {"command": [sys.executable, "-c", "print('ok')"]}
            self.assertEqual(tools.call("process.test", args)["status"], "approval_required")
            result = tools.call("process.test", args, approved=True)
            self.assertEqual(result["returncode"], 0)
            self.assertIn("ok", result["stdout"])

    def test_windows_terminal_command_runs_without_per_action_approval_in_broad(self):
        with tempfile.TemporaryDirectory() as td, patch.object(ProcessRunner, "WINDOWS", True):
            root, tools = self.make(Path(td))
            tools.set_profile("broad")
            runner = Mock(return_value={
                "shell": "powershell", "cwd": str(root), "returncode": 0,
                "timed_out": False, "stdout": "sensitive-output", "stderr": "",
                "stdout_truncated": False, "stderr_truncated": False,
            })
            tools.process.run_shell = runner
            args = {"shell": "powershell", "command": "Write-Output sensitive-output", "cwd": str(root)}
            result = tools.call("terminal.run", args)
            runner.assert_called_once_with(shell="powershell", command="Write-Output sensitive-output", cwd=str(root), timeout=120)
            self.assertEqual(result["stdout"], "sensitive-output")
            event_log = (root / ".zeroscript" / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("Write-Output sensitive-output", event_log)
            self.assertNotIn("sensitive-output", event_log)

    def test_windows_shell_argument_builders_do_not_use_shell_true(self):
        self.assertEqual(
            ProcessRunner.build_windows_argv("cmd", "echo hello", "C:\\Windows\\System32\\cmd.exe"),
            ["C:\\Windows\\System32\\cmd.exe", "/d", "/s", "/c", "echo hello"],
        )
        self.assertEqual(
            ProcessRunner.build_windows_argv("powershell", "Get-Location", "powershell.exe"),
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "Get-Location"],
        )
        with self.assertRaises(ProcessPolicyError):
            ProcessRunner.build_windows_argv("bash", "id", "bash")

    def test_posix_shell_argument_builder_uses_explicit_executable(self):
        self.assertEqual(ProcessRunner.build_posix_argv("bash", "printf ok", "/bin/bash"), ["/bin/bash", "-c", "printf ok"])
        self.assertEqual(ProcessRunner.build_posix_argv("pwsh", "Get-Location", "/usr/bin/pwsh"), ["/usr/bin/pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "Get-Location"])

    def test_path_refresh_merge_preserves_existing_order_and_deduplicates(self):
        merged = ProcessRunner._merge_path_values(r"C:\Tools;C:\Windows", r"c:\tools;C:\NewTool", separator=";")
        self.assertEqual(merged, r"C:\Tools;C:\Windows;C:\NewTool")

    def test_windows_terminal_invokes_power_shell_without_python_shell(self):
        with tempfile.TemporaryDirectory() as td, patch.object(ProcessRunner, "WINDOWS", True):
            completed = Mock(returncode=0, stdout="PowerShell output", stderr="")
            with patch("agent_core.process.shutil.which", return_value="C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"), patch("agent_core.process.subprocess.run", return_value=completed) as run:
                result = ProcessRunner(Path(td)).run_shell("powershell", "Get-Location", timeout=35)
            command_argv = run.call_args.args[0]
            self.assertEqual(command_argv[0], "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe")
            self.assertEqual(command_argv[-2:], ["-Command", "Get-Location"])
            self.assertFalse(run.call_args.kwargs.get("shell", False))
            self.assertEqual(run.call_args.kwargs["timeout"], 35)
            self.assertEqual(result["stdout"], "PowerShell output")

    @unittest.skipIf(ProcessRunner.WINDOWS, "this test only applies on non-Windows")
    def test_posix_terminal_requires_approval_and_runs_as_current_user(self):
        with tempfile.TemporaryDirectory() as td:
            root, tools = self.make(Path(td))
            args = {"shell": "sh", "command": "printf diag-ok", "cwd": str(root)}
            self.assertEqual(tools.call("terminal.run", args)["status"], "approval_required")
            result = tools.call("terminal.run", args, approved=True)
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["stdout"], "diag-ok")
            self.assertFalse(result["timed_out"])

    @unittest.skipIf(ProcessRunner.WINDOWS, "sudo askpass only applies on POSIX")
    def test_sudo_askpass_dialog_authorizes_then_runs_root_command_without_exposing_password(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = ProcessRunner(root)
            seen = []
            helper_contents = []
            completed = [Mock(returncode=0, stdout="", stderr=""), Mock(returncode=0, stdout="root-ok", stderr="")]

            def fake_run(argv, **kwargs):
                seen.append((argv, kwargs))
                if len(seen) == 1:
                    askpass = kwargs["env"]["SUDO_ASKPASS"]
                    helper_contents.append(Path(askpass).read_text(encoding="utf-8"))
                return completed[len(seen) - 1]

            which = {"sudo": "/usr/bin/sudo", "bash": "/bin/bash", "zenity": "/usr/bin/zenity"}
            with patch.object(ProcessRunner, "WINDOWS", False), patch.dict(os.environ, {"DISPLAY": ":99"}), \
                 patch("agent_core.process.shutil.which", side_effect=lambda name: which.get(name)), \
                 patch("agent_core.process.subprocess.run", side_effect=fake_run):
                result = runner.run_shell_as_admin("bash", "printf root-ok", cwd=str(root))

            self.assertEqual(result["stdout"], "root-ok")
            self.assertTrue(result["elevated"])
            self.assertEqual(seen[0][0], ["/usr/bin/sudo", "-A", "-p", "Infinix precisa de autorização de administrador", "-v"])
            self.assertEqual(seen[1][0], ["/usr/bin/sudo", "-n", "--", "/bin/bash", "-c", "printf root-ok"])
            self.assertIn("zenity", helper_contents[0])
            self.assertNotIn("mock-password", repr(seen) + repr(result) + "".join(helper_contents))
            self.assertFalse(Path(seen[0][1]["env"]["SUDO_ASKPASS"]).exists(), "temporary askpass helper should be deleted")

    @unittest.skipIf(ProcessRunner.WINDOWS, "sudo askpass only applies on POSIX")
    def test_cancelled_sudo_dialog_never_runs_the_privileged_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = ProcessRunner(root)
            calls = []
            which = {"sudo": "/usr/bin/sudo", "bash": "/bin/bash", "ssh-askpass": "/usr/bin/ssh-askpass"}
            with patch.object(ProcessRunner, "WINDOWS", False), patch.dict(os.environ, {"DISPLAY": ":99"}), \
                 patch("agent_core.process.shutil.which", side_effect=lambda name: which.get(name)), \
                 patch("agent_core.process.subprocess.run", side_effect=lambda argv, **kwargs: calls.append(argv) or Mock(returncode=1, stdout="", stderr="cancelled")):
                result = runner.run_shell_as_admin("bash", "touch /root/should-not-run", cwd=str(root))
            self.assertEqual(result["status"], "authorization_failed")
            self.assertEqual(len(calls), 1)
            self.assertNotIn("touch /root/should-not-run", repr(result))

    @unittest.skipIf(ProcessRunner.WINDOWS, "sudo askpass only applies on POSIX")
    def test_admin_tool_is_session_autonomous_in_broad_but_command_and_output_are_not_logged(self):
        with tempfile.TemporaryDirectory() as td, patch.object(ProcessRunner, "admin_shell_available", return_value=True):
            root, tools = self.make(Path(td))
            names = {tool["name"] for tool in tools.manifest()}
            self.assertIn("terminal.run_as_admin", names)
            args = {"shell": "bash", "command": "printf secret-root-output", "cwd": str(root)}
            self.assertEqual(tools.call("terminal.run_as_admin", args)["status"], "approval_required")
            tools.set_profile("broad")
            tools.process.run_shell_as_admin = Mock(return_value={
                "shell": "bash", "cwd": str(root), "returncode": 0, "timed_out": False,
                "elevated": True, "stdout": "secret-root-output", "stderr": "",
                "stdout_truncated": False, "stderr_truncated": False,
            })
            result = tools.call("terminal.run_as_admin", args)
            self.assertTrue(result["elevated"])
            tools.process.run_shell_as_admin.assert_called_once_with(shell="bash", command=args["command"], cwd=str(root), timeout=120)
            event_log = (root / ".zeroscript" / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(args["command"], event_log)
            self.assertNotIn("secret-root-output", event_log)
            self.assertIn('"elevated": true', event_log)


if __name__ == "__main__":
    unittest.main()
