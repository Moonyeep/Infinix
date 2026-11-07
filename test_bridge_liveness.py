import re
import unittest
from pathlib import Path


class BridgeLivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).parent / "bridge.py").read_text(encoding="utf-8")

    def test_local_agent_call_does_not_await_tool_in_websocket_reader(self):
        branch = re.search(
            r'elif mtype == "agent_call_tool":(?P<body>[\s\S]*?)\n\s*elif mtype == "call_tool":',
            self.source,
        )
        self.assertIsNotNone(branch, "handler should keep an agent_call_tool branch")
        body = branch.group("body")
        self.assertIn("session_id = msg.get(\"session_id\")", body)
        self.assertIn("asyncio.create_task(run_agent_tool_task(ws, name, args, approved, rid, session_id))", body)
        self.assertNotIn("await asyncio.to_thread(safe_agent_call", body)

    def test_long_local_tool_runs_in_worker_thread_and_returns_result(self):
        helper = re.search(
            r'async def run_agent_tool_task\([\s\S]*?(?=\n\nasync def broadcast_status\()',
            self.source,
        )
        self.assertIsNotNone(helper, "background task helper should exist")
        body = helper.group(0)
        self.assertIn("await asyncio.to_thread(safe_agent_call, name, args, approved, session_id)", body)
        self.assertIn('"type": "agent_tool_result"', body)
        self.assertIn('"id": rid', body)

    def test_bridge_normalizes_json_string_arguments_before_logging_keys(self):
        self.assertIn("def _coerce_object(value, field=\"arguments\"):", self.source)
        self.assertIn("decoded = json.loads(value)", self.source)
        self.assertIn("_coerce_object(msg.get(\"arguments\"))", self.source)
        self.assertIn('kind": "invalid_arguments"', self.source)


if __name__ == "__main__":
    unittest.main()
