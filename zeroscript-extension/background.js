// SPDX-License-Identifier: GPL-3.0-or-later
// background.js - service worker.
// Owns ONE resilient WebSocket to the local bridge (ws://127.0.0.1:PORT).
// Keeping the socket here (not in the content script) avoids https→ws mixed
// content issues and centralises reconnect / timeout logic.
//
// Contract with content.js: every sendMessage ALWAYS gets a response object,
// even when the bridge is offline. The agentic loop must never hang waiting.

const PORT = 17613;
// Keep the global URL constructor available for browser URL validation below.
const BRIDGE_WS_URL = `ws://127.0.0.1:${PORT}`;

// Chat sites where a Infinix provider content script runs. Status pushes go
// to every tab matching these. Add the new provider's URL pattern here (and in
// manifest.json content_scripts + host_permissions) when integrating another AI.
const PROVIDER_URLS = ["https://chat.deepseek.com/*", "https://chatgpt.com/*", "https://chat.openai.com/*", "https://gemini.google.com/*", "https://www.kimi.ai/*", "https://kimi.ai/*", "https://chat.z.ai/*", "https://chat.qwen.ai/*", "https://arena.ai/*", "https://www.meta.ai/*", "https://meta.ai/*"];

const RECONNECT_MIN = 1000;
const RECONNECT_MAX = 5000;
const HEARTBEAT_MS = 10000;
// If no message (incl. pong) arrives within this window while we believe we're
// connected, the socket is half-open: force a reconnect instead of letting
// pending requests slowly time out.
const STALE_SOCKET_MS = 25000;
const REQUEST_TIMEOUT_DEFAULT = 130000; // a bit above the 120s tool timeout

