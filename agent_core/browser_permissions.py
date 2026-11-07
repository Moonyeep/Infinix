from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class PermissionMode(str, Enum):
    ASK = "ask"
    AUTO = "auto"


class SiteRule(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    BLOCK = "block"


@dataclass(frozen=True)
class BrowserQuestion:
    url: str
    effect: str
    sensitive: bool = False

    @property
    def site(self) -> str | None:
        return urlparse(self.url).hostname


@dataclass(frozen=True)
class BrowserDecision:
    decision: str
    site: str | None
    reason: str
    can_remember: bool


class BrowserPermissions:
    """Per-site browser policy; model output cannot change these rules."""

    WRITE_EFFECTS = {"submit", "send", "delete", "upload", "purchase", "credential"}

    def __init__(self, rules: dict[str, SiteRule] | None = None) -> None:
        self.rules = dict(rules or {})

    def decide(self, mode: PermissionMode, question: BrowserQuestion) -> BrowserDecision:
        site = question.site
        if not site:
            return BrowserDecision("ask", None, "url has no host", False)
        rule = self.rules.get(site)
        if rule == SiteRule.BLOCK:
            return BrowserDecision("block", site, "site is blocked by user policy", False)
        if question.sensitive or question.effect in self.WRITE_EFFECTS:
            if rule == SiteRule.ALLOW and not question.sensitive:
                return BrowserDecision("allow", site, "site allow rule", True)
            return BrowserDecision("ask", site, "sensitive or externally visible action", rule != SiteRule.ASK)
        if rule == SiteRule.ALLOW:
            return BrowserDecision("allow", site, "site allow rule", True)
        if rule == SiteRule.ASK:
            return BrowserDecision("ask", site, "site ask rule", False)
        return BrowserDecision("allow", site, "read-only browser action", True)

    def set_rule(self, site: str, rule: SiteRule) -> None:
        if not site or "." not in site:
            raise ValueError("site must be a hostname")
        self.rules[site.lower()] = rule
