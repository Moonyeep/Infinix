const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "background.js"), "utf8");
function declaration(prefix, name) {
  const start = source.indexOf(`${prefix} ${name}(`);
  assert.notEqual(start, -1, `${name} declaration should exist`);
  const end = source.indexOf("\n}", start);
  assert.notEqual(end, -1, `${name} declaration should end at top-level`);
  return source.slice(start, end + 2);
}

const bridgeCalls = [];
const context = {
  agentTeamStateReady: Promise.resolve(),
  agentTeamTasks: new Map(),
  agentTabTasks: new Map(),
  agentTeamWaiters: new Map(),
  agentTeamConfig: { session_id: "0123456789abcdef", enabled: true, allowed_providers: ["gemini"], max_agents: 1 },
  connected: true,
  agentEnabled: true,
  AGENT_PROVIDER_URLS: { gemini: "https://example.invalid" },
  agentProfilesByTab: new Map(),
  persistAgentTeamState() {},
  createDedicatedAgentTab: async () => ({ id: 501 }),
  sendDelegatedTask: async () => ({ ok: true }),
  setTimeout,
  clearTimeout,
  crypto: { randomUUID: () => "12345678-1234-1234-1234-123456789abc" },
  send: async (request) => {
    bridgeCalls.push(request);
    if (request.type === "agent_team_inbox") {
      const messages = request.session_id === "tab:101"
        ? [{ sequence: 2, from_task_id: "task_root_child", direction: "from_supervisor", text: "Please include evidence." }]
        : [{ sequence: 1, from_task_id: "task_root_child", direction: "from_child", text: "Finding sent upward." }];
      return { ok: true, task_id: request.session_id === "tab:101" ? "task_root_child" : null,
        messages: messages.filter((message) => message.sequence > request.after_sequence),
        next_sequence: Math.max(request.after_sequence, ...messages.map((message) => message.sequence)) };
    }
    return { ok: true, sequence: 3, delivered_to: request.target_task_id };
  },
};
const code = [
  "let teamSpawnReservations = 0;",
  declaration("function", "childMayUseTool"),
  declaration("function", "isTerminalTeamState"),
  declaration("function", "notifyTeamTaskChanged"),
  declaration("function", "waitForTeamTask"),
  declaration("function", "publicTeamTask"),
  declaration("function", "teamToolResponse"),
  declaration("function", "publicTeamTree"),
  declaration("function", "teamTreeSummary"),
  declaration("function", "teamTaskVisibleTo"),
  declaration("async function", "spawnAgentTask"),
  declaration("function", "sessionIdFor"),
  declaration("function", "teamSessionToken"),
  declaration("async function", "teamCall"),
  "globalThis.childMayUseTool = childMayUseTool; globalThis.teamCall = teamCall; globalThis.spawnAgentTask = spawnAgentTask; globalThis.teamToolResponse = teamToolResponse; globalThis.waitForTeamTask = waitForTeamTask; globalThis.notifyTeamTaskChanged = notifyTeamTaskChanged; globalThis.getSpawnReservations = () => teamSpawnReservations;",
].join("\n");
vm.runInNewContext(code, context);

assert.equal(context.childMayUseTool("file.read"), true);
assert.equal(context.childMayUseTool("file.list"), true);
assert.equal(context.childMayUseTool("diagnostics.system_info"), true);
assert.equal(context.childMayUseTool("agent.diagnostics.network"), true);
assert.equal(context.childMayUseTool("diagnostics.action"), false);
assert.equal(context.childMayUseTool("terminal.run"), false);
assert.equal(context.childMayUseTool("file.write"), false);
assert.equal(context.childMayUseTool("agent.browser.click"), false);
assert.equal(JSON.parse(JSON.stringify(context.teamToolResponse({ ok: true, task_id: "task_x", state: "starting" }))).result.task_id, "task_x",
  "team tool payload must use the result envelope consumed by the agent loop");
