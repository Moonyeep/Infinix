const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const launcher = fs.readFileSync(path.join(root, "start_agent.sh"), "utf8");
const popup = fs.readFileSync(path.join(__dirname, "popup.html"), "utf8");
const main = fs.readFileSync(path.join(__dirname, "core/main.js"), "utf8");
const linuxGuide = fs.readFileSync(path.join(root, "INSTALL_LINUX.md"), "utf8");

assert.match(launcher, /python3\.10/);
assert.match(launcher, /python3 -m venv| -m venv/);
assert.match(launcher, /pip install --disable-pip-version-check websockets/);
assert.match(launcher, /astral\.sh\/uv\/install\.sh/);
assert.match(launcher, /\$UV_BIN" python install 3\.12/);
assert.doesNotMatch(launcher, /^\s*(sudo|doas|apt-get|dnf|pacman|zypper)(\s|$)/m);
assert.match(launcher, /ZS_BROWSER_ENABLED/);
assert.match(popup, /start_agent\.sh/);
assert.match(main, /start_agent\.sh/);
assert.match(linuxGuide, /Chrome\/Chromium/);
assert.match(linuxGuide, /instala automaticamente `websockets`/);
assert.doesNotMatch(main, /Run <b>start\.bat<\/b> on your PC/);

console.log("Linux launcher and cross-platform setup regression checks passed");