let ws = null;
let profileSyncedSocket = null;
let connected = false;
let extensionOnly = false;
chrome.storage?.local?.get({ extensionOnly: false }, (v) => { extensionOnly = !!v.extensionOnly; broadcastStatus(); });
let reconnectDelay = RECONNECT_MIN;
let reconnectTimer = null;
let heartbeatTimer = null;
let lastMessageAt = 0; // timestamp of the last frame received from the bridge
let nextId = 1;
const pending = new Map(); // id -> {resolve, timer}
let toolsCache = [];
let agentToolsCache = [];
const agentToolsCacheBySession = new Map();
let agentEnabled = false;
let agentApproval = null;
let agentProfile = "basic";
let agentTeamConfig = { enabled: false, selected_providers: [], allowed_providers: [], max_agents: 4, session_id: "" };
let agentTeamWindowId = null;
let agentTeamOpenedSession = "";
const agentTeamTasks = new Map();
let teamSpawnReservations = 0;
const agentTabTasks = new Map();
const agentProfilesByTab = new Map();
const agentTeamWaiters = new Map();
function persistAgentTeamState() {
  if (!chrome.storage?.session) return;
  chrome.storage.session.set({
    infinixTeamTasks: [...agentTeamTasks.entries()],
    infinixTabTasks: [...agentTabTasks.entries()],
    infinixAgentProfilesByTab: [...agentProfilesByTab.entries()],
  });
}
const AGENT_PROVIDER_URLS = {
  deepseek: "https://chat.deepseek.com/", chatgpt: "https://chatgpt.com/",
  gemini: "https://gemini.google.com/app", kimi: "https://www.kimi.ai/",
  zai: "https://chat.z.ai/", qwen: "https://chat.qwen.ai/",
  arena: "https://arena.ai/text/direct", meta: "https://www.meta.ai/",
};
const agentTeamStateReady = new Promise((resolve) => {
  if (!chrome.storage?.session) return resolve();
  chrome.storage.session.get(["infinixTeamWindowId", "infinixTeamOpenedSession", "infinixTeamTasks", "infinixTabTasks", "infinixAgentProfilesByTab"], (stored) => {
    if (Number.isInteger(stored?.infinixTeamWindowId)) agentTeamWindowId = stored.infinixTeamWindowId;
    if (typeof stored?.infinixTeamOpenedSession === "string") agentTeamOpenedSession = stored.infinixTeamOpenedSession;
    for (const [id, task] of stored?.infinixTeamTasks || []) if (typeof id === "string" && task && typeof task === "object") agentTeamTasks.set(id, task);
    for (const [tabId, id] of stored?.infinixTabTasks || []) if (Number.isInteger(tabId) && typeof id === "string") agentTabTasks.set(tabId, id);
    for (const [tabId, profile] of stored?.infinixAgentProfilesByTab || []) if (Number.isInteger(tabId) && ["basic", "development", "broad"].includes(profile)) agentProfilesByTab.set(tabId, profile);
    resolve();
  });
});
const profileReady = new Promise((resolve) => {
  if (!chrome.storage?.session) return resolve();
  chrome.storage.session.get("agentProfile", (stored) => {
    if (["basic", "development", "broad"].includes(stored?.agentProfile)) agentProfile = stored.agentProfile;
    resolve();
  });
});
function chromeCallback(api, ...args) {
  return new Promise((resolve) => api(...args, (value) => resolve(chrome.runtime.lastError ? null : value)));
}
async function ensureAgentTeamWindow(config) {
  await agentTeamStateReady;
  const session = String(config?.session_id || "");
  const previousSession = String(agentTeamOpenedSession || "");
  if (previousSession && session && previousSession !== session) {
    for (const task of agentTeamTasks.values()) {
      if (!isTerminalTeamState(task.state)) {
        task.state = "failed";
        task.phase = "bridge_session_reset";
        task.error = "the bridge team session restarted; start a new worker task";
        task.updatedAt = Date.now();
        notifyTeamTaskChanged(task);
        chrome.tabs.sendMessage(task.tabId, { type: "infinix-team-session-reset", taskId: task.id }, () => {});
      }
    }
    persistAgentTeamState();
  }
  if (!config?.enabled) {
    agentTeamConfig = config || agentTeamConfig;
    if (session) agentTeamOpenedSession = session;
    chrome.storage?.session?.set({ infinixTeamOpenedSession: agentTeamOpenedSession });
    return;
  }
  const selected = [...new Set((config.selected_providers || []).filter((id) => Object.hasOwn(AGENT_PROVIDER_URLS, id)))];
  if (!selected.length) {
    agentTeamConfig = config;
    agentTeamOpenedSession = session;
    chrome.storage?.session?.set({ infinixTeamOpenedSession: session });
    return;
  }
  const existing = agentTeamWindowId == null ? null : await chromeCallback(chrome.windows.get, agentTeamWindowId);
  if (existing && agentTeamOpenedSession === session) {
    if (existing.state !== "minimized") await chromeCallback(chrome.windows.update, agentTeamWindowId, { state: "minimized", focused: false });
    return;
  }
  const urls = selected.map((id) => AGENT_PROVIDER_URLS[id]);
  if (existing) {
    const tabs = await chromeCallback(chrome.tabs.query, { windowId: agentTeamWindowId }) || [];
    const hosts = new Set(tabs.map((tab) => { try { return new URL(tab.url).hostname; } catch { return ""; } }));
    for (const url of urls) {
      const host = new URL(url).hostname;
      if (!hosts.has(host)) await chromeCallback(chrome.tabs.create, { windowId: agentTeamWindowId, url, active: false });
    }
  } else {
    const created = await chromeCallback(chrome.windows.create, { url: urls, type: "normal", focused: false, state: "minimized" });
    if (!created || !Number.isInteger(created.id)) { log("could not open Infinix agent window", chrome.runtime.lastError?.message || "window creation failed"); return; }
    agentTeamWindowId = created.id;
  }
  const currentWindow = agentTeamWindowId == null ? null : await chromeCallback(chrome.windows.get, agentTeamWindowId);
  if (currentWindow && currentWindow.state !== "minimized") await chromeCallback(chrome.windows.update, agentTeamWindowId, { state: "minimized", focused: false });
  agentTeamConfig = config;
  agentTeamOpenedSession = session;
  chrome.storage?.session?.set({ infinixTeamWindowId: agentTeamWindowId, infinixTeamOpenedSession: session });
}
function answerOnce(state, result) {
  if (!state || state.replied) return;
  state.replied = true;
  if (state.timer) clearTimeout(state.timer);
  try { state.sendResponse(result); } catch {}
}
function announceAgentApproval(approval) {
  if (!approval) return;
  broadcastStatus();
  if (Number.isInteger(approval.sourceTabId)) {
    chrome.tabs.sendMessage(approval.sourceTabId, { type: "zs-approval-request", approval }, () => {
      if (chrome.runtime.lastError) log("approval overlay could not reach source tab", chrome.runtime.lastError.message);
    });
  }
  if (chrome.notifications) chrome.notifications.create("zs-approval", {
      type: "basic", iconUrl: "icon.png",
    title: "Infinix precisa da sua aprovação",
    message: `${approval.tool} · ${approval.capability}. Clique para revisar os detalhes.`, priority: 2,
  });
}
const EXTENSION_BROWSER_TOOLS = [
  { name: "agent.browser.tabs.list", description: "List open browser tabs (read-only)", inputSchema: { type: "object" } },
  { name: "agent.browser.tab.open", description: "Open a new browser tab and navigate it to a URL", inputSchema: { type: "object", required: ["url"], properties: { url: { type: "string" }, active: { type: "boolean" } } } },
  { name: "agent.browser.tab.navigate", description: "Navigate an existing browser tab, bringing it forward by default", inputSchema: { type: "object", required: ["url"], properties: { tabId: { type: "integer" }, url: { type: "string" }, active: { type: "boolean", description: "Defaults true; set false only when background navigation is needed" } } } },
  { name: "agent.browser.snapshot", description: "Read visible actionable elements plus page text. Supports open Shadow DOM with deep:true; wait_ms/selector_hint wait for hydration. Virtualized offscreen lists may require scroll then a fresh snapshot.", inputSchema: { type: "object", properties: { tabId: { type: "integer" }, active: { type: "boolean", description: "Defaults true" }, deep: { type: "boolean", description: "Traverse open Shadow DOM roots; closed roots are inaccessible" }, wait_ms: { type: "integer", description: "Wait up to 15000ms for a quiet DOM; if selector_hint is provided, wait for it too" }, selector_hint: { type: "string", description: "CSS selector expected to appear and be visible before snapshot" }, include_text: { type: "boolean", description: "Include capped pageText fallback; defaults true" } } } },
  { name: "agent.browser.click", description: "Click a visible element by stable ID; pass tabId from matching snapshot; target tab is activated by default. In the double-confirmed Amplo profile, clicks run without per-action prompts.", inputSchema: { type: "object", required: ["id"], properties: { id: { type: "string" }, tabId: { type: "integer" }, active: { type: "boolean", description: "Defaults true" } } } },
  { name: "agent.browser.click_at", description: "Click at x,y for visual fallback. Default coordinate_space is css; use image to convert screenshot pixels by devicePixelRatio. In Amplo, runs without per-action approval after startup confirmation.", inputSchema: { type: "object", required: ["x", "y"], properties: { x: { type: "number" }, y: { type: "number" }, coordinate_space: { type: "string", enum: ["css", "image"] }, tabId: { type: "integer" }, active: { type: "boolean" } } } },
  { name: "agent.browser.type", description: "Type into a visible input; pass tabId from matching snapshot; target tab is activated by default. In Amplo, typing runs without per-action prompts.", inputSchema: { type: "object", required: ["id", "text"], properties: { id: { type: "string" }, text: { type: "string" }, tabId: { type: "integer" }, active: { type: "boolean", description: "Defaults true" } } } },
  { name: "agent.browser.press_key", description: "Dispatch a synthetic key event to a focused element or element ID. In Amplo, keys run without per-action prompts. Some sites ignore synthetic events; no OS-level trusted keystroke is generated.", inputSchema: { type: "object", required: ["key"], properties: { key: { type: "string" }, modifiers: { type: "array", items: { type: "string", enum: ["ctrl", "shift", "alt", "meta"] } }, id: { type: "string", description: "Optional element ID; otherwise the currently focused element" }, tabId: { type: "integer" }, active: { type: "boolean" } } } },
  { name: "agent.browser.wait", description: "Wait up to timeout_ms for a visible CSS selector or page text; supports open Shadow DOM with deep:true", inputSchema: { type: "object", properties: { selector_hint: { type: "string" }, text: { type: "string" }, timeout_ms: { type: "integer" }, deep: { type: "boolean" }, tabId: { type: "integer" }, active: { type: "boolean" } } } },
  { name: "agent.browser.scroll", description: "Scroll the page or nearest/largest scroll container in steps; take a fresh snapshot after each scroll to inspect virtualized lists", inputSchema: { type: "object", required: ["direction"], properties: { direction: { type: "string", enum: ["up", "down"] }, amount: { type: "integer", description: "100–2000 pixels; defaults to 500" }, containerId: { type: "string", description: "Optional ID inside the desired scroll container" }, tabId: { type: "integer" }, active: { type: "boolean" } } } },
  { name: "agent.browser.screenshot", description: "Capture the visible viewport and attach it to the assistant for visual fallback. Use only when the selected model supports images and DOM snapshot is insufficient.", inputSchema: { type: "object", properties: { tabId: { type: "integer" }, active: { type: "boolean" } } } },
];
const EXTENSION_TEAM_TOOLS = [
  { name: "agent.team.spawn", description: "Delegate a bounded task to an authorized AI provider in the dedicated Infinix team window. A worker receives an isolated tab and read-only local tools by default; allow_children grants explicit delegation authority. No per-action confirmation is used for this isolated read-only dispatch.", inputSchema: { type: "object", required: ["provider", "task"], properties: { provider: { type: "string", enum: Object.keys(AGENT_PROVIDER_URLS) }, task: { type: "string", minLength: 1, maxLength: 12000 }, allow_children: { type: "boolean", description: "Explicitly allow this worker to spawn its own children; defaults false" } } } },
  { name: "agent.team.status", description: "Get direct-child status by default; set include_descendants=true for a bounded nested task tree and state summary.", inputSchema: { type: "object", properties: { task_id: { type: "string" }, include_descendants: { type: "boolean" } } } },
  { name: "agent.team.wait", description: "Wait for a direct child task to finish, fail, or stop, up to 90 seconds.", inputSchema: { type: "object", required: ["task_id"], properties: { task_id: { type: "string" }, timeout_ms: { type: "integer", minimum: 1000, maximum: 90000 } } } },
  { name: "agent.team.message", description: "Send a short, sequenced message to a direct child by task_id; a child may use task_id='supervisor' to message its direct supervisor.", inputSchema: { type: "object", required: ["task_id", "message"], properties: { task_id: { type: "string" }, message: { type: "string", minLength: 1, maxLength: 4000 } } } },
  { name: "agent.team.inbox", description: "Read new messages from the bridge-backed team inbox. Pass after_sequence from the previous response to avoid repeating old messages.", inputSchema: { type: "object", properties: { after_sequence: { type: "integer", minimum: 0 }, limit: { type: "integer", minimum: 1, maximum: 100 } } } },
];
function sessionIdFor(sender) {
  return Number.isInteger(sender?.tab?.id) ? `tab:${sender.tab.id}` : "";
}
function teamSessionToken() {
  const token = String(agentTeamConfig?.session_id || "");
  return /^[a-f0-9]{16,64}$/i.test(token) ? token.toLowerCase() : "";
}
function childMayUseTool(name) {
  const bare = String(name || "").replace(/^agent\./, "");
  if (["file.read", "file.list", "task.finish"].includes(bare)) return true;
  if (bare.startsWith("diagnostics.")) return bare !== "diagnostics.action";
  return false;
}
function isTerminalTeamState(state) {
  return ["completed", "failed", "stopped", "cancelled"].includes(state);
}
function notifyTeamTaskChanged(task) {
  if (!task || !isTerminalTeamState(task.state)) return;
  for (const resolve of [...(agentTeamWaiters.get(task.id) || [])]) resolve(false);
}
function waitForTeamTask(task, timeoutMs) {
  if (isTerminalTeamState(task.state)) return Promise.resolve(false);
  return new Promise((resolve) => {
    const waiters = agentTeamWaiters.get(task.id) || new Set();
    agentTeamWaiters.set(task.id, waiters);
    let timer = 0;
    const finish = (timedOut) => {
      clearTimeout(timer);
      waiters.delete(finish);
      if (!waiters.size) agentTeamWaiters.delete(task.id);
      resolve(timedOut);
    };
    waiters.add(finish);
    timer = setTimeout(() => finish(true), timeoutMs);
    if (isTerminalTeamState(task.state)) finish(false);
  });
}
function publicTeamTask(task) {
  if (!task) return null;
  return { task_id: task.id, provider: task.provider, parent_task_id: task.parentTaskId || null, depth: task.depth || 1, state: task.state, phase: task.phase || task.state, created_at: task.createdAt, updated_at: task.updatedAt, result: task.result || "", error: task.error || "" };
}
function publicTeamTree(task, seen = new Set()) {
  if (!task) return null;
  const node = publicTeamTask(task);
  if (seen.has(task.id) || (task.depth || 1) >= 3) { node.children = []; return node; }
  seen.add(task.id);
  node.children = [...agentTeamTasks.values()]
    .filter((child) => child.parentTaskId === task.id && child.parentTabId === task.tabId)
    .map((child) => publicTeamTree(child, seen));
  return node;
}
function teamTreeSummary(roots) {
  const counts = { starting: 0, running: 0, completed: 0, failed: 0, stopped: 0 };
  let total = 0;
  const visit = (node) => {
    if (!node) return;
    total += 1;
    if (Object.hasOwn(counts, node.state)) counts[node.state] += 1;
    for (const child of node.children || []) visit(child);
  };
  for (const root of roots) visit(root);
  return { total_tasks: total, by_state: counts };
}
async function createDedicatedAgentTab(provider) {
  await agentTeamStateReady;
  const url = AGENT_PROVIDER_URLS[provider];
  if (!url) return null;
  let win = agentTeamWindowId == null ? null : await chromeCallback(chrome.windows.get, agentTeamWindowId);
  if (!win) {
    const created = await chromeCallback(chrome.windows.create, { url, type: "normal", focused: false, state: "minimized" });
    if (!created || !Number.isInteger(created.id)) return null;
    agentTeamWindowId = created.id;
    agentTeamOpenedSession = String(agentTeamConfig.session_id || "");
    chrome.storage?.session?.set({ infinixTeamWindowId: agentTeamWindowId, infinixTeamOpenedSession: agentTeamOpenedSession });
    const tabs = created.tabs || [];
    const tab = tabs.find((item) => Number.isInteger(item.id));
    return tab || null;
  }
  if (win.state !== "minimized") await chromeCallback(chrome.windows.update, agentTeamWindowId, { state: "minimized", focused: false });
  return await chromeCallback(chrome.tabs.create, { windowId: agentTeamWindowId, url, active: false });
}
async function sendDelegatedTask(tabId, message) {
  const deadline = Date.now() + 120000;
  let attempt = 0;
  while (Date.now() < deadline) {
    const response = await chromeCallback(chrome.tabs.sendMessage, tabId, message);
    if (response?.ok) return response;
    if (response?.fatal) return response;
    const delay = Math.min(500 * (2 ** Math.min(attempt++, 4)), 5000);
    await new Promise((resolve) => setTimeout(resolve, delay));
  }
  return { ok: false, fatal: true, error: "provider content script/bridge handshake timed out after 120 seconds" };
}
async function spawnAgentTask(args, sender) {
  await agentTeamStateReady;
  const parentTabId = sender?.tab?.id;
  if (!Number.isInteger(parentTabId)) return { ok: false, error: "team dispatch must originate from an AI chat tab" };
  if (!agentTeamConfig?.enabled) return { ok: false, error: "the dedicated agent team is not enabled for this session" };
  if (!connected || !agentEnabled) return { ok: false, error: "local bridge agent is unavailable; reconnect the bridge before spawning workers" };
  const provider = String(args?.provider || "");
  const taskText = String(args?.task || "").trim();
  const allowed = new Set([...(agentTeamConfig.allowed_providers || []), ...(agentTeamConfig.selected_providers || [])]);
  if (!Object.hasOwn(AGENT_PROVIDER_URLS, provider) || !allowed.has(provider)) return { ok: false, error: "provider is not authorized in the session's startup allowlist" };
  if (!taskText || taskText.length > 12000) return { ok: false, error: "task must contain 1-12000 characters" };
  const parentTaskId = agentTabTasks.get(parentTabId) || "";
  const parentTask = parentTaskId ? agentTeamTasks.get(parentTaskId) : null;
  if (parentTask && !parentTask.allowChildren) return { ok: false, error: "this worker was not explicitly authorized to spawn child agents" };
  if (parentTask && parentTask.state !== "running") return { ok: false, error: "only a running worker may create child tasks" };
  const depth = (parentTask?.depth || 0) + 1;
  if (depth > 3) return { ok: false, error: "maximum team depth of three levels reached" };
  const maxAgents = Math.max(1, Math.min(16, Number(agentTeamConfig.max_agents) || 4));
  const active = [...agentTeamTasks.values()].filter((task) => ["starting", "running"].includes(task.state)).length;
  if (active + teamSpawnReservations >= maxAgents) return { ok: false, error: `team concurrency limit reached (${maxAgents})` };
  // Reserve synchronously before the first await so concurrent spawn requests
  // cannot all pass the same active-count check.
  teamSpawnReservations += 1;
  let reservationHeld = true;
  try {
    const tab = await createDedicatedAgentTab(provider);
    if (!tab || !Number.isInteger(tab.id)) return { ok: false, error: "could not create a tab in the dedicated team window" };
    const id = `task_${crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
    const now = Date.now();
    const task = { id, task: taskText, provider, parentTabId, parentTaskId, depth, tabId: tab.id, allowChildren: args?.allow_children === true, state: "starting", phase: "waiting_for_content_script", createdAt: now, updatedAt: now, result: "", error: "" };
    agentTeamTasks.set(id, task);
    agentTabTasks.set(tab.id, id);
    teamSpawnReservations = Math.max(0, teamSpawnReservations - 1);
    reservationHeld = false;
    persistAgentTeamState();
    const accepted = await sendDelegatedTask(tab.id, { type: "infinix-delegated-task", taskId: id, task: taskText, allowChildren: task.allowChildren });
    if (!accepted.ok) {
      task.state = "failed"; task.error = accepted.error || "worker did not accept task"; task.updatedAt = Date.now();
      task.phase = "failed";
      persistAgentTeamState();
      notifyTeamTaskChanged(task);
      return { ok: false, task_id: id, state: task.state, error: task.error };
    }
    // Receipt of the delegated payload is not readiness. The worker remains
    // `starting` until its provider bootstrap explicitly reports ready.
    task.state = "starting"; task.updatedAt = Date.now();
    task.phase = "provider_bootstrap";
    persistAgentTeamState();
    return { ok: true, task_id: id, provider, state: task.state, tab_id: tab.id, parent_task_id: parentTaskId || null };
  } finally {
    if (reservationHeld) teamSpawnReservations = Math.max(0, teamSpawnReservations - 1);
  }
}
function teamToolResponse(result) {
  if (result && result.ok === false) return { ok: false, error: result.error || "team operation failed", result };
  return { ok: true, result };
}
function teamTaskVisibleTo(task, senderTabId) {
  if (!task || !Number.isInteger(senderTabId)) return false;
  if (task.parentTabId === senderTabId) return true;
  const selfId = agentTabTasks.get(senderTabId);
  return task.id === selfId;
}
async function teamCall(name, args, sender) {
  await agentTeamStateReady;
  const senderTabId = sender?.tab?.id;
  if (name === "agent.team.spawn") return spawnAgentTask(args || {}, sender);
  if (name === "agent.team.status") {
    const taskId = String(args?.task_id || "");
    if (taskId) {
      const target = agentTeamTasks.get(taskId);
      if (!teamTaskVisibleTo(target, senderTabId)) return { ok: false, error: "task is not a direct child or this agent's own task" };
      if (args?.include_descendants === true) {
        const tree = publicTeamTree(target);
        return { ok: true, task: tree, summary: teamTreeSummary([tree]) };
      }
      return { ok: true, task: publicTeamTask(target) };
    }
    const childTasks = [...agentTeamTasks.values()].filter((task) => task.parentTabId === senderTabId);
    const children = childTasks.map(publicTeamTask);
    const selfId = agentTabTasks.get(senderTabId);
    const response = { ok: true, self: publicTeamTask(agentTeamTasks.get(selfId)), children };
    if (args?.include_descendants === true) {
      const tree = childTasks.map((task) => publicTeamTree(task));
      response.tree = tree;
      response.summary = teamTreeSummary(tree);
    }
    return response;
  }
  if (name === "agent.team.wait") {
    const taskId = String(args?.task_id || "");
    const task = agentTeamTasks.get(taskId);
    if (!teamTaskVisibleTo(task, senderTabId) || task?.parentTabId !== senderTabId) return { ok: false, error: "wait is limited to a direct child task" };
    const timeout = Math.max(1000, Math.min(90000, Number(args?.timeout_ms) || 30000));
    const timedOut = await waitForTeamTask(task, timeout);
    return { ok: true, task: publicTeamTask(task), timed_out: timedOut };
  }
  if (name === "agent.team.message") {
    const targetId = String(args?.task_id || "");
    const text = String(args?.message || "").trim();
    if (!text || text.length > 4000) return { ok: false, error: "message must contain 1-4000 characters" };
    const selfId = agentTabTasks.get(senderTabId);
    const self = selfId ? agentTeamTasks.get(selfId) : null;
    if (targetId === "supervisor") {
      if (!self) return { ok: false, error: "only a registered worker can message its supervisor" };
    } else {
      const target = agentTeamTasks.get(targetId);
      if (!target || target.parentTabId !== senderTabId) return { ok: false, error: "messages may only be sent to a direct child task" };
    }
    const messageId = `msg_${crypto.randomUUID?.() || `${Date.now()}_${Math.random().toString(16).slice(2)}`}`;
    const payload = { type: "agent_team_message", session_id: sessionIdFor(sender), team_session_id: teamSessionToken(), target_task_id: targetId, message_id: messageId, message: text };
    let response = await send(payload, 12000);
    // A response can time out after the bridge has committed the message. Retry
    // once with the same ID; the bridge deduplicates it and preserves sequence.
    if (!response.ok && response.kind === "timeout") response = await send(payload, 12000);
    return response;
  }
  if (name === "agent.team.inbox") {
    return await send({ type: "agent_team_inbox", session_id: sessionIdFor(sender), team_session_id: teamSessionToken(),
      after_sequence: Math.max(0, Number(args?.after_sequence) || 0),
      limit: Math.max(1, Math.min(100, Number(args?.limit) || 50)) }, 12000);
  }
  return { ok: false, error: "unknown team operation" };
}
let mcpAlive = false;
let serversCache = [];
let generalAgent = false;
let robloxEnabled = false;
// true/false = a PLACE is loaded and usable in Roblox Studio; null = unknown.
// The MCP process stays alive when Studio is closed or its MCP option is off,
// so this is probed separately (bridge "studio_status").
let studioConnected = null;
// true/false = a Roblox Studio app is connected to the MCP server at all; null =
// unknown. studioApp=true with studioConnected=false means "Studio open but no
// place"; studioApp=false means "Studio closed OR its MCP option disabled".
let studioApp = null;
// true/false = a Roblox Studio WINDOW/PROCESS exists on this machine (checked
// bridge-side via tasklist); null = unknown/old bridge. Distinguishes the two
// studioApp=false sub-cases the UI must word differently: Studio genuinely not
// launched ("open Roblox Studio") vs Studio OPEN but its MCP plugin never
// registered with the bridge - the documented fix for the latter is opening
// Assistant Settings > MCP Servers inside Studio (validated live 3x), which
// "open Roblox Studio" wording completely fails to convey.
let studioProc = null;

function log(...a) {
  console.log("[zs-bg]", ...a);
}

function clearBridgeState(reason) {
  connected = false;
  profileSyncedSocket = null;
  mcpAlive = false;
  studioConnected = null;
  studioApp = null;
  studioProc = null;
  agentEnabled = false;
  agentToolsCache = [];
  serversCache = [];
  const approvalResponse = agentApproval?.responseState;
  agentApproval = null;
  stopHeartbeat();
  failAllPending(reason);
  if (approvalResponse) answerOnce(approvalResponse, { ok: false, error: `${reason}; pending action was not executed` });
  broadcastStatus();
}

// ── WebSocket lifecycle ─────────────────────────────────────────────────
function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  clearTimeout(reconnectTimer);
  const previousSocket = ws;
  if (previousSocket) {
    ws = null;
    clearBridgeState("bridge connection replaced");
    try { previousSocket.close(); } catch {}
  }
  let socket;
  try {
    socket = new WebSocket(BRIDGE_WS_URL);
    ws = socket;
  } catch (e) {
    ws = null;
    log("WebSocket ctor failed", e);
    scheduleReconnect();
    return;
  }

  socket.onopen = () => {
    if (ws !== socket) { try { socket.close(); } catch {} return; }
    connected = true;
    reconnectDelay = RECONNECT_MIN;
    lastMessageAt = Date.now();
    log("connected to bridge");
    startHeartbeat();
    broadcastStatus();
  };

  socket.onmessage = (ev) => {
    if (ws !== socket) return;
    lastMessageAt = Date.now();
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    handleBridgeMessage(msg);
  };

  socket.onclose = (event) => {
    if (ws !== socket) return; // stale close from an older connection
    ws = null;
    log("bridge socket closed", { code: event?.code, reason: event?.reason || "", clean: !!event?.wasClean });
    clearBridgeState("bridge connection closed");
    scheduleReconnect();
  };

  socket.onerror = () => {
    if (ws !== socket) return;
    // onclose will follow; nothing to do here but avoid an unhandled error.
    try { socket.close(); } catch {}
  };
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 1.7, RECONNECT_MAX);
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (connected) {
      // Half-open socket: the WS still reports OPEN but nothing comes through.
      // The pong (and every other frame) refreshes lastMessageAt; if it has
      // gone stale, drop the dead socket so onclose triggers a reconnect.
      if (lastMessageAt && Date.now() - lastMessageAt > STALE_SOCKET_MS) {
        log("socket stale, forcing reconnect");
        try { ws.close(); } catch {}
        return;
      }
      // Keeps the MV3 service worker alive AND detects a half-open socket.
      send({ type: "ping" }).catch(() => {});
      refreshStudioStatus();
    }
  }, HEARTBEAT_MS);
}

function stopHeartbeat() {
  clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

// Resolve once the socket is OPEN, or false after `timeout` ms.
function waitForConnection(timeout = 8000) {
  return new Promise((resolve) => {
    if (connected && ws && ws.readyState === WebSocket.OPEN) return resolve(true);
    connect(); // nudge a (re)connection - important after a worker wake-up
    const t0 = Date.now();
    const iv = setInterval(() => {
      if (connected && ws && ws.readyState === WebSocket.OPEN) {
        clearInterval(iv);
        resolve(true);
      } else if (Date.now() - t0 > timeout) {
        clearInterval(iv);
        resolve(false);
      }
    }, 100);
  });
}

// ── request/response over the socket ────────────────────────────────────
async function send(obj, timeout = REQUEST_TIMEOUT_DEFAULT, context = {}) {
  // The MV3 service worker can be suspended; the first message after a wake-up
  // arrives before the socket has re-opened. Wait for it instead of failing -
  // otherwise Kimi wrongly hears "bridge offline".
  if (!connected || !ws || ws.readyState !== WebSocket.OPEN) {
    await waitForConnection(8000);
  }
  return new Promise((resolve) => {
    if (!connected || !ws || ws.readyState !== WebSocket.OPEN) {
      resolve({ ok: false, kind: "disconnected", error: "bridge not connected" });
      return;
    }
    const id = nextId++;
    const payload = { ...obj, id };
    const timer = setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id);
        resolve({ ok: false, kind: "timeout", error: "bridge did not respond in time" });
      }
    }, timeout);
    pending.set(id, { resolve, timer, context });
    try {
      ws.send(JSON.stringify(payload));
    } catch (e) {
      clearTimeout(timer);
      pending.delete(id);
      resolve({ ok: false, kind: "disconnected", error: String(e) });
    }
  });
}

// Ask the bridge whether a Roblox Studio instance is actually connected to the
// MCP server. Broadcasts only on change so the UI updates promptly but quietly.
let studioProbing = false;
async function refreshStudioStatus() {
  if (studioProbing || !connected) return;
  studioProbing = true;
  try {
    const r = await send({ type: "studio_status" }, 12000);
    const v = r && r.ok && typeof r.studio === "boolean" ? r.studio : null;
    if (v !== studioConnected) {
      studioConnected = v;
      broadcastStatus();
    }
  } finally {
    studioProbing = false;
  }
}

function handleBridgeMessage(msg) {
  if ("studio" in msg && (typeof msg.studio === "boolean" || msg.studio === null)) {
    studioConnected = msg.studio;
  }
  if ("studio_app" in msg && (typeof msg.studio_app === "boolean" || msg.studio_app === null)) {
    studioApp = msg.studio_app;
  }
  if ("studio_proc" in msg && (typeof msg.studio_proc === "boolean" || msg.studio_proc === null)) {
    studioProc = msg.studio_proc;
  }
  if (msg.type === "studio_status") {
    resolvePending(msg.id, { ok: true, studio: studioConnected });
    broadcastStatus();
    return;
  }
  if (msg.type === "connected") {
    mcpAlive = !!msg.mcp_alive;
    generalAgent = !!msg.general_agent;
    robloxEnabled = !!msg.roblox_enabled;
    if ("agent_enabled" in msg) agentEnabled = !!msg.agent_enabled;
    if (Array.isArray(msg.tools)) toolsCache = msg.tools;
    if (Array.isArray(msg.servers)) serversCache = msg.servers;
    if (msg.agent_team && typeof msg.agent_team === "object") {
      agentTeamConfig = msg.agent_team;
      void ensureAgentTeamWindow(msg.agent_team);
    }
    if (msg.agent_enabled && ws && profileSyncedSocket !== ws) {
      const socket = ws;
      profileSyncedSocket = socket;
      profileReady.then(async () => {
        await agentTeamStateReady;
        if (ws !== socket || !connected) return;
        const result = await send({ type: "agent_set_profile", profile: agentProfile }, 10000);
        if (!result.ok && ws === socket) {
          profileSyncedSocket = null;
          log("could not restore agent profile after bridge reconnect", result.error);
        }
        for (const [tabId, profile] of agentProfilesByTab) {
          if (ws !== socket || !connected) return;
          if (!await chromeCallback(chrome.tabs.get, tabId)) { agentProfilesByTab.delete(tabId); continue; }
          const restored = await send({ type: "agent_set_profile", profile, session_id: `tab:${tabId}` }, 10000);
          if (!restored.ok) log("could not restore tab agent profile", { tabId, error: restored.error });
        }
        const activeTasks = [...agentTeamTasks.values()]
          .filter((task) => ["starting", "running"].includes(task.state))
          .sort((a, b) => (a.depth || 1) - (b.depth || 1));
        for (const task of activeTasks) {
          if (ws !== socket || !connected) return;
          if (!await chromeCallback(chrome.tabs.get, task.tabId)) continue;
          const registered = await send({ type: "agent_team_register", task_id: task.id,
            session_id: `tab:${task.tabId}`, parent_session_id: `tab:${task.parentTabId}`,
            team_session_id: teamSessionToken(),
            parent_task_id: task.parentTaskId || "", provider: task.provider,
            depth: task.depth, allow_children: task.allowChildren }, 10000);
          if (!registered.ok) {
            log("could not restore team task in bridge", { task_id: task.id, error: registered.error });
            continue;
          }
          if (task.state === "running") {
            const status = await send({ type: "agent_team_update", task_id: task.id,
              session_id: `tab:${task.tabId}`, team_session_id: teamSessionToken(), state: "running" }, 10000);
            if (!status.ok) log("could not restore running worker state", { task_id: task.id, error: status.error });
          }
        }
        persistAgentTeamState();
      });
    }
    broadcastStatus();
    return;
  }
  if (msg.type === "agent_tools") {
    agentEnabled = !!msg.enabled;
    if (Array.isArray(msg.tools)) agentToolsCache = msg.tools;
    resolvePending(msg.id, { ok: true, enabled: agentEnabled, tools: agentToolsCache });
    broadcastStatus();
    return;
  }
  if (msg.type === "pong") {
    resolvePending(msg.id, { ok: true });
    return;
  }
  if (msg.type === "tools") {
    if (Array.isArray(msg.tools)) toolsCache = msg.tools;
    if (Array.isArray(msg.servers)) serversCache = msg.servers;
    mcpAlive = !!msg.mcp_alive;
    resolvePending(msg.id, { ok: true, tools: toolsCache });
    broadcastStatus();
    return;
  }
  if (msg.type === "tool_result") {
    resolvePending(msg.id, msg.ok
      ? { ok: true, text: msg.text, images: msg.images || [] }
      : { ok: false, kind: msg.kind, error: msg.error });
    return;
  }
  if (msg.type === "agent_profile_result") {
    resolvePending(msg.id, { ok: !!msg.ok, profile: msg.profile, error: msg.error });
    return;
  }
  if (msg.type === "agent_team_result") {
    const result = { ...msg };
    delete result.type;
    delete result.id;
    resolvePending(msg.id, result);
    return;
  }
  if (msg.type === "agent_tool_result") {
    if (msg.ok && msg.result && msg.result.status === "approval_required") {
      const requestContext = pending.get(msg.id)?.context || {};
      const responseState = requestContext.responseState;
      agentApproval = {
        tool: msg.result.tool,
        capability: msg.result.capability,
        args: msg.result.args,
        sourceTabId: requestContext.tabId,
        sourceWindowId: requestContext.windowId,
        sessionId: requestContext.sessionId || "",
        responseState,
      };
      if (responseState) responseState.timer = setTimeout(() => {
        if (agentApproval?.responseState !== responseState) return;
        agentApproval = null;
        answerOnce(responseState, { ok: false, error: "approval request expired without a decision" });
        if (chrome.notifications) chrome.notifications.clear("zs-approval");
        broadcastStatus();
      }, 140000);
      announceAgentApproval(agentApproval);
    }
    resolvePending(msg.id, msg.ok
      ? { ok: true, result: msg.result }
      : { ok: false, kind: msg.kind, error: msg.error });
    return;
  }
  if (msg.type === "mcp_status") {
    mcpAlive = !!msg.alive;
    if (Array.isArray(msg.tools)) toolsCache = msg.tools;
    if (Array.isArray(msg.servers)) serversCache = msg.servers;
    resolvePending(msg.id, { ok: !!msg.ok, alive: msg.alive, error: msg.error });
    broadcastStatus();
    return;
  }
  if (msg.type === "server_changed") {
    // The bridge acks, then restarts itself to reload config.json. The socket
    // will drop right after this - the content script shows a spinner until the
    // reconnect lands and a fresh status arrives.
    resolvePending(msg.id, { ok: !!msg.ok, error: msg.error, restarting: !!msg.restarting });
    return;
  }
  if (msg.type === "error") {
    resolvePending(msg.id, { ok: false, error: msg.error });
    return;
  }
}

function resolvePending(id, value) {
  const p = pending.get(id);
  if (!p) return;
  clearTimeout(p.timer);
  pending.delete(id);
  p.resolve(value);
}

function failAllPending(reason) {
  for (const [, p] of pending) {
    clearTimeout(p.timer);
    p.resolve({ ok: false, kind: "disconnected", error: reason });
  }
  pending.clear();
}

// ── status push to any open DeepSeek tab + popup ─────────────────────────
function statusObj() {
  return { type: "zs-status", connected, extensionOnly, generalAgent, robloxEnabled, mcpAlive, studio: studioConnected, studioApp, studioProc, tools: toolsCache.length, agentEnabled, agentTools: agentToolsCache.length, agentApproval, agentProfile, agentTeam: agentTeamConfig, servers: serversCache };
}

function broadcastStatus() {
  chrome.runtime.sendMessage(statusObj()).catch(() => {});
  chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
    for (const t of tabs) chrome.tabs.sendMessage(t.id, statusObj()).catch(() => {});
  });
}

function requestedBrowserUrl(value) {
  if (value && typeof value === "object") value = value.url || value.href;
  let text = String(value == null ? "" : value).trim();
  text = text.replace(/^<|>$/g, "").replace(/^['"]|['"]$/g, "");
  if (/^www\./i.test(text)) text = `https://${text}`;
  return text;
}
function isAllowedBrowserUrl(value) {
  try {
    const parsed = new URL(requestedBrowserUrl(value));
    return (parsed.protocol === "http:" || parsed.protocol === "https:") && !!parsed.hostname;
  } catch { return false; }
}
function targetTabId(args, sender) {
  if (Number.isInteger(args.tabId)) return Promise.resolve(args.tabId);
  if (Number.isInteger(args.tab)) return Promise.resolve(args.tab);
  if (sender?.tab && Number.isInteger(sender.tab.id)) return Promise.resolve(sender.tab.id);
  return new Promise((resolve) => chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs) => resolve(tabs[0]?.id)));
}
function normalizeBrowserArgs(value, senderTabId) {
  const args = value && typeof value === "object" && !Array.isArray(value) ? { ...value } : {};
  if (args.id == null) {
    const aliasId = args.elementId ?? args.element_id ?? args.nodeId ?? args.node_id;
    if (aliasId != null) args.id = String(aliasId);
  }
  if (!Number.isInteger(args.tabId) && Number.isInteger(args.tab)) args.tabId = args.tab;
  if (!Number.isInteger(args.tabId) && Number.isInteger(args.targetTabId)) args.tabId = args.targetTabId;
  if (!Number.isInteger(args.tabId) && Number.isInteger(senderTabId)) args.tabId = senderTabId;
  delete args.elementId;
  delete args.element_id;
  delete args.nodeId;
  delete args.node_id;
  delete args.tab;
  delete args.targetTabId;
  return args;
}
function activateBrowserTab(tabId) {
  return new Promise((resolve) => {
    chrome.tabs.get(tabId, (tab) => {
      if (chrome.runtime.lastError || !tab) return resolve({ ok: false, error: chrome.runtime.lastError?.message || "target tab not found" });
      let finished = false;
      let timer = null;
      const done = (result) => {
        if (finished) return;
        finished = true;
        if (timer) clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(onUpdated);
        resolve(result);
      };
      const onUpdated = (updatedId, change) => { if (updatedId === tabId && change.status === "complete") setTimeout(() => done({ ok: true }), 350); };
      if (tab.status === "complete" && !tab.discarded) {
        chrome.tabs.update(tabId, { active: true }, () => {
          if (chrome.runtime.lastError) return done({ ok: false, error: chrome.runtime.lastError.message });
          chrome.windows.update(tab.windowId, { focused: true }, () => setTimeout(() => done({ ok: true }), 350));
        });
      } else {
        chrome.tabs.onUpdated.addListener(onUpdated);
        timer = setTimeout(() => done({ ok: false, error: "timed out waiting for target tab to load" }), 15000);
        chrome.tabs.update(tabId, { active: true }, () => {
          if (chrome.runtime.lastError) done({ ok: false, error: chrome.runtime.lastError.message });
          else chrome.windows.update(tab.windowId, { focused: true });
        });
      }
    });
  });
}
async function restoreAgentTab(sender, targetTabId, active) {
  const sourceId = sender?.tab?.id;
  if (active === false || !Number.isInteger(sourceId) || sourceId === targetTabId) return;
  try { await activateBrowserTab(sourceId); } catch {}
}
async function browserActionNeedsApproval(name, args, sender) {
  // Broad is activated only after two separate startup confirmations. It grants
  // browser actions for the session so the agent can complete tasks unattended.
  const tabProfile = Number.isInteger(sender?.tab?.id) ? agentProfilesByTab.get(sender.tab.id) : null;
  return (tabProfile || agentProfile) !== "broad";
}
async function extensionBrowserCall(name, args, sender) {
  if (name === "agent.browser.tabs.list") {
    return new Promise((resolve) => chrome.tabs.query({}, (tabs) => resolve({ ok: true, result: tabs.map((t) => ({ id: t.id, title: t.title || "", url: t.url || "", active: !!t.active, windowId: t.windowId })) })));
  }
  if (name === "agent.browser.tab.open") {
    if (!isAllowedBrowserUrl(args.url)) return Promise.resolve({ ok: false, error: "only http:// and https:// URLs are allowed" });
    const url = requestedBrowserUrl(args.url);
    const created = await new Promise((resolve) => chrome.tabs.create({ url, active: args.active !== false }, (tab) => {
      if (chrome.runtime.lastError) resolve({ ok: false, error: chrome.runtime.lastError.message });
      else resolve({ ok: true, tab });
    }));
    if (!created.ok) return created;
    if (args.active !== false) {
      const focus = await activateBrowserTab(created.tab.id);
      if (!focus.ok) return focus;
      await restoreAgentTab(sender, created.tab.id, true);
    }
    return { ok: true, result: { tabId: created.tab.id, url: created.tab.pendingUrl || created.tab.url || url } };
  }
  if (name === "agent.browser.tab.navigate") {
    if (!isAllowedBrowserUrl(args.url)) return Promise.resolve({ ok: false, error: "only http:// and https:// URLs are allowed" });
    const url = requestedBrowserUrl(args.url);
    const tabId = await targetTabId(args, sender);
    if (!Number.isInteger(tabId)) return { ok: false, error: "no target tab" };
    const tab = await new Promise((resolve) => chrome.tabs.update(tabId, { url, active: args.active !== false }, (updated) => resolve(chrome.runtime.lastError ? { error: chrome.runtime.lastError.message } : { tab: updated })));
    if (tab.error) return { ok: false, error: tab.error };
    if (args.active !== false) {
      const focus = await activateBrowserTab(tabId);
      if (!focus.ok) return focus;
      await restoreAgentTab(sender, tabId, true);
    }
    return { ok: true, result: { tabId, url } };
  }
  if (name === "agent.browser.screenshot") {
    const tabId = await targetTabId(args, sender);
    if (!Number.isInteger(tabId)) return { ok: false, error: "no target tab" };
    const tab = await new Promise((resolve) => chrome.tabs.get(tabId, (value) => resolve(chrome.runtime.lastError ? { error: chrome.runtime.lastError.message } : { tab: value })));
    if (tab.error) return { ok: false, error: tab.error };
    if (args.active === false) return { ok: false, error: "screenshot requires the target tab to be visible; omit active:false" };
    const focus = await activateBrowserTab(tabId);
    if (!focus.ok) return focus;
    try {
      const viewport = await new Promise((resolve) => chrome.tabs.sendMessage(tabId, { type: "zs-browser-action", action: "viewport" }, (value) => resolve(chrome.runtime.lastError ? null : value?.result || null)));
      const dataUrl = await new Promise((resolve) => chrome.tabs.captureVisibleTab(tab.tab.windowId, { format: "jpeg", quality: 55 }, (image) => resolve(chrome.runtime.lastError ? { error: chrome.runtime.lastError.message } : { image })));
      if (dataUrl.error) return { ok: false, error: dataUrl.error };
      const comma = dataUrl.image.indexOf(",");
      if (comma < 0) return { ok: false, error: "browser returned an invalid screenshot" };
      const viewportNote = viewport ? ` CSS viewport ${viewport.width}x${viewport.height}, devicePixelRatio ${viewport.devicePixelRatio}. If using screenshot pixel coordinates, call click_at with coordinate_space:"image".` : " Use CSS viewport coordinates for click_at.";
      return { ok: true, text: `Visible viewport screenshot captured from tab ${tabId}.${viewportNote}`, images: [{ data: dataUrl.image.slice(comma + 1), mimeType: "image/jpeg" }] };
    } finally {
      await restoreAgentTab(sender, tabId, true);
    }
  }
  const action = name.slice("agent.browser.".length);
  const tabId = await targetTabId(args, sender);
  if (!Number.isInteger(tabId)) return { ok: false, error: "no target tab" };
  if (args.active !== false) {
    const focus = await activateBrowserTab(tabId);
    if (!focus.ok) return focus;
  }
  const result = await new Promise((resolve) => chrome.tabs.sendMessage(tabId, { type: "zs-browser-action", action, ...args }, (r) => {
    if (chrome.runtime.lastError) resolve({ ok: false, error: chrome.runtime.lastError.message });
    else resolve(r || { ok: false, error: "empty browser response" });
  }));
  await restoreAgentTab(sender, tabId, args.active !== false);
  return result;
}
if (chrome.notifications) chrome.notifications.onClicked.addListener((notificationId) => {
  if (notificationId === "zs-approval" && agentApproval) {
    chrome.notifications.clear(notificationId);
    if (Number.isInteger(agentApproval.sourceTabId)) chrome.tabs.update(agentApproval.sourceTabId, { active: true }, () => {
      if (!chrome.runtime.lastError && Number.isInteger(agentApproval.sourceWindowId)) chrome.windows.update(agentApproval.sourceWindowId, { focused: true });
    });
  }
});

