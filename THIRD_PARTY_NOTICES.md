# Third-party notices

The Infinix Agent core contains original code informed by and adapted from interfaces and implementation patterns in the following open-source projects. No proprietary Claude Code or OpenAI CUA source code is included.

## OpenManus

Repository: https://github.com/FoundationAgents/OpenManus
License: MIT. The local reference checkout is pinned under `reference-agents/openmanus/`. The Infinix `AgentLoop` adapts the ideas of explicit agent state, bounded steps, duplicate/stuck detection and tool collection. It is rewritten against the Python standard library and Infinix's PolicyBroker; it is not a verbatim copy of `app/agent/base.py`.

## SWE-agent

Repository: https://github.com/SWE-agent/SWE-agent
License: MIT. The local reference checkout is pinned under `reference-agents/swe-agent/`. The Infinix loop adapts bounded observations and explicit feedback for repeated or oversized tool results. SWE-agent's execution environment and dependencies are not embedded.

## BrowserGym

Repository: https://github.com/ServiceNow/BrowserGym
License: Apache-2.0. The local reference checkout is pinned under `reference-agents/browsergym/`. The Infinix browser adapter follows the ideas of an explicit provider, allowlisted actions and observation snapshots. BrowserGym code is not bundled into the runtime.

## OpenClaw, OpenHands and WebArena

Repositories:

- https://github.com/openclaw/openclaw — MIT
- https://github.com/OpenHands/OpenHands — MIT
- https://github.com/web-arena-x/webarena — Apache-2.0

These projects remain reference checkouts for gateway/session/workspace, isolated execution and evaluation patterns. Their licenses and original files are preserved in the reference directory. Any future copied substantial code must carry the applicable license text and attribution into the distributed package.

## Nanobrowser

Repository: https://github.com/nanobrowser/nanobrowser
License: Apache-2.0. The Infinix browser work uses its documented patterns for side-panel sessions, Ask/Auto permissions, per-site rules, confirmation of irreversible actions and takeover for credentials/CAPTCHA. The source checkout is under `reference-browser-agents/nanobrowser/`; the distributed Infinix implementation is an independent adaptation.

## AIPex

Repository: https://github.com/AIPexStudio/AIPex
License: MIT. The Infinix browser work uses its documented local daemon/WebSocket shape, stable element identifiers, DOM-before-vision strategy and tool registry ideas. The source checkout is under `reference-browser-agents/aipex/`; `core/dom_snapshot.js` is a small independent implementation of the stable-ID observation/action contract, not a copied bundle.