assert.equal(context.teamToolResponse({ ok: false, error: "bad input" }).error, "bad input");
assert.match(source, /teamToolResponse\(await teamCall/);
assert.match(source, /state: "minimized"/);
assert.match(source, /active: false \}\);/);
assert.match(source, /type: "agent_list_tools", session_id: sessionId/);
assert.match(source, /approved: !!msg\.approved, session_id: sessionId/);
assert.match(source, /120000/);
assert.match(source, /agent_team_register/);
assert.match(source, /agent_team_worker_started/);
assert.match(source, /task\.state = "starting"/);
assert.match(source, /agent_team_message/);
assert.match(source, /agent_team_inbox/);
assert.match(source, /team_session_id: teamSessionToken\(\)/);
assert.doesNotMatch(source, /while \(!isTerminalTeamState\(task\.state\).*setTimeout/);

const rootTask = {
  id: "task_root_child", provider: "gemini", parentTabId: 10, tabId: 101,
  parentTaskId: "", depth: 1, state: "completed", createdAt: 1, updatedAt: 2,
  allowChildren: false, result: "finding A", error: "",
};
const siblingTask = {
  id: "task_other_parent", provider: "qwen", parentTabId: 20, tabId: 201,
  parentTaskId: "", depth: 1, state: "running", createdAt: 1, updatedAt: 1,
  allowChildren: false, result: "", error: "",
};
const childTask = {
  id: "task_grandchild", provider: "deepseek", parentTabId: 101, tabId: 102,
  parentTaskId: rootTask.id, depth: 2, state: "completed", createdAt: 1, updatedAt: 2,
  allowChildren: false, result: "finding child", error: "",
};
context.agentTeamTasks.set(rootTask.id, rootTask);
context.agentTeamTasks.set(siblingTask.id, siblingTask);
context.agentTeamTasks.set(childTask.id, childTask);
context.agentTabTasks.set(101, rootTask.id);
context.agentTabTasks.set(102, childTask.id);
context.agentTabTasks.set(201, siblingTask.id);

(async () => {
  const rootSender = { tab: { id: 10 } };
  // Hold tab creation at its first await; the next simultaneous request must
  // observe the reserved slot rather than pass the same active-count check.
  context.agentTeamTasks.clear();
  context.agentTabTasks.clear();
  let resolveTab;
  let announceTabCreation;
  const tabCreationStarted = new Promise((resolve) => { announceTabCreation = resolve; });
  context.createDedicatedAgentTab = () => {
    announceTabCreation();
    return new Promise((resolve) => { resolveTab = resolve; });
  };
  const firstSpawn = context.spawnAgentTask({ provider: "gemini", task: "inspect A" }, rootSender);
  await tabCreationStarted;
  assert.equal(context.getSpawnReservations(), 1);
  const rejectedSpawn = await context.spawnAgentTask({ provider: "gemini", task: "inspect B" }, rootSender);
  assert.equal(rejectedSpawn.ok, false);
  assert.match(rejectedSpawn.error, /concurrency limit/);
  resolveTab({ id: 501 });
  const acceptedSpawn = await firstSpawn;
  assert.equal(acceptedSpawn.ok, true);
  assert.equal(context.getSpawnReservations(), 0);
  context.agentTeamTasks.clear();
  context.agentTabTasks.clear();
  for (const fixture of [rootTask, siblingTask, childTask]) context.agentTeamTasks.set(fixture.id, fixture);
  context.agentTabTasks.set(101, rootTask.id);
  context.agentTabTasks.set(102, childTask.id);
  context.agentTabTasks.set(201, siblingTask.id);

  const ownStatus = await context.teamCall("agent.team.status", {}, rootSender);
  assert.equal(ownStatus.children.length, 1);
  assert.equal(ownStatus.children[0].task_id, rootTask.id);
  assert.equal(ownStatus.children[0].depth, 1);
  const hierarchical = await context.teamCall("agent.team.status", { include_descendants: true }, rootSender);
  assert.equal(hierarchical.tree[0].children[0].task_id, childTask.id);
  assert.equal(hierarchical.summary.total_tasks, 2);
  assert.equal(hierarchical.summary.by_state.completed, 2);
  assert.equal((await context.teamCall("agent.team.status", { task_id: siblingTask.id }, rootSender)).ok, false,
    "supervisor must not inspect another supervisor's child");
  assert.equal((await context.teamCall("agent.team.wait", { task_id: siblingTask.id, timeout_ms: 1000 }, rootSender)).ok, false,
    "wait must be restricted to direct children");
  assert.equal((await context.teamCall("agent.team.wait", { task_id: rootTask.id, timeout_ms: 1000 }, rootSender)).task.state, "completed");

  const pendingWait = context.waitForTeamTask(siblingTask, 1000);
  siblingTask.state = "completed";
  context.notifyTeamTaskChanged(siblingTask);
  assert.equal(await pendingWait, false, "waiter wakes from terminal event rather than a timer loop");
  assert.equal(context.agentTeamWaiters.size, 0);

  const sentToChild = await context.teamCall("agent.team.message", { task_id: rootTask.id, message: "Please include evidence." }, rootSender);
  assert.equal(sentToChild.ok, true);
  assert.equal(bridgeCalls.at(-1).type, "agent_team_message");
  assert.equal(bridgeCalls.at(-1).session_id, "tab:10");
  assert.equal(bridgeCalls.at(-1).team_session_id, "0123456789abcdef");
  assert.equal(bridgeCalls.at(-1).target_task_id, rootTask.id);
  assert.equal(typeof bridgeCalls.at(-1).message_id, "string");
  assert.equal((await context.teamCall("agent.team.message", { task_id: siblingTask.id, message: "unauthorized" }, rootSender)).ok, false);

  const workerSender = { tab: { id: 101 } };
  assert.equal((await context.teamCall("agent.team.message", { task_id: "supervisor", message: "Finding sent upward." }, workerSender)).ok, true);
  assert.equal(bridgeCalls.at(-1).session_id, "tab:101");
  assert.equal(bridgeCalls.at(-1).target_task_id, "supervisor");
  const workerInbox = await context.teamCall("agent.team.inbox", { after_sequence: 1 }, workerSender);
  assert.equal(bridgeCalls.at(-1).type, "agent_team_inbox");
  assert.equal(bridgeCalls.at(-1).after_sequence, 1);
  assert.equal(bridgeCalls.at(-1).team_session_id, "0123456789abcdef");
  assert.equal(workerInbox.messages.length, 1);
  assert.equal(workerInbox.messages[0].direction, "from_supervisor");
  const rootInbox = await context.teamCall("agent.team.inbox", {}, rootSender);
  assert.equal(rootInbox.messages[0].text, "Finding sent upward.");
  console.log("agent team bridge messaging, startup, background wait, access, and hierarchy tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
