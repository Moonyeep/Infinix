// SPDX-License-Identifier: GPL-3.0-or-later
const KOFI_URL = "https://ko-fi.com/moonyeep";
const SUPPORTED_HOSTS = ["chat.deepseek.com", "deepseek.com", "chatgpt.com", "chat.openai.com", "gemini.google.com", "www.kimi.ai", "kimi.ai", "chat.z.ai", "chat.qwen.ai", "arena.ai", "www.meta.ai", "meta.ai"];
const DEFAULT_AI_URL = "https://chat.deepseek.com/";
document.getElementById("ver").textContent = `v${chrome.runtime.getManifest().version}`;
function redact(value) {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, val]) => [key, /pass(word)?|secret|token|credential|api.?key/i.test(key) ? "[REDACTED]" : redact(val)]));
  return value;
}
function render(s) {
  window.__extensionOnly = !!s.extensionOnly;
  const dot = document.getElementById("dot"), state = document.getElementById("state"), tools = document.getElementById("tools"), agent = document.getElementById("agent"), team = document.getElementById("team"), servers = document.getElementById("servers");
  const pending = s.agentApproval;
  const list = s.servers || [], up = list.filter((x) => x.alive).length;
  const mcpOk = s.connected && (s.mcpAlive || up > 0 || s.tools > 0);
  const studioOff = mcpOk && s.studio === false;
  const modeButton = document.getElementById("extensionMode");
  if (modeButton) modeButton.textContent = s.extensionOnly ? "✓ Somente extensão ativo · voltar à Bridge" : "Usar somente extensão (opcional)";
  dot.className = "dot " + (s.extensionOnly ? "on" : s.connected ? (mcpOk && !studioOff ? "on" : "warn") : "");
  state.textContent = s.extensionOnly ? "Somente extensão · bridge não necessária" : s.connected ? (mcpOk && !studioOff ? "Connected · services ready" : studioOff ? "Studio not connected" : "Bridge connected") : "Bridge offline";
  tools.textContent = s.extensionOnly ? "Automação de navegador · sem ferramentas locais" : s.connected ? `${s.tools || 0} ferramentas disponíveis` : "Inicie a bridge Infinix";
  agent.textContent = s.extensionOnly ? "Bridge mode continua disponível ao desativar esta opção" : s.connected ? (s.agentEnabled ? `Local agent · ${s.agentTools || 0} tools` : "Local agent disabled") : "";
  const teamConfig = s.agentTeam || s.agent_team;
  team.textContent = teamConfig?.enabled
    ? `Agentes: ${(teamConfig.selected_providers || []).join(", ") || "sob demanda"} · janela dedicada`
    : "Equipe multiagente não configurada";
  const box = document.getElementById("approval");
  box.style.display = pending ? "block" : "none";
  document.getElementById("approve").disabled = document.getElementById("reject").disabled = !pending;
  if (pending) {
    document.getElementById("approvalSummary").textContent = `${pending.tool} · ${pending.capability}`;
    document.getElementById("approvalArgs").textContent = JSON.stringify(redact(pending.args || {}), null, 2);
  }
  servers.textContent = s.connected ? list.map((x) => `${x.alive ? "●" : "○"} ${x.id} (${x.alive ? x.tools + " tools" : "down"})`).join("\n") : "";
}
function refresh() { chrome.runtime.sendMessage({ type: "status" }, (s) => s && render(s)); }
function approvalAction(type, button, otherButton, busy, success) {
  button.disabled = otherButton.disabled = true; button.textContent = busy;
  chrome.runtime.sendMessage({ type }, (r) => {
    if (chrome.runtime.lastError) {
      button.textContent = type === "approve_agent" ? "Estado incerto — não repetir" : "Falha ao rejeitar";
      if (type !== "approve_agent") button.disabled = otherButton.disabled = false;
      return;
    }
    if (r && r.ok) { button.textContent = success; setTimeout(refresh, 300); }
    else if (r?.approvalConsumed) { button.textContent = r.error || "Execução falhou; aprovação consumida"; setTimeout(refresh, 300); }
    else { button.disabled = otherButton.disabled = false; button.textContent = r?.error || "Falha — tente novamente"; }
  });
}
document.getElementById("approve").addEventListener("click", (e) => approvalAction("approve_agent", e.currentTarget, document.getElementById("reject"), "Executando…", "Ação executada"));
document.getElementById("reject").addEventListener("click", (e) => approvalAction("reject_agent", e.currentTarget, document.getElementById("approve"), "Rejeitando…", "Ação rejeitada"));
document.getElementById("extensionMode").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "set_extension_only", enabled: !window.__extensionOnly }, (r) => { if (r?.ok) { window.__extensionOnly = r.enabled; setTimeout(refresh, 100); } });
});
document.getElementById("reconnect").addEventListener("click", () => chrome.runtime.sendMessage({ type: "reconnect" }, () => setTimeout(refresh, 600)));
document.getElementById("restart").addEventListener("click", (e) => { e.currentTarget.textContent = "Restarting…"; chrome.runtime.sendMessage({ type: "restart_mcp" }, () => setTimeout(refresh, 600)); });
document.getElementById("kofi").addEventListener("click", () => chrome.tabs.create({ url: KOFI_URL }));
document.getElementById("settings").addEventListener("click", () => chrome.tabs.query({}, (tabs) => {
  const active = tabs.find((t) => t.active && t.url && SUPPORTED_HOSTS.some((h) => t.url.includes(h)));
  const any = active || tabs.find((t) => t.url && SUPPORTED_HOSTS.some((h) => t.url.includes(h)));
  if (any) {
    chrome.tabs.sendMessage(any.id, { type: "zs-open-menu" }, () => {
      if (chrome.runtime.lastError) {
        // Don't reload automatically: the user may have an unsent draft.
        document.getElementById("state").textContent = "Infinix ainda não está carregado nesta aba. Salve o rascunho e recarregue a página; depois abra Settings novamente.";
        return;
      }
      chrome.tabs.update(any.id, { active: true });
    });
  } else chrome.tabs.create({ url: DEFAULT_AI_URL });
}));
chrome.runtime.onMessage.addListener((msg) => { if (msg?.type === "zs-status") render(msg); });
refresh();
setInterval(refresh, 1500);
