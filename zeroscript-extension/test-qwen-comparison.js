const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "providers/qwen.js"), "utf8");
const start = source.indexOf("function resolveComparison() {");
assert.notEqual(start, -1, "Qwen comparison resolver must exist");
const open = source.indexOf("{", start);
let depth = 0, quote = "", escaped = false, end = -1;
for (let i = open; i < source.length; i++) {
  const ch = source[i];
  if (quote) {
    if (escaped) escaped = false;
    else if (ch === "\\") escaped = true;
    else if (ch === quote) quote = "";
    continue;
  }
  if (ch === "\"" || ch === "'" || ch === "`") { quote = ch; continue; }
  if (ch === "{") depth++;
  if (ch === "}" && --depth === 0) { end = i + 1; break; }
}
assert.notEqual(end, -1, "resolver function must be balanced");
const resolver = source.slice(start, end);

let clicked = 0;
const button = {
  textContent: "Prefiro esta resposta",
  getAttribute: () => null,
  click: () => { clicked++; },
};
const firstBox = { querySelectorAll: () => [button] };
const dual = { querySelector: () => firstBox };
const document = { querySelectorAll: () => [dual] };
const result = vm.runInNewContext(`${resolver}; resolveComparison();`, { document });
assert.equal(result, true, "localized Qwen option should be recognized");
assert.equal(clicked, 1, "resolver should click exactly one (first-candidate) response button");
console.log("Qwen Portuguese A/B comparison auto-selection test passed");
