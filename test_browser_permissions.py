import unittest

from agent_core.browser_permissions import BrowserPermissions, BrowserQuestion, PermissionMode, SiteRule


class BrowserPermissionTests(unittest.TestCase):
    def test_reads_are_allowed_but_sensitive_actions_ask(self):
        policy = BrowserPermissions()
        self.assertEqual(policy.decide(PermissionMode.ASK, BrowserQuestion("https://example.com", "read")).decision, "allow")
        self.assertEqual(policy.decide(PermissionMode.AUTO, BrowserQuestion("https://example.com", "submit")).decision, "ask")

    def test_block_rule_wins(self):
        policy = BrowserPermissions({"example.com": SiteRule.BLOCK})
        self.assertEqual(policy.decide(PermissionMode.AUTO, BrowserQuestion("https://example.com", "read")).decision, "block")

    def test_allow_does_not_bypass_sensitive(self):
        policy = BrowserPermissions({"example.com": SiteRule.ALLOW})
        self.assertEqual(policy.decide(PermissionMode.AUTO, BrowserQuestion("https://example.com", "credential", sensitive=True)).decision, "ask")


if __name__ == "__main__":
    unittest.main()
