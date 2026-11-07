// SPDX-License-Identifier: GPL-3.0-or-later
// Model-free DOM helpers for the Infinix browser extension.
// Deep traversal is limited to open Shadow DOM roots; closed roots remain inaccessible.
(function (global) {
  "use strict";
  const ATTR = "data-zs-nodeid";
  const ACTIONABLE = "a,button,input,textarea,select,[role='button'],[role='link'],[role='option'],[role='listitem'],[role='menuitem'],[role='gridcell'],[role='tab'],[role='checkbox'],[role='radio'],[contenteditable='true'],[tabindex]:not([tabindex='-1'])";
  const MAX_ELEMENTS = 700;
  const MAX_TEXT = 18000;
  let nextId = 1;
  let elementsById = new Map();

  function visible(el) {
    if (!(el instanceof Element)) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
  }

  function label(el) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    const explicit = el.getAttribute("aria-label") || el.getAttribute("title") || el.getAttribute("placeholder") || el.getAttribute("alt") || "";
    if (type === "password" || /password|token|secret|credential|security code|cvv|card number/i.test(`${explicit} ${el.getAttribute("name") || ""}`)) {
      return `${explicit || el.getAttribute("name") || "field"} [value hidden]`.replace(/\s+/g, " ").trim().slice(0, 200);
    }
    const text = explicit || (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement ? "" : (el.innerText || el.textContent || ""));
    return String(text).replace(/\s+/g, " ").trim().slice(0, 200);
  }

  function ensureId(el) {
    let id = el.getAttribute(ATTR);
    if (!id) {
      id = `zs-${nextId++}`;
      el.setAttribute(ATTR, id);
    }
    elementsById.set(id, el);
    return id;
  }

  function rootsFor(deep = false) {
    const roots = [document];
    if (!deep) return roots;
    const seen = new Set(roots);
    for (let i = 0; i < roots.length && roots.length < 120; i++) {
      const root = roots[i];
      for (const el of root.querySelectorAll("*")) {
        if (el.shadowRoot && !seen.has(el.shadowRoot)) {
          seen.add(el.shadowRoot);
          roots.push(el.shadowRoot);
        }
      }
    }
    return roots;
  }

  function queryAcrossRoots(selector, deep = false, knownRoots = null) {
    const found = [];
    const seen = new Set();
    for (const root of knownRoots || rootsFor(deep)) {
      for (const el of root.querySelectorAll(selector)) {
        if (!seen.has(el)) { seen.add(el); found.push(el); }
      }
    }
    return found;
  }

  function pageText(deep = false) {
    let text = document.body?.innerText || "";
    if (deep) {
      for (const root of rootsFor(true).slice(1)) {
        const extra = (root.textContent || "").replace(/\s+/g, " ").trim();
        if (extra) text += `\n${extra}`;
        if (text.length >= MAX_TEXT) break;
      }
    }
    return text.replace(/\n{3,}/g, "\n\n").slice(0, MAX_TEXT);
  }

  function selectorMatches(selector, deep = false, knownRoots = null) {
    if (!selector) return null;
    for (const root of knownRoots || rootsFor(deep)) {
      const el = root.querySelector(selector);
      if (el && visible(el)) return el;
    }
    return null;
  }

  async function waitForStability({ waitMs = 0, selectorHint = "", deep = false } = {}) {
    const maxWait = Math.max(0, Math.min(Number(waitMs) || 0, 15000));
    const deadline = Date.now() + (selectorHint && !maxWait ? 5000 : maxWait);
    let lastMutation = Date.now();
    let selectorFound = !selectorHint;
    const observers = [];
    const observedRoots = new Set();
    let roots = rootsFor(deep);
    let rootsDirty = false;
    let rootsRefreshedAt = Date.now();
    const observeRoot = (root) => {
      if (!global.MutationObserver || !root || observedRoots.has(root)) return;
      const observer = new MutationObserver(() => { lastMutation = Date.now(); rootsDirty = true; });
      try {
        observer.observe(root, { subtree: true, childList: true, attributes: true, characterData: true });
        observedRoots.add(root);
        observers.push(observer);
      } catch { observer.disconnect(); }
    };
    try {
      for (const root of roots) observeRoot(root);
      if (!selectorHint && !maxWait) return { stable: true, selectorFound: true, waitedMs: 0 };
      while (Date.now() < deadline) {
        if (deep && (rootsDirty || Date.now() - rootsRefreshedAt > 500)) {
          roots = rootsFor(true);
          for (const root of roots) observeRoot(root);
          rootsDirty = false;
          rootsRefreshedAt = Date.now();
        }
        if (selectorHint) {
          try { selectorFound = !!selectorMatches(selectorHint, deep, roots); }
          catch (e) { throw new Error(`invalid selector_hint: ${String(e && e.message || e)}`); }
        }
        if (selectorFound && Date.now() - lastMutation >= 280) break;
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      return { stable: selectorFound && Date.now() - lastMutation >= 280, selectorFound, waitedMs: Math.max(0, Date.now() - (deadline - (selectorHint && !maxWait ? 5000 : maxWait))) };
    } finally {
      for (const observer of observers) observer.disconnect();
    }
  }

  async function snapshot(options = {}) {
    const deep = options.deep === true;
    const settled = await waitForStability({ waitMs: options.wait_ms, selectorHint: options.selector_hint, deep });
    const elements = [];
    elementsById = new Map();
    const roots = rootsFor(deep);
    const candidates = queryAcrossRoots(ACTIONABLE, deep, roots);
    for (const el of candidates) {
      if (!visible(el)) continue;
      const id = ensureId(el);
      const role = el.getAttribute("role") || (el.tagName === "A" ? "link" : el.tagName.toLowerCase());
      const item = {
        id,
        tag: el.tagName.toLowerCase(),
        role,
        text: label(el),
        disabled: !!el.disabled || el.getAttribute("aria-disabled") === "true",
        ...(el.getAttribute("placeholder") ? { placeholder: el.getAttribute("placeholder").slice(0, 120) } : {}),
        ...(el.getAttribute("name") ? { name: el.getAttribute("name").slice(0, 120) } : {}),
        ...(el.getAttribute("type") ? { inputType: el.getAttribute("type").slice(0, 40) } : {}),
        ...(el.getAttribute("href") ? { href: el.getAttribute("href").slice(0, 500) } : {}),
      };
      elements.push(item);
      if (elements.length >= MAX_ELEMENTS) break;
    }
    const result = {
      url: location.href,
      title: document.title,
      viewport: { width: global.innerWidth, height: global.innerHeight, devicePixelRatio: global.devicePixelRatio || 1 },
      elements,
      candidateCount: candidates.length,
      elementLimit: MAX_ELEMENTS,
      truncated: candidates.length > MAX_ELEMENTS,
      inspectedRoots: roots.length,
      collectedAt: new Date().toISOString(),
      stability: settled,
      deep,
    };
    if (options.include_text !== false) result.pageText = pageText(deep);
    return result;
  }

  function find(id, deep = true) {
    if (id && elementsById.has(id)) {
      const cached = elementsById.get(id);
      if (cached?.isConnected && visible(cached)) return cached;
    }
    if (!id) throw new Error("element id is required");
    for (const root of rootsFor(deep)) {
      const el = root.querySelector(`[${ATTR}="${CSS.escape(String(id))}"]`);
      if (el && visible(el)) { elementsById.set(id, el); return el; }
    }
    throw new Error("element is missing or not visible; take a fresh snapshot");
  }

  function elementAt(x, y, coordinateSpace = "css") {
    x = Number(x); y = Number(y);
    if (coordinateSpace === "image") { const scale = global.devicePixelRatio || 1; x /= scale; y /= scale; }
    else if (coordinateSpace !== "css") throw new Error("coordinate_space must be css or image");
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 || x >= global.innerWidth || y >= global.innerHeight) throw new Error("coordinates must be within the current viewport in CSS pixels");
    let el = document.elementFromPoint(x, y);
    for (let depth = 0; el?.shadowRoot?.elementFromPoint && depth < 20; depth++) {
      const inner = el.shadowRoot.elementFromPoint(x, y);
      if (!inner || inner === el) break;
      el = inner;
    }
    if (!el || !visible(el)) throw new Error("no visible element at those coordinates");
    return el;
  }

  function classify(action, id, details = {}) {
    let el = action === "click_at" ? elementAt(details.x, details.y, details.coordinate_space) : action === "press_key" && !id ? (document.activeElement || document.body) : find(id);
    if (action === "click_at") el = el.closest("button,a,input,[role='button'],[role='link'],[role='menuitem'],[role='option']") || el;
    const editableTarget = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el.isContentEditable;
    const metadata = [el.getAttribute?.("aria-label"), el.getAttribute?.("title"), el.getAttribute?.("name"), el.getAttribute?.("placeholder"), el.getAttribute?.("autocomplete"), el.getAttribute?.("type"), el.id, editableTarget ? "" : label(el)].filter(Boolean).join(" ").toLowerCase();
    const sensitive = /password|passcode|credential|one.?time|otp|2fa|verification code|security code|api.?key|access.?token|credit.?card|card.?number|cvv|cvc|bank|payment|checkout|purchase|delete|remove|destroy|publish|post|send|submit|transfer|upload|share|invite|subscribe|sign.?out|log.?out/.test(metadata);
    if (action === "type") {
      const secretField = el instanceof HTMLInputElement && el.type.toLowerCase() === "password";
      return { highRisk: !!(secretField || sensitive), reason: secretField ? "credential field" : sensitive ? "sensitive field or content" : "ordinary editable field", tag: el.tagName.toLowerCase(), label: label(el) };
    }
    if (action === "press_key") {
      const key = String(details.key || "");
      const modifiers = Array.isArray(details.modifiers) ? details.modifiers : [];
      const destructiveOrSubmit = ["Enter", "Backspace", "Delete"].includes(key) || modifiers.some((m) => ["ctrl", "meta"].includes(String(m).toLowerCase()));
      return { highRisk: !!(sensitive || destructiveOrSubmit), reason: sensitive ? "sensitive control" : destructiveOrSubmit ? "submit/edit/shortcut key" : "ordinary navigation key", tag: el.tagName.toLowerCase(), label: label(el) };
    }
    const isButton = el.tagName === "BUTTON" || el.getAttribute("role") === "button" || el.tagName === "INPUT" && ["submit", "button"].includes(el.type);
    const isSubmit = isButton && (el.type === "submit" || !!el.closest("form"));
    const unknownCoordinate = action === "click_at" && !label(el) && !isButton && el.getAttribute("role") !== "link";
    return { highRisk: !!(sensitive || isSubmit || unknownCoordinate), reason: sensitive ? "sensitive or external-effect control" : isSubmit ? "form submission" : unknownCoordinate ? "unlabelled coordinate target" : "ordinary control", tag: el.tagName.toLowerCase(), label: label(el) };
  }

  function click(id) {
    const el = find(id);
    el.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
    el.click();
    return { id, action: "click", ok: true };
  }

  function clickAt(x, y, coordinateSpace = "css") {
    const target = elementAt(x, y, coordinateSpace);
    target.click();
    return { id: ensureId(target), action: "click_at", x: Number(x), y: Number(y), coordinateSpace, target: label(target), ok: true };
  }

  function type(id, text) {
    const el = find(id);
    if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el.isContentEditable)) throw new Error("element is not editable");
    el.focus();
    const value = String(text);
    if (el.isContentEditable) {
      el.textContent = value;
    } else {
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) setter.call(el, value); else el.value = value;
    }
    el.dispatchEvent(new InputEvent("input", { bubbles: true, composed: true, data: value, inputType: "insertText" }));
    el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    return { id, action: "type", ok: true };
  }

  function validateKey(key) {
    const allowed = new Set(["Enter", "Tab", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown", "Backspace", "Delete", "Space", " "]);
    if (typeof key !== "string" || !(allowed.has(key) || /^[a-zA-Z0-9]$/.test(key) || /^F(?:[1-9]|1[0-2])$/.test(key))) throw new Error("unsupported key; use a named key (Enter, Tab, Escape, arrows) or one alphanumeric character");
    return key === "Space" ? " " : key;
  }

  function pressKey(key, modifiers = [], id) {
    key = validateKey(key);
    const allowedModifiers = new Set(["ctrl", "shift", "alt", "meta"]);
    const normalized = [...new Set((Array.isArray(modifiers) ? modifiers : []).map((m) => String(m).toLowerCase()))];
    if (normalized.some((m) => !allowedModifiers.has(m))) throw new Error("unsupported modifier; use ctrl, shift, alt, or meta");
    const target = id ? find(id) : (document.activeElement || document.body);
    if (!target || !(target instanceof Element)) throw new Error("no focused element");
    if (id) target.focus();
    const opts = { key, code: key === " " ? "Space" : key, bubbles: true, cancelable: true, composed: true, ctrlKey: normalized.includes("ctrl"), shiftKey: normalized.includes("shift"), altKey: normalized.includes("alt"), metaKey: normalized.includes("meta") };
    const down = new KeyboardEvent("keydown", opts);
    target.dispatchEvent(down);
    target.dispatchEvent(new KeyboardEvent("keyup", opts));
    if (key === "Tab" && !opts.ctrlKey && !opts.altKey && !opts.metaKey) {
      const focusables = queryAcrossRoots("a,button,input,textarea,select,[tabindex]:not([tabindex='-1'])", true).filter((el) => visible(el) && !el.disabled);
      const current = focusables.indexOf(target);
      const direction = opts.shiftKey ? -1 : 1;
      const next = focusables[(current + direction + focusables.length) % focusables.length];
      if (next) next.focus();
    } else if ((key === "Enter" || key === " ") && (target.tagName === "BUTTON" || target.getAttribute("role") === "button" || target.tagName === "A")) {
      target.click();
    }
    return { action: "press_key", key, modifiers: normalized, target: label(target), synthetic: true, note: "Synthetic DOM keyboard events are not trusted OS keystrokes; some sites may ignore them." };
  }

  function scrollContainer(el) {
    let node = el;
    while (node && node !== document.body && node !== document.documentElement) {
      if (node instanceof HTMLElement && node.scrollHeight > node.clientHeight + 30 && /(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node;
      node = node.parentElement || node.getRootNode()?.host || null;
    }
    const candidates = queryAcrossRoots("main,[role='main'],[role='list'],[role='grid'],[role='listbox'],[data-testid]", true)
      .filter((item) => item instanceof HTMLElement && item.scrollHeight > item.clientHeight + 60 && /(auto|scroll)/.test(getComputedStyle(item).overflowY));
    candidates.sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
    return candidates[0] || null;
  }

  async function scroll(direction, amount = 500, containerId) {
    if (!["up", "down"].includes(direction)) throw new Error("direction must be up or down");
    const distance = Math.max(100, Math.min(Number(amount) || 500, 2000)) * (direction === "down" ? 1 : -1);
    const reference = containerId ? find(containerId) : null;
    const container = scrollContainer(reference);
    if (container) {
      container.scrollBy({ top: distance, behavior: "instant" });
      await new Promise((resolve) => setTimeout(resolve, 300));
      return { action: "scroll", direction, container: label(container), scrollTop: container.scrollTop, scrollHeight: container.scrollHeight, clientHeight: container.clientHeight, atTop: container.scrollTop <= 0, atBottom: container.scrollTop + container.clientHeight >= container.scrollHeight - 2 };
    }
    const root = document.scrollingElement || document.documentElement;
    window.scrollBy({ top: distance, behavior: "instant" });
    await new Promise((resolve) => setTimeout(resolve, 300));
    return { action: "scroll", direction, container: "document", scrollTop: root.scrollTop, scrollHeight: root.scrollHeight, clientHeight: root.clientHeight, atTop: root.scrollTop <= 0, atBottom: root.scrollTop + root.clientHeight >= root.scrollHeight - 2 };
  }

  async function waitFor({ selector_hint = "", text = "", timeout_ms = 5000, deep = false } = {}) {
    if (!selector_hint && !text) throw new Error("wait requires selector_hint or text");
    const timeout = Math.max(100, Math.min(Number(timeout_ms) || 5000, 15000));
    const started = Date.now();
    while (Date.now() - started < timeout) {
      let matched = false;
      if (selector_hint) {
        try { matched = !!selectorMatches(selector_hint, deep); }
        catch (e) { throw new Error(`invalid selector_hint: ${String(e && e.message || e)}`); }
      }
      if (text && pageText(deep).toLowerCase().includes(String(text).toLowerCase())) matched = true;
      if (matched) return { ok: true, matchedBy: selector_hint && text ? "selector_or_text" : selector_hint ? "selector" : "text", waitedMs: Date.now() - started };
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    return { ok: false, timedOut: true, error: "timed out waiting for the requested selector/text", waitedMs: Date.now() - started };
  }

  global.InfinixDOM = { snapshot, click, clickAt, type, classify, pressKey, scroll, waitFor };
  if (global.chrome && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
      if (!msg || msg.type !== "zs-browser-action") return false;
      (async () => {
        try {
          if (msg.action === "snapshot") sendResponse({ ok: true, result: await snapshot(msg) });
          else if (msg.action === "classify") sendResponse({ ok: true, result: classify(msg.operation, msg.id, msg) });
          else if (msg.action === "click") sendResponse({ ok: true, result: click(msg.id) });
          else if (msg.action === "click_at") sendResponse({ ok: true, result: clickAt(msg.x, msg.y, msg.coordinate_space) });
          else if (msg.action === "viewport") sendResponse({ ok: true, result: { width: global.innerWidth, height: global.innerHeight, devicePixelRatio: global.devicePixelRatio || 1 } });
          else if (msg.action === "type") sendResponse({ ok: true, result: type(msg.id, msg.text) });
          else if (msg.action === "press_key") sendResponse({ ok: true, result: pressKey(msg.key, msg.modifiers, msg.id) });
          else if (msg.action === "scroll") sendResponse({ ok: true, result: await scroll(msg.direction, msg.amount, msg.containerId) });
          else if (msg.action === "wait") sendResponse({ ok: true, result: await waitFor(msg) });
          else sendResponse({ ok: false, error: "unknown browser action" });
        } catch (e) {
          sendResponse({ ok: false, error: String(e && e.message || e) });
        }
      })();
      return true;
    });
  }
})(globalThis);