// ── messages from content.js / popup.js ─────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    switch (msg.type) {
      case "status":
        if (!connected) connect(); // self-heal after a worker wake-up
        sendResponse(statusObj());
        break;
      case "set_extension_only": {
        extensionOnly = !!msg.enabled;
        chrome.storage?.local?.set({ extensionOnly });
        broadcastStatus();
        sendResponse({ ok: true, enabled: extensionOnly });
        break;
      }
      case "list_tools": {
        await agentTeamStateReady;
        // Prefer a live refresh; fall back to cache so the loop never stalls.
        // 10s, not 25s: a catalogue request only blocks this long when one of the
        // MCP servers is dead (typically Roblox in a degraded, Blender-only
        // session), and in that exact case we already hold a perfectly good cached
        // catalogue. Waiting the full 25s just froze the boot for no new data.
        if (extensionOnly) {
          sendResponse({ ok: true, tools: EXTENSION_BROWSER_TOOLS.filter((tool) => tool.name !== "agent.browser.screenshot") });
          break;
        }
        const sessionId = sessionIdFor(sender);
        const ownTaskId = agentTabTasks.get(sender?.tab?.id);
        const ownTask = ownTaskId ? agentTeamTasks.get(ownTaskId) : null;
        const [r, ar] = await Promise.all([
          send({ type: "list_tools" }, 10000),
          send({ type: "agent_list_tools", session_id: sessionId }, 10000),
        ]);
        if (r.ok) toolsCache = r.tools || toolsCache;
        const cacheKey = sessionId || "__default__";
        let sessionAgentTools = agentToolsCacheBySession.get(cacheKey) || agentToolsCache;
        if (ar.ok) {
          agentEnabled = !!ar.enabled;
          sessionAgentTools = ar.tools || [];
          agentToolsCacheBySession.set(cacheKey, sessionAgentTools);
          if (!sessionId) agentToolsCache = sessionAgentTools;
        }
        const visibleAgentTools = sessionAgentTools.filter((t) => !ownTask || childMayUseTool(t.name)).map((t) => ({
            name: `agent.${t.name}`,
            description: `[local agent] ${t.description || ""}`,
            inputSchema: t.input_schema || { type: "object" },
          }));
        const teamTools = ownTask && !ownTask.allowChildren ? EXTENSION_TEAM_TOOLS.filter((tool) => tool.name !== "agent.team.spawn") : EXTENSION_TEAM_TOOLS;
        const merged = [...(ownTask ? [] : toolsCache), ...visibleAgentTools, ...teamTools, ...(ownTask ? [] : EXTENSION_BROWSER_TOOLS)];
        sendResponse({ ok: r.ok || ar.ok, tools: merged, error: r.ok ? undefined : r.error });
        break;
      }
      case "set_agent_profile": {
        await agentTeamStateReady;
        await profileReady;
        const profile = msg.profile;
        if (!["basic", "development", "broad"].includes(profile)) {
          sendResponse({ ok: false, error: "invalid capability profile" });
          break;
        }
        const sessionId = sessionIdFor(sender);
        const r = await send({ type: "agent_set_profile", profile, session_id: sessionId }, 10000);
        if (r.ok) {
          agentProfile = r.profile || profile;
          if (chrome.storage?.session) chrome.storage.session.set({ agentProfile });
          if (Number.isInteger(sender?.tab?.id)) {
            agentProfilesByTab.set(sender.tab.id, agentProfile);
            persistAgentTeamState();
          }
          broadcastStatus();
        }
        sendResponse(r);
        break;
      }
      case "call_tool": {
        if (extensionOnly && !String(msg.name || "").startsWith("agent.browser.")) {
          sendResponse({ ok: false, error: "This tool is unavailable in extension-only mode; switch back to Bridge mode for local tools." });
          break;
        }
        await agentTeamStateReady;
        await profileReady;
        const timeout = (msg.timeout || 120000) + 10000;
        const local = typeof msg.name === "string" && msg.name.startsWith("agent.");
        const ownTaskId = agentTabTasks.get(sender?.tab?.id);
        const ownTask = ownTaskId ? agentTeamTasks.get(ownTaskId) : null;
        if (typeof msg.name === "string" && msg.name.startsWith("agent.team.")) {
          if (ownTask && msg.name === "agent.team.spawn" && !ownTask.allowChildren) {
            sendResponse({ ok: false, error: "this worker was not explicitly authorized to spawn child agents" });
            break;
          }
          sendResponse(teamToolResponse(await teamCall(msg.name, msg.arguments || {}, sender)));
          break;
        }
        if (ownTask && (!local || !childMayUseTool(msg.name))) {
          sendResponse({ ok: false, error: "worker isolation permits only read-only diagnostics and workspace file reads" });
          break;
        }
        if (typeof msg.name === "string" && msg.name.startsWith("agent.browser.")) {
          const responseState = { sendResponse, replied: false, timer: null };
          const browserArgs = normalizeBrowserArgs(msg.arguments, sender?.tab?.id);
          const readOnly = ["agent.browser.snapshot", "agent.browser.tabs.list", "agent.browser.tab.open", "agent.browser.tab.navigate", "agent.browser.wait", "agent.browser.scroll", "agent.browser.screenshot"].includes(msg.name);
          if (!readOnly && !msg.approved && await browserActionNeedsApproval(msg.name, browserArgs, sender)) {
            const approvalArgs = { ...browserArgs };
            if (agentApproval) { answerOnce(responseState, { ok: false, error: "another action is already awaiting approval" }); break; }
            agentApproval = { extension: true, tool: msg.name, capability: "browser.control", args: approvalArgs, sourceTabId: sender?.tab?.id, sourceWindowId: sender?.tab?.windowId, responseState };
            responseState.timer = setTimeout(() => {
              if (agentApproval?.responseState !== responseState) return;
              agentApproval = null;
              answerOnce(responseState, { ok: false, error: "approval request expired without a decision" });
              if (chrome.notifications) chrome.notifications.clear("zs-approval");
              broadcastStatus();
            }, 140000);
            announceAgentApproval(agentApproval);
            break;
          }
          answerOnce(responseState, await extensionBrowserCall(msg.name, browserArgs, sender));
          break;
        }
        const responseState = { sendResponse, replied: false, timer: null };
        const sessionId = sessionIdFor(sender);
        const r = await send(local
          ? { type: "agent_call_tool", name: msg.name.slice("agent.".length), arguments: msg.arguments, approved: !!msg.approved, session_id: sessionId }
          : { type: "call_tool", name: msg.name, arguments: msg.arguments, timeout: msg.timeout }, timeout,
          { tabId: sender?.tab?.id, windowId: sender?.tab?.windowId, sessionId, responseState });
        if (r?.result?.status !== "approval_required") answerOnce(responseState, r);
        break;
      }
      case "approve_agent": {
        if (!agentApproval) {
          sendResponse({ ok: false, error: "no pending agent approval" });
          break;
        }
        const approval = agentApproval;
        agentApproval = null;
        if (approval.responseState?.timer) {
          clearTimeout(approval.responseState.timer);
          approval.responseState.timer = null;
        }
        if (chrome.notifications) chrome.notifications.clear("zs-approval");
        let r;
        try {
          r = approval.extension
            ? await extensionBrowserCall(approval.tool, approval.args, sender)
            : await send({
                type: "agent_call_tool",
                name: approval.tool,
                arguments: approval.args,
                approved: true,
                session_id: approval.sessionId || "",
              }, approval.tool === "terminal.run" ? Math.min(120, Math.max(1, Number(approval.args?.timeout) || 120)) * 1000 + 10000 : 130000);
        } catch (error) {
          r = { ok: false, kind: "approval_execution_failed", error: String(error && error.message || error) };
        }
        answerOnce(approval.responseState, r);
        broadcastStatus();
        sendResponse({ ...r, approvalConsumed: true });
        break;
      }
      case "reject_agent": {
        if (!agentApproval) {
          sendResponse({ ok: false, error: "no pending agent approval" });
          break;
        }
        const rejected = agentApproval;
        agentApproval = null;
        if (rejected.responseState?.timer) {
          clearTimeout(rejected.responseState.timer);
          rejected.responseState.timer = null;
        }
        answerOnce(rejected.responseState, { ok: false, kind: "approval_rejected", error: "the user rejected this action; do not retry it" });
        if (chrome.notifications) chrome.notifications.clear("zs-approval");
        broadcastStatus();
        sendResponse({ ok: true, rejected: { tool: rejected.tool, capability: rejected.capability } });
        break;
      }
      case "agent_team_child_ready": {
        await agentTeamStateReady;
        const task = agentTeamTasks.get(String(msg.task_id || ""));
        const tabId = sender?.tab?.id;
        if (!task || task.tabId !== tabId) { sendResponse({ ok: false, error: "unknown task or wrong worker tab" }); break; }
        if (isTerminalTeamState(task.state)) { sendResponse({ ok: false, fatal: true, error: "team task is already terminal" }); break; }
        const sessionId = sessionIdFor(sender);
        const result = await send({ type: "agent_set_profile", profile: "basic", session_id: sessionId }, 10000);
        if (!result.ok) {
          task.state = "failed"; task.phase = "failed"; task.error = result.error || "could not initialize isolated worker profile"; task.updatedAt = Date.now();
          persistAgentTeamState(); notifyTeamTaskChanged(task); sendResponse({ ok: false, fatal: true, error: task.error }); break;
        }
        const parentSessionId = `tab:${task.parentTabId}`;
        const registered = await send({
          type: "agent_team_register", task_id: task.id, session_id: sessionId,
          team_session_id: teamSessionToken(),
          parent_session_id: parentSessionId, parent_task_id: task.parentTaskId || "",
          provider: task.provider, depth: task.depth, allow_children: task.allowChildren,
        }, 12000);
        if (!registered.ok) {
          task.state = "failed"; task.phase = "failed"; task.error = registered.error || "bridge rejected worker registration"; task.updatedAt = Date.now();
          persistAgentTeamState(); notifyTeamTaskChanged(task); sendResponse({ ok: false, fatal: true, error: task.error }); break;
        }
        agentProfilesByTab.set(tabId, "basic");
        task.state = "starting"; task.phase = "provider_bootstrap"; task.updatedAt = Date.now();
        persistAgentTeamState();
        sendResponse({ ok: true, session_id: sessionId });
        break;
      }
      case "agent_team_worker_started": {
        await agentTeamStateReady;
        const task = agentTeamTasks.get(String(msg.task_id || ""));
        if (!task || task.tabId !== sender?.tab?.id) { sendResponse({ ok: false, error: "unknown task or wrong worker tab" }); break; }
        if (isTerminalTeamState(task.state)) { sendResponse({ ok: false, error: "team task is already terminal" }); break; }
        const ready = await send({ type: "agent_team_update", task_id: task.id,
          session_id: sessionIdFor(sender), team_session_id: teamSessionToken(), state: "running" }, 10000);
        if (!ready.ok) { sendResponse({ ok: false, error: ready.error || "bridge could not mark worker ready" }); break; }
        task.state = "running"; task.phase = "running"; task.updatedAt = Date.now();
        persistAgentTeamState();
        sendResponse({ ok: true, task: publicTeamTask(task) });
        break;
      }
      case "agent_team_complete": {
        await agentTeamStateReady;
        const task = agentTeamTasks.get(String(msg.task_id || ""));
        if (!task || task.tabId !== sender?.tab?.id) { sendResponse({ ok: false, error: "unknown task or wrong worker tab" }); break; }
        const state = ["completed", "failed", "stopped", "cancelled"].includes(msg.state) ? msg.state : "completed";
        task.state = state;
        task.result = String(msg.result || "").slice(0, 12000);
        task.error = String(msg.error || "").slice(0, 2000);
        task.phase = state;
        task.updatedAt = Date.now();
        persistAgentTeamState();
        notifyTeamTaskChanged(task);
        void send({ type: "agent_team_update", task_id: task.id, session_id: sessionIdFor(sender),
          team_session_id: teamSessionToken(), state, result: task.result, error: task.error }, 10000).then((r) => {
            if (!r.ok) log("could not sync worker completion to bridge", { task_id: task.id, error: r.error });
          });
        sendResponse({ ok: true, task: publicTeamTask(task) });
        break;
      }
      case "restart_mcp": {
        const r = await send({ type: "restart_mcp" }, 30000);
        sendResponse(r);
        break;
      }
      case "add_server": {
        const r = await send({
          type: "add_server", server_id: msg.server_id,
          command: msg.command, args: msg.args, env: msg.env,
        }, 15000);
        sendResponse(r);
        break;
      }
      case "remove_server": {
        const r = await send({ type: "remove_server", server_id: msg.server_id }, 15000);
        sendResponse(r);
        break;
      }
      case "reconnect":
        reconnectDelay = RECONNECT_MIN;
        connect();
        sendResponse({ ok: true });
        break;
      default:
        sendResponse({ ok: false, error: "unknown message" });
    }
  })();
  return true; // async sendResponse
});

// Wake/keepalive hooks.
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
if (chrome.tabs?.onRemoved?.addListener) chrome.tabs.onRemoved.addListener((tabId) => {
  void (async () => {
    await agentTeamStateReady;
    const taskId = agentTabTasks.get(tabId);
    if (taskId) {
      const task = agentTeamTasks.get(taskId);
      if (task && !isTerminalTeamState(task.state)) {
        task.state = "failed";
        task.phase = "tab_closed";
        task.error = "worker tab closed before the task reached a terminal state";
        task.updatedAt = Date.now();
        notifyTeamTaskChanged(task);
        void send({ type: "agent_team_update", task_id: task.id, session_id: `tab:${tabId}`,
          team_session_id: teamSessionToken(), state: "failed", error: task.error }, 10000);
      }
      agentTabTasks.delete(tabId);
    }
    agentProfilesByTab.delete(tabId);
    persistAgentTeamState();
  })();
});

connect();
