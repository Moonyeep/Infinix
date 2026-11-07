# Infinix — Local Autonomous Agent for Windows and Linux

> **⚠️ Project Status:** ABANDONED / BASE FOR COMMUNITY. This project is no longer actively maintained by the original creator. The codebase is released as an open-source foundation for anyone to fork, improve, modify, or build upon. The only requirement: your derivative work must also remain free and open-source (GPL-3.0).

> **Original Creator:** Moonyeep - Built with Manus AI, based on ZeroScript architecture

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)
![Status](https://img.shields.io/badge/status-abandoned%20(base%20for%20community)-red)

**Infinix** is a local autonomous AI agent for Windows and Linux, controlled through supported browser-based AI chats. Its local bridge provides endpoint diagnostics, workspace tools, browser automation, shell access under a selectable capability profile, and hierarchical multi-agent delegation. No separate model API key is required for browser providers.

## 📢 About This Project

This project was created by **Moonyeep** using **Manus AI**, built upon the **ZeroScript** architecture. The original creator has abandoned this project and is releasing it as an open-source base for the community.

**Why release this?**
- The project works but needs significant improvements
- Looking for capable developers to take this base and make it better
- Fork it, modify it, rebuild it - do whatever you want
- **Only requirement:** Your derivative work must remain FREE and OPEN-SOURCE (GPL-3.0)
- No commercial use without keeping it open-source

Roblox Studio is an optional integration. When enabled, Infinix can also control Studio through its MCP server; the general local agent does not require Roblox Studio.

Eight AI providers are supported: **DeepSeek** (chat.deepseek.com, recommended), **ChatGPT** (chatgpt.com), **Google Gemini** (gemini.google.com), **Kimi** (kimi.ai, Moonshot AI), **GLM** (chat.z.ai, Z.ai), **Qwen** (chat.qwen.ai), **Arena** (arena.ai, a multi-model playground) and **Meta AI** (meta.ai). On ChatGPT, screenshots and image input are turned off on purpose: the free tier limits files and images on a separate quota from messages, so vision would only work part of the day. Gemini and Kimi can be unstable: Gemini tends to stop using the Roblox tools in long sessions, and Kimi sometimes uses its own native tools instead of the Roblox commands. On Arena, use **Direct** mode (Infinix only supports Direct; it blocks Start in Battle / Side-by-Side / Agent modes). DeepSeek is the recommended provider.

> 💬 **Discord community:** [Join here](https://discord.gg/9aNyZsMWcb) for help and discussions.

> *Also known as: Free Claude Code alternative, Free Codex alternative, OpenClaw without API key, Infinix Roblox, Infinix free download, Roblox ChatGPT agent, Roblox DeepSeek agent, Roblox Gemini agent, Roblox Kimi agent, Roblox GLM agent, Roblox Qwen agent, Roblox Arena agent, Roblox Meta AI agent, Roblox Studio AI automation, Luau AI, MCP Roblox, lemonade alternative free, lemonade.gg alternative, free Roblox AI agent, free lemonade roblox alternative*

## ⚠️ Infinix is Free Beware of Paid Copycats

Infinix is 100% free and open-source. It always has been, and it always will be. There is no official paid version, no subscription, and no sign-in required to use the extension.

If you come across a site or extension using the Infinix name that asks for payment or account creation, it is **not** this project. The only official links are the ones listed at the top of this README.

## How it works

```
AI chat in browser <-> Infinix Extension <-> local Bridge -> endpoint/workspace tools and optional MCP integrations (including Roblox Studio)
```

The extension runs inside a supported chat page and connects to the local bridge on the same PC. The bridge provides enabled local diagnostics, workspace and process tools; the extension provides browser automation. Roblox Studio is optional and its tools appear only when that integration is enabled.

## Multi-agent teams

The supervisor can delegate bounded tasks to providers authorized at startup. Each worker runs in an inactive tab in a minimized dedicated Infinix team window with a separate per-tab ToolRegistry, so provider pages do not take focus or remain visibly open. Workers use the Basic profile and read-only diagnostics/workspace tools, including source search and Git inspection; they do not inherit terminal access, browser control, file writes, remediation, or the supervisor's Amplo permissions. Delegating children requires explicit `allow_children` and is bounded by the session concurrency setting and a three-level depth limit. Spawn slots are reserved before asynchronous tab creation, preventing parallel requests from exceeding the configured limit. Worker startup can take up to two minutes before a handshake timeout, and status remains `starting` until the provider is ready. Tool results are returned through the same result envelope as other extension tools so the supervisor receives the assigned task ID, rather than an empty `{}` response. Supervisor/worker messages are routed through the local bridge with direct-parent/child checks; message retries are idempotent only when the original sender and content match. `agent.team.status` preserves its direct-child response by default and can optionally return `include_descendants=true` with a bounded hierarchy and state counts. Hidden tabs continue to run where the browser allows it, but browser or OS suspension can pause them.

Reliability requirements for slow provider startup, hidden-tab execution and bridge-mediated team messaging are tracked in [MULTIAGENT_RELIABILITY_REQUIREMENTS.md](MULTIAGENT_RELIABILITY_REQUIREMENTS.md); some items still require implementation.

## Software development workflow

For repository work, the local agent can load root `AGENTS.md`/`CLAUDE.md` guidance and common project manifests with `workspace.context`, search literal source text with `workspace.search`, and inspect local changes using `git.status` and bounded `git.diff`. File reads support bounded line ranges. The recommended flow is to inspect repository guidance and existing changes first, search call sites before editing, make focused changes, add targeted tests, run relevant checks, and review the resulting diff. These additions provide repository context and code navigation; worker agents remain read-only and should return findings/evidence to the supervisor.

Core regression tests: `python3 -m unittest discover -q`. Extension tests: run `node` over each `zeroscript-extension/test-*.js` file from the repository root.

## Reusable skills

The package includes 12 task skills for endpoint diagnostics, incident response, browser automation, software development, testing, study, secure downloads, Linux privileged operations, research, data analysis, administrative assistance and multi-agent delegation. See [`skills/INDEX.md`](skills/INDEX.md). The agent should load only the relevant skill and references; these guides do not grant permissions or override the active profile.

## Setup

Linux is supported with Chrome/Chromium or Edge and the start_agent.sh launcher. The launcher automatically prepares Python dependencies; see INSTALL_LINUX.md.

On Linux, the Amplo session can use the terminal.run_as_admin tool when sudo is available. If needed, the OS desktop opens its askpass authentication dialog. Enter the password there—not in the chat. It is passed directly to sudo, never to the model or Infinix logs, and is not stored by Infinix; the system may cache sudo authorization until its normal timeout.

📺 **Setup tutorial on YouTube** covers every step below.

### 1. Download the zip and install the extension

Download the latest zip from the Releases page and extract it. The zip contains both the Bridge and the extension folder.

On Linux, Chrome/Chromium and Edge are supported. To load the extension:

- Go to `edge://extensions` (Edge) or `chrome://extensions` (Chrome)
- Enable Developer mode (top right toggle)
- Click Load unpacked
- Select the `zeroscript-extension` folder from the extracted zip

### 2. (Optional) Connect Roblox Studio

Open Studio and load a Place, then enable MCP (first time only):

- Click Assistant AI in the top bar
- Click ... (top right of the Assistant panel)
- Click Manage MCP Servers
- Click Enable Studio as MCP Server

*Not sure where to find these options? The video tutorial shows exactly where to click.*

### 3. Run the Bridge

**Windows:** double-click `start.bat` inside the extracted folder.

**macOS:** double-click `MacOS_Start.command` inside the extracted folder. The first time, macOS will show a security warning ("could not verify... free of malware") - this is normal for any script downloaded outside the App Store, click Done, then go to System Settings > Privacy & Security, scroll to the bottom, and click Open Anyway. You only need to do this once.

**Linux:** open a terminal in the extracted project folder and run `chmod +x start_agent.sh` (if needed), then `./start_agent.sh`. It creates a local virtual environment, installs websockets, and downloads Python 3.12 into your user directories if the system only has an older Python (e.g. Ubuntu 20.04). It does not use sudo or change system packages. See INSTALL_LINUX.md.

Keep the terminal/window open while using Infinix. The General Agent does not require Roblox Studio; enable the Studio MCP server only when you want Roblox-specific tools.

### 4. Start a session

Go to https://chat.deepseek.com (recommended), https://chatgpt.com, https://gemini.google.com, https://www.kimi.ai, https://chat.z.ai, https://chat.qwen.ai, https://arena.ai or https://www.meta.ai and open a new chat. The Infinix bar appears above the input box. Click Start session. Type what you want to build.

Only works on chat.deepseek.com, chatgpt.com, gemini.google.com, kimi.ai, chat.z.ai, chat.qwen.ai, arena.ai and meta.ai - it will not work on any other site. On Arena, keep the mode dropdown on Direct - Infinix blocks Start in Battle / Side-by-Side / Agent modes (it only drives a single Direct reply). Gemini and Kimi can be unstable (model behavior, not the extension): Gemini may stop using the Roblox tools after a while, and Kimi may use its own native tools instead. If the AI starts answering in plain text instead of acting, remind it to use the commands or start a new session.

### 5. Watch the setup tutorial

[Watch the setup tutorial on YouTube](https://youtu.be/kPKiZLZ9_Ps)

## What the AI can do

- Read and edit scripts
- Run Luau code directly in Studio
- Inspect the game tree and instances
- Generate meshes, materials, and models
- Browse and insert from the Creator Store
- Control play-testing
- Remember your project across sessions (persistent project memory saved inside your place)

## New in 1.6.24

Autonomous Amplo session restored: the profile still shows two warnings at startup; after confirming both, diagnostics, scans, repairs, terminal commands, and authorized account actions run without per-action approval. Basic/Development keep their own prompts. The bridge does not bypass or auto-accept UAC/sudo.

## New in 1.6.23

- **Local endpoint diagnostics:** added bounded read-only tools for OS/architecture, processes, services, addresses/listeners, security status, recent events, startup entries and installed tools on Windows/Linux.
- **Windows account incident snapshot:** inventories local users, members of the built-in Administrators group, user profiles, CMD policy and command-redirection indicators without changing them; specifically helps distinguish an account from its Windows profile.
- **Session-wide autonomy:** after the two startup confirmations for the Amplo profile, diagnostics, scans, repairs, terminal commands and account-disable actions run without per-action approval. Basic/Development retain their configured prompts. A fixed Windows action can disable one confirmed local account by exact SID, refusing the current account, built-in -500, and the last verifiable enabled local administrator; it does not delete profiles or end existing sessions. The bridge never auto-elevates through UAC or sudo.
- **Linux shell support:** terminal.run now offers Bash/sh/zsh and installed PowerShell Core as the bridge user. Windows keeps CMD/PowerShell; command execution still follows the existing permission profile.
- **Security skill and research:** added a reusable endpoint-diagnosis skill with incident-response guidance and a Windows architecture-detection/CMD/account test workflow; ARM is not assumed. See INSTALL_LINUX.md and skills/sistema-e-seguranca/diagnostico-endpoint in the package.

## New in 1.6.19

- **Network tools added:** network.http_request for making HTTP requests (GET, POST, PUT, DELETE, PATCH) with full response details including status code, headers, body, and timing. network.check_port for TCP port scanning and service discovery.
- **Data transformation suite:** Six new utilities - data.parse_json, data.format_json, data.parse_csv, data.format_csv, data.merge_dicts, and data.flatten_dict for powerful data manipulation directly from chat.
- **50% more capabilities:** Tool registry expanded from 7 to 15 tools, enabling API integration, data processing, and network diagnostics without leaving the AI chat.
- **Enhanced security model:** All new tools follow the same profile-based access control, redacted event logging, and workspace confinement patterns.
- **Meta AI fixed:** No longer forces Réflexion (thinking) mode automatically. Users can now choose their preferred mode or use Meta's default setting.

## New in 1.6.17

- **Autonomous self-improvement cycles.** The isolated protocol runs without per-call approval and supports work lasting up to four hours; remote source transfer remains disabled unless ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1 is set once in the user's environment.
- **Windows/Python portability.** SQLite connections close deterministically, workspace-relative paths use consistent / separators, and process.test uses the active Python interpreter (including Python 3.15).
- **Weekly local scheduling.** Optional Windows Task Scheduler and Linux systemd user-unit setup produces reports and candidate ZIPs without elevated privileges. Review and sandbox testing remain required before promotion.

## New in 1.5.5

- **DeepSeek:** the agent starts again on the new unified model. DeepSeek merged Instant, Expert and Vision into one model and removed the model picker, which left "Start Roblox agent" stuck on "DeepSeek mode not ready". Infinix now recognises the new chat box, switches Search off and starts, with DeepThink left on.
- **DeepSeek:** screenshots work on every chat. Images no longer need the Vision tab (it is gone) - the unified model sees your Studio captures, one at a time or several in a row.

## New in 1.5.4

- **ChatGPT:** the Infinix bar is back above the composer. ChatGPT redesigned its input box and renamed the layout slot the bar sits in. Infinix kept asking for the old name, so the browser dropped the bar into a stray strip at the bottom right of the composer and squeezed the textarea.

## Credits

- **Original Creator:** Moonyeep
- **Built with:** Manus AI
- **Based on:** ZeroScript architecture
- **License:** GPL-3.0

This project stands on the shoulders of the ZeroScript foundation but represents an independent implementation. The original creator has abandoned this project and releases it as a base for the community to improve upon.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

**Important:** Any derivative work based on this project MUST also be free and open-source under GPL-3.0. Commercial closed-source derivatives are NOT permitted.
