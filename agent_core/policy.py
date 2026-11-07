from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str
    capability: str


class PolicyBroker:
    """Profile-aware policy: explicit deny always wins; broad grants the remaining asks."""

    def __init__(self) -> None:
        self._deny: set[str] = set()
        self.profile = "basic"
        # Basic/development retain action-level approvals. The double-confirmed
        # broad profile grants these capabilities for the session; explicit deny
        # rules still win. Workspace APIs remain confined by Workspace roots.
        self._ask: set[str] = {"process.exec", "process.admin_exec", "browser.control", "desktop.control", "network.egress", "network.http", "network.scan", "data.transform", "workspace.write", "diagnostics.action"}
        self._allow: set[str] = {"workspace.read", "diagnostics.read"}

    def set_profile(self, profile: str) -> str:
        if profile not in {"basic", "development", "broad"}:
            raise ValueError("profile must be basic, development, or broad")
        self.profile = profile
        if "workspace.write" not in self._deny:
            self._ask.discard("workspace.write")
            self._allow.discard("workspace.write")
            (self._ask if profile == "basic" else self._allow).add("workspace.write")
        return self.profile

    def set_rule(self, capability: str, decision: Decision) -> None:
        self._deny.discard(capability)
        self._ask.discard(capability)
        self._allow.discard(capability)
        {Decision.DENY: self._deny, Decision.ASK: self._ask, Decision.ALLOW: self._allow}[decision].add(capability)

    def evaluate(self, capability: str, args: dict[str, Any] | None = None) -> PolicyResult:
        if capability in self._deny:
            return PolicyResult(Decision.DENY, "blocked by deny rule", capability)
        if capability == "process.admin_exec" and "process.exec" in self._deny:
            return PolicyResult(Decision.DENY, "blocked by process.exec deny rule", capability)
        if capability == "self_improve.run":
            return PolicyResult(Decision.ALLOW, "bounded self-improvement tool runs without per-cycle approval; deny rules still apply", capability)
        if capability == "workspace.write" and self.profile != "basic":
            return PolicyResult(Decision.ALLOW, f"workspace changes allowed in {self.profile} profile", capability)
        if self.profile == "broad" and capability in self._ask:
            return PolicyResult(Decision.ALLOW, "authorized for this session by the double-confirmed broad profile", capability)
        if capability in self._ask:
            return PolicyResult(Decision.ASK, "human approval required", capability)
        if capability in self._allow:
            return PolicyResult(Decision.ALLOW, "matched allow rule", capability)
        return PolicyResult(Decision.DENY, "no rule exists for capability", capability)
