from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

from agent_core.diagnostics import EndpointDiagnostics
from agent_core.events import EventLog
from agent_core.policy import PolicyBroker
from agent_core.tools import ToolRegistry
from agent_core.workspace import Workspace


class EndpointDiagnosticsTests(unittest.TestCase):
    def make_tools(self, root: Path) -> tuple[ToolRegistry, Path]:
        events_path = root / ".zeroscript" / "events.jsonl"
        tools = ToolRegistry(Workspace(root), PolicyBroker(), EventLog(events_path, session_id="diagnostics-test"))
        return tools, events_path

    def test_system_info_is_read_only_and_available_in_basic_profile(self):
        with tempfile.TemporaryDirectory() as td:
            tools, _ = self.make_tools(Path(td))
            result = tools.call("diagnostics.system_info", {})
            self.assertIn(result["platform"], {"linux", "windows", "darwin"})
            self.assertIn("architecture", result)
            self.assertIn("bridge_is_admin_or_root", result)

    def test_expected_diagnostic_tools_are_in_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            tools, _ = self.make_tools(Path(td))
            names = {item["name"] for item in tools.manifest()}
            self.assertTrue({
                "diagnostics.system_info", "diagnostics.processes", "diagnostics.services",
                "diagnostics.network", "diagnostics.security_status", "diagnostics.recent_events",
                "diagnostics.startup_items", "diagnostics.windows_account_snapshot",
                "diagnostics.tools_inventory", "diagnostics.action", "terminal.run",
            }.issubset(names))

    def test_windows_account_snapshot_is_gracefully_unsupported_on_non_windows(self):
        with tempfile.TemporaryDirectory() as td:
            result = EndpointDiagnostics(ToolRegistry(Workspace(Path(td)), PolicyBroker(), EventLog(Path(td) / "events.jsonl")).process).windows_account_snapshot()
            if result["platform"] != "windows":
                self.assertFalse(result["available"])
                self.assertIn("específica de Windows", result["error"])

    def test_windows_account_snapshot_uses_read_only_queries_and_group_sid(self):
        with tempfile.TemporaryDirectory() as td:
            diagnostics = EndpointDiagnostics(ToolRegistry(Workspace(Path(td)), PolicyBroker(), EventLog(Path(td) / "events.jsonl")).process)
            diagnostics._windows_ps = Mock(return_value={"operation": "windows_account_snapshot", "platform": "windows", "returncode": 0})
            with patch.object(EndpointDiagnostics, "system", new_callable=PropertyMock, return_value="windows"):
                diagnostics.windows_account_snapshot()
            script = diagnostics._windows_ps.call_args.args[1]
            self.assertIn("Get-LocalUser", script)
            self.assertIn("Get-LocalGroup -SID 'S-1-5-32-544'", script)
            self.assertIn("Get-LocalGroupMember -Group $group", script)
            self.assertIn("S-1-5-32-544", script)
            self.assertIn("Win32_UserProfile", script)
            self.assertIn("DisableCMD", script)
            self.assertIn("Image File Execution Options\\cmd.exe", script)
            for destructive in ("Remove-LocalUser", "Remove-CimInstance", "Remove-Item", "Set-ItemProperty"):
                self.assertNotIn(destructive, script)

    def test_action_runs_without_per_action_approval_in_broad_profile(self):
        with tempfile.TemporaryDirectory() as td:
            tools, _ = self.make_tools(Path(td))
            tools.set_profile("broad")
            tools.diagnostics.run_action = Mock(return_value={"operation": "action:test", "platform": "linux"})
            args = {"action": "windows_sfc_scannow"}
            result = tools.call("diagnostics.action", args)
            self.assertEqual(result["operation"], "action:test")
            tools.diagnostics.run_action.assert_called_once_with(action="windows_sfc_scannow", target=None, sid=None)

    def test_basic_and_development_profiles_keep_per_action_approval(self):
        for profile in ("basic", "development"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as td:
                tools, _ = self.make_tools(Path(td))
                tools.set_profile(profile)
                tools.diagnostics.run_action = Mock(return_value={"operation": "action:test", "platform": "windows"})
                args = {"action": "windows_sfc_scannow"}
                result = tools.call("diagnostics.action", args)
                self.assertEqual(result["status"], "approval_required")
                tools.diagnostics.run_action.assert_not_called()
                approved = tools.call("diagnostics.action", args, approved=True)
                self.assertEqual(approved["operation"], "action:test")
                tools.diagnostics.run_action.assert_called_once_with(action="windows_sfc_scannow", target=None, sid=None)

    def test_account_disable_runs_autonomously_in_confirmed_broad_profile_and_redacts_sid_from_log(self):
        with tempfile.TemporaryDirectory() as td:
            tools, events_path = self.make_tools(Path(td))
            tools.set_profile("broad")
            tools.diagnostics.run_action = Mock(return_value={"operation": "action:test", "platform": "windows"})
            sid = "S-1-5-21-111-222-333-1001"
            args = {"action": "windows_disable_local_account", "sid": sid}
            result = tools.call("diagnostics.action", args)
            self.assertEqual(result["operation"], "action:test")
            tools.diagnostics.run_action.assert_called_once_with(action="windows_disable_local_account", target=None, sid=sid)
            log = events_path.read_text(encoding="utf-8")
            self.assertNotIn(sid, log)

    def test_windows_disable_account_has_sid_and_lockout_guardrails(self):
        with tempfile.TemporaryDirectory() as td:
            diagnostics = EndpointDiagnostics(ToolRegistry(Workspace(Path(td)), PolicyBroker(), EventLog(Path(td) / "events.jsonl")).process)
            diagnostics.is_admin = Mock(return_value=True)
            diagnostics._windows_ps = Mock(return_value={"operation": "action:windows_disable_local_account", "platform": "windows"})
            sid = "S-1-5-21-111-222-333-1001"
            with patch.object(EndpointDiagnostics, "system", new_callable=PropertyMock, return_value="windows"):
                result = diagnostics.run_action("windows_disable_local_account", sid=sid)
            self.assertEqual(result["mode"], "remediation")
            script = diagnostics._windows_ps.call_args.args[1]
            self.assertIn(f"$targetSid='{sid}'", script)
            self.assertIn("$currentSid", script)
            self.assertIn("$otherEnabledLocalAdmins -lt 1", script)
            self.assertIn("Disable-LocalUser", script)
            self.assertIn("Existing sessions are not terminated", script)
            self.assertNotIn("Remove-LocalUser", script)

    def test_windows_disable_account_rejects_bad_sid_and_builtin_admin(self):
        with tempfile.TemporaryDirectory() as td:
            diagnostics = EndpointDiagnostics(ToolRegistry(Workspace(Path(td)), PolicyBroker(), EventLog(Path(td) / "events.jsonl")).process)
            with patch.object(EndpointDiagnostics, "system", new_callable=PropertyMock, return_value="windows"):
                malformed = diagnostics.run_action("windows_disable_local_account", sid="someone; Remove-LocalUser")
                builtin = diagnostics.run_action("windows_disable_local_account", sid="S-1-5-21-111-222-333-500")
            self.assertEqual(malformed["status"], "invalid_sid")
            self.assertEqual(builtin["status"], "protected_target")

    def test_action_target_is_not_written_to_event_log(self):
        with tempfile.TemporaryDirectory() as td:
            tools, events_path = self.make_tools(Path(td))
            tools.set_profile("development")
            tools.diagnostics.run_action = Mock(return_value={"operation": "action:test", "platform": "linux", "returncode": 0, "stdout": "private-scan-output"})
            target = "/home/person/private-folder"
            tools.call("diagnostics.action", {"action": "linux_clamav_scan", "target": target}, approved=True)
            log = events_path.read_text(encoding="utf-8")
            self.assertNotIn(target, log)
            self.assertNotIn("private-scan-output", log)
            records = [json.loads(line) for line in log.splitlines()]
            finish = next(item for item in records if item["event"] == "tool.finish")
            self.assertEqual(finish["data"]["result"]["stdout_chars"], len("private-scan-output"))

    def test_recent_events_bounds_user_supplied_limits(self):
        with tempfile.TemporaryDirectory() as td:
            diagnostics = EndpointDiagnostics(ToolRegistry(Workspace(Path(td)), PolicyBroker(), EventLog(Path(td) / "events.jsonl")).process)
            diagnostics._windows_ps = Mock(return_value={"operation": "recent_events", "platform": "windows"})
            with patch.object(EndpointDiagnostics, "system", new_callable=PropertyMock, return_value="windows"):
                diagnostics.recent_events("System", limit=100000, hours=100000)
            script = diagnostics._windows_ps.call_args.args[1]
            self.assertIn("-MaxEvents 50", script)
            self.assertIn("AddHours(-72)", script)

    def test_posix_storage_and_process_checks_are_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            diagnostics = EndpointDiagnostics(ToolRegistry(Workspace(Path(td)), PolicyBroker(), EventLog(Path(td) / "events.jsonl")).process)
            if diagnostics.system == "linux":
                processes = diagnostics.processes(limit=3)
                self.assertEqual(processes["operation"], "processes")
                self.assertLessEqual(len(processes["stdout"].splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
