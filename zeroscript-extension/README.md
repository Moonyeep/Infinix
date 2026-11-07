# Infinix — Local Autonomous Agent for Windows and Linux

> **Current package mode:** the extension starts the local General Agent. Roblox Studio is optional; use the general-agent launcher for local diagnostics, workspace, and browser capabilities. The separate Roblox launcher is retained for the legacy integration.

Infinix is a local autonomous agent controlled through supported browser-based AI chats. Its bridge provides cross-platform endpoint diagnostics, workspace tools, browser automation, and shell access under the selected capability profile. No separate model API key is required for browser providers.

It's a Chrome/Edge browser extension plus an optional local bridge. **DeepSeek is the recommended provider.** The bridge-backed mode remains the default and keeps all existing local tools. An opt-in **extension-only mode** is also available from the extension popup for browser automation only; it does not provide filesystem, terminal, Roblox Studio, MCP, or local-agent tools. ChatGPT, Gemini, Kimi, GLM, Qwen, Arena and Meta AI are also supported. Roblox Studio remains an optional integration through its official MCP server.

## Setup

**Load the extension manually (Chrome/Chromium or Edge):**
1. Go to `edge://extensions` (Edge) or `chrome://extensions` (Chrome/Chromium; Linux is supported)
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `zeroscript-extension` folder
5. The extension is now active

**Optional: extension-only mode**
Use the extension popup and choose **Use extension-only mode**. This mode is opt-in and does not require the bridge process. It provides browser-tab and page automation only. Local file/terminal tools, Roblox Studio, MCP servers, and local agent/team features remain available only in the default Bridge mode. Switch back to Bridge mode in the popup at any time.

**Then set up the Bridge for full local capabilities:**
1. **Download the Bridge** from the [Infinix GitHub releases page](https://github.com/Moonyeep/Infinix)
2. **Optional:** open Roblox Studio and load a Place if you need Roblox-specific tools
3. **Enable the MCP server in Roblox Studio** (first time only): click **Assistant AI** in the top bar, then **...** > **Manage MCP Servers** > **Enable Studio as MCP Server**
4. **Run the Bridge** - Windows: run `Start_Agent.bat`; macOS: run `Start_Agent.command`; Linux: in the extracted project folder run `chmod +x start_agent.sh && ./start_agent.sh`. On Linux the launcher creates a local virtual environment, installs bridge dependencies, and downloads a managed Python 3.12 into your user directories when needed. It does not use sudo or change system packages. Keep its terminal open while using the extension.
5. **Go to https://chat.deepseek.com** (recommended), https://chatgpt.com, https://gemini.google.com, https://www.kimi.com, https://chat.z.ai, https://chat.qwen.ai, https://arena.ai, or https://www.meta.ai, open a new chat (only works on these exact addresses; on Arena use Direct mode)
6. Click **Start session** in the Infinix panel
7. Type what you want to build

📺 [Watch the setup tutorial](https://youtu.be/kPKiZLZ9_Ps)

## Architecture (for contributors)

The extension is split between a provider-agnostic core and per-AI-site providers:

```
core/config.js        system prompt, feedback strings, tool categories (global ZS)
core/parser.js        Infinix command parsing - pure string logic   (global ZSParse)
core/main.js          agentic loop, UI, camouflage, session state      (uses ZSProvider)
providers/deepseek.js everything DeepSeek-specific: DOM selectors, generation
                      detection, send mechanics, composer modes…       (global ZSProvider)
providers/gemini.js   same interface for Google Gemini (Angular DOM, Quill
                      composer, code-block masking)                    (global ZSProvider)
providers/kimi.js     same interface for Kimi / Moonshot AI (Vue DOM, Lexical
                      composer, segment-code masking)                  (global ZSProvider)
providers/glm.js      same interface for GLM / Z.ai (Svelte DOM, code-block
                      wrapper masking)                                 (global ZSProvider)
providers/qwen.js     same interface for Qwen / chat.qwen.ai (Vue DOM, network-tap
                      SSE stream, Monaco disposal guard)               (global ZSProvider)
providers/qwen-net.js MAIN-world fetch tap for Qwen SSE stream        (injected by manifest)
providers/chatgpt.js  same interface for ChatGPT / chatgpt.com (React DOM,
                      ProseMirror composer, CodeMirror reply reading) (global ZSProvider)
providers/chatgpt-cm.js MAIN-world CodeMirror tap: republishes each code block's
                      TRUE document (the rendered DOM truncates long
                      lines)                                          (injected by manifest)
providers/arena.js    same interface for Arena / arena.ai (React DOM, multi-model
                      playground, A/B-comparison auto-commit, Direct-mode gate) (global ZSProvider)
providers/meta.js     same interface for Meta AI / meta.ai (React DOM, textarea
                      composer, JSON-viewer + code-collapse masking)   (global ZSProvider)
background.js         WebSocket to the local bridge (provider-agnostic)
```

`core/main.js` never touches the host site's DOM directly - it only calls the
`ZSProvider` interface. To integrate another AI site: write a new
`providers/<site>.js` exporting the same interface, then add its URL pattern to
`manifest.json` (`content_scripts` + `host_permissions`) and to
`PROVIDER_URLS` in `background.js`. No core change required.

Smoke tests (plain Node, no dependencies - run them from this directory):

- `node test-parser.js` - the command parser (`core/parser.js`).
- `node test-chatgpt.js` - ChatGPT reply reading (`providers/chatgpt.js`),
  driven against a stub DOM: CodeMirror line joining, the `data-zs-cm`
  MAIN-world tap that long code blocks depend on, and subtree exclusion.

Both print `PASS`/`FAIL` per case and exit non-zero on failure.

## Support

☕ [Ko-fi](https://ko-fi.com/moonyeep) - Robux tip passes available in the extension panel
