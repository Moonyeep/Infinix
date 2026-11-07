import hashlib
import tempfile
import unittest
from pathlib import Path

from agent_core.team_bus import TeamMessageBus


def tid(label):
    return "task_" + hashlib.sha256(label.encode("utf-8")).hexdigest()


class TeamMessageBusTests(unittest.TestCase):
    def setUp(self):
        self.bus = TeamMessageBus()
        self.root_task = tid("root-worker")
        self.grandchild = tid("grandchild")
        self.sibling = tid("sibling")
        self.assertTrue(self.bus.register(
            task_id=self.root_task, session_id="tab:101", parent_session_id="tab:1",
            provider="gemini", depth=1, allow_children=True,
        )["ok"])
        self.assertTrue(self.bus.update(session_id="tab:101", task_id=self.root_task, state="running")["ok"])
        self.assertTrue(self.bus.register(
            task_id=self.grandchild, session_id="tab:102", parent_session_id="tab:101",
            parent_task_id=self.root_task, provider="qwen", depth=2,
        )["ok"])
        self.assertTrue(self.bus.register(
            task_id=self.sibling, session_id="tab:201", parent_session_id="tab:2",
            provider="deepseek", depth=1,
        )["ok"])

    def test_bridge_routes_messages_both_directions_with_monotonic_cursors(self):
        sent = self.bus.send_message(session_id="tab:1", target_task_id=self.root_task, message_id="message-0001", text="status please")
        self.assertTrue(sent["ok"])
        self.assertEqual(sent["sequence"], 1)
        worker_inbox = self.bus.inbox(session_id="tab:101")
        self.assertEqual(worker_inbox["messages"][0]["direction"], "from_supervisor")
        self.assertEqual(worker_inbox["messages"][0]["text"], "status please")
        reply = self.bus.send_message(session_id="tab:101", target_task_id="supervisor", message_id="message-0002", text="evidence found")
        self.assertEqual(reply["delivered_to"], "supervisor")
        supervisor_inbox = self.bus.inbox(session_id="tab:1")
        self.assertEqual(supervisor_inbox["messages"][0]["sequence"], 1)
        self.assertEqual(supervisor_inbox["messages"][0]["direction"], "from_child")
        self.assertEqual(self.bus.inbox(session_id="tab:1", after_sequence=1)["messages"], [])

    def test_retries_are_idempotent_and_message_id_cannot_be_retargeted(self):
        first = self.bus.send_message(session_id="tab:1", target_task_id=self.root_task, message_id="message-repeat", text="same task")
        again = self.bus.send_message(session_id="tab:1", target_task_id=self.root_task, message_id="message-repeat", text="same task")
        self.assertEqual(first["sequence"], again["sequence"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(len(self.bus.inbox(session_id="tab:101")["messages"]), 1)
        self.assertFalse(self.bus.send_message(session_id="tab:1", target_task_id=self.sibling, message_id="message-repeat", text="retarget")["ok"])

    def test_rejects_sibling_and_unrelated_session_access(self):
        self.assertFalse(self.bus.send_message(session_id="tab:201", target_task_id=self.grandchild, message_id="message-sibling", text="no")["ok"])
        self.assertFalse(self.bus.send_message(session_id="tab:999", target_task_id=self.root_task, message_id="message-stranger", text="no")["ok"])
        self.assertFalse(self.bus.update(session_id="tab:999", task_id=self.root_task, state="running")["ok"])

    def test_startup_state_and_authorized_depth_are_enforced(self):
        self.assertEqual(self.bus.tasks[self.grandchild]["state"], "starting")
        self.assertFalse(self.bus.update(session_id="tab:101", task_id=self.root_task, state="starting")["ok"])
        no_authority = tid("no-authority")
        self.assertTrue(self.bus.register(task_id=no_authority, session_id="tab:300", parent_session_id="tab:3", depth=1)["ok"])
        unauthorized = self.bus.register(task_id=tid("forbidden"), session_id="tab:301", parent_session_id="tab:300", parent_task_id=no_authority, depth=2)
        self.assertFalse(unauthorized["ok"])
        too_deep = self.bus.register(task_id=tid("fourth-level"), session_id="tab:400", parent_session_id="tab:102", parent_task_id=self.grandchild, depth=4)
        self.assertFalse(too_deep["ok"])

    def test_capacity_retires_old_unreferenced_terminal_tasks(self):
        bus = TeamMessageBus()
        first = ""
        for index in range(257):
            task_id = tid(f"retention-{index}")
            if index == 0:
                first = task_id
            session_id = f"tab:{10000 + index}"
            registered = bus.register(task_id=task_id, session_id=session_id,
                                      parent_session_id="tab:9000", depth=1)
            self.assertTrue(registered["ok"], registered)
            bus.update(session_id=session_id, task_id=task_id, state="completed")
        self.assertEqual(len(bus.tasks), 256)
        self.assertNotIn(first, bus.tasks)
        self.assertNotIn("tab:10000", bus.session_tasks)

    def test_terminal_parent_cannot_spawn_child(self):
        self.bus.update(session_id="tab:101", task_id=self.root_task, state="completed")
        result = self.bus.register(
            task_id=tid("late-child"), session_id="tab:103", parent_session_id="tab:101",
            parent_task_id=self.root_task, provider="qwen", depth=2,
        )
        self.assertFalse(result["ok"])
        self.assertIn("depth/state", result["error"])

    def test_message_id_retry_with_changed_content_is_rejected(self):
        first = self.bus.send_message(session_id="tab:1", target_task_id=self.root_task,
                                      message_id="message-collision", text="original")
        self.assertTrue(first["ok"])
        collision = self.bus.send_message(session_id="tab:1", target_task_id=self.root_task,
                                          message_id="message-collision", text="different payload")
        self.assertFalse(collision["ok"])
        self.assertIn("different sender or content", collision["error"])
        inbox = self.bus.inbox(session_id="tab:101")["messages"]
        self.assertEqual([item["text"] for item in inbox], ["original"])

    def test_state_survives_bridge_restart_without_duplicate_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".zeroscript" / "team-bus.json"
            bus = TeamMessageBus(path)
            task_id = tid("persist")
            self.assertTrue(bus.register(task_id=task_id, session_id="tab:501", parent_session_id="tab:5", depth=1)["ok"])
            bus.update(session_id="tab:501", task_id=task_id, state="running")
            bus.send_message(session_id="tab:5", target_task_id=task_id, message_id="message-persist", text="kept")
            restarted = TeamMessageBus(path)
            inbox = restarted.inbox(session_id="tab:501")
            self.assertEqual(inbox["messages"][0]["text"], "kept")
            retry = restarted.send_message(session_id="tab:5", target_task_id=task_id, message_id="message-persist", text="kept")
            self.assertTrue(retry["duplicate"])
            self.assertEqual(restarted.inbox(session_id="tab:501")["messages"][0]["sequence"], 1)


if __name__ == "__main__":
    unittest.main()
