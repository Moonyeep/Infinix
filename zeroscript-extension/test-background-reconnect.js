const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "background.js"), "utf8");
assert.match(source, /if \(msg\.agent_enabled && ws && profileSyncedSocket !== ws\)/);
assert.match(source, /send\(\{ type: "agent_set_profile", profile: agentProfile \}, 10000\)/);
const match = source.match(/function connect\(\) \{[\s\S]*?\n\}(?=\n\nfunction scheduleReconnect\()/);
assert.ok(match, "connect() should exist and be testable");

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances = [];
  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.closeCalls = 0;
    FakeWebSocket.instances.push(this);
  }
  close() {
    this.closeCalls++;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code: 1000, reason: "closed", wasClean: true });
  }
}

const context = {
  WebSocket: FakeWebSocket,
  BRIDGE_WS_URL: "ws://127.0.0.1:17613",
  RECONNECT_MIN: 1000,
  RECONNECT_MAX: 5000,
  ws: null,
  connected: false,
  reconnectDelay: 1000,
  reconnectTimer: null,
  clearTimeout() {},
  scheduleReconnect() {},
  clearBridgeState() {},
  log() {},
  startHeartbeat() {},
  broadcastStatus() {},
  handleBridgeMessage() {},
};
vm.runInNewContext(`let ws = null; let connected = false;\n${match[0]}\nglobalThis.connect = connect; globalThis.getSocket = () => ws; globalThis.isConnected = () => connected;`, context);

context.connect();
const stale = context.getSocket();
assert.ok(stale);
stale.readyState = FakeWebSocket.CLOSED; // onclose has not run yet
context.connect();
const current = context.getSocket();
assert.ok(current && current !== stale, "a closed socket should be replaced");
current.readyState = FakeWebSocket.OPEN;
current.onopen();
stale.onerror?.();
stale.onclose?.({ code: 1006, reason: "late stale close", wasClean: false });
assert.equal(context.getSocket(), current, "stale callbacks must not replace the active socket");
assert.equal(context.isConnected(), true, "stale callbacks must not mark a healthy socket offline");
assert.equal(current.closeCalls, 0, "stale onerror must not close the current socket");
console.log("background reconnect stale-socket regression passed");
