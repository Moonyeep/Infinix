import unittest
import sys
import types
import threading

from unittest.mock import Mock, patch

from agent_core.browser import BrowserPolicy, BrowserProvider


class BrowserPolicyTests(unittest.TestCase):
    def test_host_allowlist(self):
        browser = BrowserProvider(BrowserPolicy(allowed_hosts=("example.com",), allow_navigation=True))
        browser._check_url("https://example.com/docs")
        with self.assertRaises(PermissionError):
            browser._check_url("https://not-example.com/")
        with self.assertRaises(PermissionError):
            browser._check_url("file:///etc/passwd")
        browser.close()

    def test_empty_allowlist_denies_navigation(self):
        browser = BrowserProvider(BrowserPolicy(allow_navigation=True))
        with self.assertRaisesRegex(PermissionError, "allowlist"):
            browser._check_url("https://example.com")
        browser.close()

    def test_credentials_and_bad_ports_are_rejected(self):
        browser = BrowserProvider(BrowserPolicy(("example.com",), allow_navigation=True))
        for url in ("https://user:pass@example.com/", "https://example.com:bad/"):
            with self.subTest(url=url), self.assertRaises(PermissionError):
                browser._check_url(url)
        browser.close()

    def test_private_destinations_blocked_unless_explicitly_enabled(self):
        for host in ("localhost", "dev.local", "127.0.0.1", "192.168.1.20", "169.254.3.2", "::1"):
            url_host = f"[{host}]" if ":" in host else host
            browser = BrowserProvider(BrowserPolicy((host,), allow_navigation=True))
            with self.subTest(host=host), self.assertRaises(PermissionError):
                browser._check_url(f"http://{url_host}/")
            browser.close()
        local = BrowserProvider(BrowserPolicy(("127.0.0.1",), allow_navigation=True, allow_private_hosts=True))
        local._check_url("http://127.0.0.1:8080/")
        local.close()

    def test_external_effects_are_disabled_by_default(self):
        browser = BrowserProvider(BrowserPolicy(("example.com",), allow_navigation=True))
        with self.assertRaisesRegex(PermissionError, "disabled"):
            browser.click("button", "Continue")
        with self.assertRaisesRegex(PermissionError, "disabled"):
            browser.fill("Email", "person@example.com")
        browser.close()

    def test_click_uses_exact_accessible_role_and_name(self):
        browser = BrowserProvider(BrowserPolicy(("example.com",), allow_navigation=True, allow_external_effects=True))
        fake_page = Mock()
        fake_page.url = "https://example.com/form"
        locator = fake_page.get_by_role.return_value
        browser._page = fake_page
        result = browser._click("button", "Save")
        fake_page.get_by_role.assert_called_once_with("button", name="Save", exact=True)
        locator.click.assert_called_once_with(timeout=5000)
        self.assertTrue(result["clicked"])
        browser.close()

    def test_fill_uses_exact_label_and_does_not_echo_value(self):
        browser = BrowserProvider(BrowserPolicy(("example.com",), allow_navigation=True, allow_external_effects=True))
        fake_page = Mock()
        fake_page.url = "https://example.com/form"
        browser._page = fake_page
        result = browser._fill("Email", "private@example.com")
        fake_page.get_by_label.assert_called_once_with("Email", exact=True)
        self.assertNotIn("private@example.com", str(result))
        browser.close()

    def test_redirect_navigation_is_checked_against_allowlist(self):
        browser = BrowserProvider(BrowserPolicy(("example.com",), allow_navigation=True))
        route = Mock()
        route.request.is_navigation_request.return_value = True
        route.request.url = "https://outside.example/redirect"
        browser._guard_navigation(route)
        route.abort.assert_called_once_with()
        route.continue_.assert_not_called()
        browser.close()

    def test_playwright_calls_are_serialized_on_one_worker_thread(self):
        thread_ids = []
        fake_page = Mock()
        fake_page.url = "https://example.com/"
        fake_page.title.return_value = "Example"
        fake_page.goto.side_effect = lambda url, **kwargs: (thread_ids.append(threading.get_ident()) or Mock(status=200))
        fake_context = Mock()
        fake_context.new_page.return_value = fake_page
        fake_browser = Mock()
        fake_browser.new_context.return_value = fake_context
        fake_browser.chromium.launch.side_effect = lambda **kwargs: (thread_ids.append(threading.get_ident()) or fake_browser)
        fake_playwright = Mock()
        fake_playwright.chromium.launch.side_effect = lambda **kwargs: (thread_ids.append(threading.get_ident()) or fake_browser)
        fake_api = types.ModuleType("playwright.sync_api")
        fake_api.sync_playwright = Mock(return_value=Mock(start=Mock(return_value=fake_playwright)))
        fake_package = types.ModuleType("playwright")
        fake_package.sync_api = fake_api
        browser = BrowserProvider(BrowserPolicy(("example.com",), allow_navigation=True))
        with patch.dict(sys.modules, {"playwright": fake_package, "playwright.sync_api": fake_api}):
            browser.navigate("https://example.com/")
        self.assertGreaterEqual(len(thread_ids), 2)
        self.assertEqual(len(set(thread_ids)), 1)
        browser.close()


if __name__ == "__main__":
    unittest.main()
