import tempfile
import unittest
from pathlib import Path

from agent_core.session import SessionStore


class SessionTests(unittest.TestCase):
    def test_session_checkpoint_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(Path(td) / "state.db")
            sid = store.create({"task": "demo"})
            store.set_state(sid, "RUNNING")
            store.checkpoint(sid, "before-edit", {"files": ["a.txt"], "step": 1})
            self.assertEqual(store.get(sid)["state"], "RUNNING")
            self.assertEqual(store.latest_checkpoint(sid)["payload"]["step"], 1)
            # Windows cannot remove a temporary directory while SQLite handles
            # remain open; every SessionStore operation must close its connection.
            store.path.unlink()
            self.assertFalse(store.path.exists())


if __name__ == "__main__":
    unittest.main()
