import tempfile
import unittest
from pathlib import Path

from agent_core.events import EventLog
from agent_core.loop import AgentLoop, AgentState
from agent_core.policy import PolicyBroker
from agent_core.session import SessionStore
from agent_core.tools import ToolRegistry
from agent_core.workspace import Workspace


class LoopTests(unittest.TestCase):
    def make(self, td):
        root = Path(td)
        events = EventLog(root / "events.jsonl", session_id="loop-test")
        sessions = SessionStore(root / "state.db")
        tools = ToolRegistry(Workspace(root), PolicyBroker(), events)
        tools.set_profile("development")
        return AgentLoop(tools, events, sessions=sessions, max_steps=3), sessions

    def test_finish_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            loop, sessions = self.make(td)
            result = loop.run("finish", lambda history: {"finish": "done"})
            self.assertEqual(result["state"], AgentState.SUCCEEDED.value)
            self.assertEqual(sessions.get(result["session_id"])["state"], AgentState.SUCCEEDED.value)

    def test_write_runs_autonomously_inside_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            loop, _ = self.make(td)
            result = loop.run("write", lambda history: {"tool": "file.patch", "args": {"path": "a.txt", "old_text": "", "new_text": "x"}})
            self.assertEqual((Path(td) / "a.txt").read_text(encoding="utf-8"), "x")
            self.assertNotEqual(result["state"], AgentState.WAITING_APPROVAL.value)


if __name__ == "__main__":
    unittest.main()
