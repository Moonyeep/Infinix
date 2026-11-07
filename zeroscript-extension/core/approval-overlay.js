// SPDX-License-Identifier: GPL-3.0-or-later
// In-page approval dialog: only rendered in the AI tab that initiated a request.
(() => {
  "use strict";
  const ROOT_ID = "zs-approval-modal";
  const root = () => document.getElementById(ROOT_ID);
  function redact(value) {
    if (Array.isArray(value)) return value.map(redact);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, val]) => [key, /pass(word)?|secret|token|credential|api.?key/i.test(key) ? "[REDACTED]" : redact(val)]));
    return value;
  }
  function close() { root()?.remove(); }
  function show(request) {
    close();
    const backdrop = document.createElement("div");
    backdrop.id = ROOT_ID;
    backdrop.setAttribute("role", "presentation");
    Object.assign(backdrop.style, {
      position: "fixed", inset: "0", zIndex: "2147483647", display: "grid", placeItems: "center",
      padding: "20px", background: "rgba(25,22,36,.24)", backdropFilter: "blur(16px) saturate(1.25)", WebkitBackdropFilter: "blur(16px) saturate(1.25)", fontFamily: "-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',sans-serif",
    });
    const card = document.createElement("section");
    card.setAttribute("role", "dialog"); card.setAttribute("aria-modal", "true"); card.setAttribute("aria-labelledby", "zs-approval-title");
    Object.assign(card.style, { boxSizing: "border-box", width: "min(620px, 100%)", maxHeight: "88vh", overflow: "auto", padding: "26px", color: "#1d1d1f", background: "linear-gradient(145deg,rgba(255,255,255,.9),rgba(248,247,252,.8))", border: "1px solid rgba(255,255,255,.8)", borderRadius: "22px", boxShadow: "0 24px 72px rgba(29,24,48,.22),inset 0 1px rgba(255,255,255,.95)", backdropFilter: "blur(32px) saturate(1.55)", WebkitBackdropFilter: "blur(32px) saturate(1.55)" });
    const title = document.createElement("h2"); title.id = "zs-approval-title"; title.textContent = "Aprovação necessária";
    Object.assign(title.style, { margin: "0 0 9px", fontSize: "21px", lineHeight: "1.25", letterSpacing: "-.45px", fontWeight: "700" });
    const warning = document.createElement("p"); warning.textContent = "Confira a ação. Nada será executado até você aprovar.";
    Object.assign(warning.style, { color: "#9a4c18", margin: "0 0 14px", fontSize: "14px", lineHeight: "1.45" });
    const summary = document.createElement("div"); summary.textContent = `${request.tool || "Ação"} · ${request.capability || "permissão"}`;
    Object.assign(summary.style, { font: "600 13px ui-monospace,monospace", color: "#35313d", overflowWrap: "anywhere", marginBottom: "10px" });
    const args = document.createElement("pre"); args.textContent = JSON.stringify(redact(request.args || {}), null, 2);
    Object.assign(args.style, { whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: "35vh", overflow: "auto", padding: "13px", color: "#393640", background: "rgba(238,236,245,.72)", border: "1px solid rgba(70,60,98,.1)", borderRadius: "13px", font: "12px/1.5 ui-monospace,monospace" });
    const message = document.createElement("p"); message.setAttribute("role", "status");
    Object.assign(message.style, { minHeight: "20px", color: "#62616a", fontSize: "13px", lineHeight: "1.45" });
    const actions = document.createElement("div"); Object.assign(actions.style, { display: "flex", gap: "10px", marginTop: "16px" });
    const makeButton = (label, kind) => {
      const button = document.createElement("button"); button.type = "button"; button.textContent = label;
      const danger = kind === "danger";
      Object.assign(button.style, { flex: "1", border: `1px solid ${danger ? "rgba(199,45,76,.16)" : "rgba(255,255,255,.3)"}`, borderRadius: "13px", padding: "12px", color: danger ? "#a61b34" : "white", background: danger ? "rgba(255,239,242,.8)" : "linear-gradient(105deg,#a56bf2,#6e83ee 58%,#ee82c6)", cursor: "pointer", fontWeight: "700", fontSize: "14px", boxShadow: danger ? "0 2px 8px rgba(30,25,48,.04)" : "0 7px 18px rgba(126,91,205,.2),inset 0 1px rgba(255,255,255,.3)", transition: "transform .18s cubic-bezier(.2,.75,.25,1),box-shadow .18s" });
      button.addEventListener("pointerenter", () => { if (!button.disabled) button.style.transform = "translateY(-1px)"; });
      button.addEventListener("pointerleave", () => { button.style.transform = "none"; });
      return button;
    };
    const reject = makeButton("Rejeitar", "danger");
    const approve = makeButton("Aprovar e executar", "primary");
    actions.append(reject, approve); card.append(title, warning, summary, args, message, actions); backdrop.append(card); document.documentElement.append(backdrop);
    const decide = (type) => {
      approve.disabled = reject.disabled = true;
      message.textContent = type === "approve_agent" ? "Executando ação aprovada…" : "Rejeitando solicitação…";
      chrome.runtime.sendMessage({ type }, (result) => {
        if (chrome.runtime.lastError) {
          message.textContent = type === "approve_agent"
            ? "Estado incerto após aprovação. Não clique novamente; verifique o bridge e inicie uma nova solicitação se necessário."
            : "Falha de comunicação ao rejeitar. Verifique se a solicitação ainda está pendente.";
          approve.disabled = reject.disabled = type === "approve_agent";
          return;
        }
        if (result && result.ok) {
          message.textContent = type === "approve_agent" ? "Ação aprovada e enviada para execução." : "Solicitação rejeitada; a ação não foi executada.";
          approve.disabled = reject.disabled = true;
          setTimeout(close, 1400);
        } else {
          message.textContent = result?.approvalConsumed
            ? `A aprovação foi consumida, mas a execução falhou: ${result.error || "erro sem detalhes"}`
            : (result && result.error) || "A ação não foi concluída.";
          approve.disabled = reject.disabled = !!result?.approvalConsumed;
        }
      });
    };
    reject.addEventListener("click", () => decide("reject_agent"));
    approve.addEventListener("click", () => decide("approve_agent"));
    approve.focus();
  }
  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg) return;
    if (msg.type === "zs-approval-request" && msg.approval) show(msg.approval);
    if (msg.type === "zs-status" && !msg.agentApproval) close();
  });
})();
