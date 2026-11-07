from __future__ import annotations

import ipaddress
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse


@dataclass(frozen=True)
class BrowserPolicy:
    allowed_hosts: tuple[str, ...] = ()
    allow_navigation: bool = False
    allow_external_effects: bool = False
    allow_private_hosts: bool = False


class BrowserUnavailable(RuntimeError):
    pass


class BrowserProvider:
    """Optional isolated Playwright browser; never attaches to a personal profile."""

    def __init__(self, policy: BrowserPolicy) -> None:
        self.policy = policy
        self._browser = None
        self._context = None
        self._page = None
        self._pw = None
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zs-playwright")
        self._state_lock = threading.Lock()

    def _run(self, fn: Callable[..., Any], *args: Any) -> Any:
        with self._state_lock:
            if self._closed:
                raise BrowserUnavailable("browser provider is closed")
            future = self._executor.submit(fn, *args)
        return future.result()

    def _check_url(self, url: str) -> None:
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").rstrip(".").lower()
            # Accessing .port also validates malformed port strings.
            _ = parsed.port
        except (TypeError, ValueError) as exc:
            raise PermissionError("invalid browser URL") from exc
        if parsed.scheme.lower() not in {"http", "https"}:
            raise PermissionError("browser accepts only http/https URLs")
        if not host or parsed.username is not None or parsed.password is not None:
            raise PermissionError("URL must have a host and must not contain credentials")
        allowed = {h.strip().rstrip(".").lower() for h in self.policy.allowed_hosts if h.strip()}
        if not self.policy.allow_navigation or not allowed:
            raise PermissionError("navigation is disabled until an explicit host allowlist is configured")
        if host not in allowed:
            raise PermissionError("host is not allowlisted")
        if not self.policy.allow_private_hosts:
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                raise PermissionError("local/private browser destinations are blocked by default")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified):
                raise PermissionError("private or special-use IP destinations are blocked by default")

    def start(self) -> None:
        self._run(self._start)

    def _start(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailable("install the optional Playwright dependency to enable browser tools") from exc
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            # An explicit fresh context keeps cookies/storage isolated from the
            # user's everyday Chrome profile and does not accept file downloads.
            self._context = self._browser.new_context(accept_downloads=False)
            self._context.route("**/*", self._guard_navigation)
            self._page = self._context.new_page()
        except Exception:
            self._close()
            raise

    def _guard_navigation(self, route: Any) -> None:
        request = route.request
        if request.is_navigation_request():
            try:
                self._check_url(request.url)
            except PermissionError:
                route.abort()
                return
        route.continue_()

    def navigate(self, url: str) -> dict[str, Any]:
        return self._run(self._navigate, url)

    def _navigate(self, url: str) -> dict[str, Any]:
        self._check_url(url)
        self._start()
        response = self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Also validate the final URL in case navigation completed without the
        # route guard observing a redirect (for example, due to engine changes).
        self._check_url(self._page.url)
        return {"url": self._page.url, "status": response.status if response else None, "title": self._page.title()}

    def snapshot(self) -> dict[str, Any]:
        return self._run(self._snapshot)

    def _snapshot(self) -> dict[str, Any]:
        if self._page is None:
            raise BrowserUnavailable("browser provider is not started")
        self._check_url(self._page.url)
        return {"url": self._page.url, "title": self._page.title(), "text": self._page.locator("body").inner_text(timeout=5000)[:12000]}

    def click(self, role: str, name: str) -> dict[str, Any]:
        return self._run(self._click, role, name)

    def _click(self, role: str, name: str) -> dict[str, Any]:
        if not self.policy.allow_external_effects:
            raise PermissionError("browser clicks are disabled; explicitly enable ZS_BROWSER_ALLOW_EXTERNAL_EFFECTS=1 first")
        self._require_page()
        if role not in {"button", "link", "checkbox", "radio", "tab", "menuitem", "option", "switch"}:
            raise ValueError("unsupported accessible role")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("provide an exact accessible name (1-200 characters)")
        self._page.get_by_role(role, name=name, exact=True).click(timeout=5000)
        return {"clicked": True, "role": role, "name": name, "url": self._page.url}

    def fill(self, label: str, value: str) -> dict[str, Any]:
        return self._run(self._fill, label, value)

    def _fill(self, label: str, value: str) -> dict[str, Any]:
        if not self.policy.allow_external_effects:
            raise PermissionError("form filling is disabled; explicitly enable ZS_BROWSER_ALLOW_EXTERNAL_EFFECTS=1 first")
        self._require_page()
        if not isinstance(label, str) or not label.strip() or len(label) > 200:
            raise ValueError("provide an exact accessible field label (1-200 characters)")
        if not isinstance(value, str) or len(value) > 4000:
            raise ValueError("form value must be text of at most 4000 characters")
        self._page.get_by_label(label, exact=True).fill(value, timeout=5000)
        return {"filled": True, "label": label, "characters": len(value)}

    def _require_page(self) -> None:
        if self._page is None:
            raise BrowserUnavailable("browser provider is not started")
        self._check_url(self._page.url)

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
        try:
            self._executor.submit(self._close).result()
        finally:
            with self._state_lock:
                self._closed = True
            self._executor.shutdown(wait=True, cancel_futures=True)

    def _close(self) -> None:
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._context = self._page = self._browser = self._pw = None
