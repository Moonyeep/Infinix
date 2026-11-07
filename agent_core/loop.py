from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .events import EventLog
from .session import SessionStore
from .tools import ToolRegistry


class AgentState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class AgentLoop:
    """Provider-agnostic observe/decide/act loop.

    Adapted from the state, max-step and duplicate-response ideas in OpenManus
    BaseAgent, with SWE-agent-style bounded observations. The policy remains
    outside the model and every tool call is revalidated by ToolRegistry.
    """

    tools: ToolRegistry
    events: EventLog
    sessions: SessionStore | None = None
    max_steps: int = 20
    max_observation: int = 12000
    state: AgentState = AgentState.IDLE
    step: int = 0
    cancelled: bool = False
    _observations: list[str] = field(default_factory=list)

    def cancel(self) -> None:
        self.cancelled = True

    def run(self, request: str, decide: Callable[[list[dict[str, Any]]], dict[str, Any]]) -> dict[str, Any]:
        if self.state != AgentState.IDLE:
            raise RuntimeError(f"cannot run from state {self.state.value}")
        session_id = self.sessions.create({"request": request}) if self.sessions else None
        if self.sessions and session_id:
            self.sessions.set_state(session_id, AgentState.RUNNING.value)
        self.state = AgentState.RUNNING
        history: list[dict[str, Any]] = [{"role": "user", "content": request}]
        self.events.emit("agent.start", session_id=session_id, request=request, max_steps=self.max_steps)
        try:
            while self.step < self.max_steps:
                if self.cancelled:
                    self.state = AgentState.CANCELLED
                    break
                self.step += 1
                proposal = decide(history)
                self.events.emit("agent.decision", session_id=session_id, step=self.step, proposal=proposal)
                if proposal.get("finish") is not None:
                    self.state = AgentState.SUCCEEDED
                    history.append({"role": "assistant", "content": str(proposal["finish"])})
                    break
                name = proposal.get("tool")
                args = proposal.get("args") or {}
                if not isinstance(name, str):
                    raise ValueError("decision must contain tool or finish")
                result = self.tools.call(name, args, approved=bool(proposal.get("approved")))
                encoded = str(result)
                if len(encoded) > self.max_observation:
                    encoded = encoded[:self.max_observation] + "...[OBSERVATION_TRUNCATED]"
                if encoded in self._observations[-2:]:
                    history.append({"role": "tool", "content": "Repeated observation; choose a different strategy."})
                else:
                    history.append({"role": "tool", "name": name, "content": encoded})
                self._observations.append(encoded)
                if isinstance(result, dict) and result.get("status") == "approval_required":
                    self.state = AgentState.WAITING_APPROVAL
                    break
                if self.sessions and session_id:
                    self.sessions.checkpoint(session_id, f"step-{self.step}", {"history": history[-3:], "tool": name, "result": result})
            else:
                self.state = AgentState.FAILED
            if self.sessions and session_id:
                self.sessions.set_state(session_id, self.state.value)
            self.events.emit("agent.finish", session_id=session_id, state=self.state.value, steps=self.step)
            return {"session_id": session_id, "state": self.state.value, "steps": self.step, "history": history}
        except Exception as exc:
            self.state = AgentState.FAILED
            if self.sessions and session_id:
                self.sessions.set_state(session_id, self.state.value)
            self.events.emit("agent.error", session_id=session_id, error=str(exc))
            raise
