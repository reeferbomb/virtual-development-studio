"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {spawnSync} = require("node:child_process");
const {mkdtempSync, writeFileSync, rmSync} = fs;
const os = require("node:os");

class Node {
  constructor(tag) { Object.assign(this, {tag, children: [], attrs: {}, events: {}, textContent: ""}); }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  *all() { yield this; for (const child of this.children) yield* child.all(); }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  addEventListener(key, callback) { this.events[key] = callback; }
  set innerHTML(value) { throw Error("Private report content must be rendered as text only"); }
}
const view = new Node("main"), location = {hash: "#intelligence"};
const elements = {"#view": view, "#new-project": new Node("dialog"), "#location": new Node("p")};
const document = {createElement: tag => new Node(tag), querySelector: key => elements[key], querySelectorAll: () => []};
const directory = path.join(__dirname, "../command_center/ui");
const script = fs.readFileSync(path.join(directory, "app.js"), "utf8").split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const requests = [];
const route = vm.runInNewContext(script + "\n;route", {document, location, fetch: async url => {
  requests.push(url); return {ok: true, json: async () => []};
}, setTimeout});
const find = fn => [...view.all()].find(fn);
const text = value => find(node => node.textContent === value);
const byId = id => find(node => node.id === id);
const digest = "a".repeat(64), missing = ["balance", "playtest", "ui", "audio", "build"];
const report = {schema_version: 1, kind: "production-intelligence", status: "warn", input_sha256: digest,
  report_sha256: digest, missing, advisory: "Advisory only.", reports: [{schema_version: 1, kind: "frame",
    status: "pass", capture_sha256: digest, advisory: "Only measured data.", metrics: {p99: 19000}, checks: [
      {id: "pacing", label: "Pacing", status: "pass", detail: "<img src='private'>"}]}]};
const select = async (picker, value, size) => {
  const source = JSON.stringify(value);
  picker.files = [{size: size ?? source.length, text: async () => source}];
  await picker.events.change();
};

async function run() {
  await route(); assert.equal(requests.length, 0, "Report page must not fetch or upload data");
  assert.match(fs.readFileSync(path.join(directory, "index.html"), "utf8"), /href="#intelligence" data-page="intelligence"/);
  assert(text("Production intelligence"));
  const picker = byId("intelligence-report-file"), status = byId("intelligence-report-status");
  assert(find(node => node.tag === "label" && node.htmlFor === picker.id));
  await select(picker, report);
  assert(text("1 of 6 domains supplied")); assert(text("<img src='private'>"));
  assert.match(status.textContent, /opened/);
  for (const invalid of [{...report, status: "pass"}, {...report, missing: ["balance", "balance", "ui", "audio", "build"]},
    {...report, report_sha256: "bad"}, {...report, reports: [{...report.reports[0], status: "fail"}]},
    {...report, reports: [{...report.reports[0], checks: []}]}]) {
    await select(picker, invalid); assert.equal(picker.attrs["aria-invalid"], "true");
    assert(!text("<img src='private'>"));
  }
  await select(picker, report, 2 * 1024 * 1024 + 1);
  assert.match(status.textContent, /2 MiB or less/);
  let resolve;
  picker.files = [{size: 1, text: () => new Promise(done => { resolve = done; })}];
  const slow = picker.events.change(); await select(picker, {...report, status: "pass"});
  resolve(JSON.stringify(report)); await slow;
  assert(!text("<img src='private'>"), "A stale file read cannot replace a new result");
  const temp = mkdtempSync(path.join(os.tmpdir(), "gf-intelligence-"));
  try {
    const python = args => spawnSync("python3", ["-m", "command_center.production_intelligence_cli", ...args],
      {cwd: path.join(__dirname, ".."), encoding: "utf8", timeout: 20000});
    const example = python(["example"]); assert.equal(example.status, 0, example.stderr);
    const filename = path.join(temp, "example.json"); writeFileSync(filename, example.stdout);
    const result = python(["analyze", filename]); assert([0, 1].includes(result.status), result.stderr);
    await select(picker, JSON.parse(result.stdout)); assert(text("6 of 6 domains supplied"));
    assert.match(status.textContent, /opened/);
  } finally { rmSync(temp, {recursive: true, force: true}); }
  let lateResolve;
  picker.files = [{size: 1, text: () => new Promise(done => { lateResolve = done; })}];
  const late = picker.events.change(); location.hash = "#projects"; await route();
  lateResolve(JSON.stringify(report)); await late;
  assert(!text("<img src='private'>")); assert.deepEqual(requests, ["/api/projects"]);
  console.log("PASS Production intelligence report shape, real CLI bundle, privacy, invalid files, and stale selection.");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
