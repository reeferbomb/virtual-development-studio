"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag) { Object.assign(this, {tag, events: {}, attrs: {}, children: [], textContent: ""}); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  *all() { yield this; for (const child of this.children) yield* child.all(); }
  addEventListener(event, handler) { this.events[event] = handler; }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  set textContent(value) { this.text = String(value); }
  get textContent() { return this.text; }
  set innerHTML(value) { throw new Error("Unexpected HTML sink: " + value); }
}
const directory = path.join(__dirname, "../command_center/ui");
assert.match(fs.readFileSync(path.join(directory, "index.html"), "utf8"), /href="#quality" data-page="quality"/);
assert.match(fs.readFileSync(path.join(directory, "index.html"), "utf8"), /href="#training" data-page="training"/);
const script = fs.readFileSync(path.join(directory, "app.js"), "utf8").split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const view = new Element("main"), link = new Element("a"), location = {hash: "#quality"};
link.dataset = {page: "quality"};
const nodes = {"#view": view, "#location": new Element("strong"), "#new-project": new Element("dialog")};
const document = {createElement: tag => new Element(tag), querySelector: key => nodes[key], querySelectorAll: () => [link]};
const projects = [{id: "alpha", name: "Alpha"}, {id: "beta", name: "Beta"}];
const roles = ["architecture", "gameplay", "verification", "ui", "content", "build_operations"];
const gates = ["build", "release", "task_board", "manual_review", "defects", "performance", "audit_history"];
const spec = "a".repeat(64), baseline = "f".repeat(32), cycleId = "e".repeat(64);
const evidence = "<img src=x onerror=review()>", title = "<script>dispatch()</script>";
const matrix = {status: "blocked", note: "Inspect the current gates.", summary: {pass: 6, pending: 0, fail: 1},
  checks: gates.map((id, i) => ({id, label: id + " gate", status: i ? "pass" : "fail", evidence,
    role: i < 2 || i === 5 ? "build_operations" : i === 2 ? "architecture" : "verification", next_action: "Review evidence."}))};
const trends = {status: "current", note: "Compare the latest current-spec capture.", history_revision: 3, historical_count: 1,
  baseline_id: baseline, baseline_status: "attention", live_status: "blocked", summary: {improved: 0, regressed: 1, unchanged: 5},
  checks: gates.slice(0, 6).map((id, i) => ({id, label: id + " check", baseline_status: i ? "pass" : "warn",
    live_status: i ? "pass" : "fail", trend: i ? "unchanged" : "regressed"}))};
const analytics = {status: "current", historical_count: 2, handoff_revision: 8, note: "Lead-reviewed handoffs.",
  roles: roles.map((role, i) => ({role, submitted: i ? 0 : 3, accepted: i ? 0 : 1, rejected: i ? 0 : 1, pending: i ? 0 : 1,
    unique_orders: i ? 0 : 2, completed: i ? 0 : 1, blocked: 0, progress: 0, median_review_seconds: i ? null : 12.5}))};
const step = {project_id: "alpha", task_id: "verify", role: "verification", title, priority: 5,
  expected_revision: 9, spec_sha256: spec, action: {op: "start", task_id: "verify"}};
const cycle = {status: "ready", cycle_id: cycleId, steps: [step], conflicts: [], note: "Refresh after each claim."};
const sources = {"quality-matrix": matrix, "quality-trends": trends, "specialist-analytics": analytics};
const lesson = {id: "simulation", title: "Gameplay practice", roles: ["gameplay"], workflow: ["Prototype the loop."],
  deliverables: ["Playable loop."], verification: ["Test the transition."], exercise: "<script>practice()</script>"};
const curriculum = {version: 1, curriculum_sha256: "d".repeat(64), tracks: [lesson,
  {...lesson, id: "modeling", title: "Modeling practice", roles: ["content"]}], note: "Production playbooks."};
function normal(url) {
  if (url === "/api/training") return curriculum;
  if (url === "/api/projects") return projects;
  if (url === "/api/dispatch-cycle") return cycle;
  const [, id, source] = /^\/api\/projects\/(alpha|beta)\/(quality-matrix|quality-trends|specialist-analytics)$/.exec(url);
  return {...sources[source], project_id: id, spec_sha256: spec};
}
let override;
const requests = [];
async function fetch(url, options) {
  assert.equal(options.method, "GET"); assert.equal(options.body, undefined);
  requests.push(url);
  const [status, value] = override?.(url) ?? [200, normal(url)];
  return {ok: status === 200, status, json: async () => structuredClone(await value)};
}
const {route, state} = vm.runInNewContext(script + "\n;({route,state});", {document, location, fetch});
const all = () => [...view.all()];
const find = text => all().find(node => node.textContent === text);
const refresh = () => find("Refresh quality").events.click();
const patch = (source, changes) => { override = url => url.endsWith("/" + source) ? [200, {...normal(url), ...changes}] : null; };
async function run() {
  await route();
  assert.equal(link.attrs["aria-current"], "page"); assert.equal(document.title, "Quality · Studio Command Center");
  assert.deepEqual(requests, ["/api/projects", ...Object.keys(sources).map(key => "/api/projects/alpha/" + key), "/api/dispatch-cycle"]);
  assert.equal(all().find(node => node.tag === "label").htmlFor, all().find(node => node.tag === "select").id);
  assert(all().some(node => node.attrs.role === "status"));
  for (const text of ["Quality matrix", "Quality trends", "Specialist analytics", "Workspace dispatch cycle", evidence, title,
    "Review evidence.", "Regressed", "12.5", "No reviews", "Capture " + baseline, "Cycle " + cycleId]) assert(find(text), text);
  assert.equal(all().filter(node => node.tag === "button").length, 1);
  assert(!all().some(node => ["img", "script", "form"].includes(node.tag)));
  for (const [source, change] of [["quality-matrix", {checks: matrix.checks.slice(1)}],
    ["quality-matrix", {status: "ready"}], ["quality-trends", {checks: trends.checks.map(row => ({...row, trend: "unchanged"}))}],
    ["specialist-analytics", {roles: analytics.roles.map(row => ({...row, accepted: 5}))}],
    ["dispatch-cycle", {steps: [{...step, action: {op: "start", task_id: "other"}}]}],
    ["dispatch-cycle", {steps: [{...step, project_id: "unknown"}]}],
    ["dispatch-cycle", {steps: [step, {...step, role: "ui", task_id: "ui", expected_revision: 10, action: {op: "start", task_id: "ui"}}]}],
    ["dispatch-cycle", {status: "blocked", conflicts: [{role: "ui", project_ids: ["alpha", "beta"]}]}]]) {
    patch(source, change); await refresh();
    assert(find("Some quality reports are unavailable."), source); assert(!find(source === "quality-matrix" ? evidence :
      source === "quality-trends" ? "Regressed" : source === "specialist-analytics" ? "12.5" : title));
  }
  for (const [source, change] of [["quality-matrix", {project_id: "beta"}], ["quality-trends", {spec_sha256: "b".repeat(64)}],
    ["dispatch-cycle", {steps: [{...step, spec_sha256: "b".repeat(64)}]}]]) {
    patch(source, change); await refresh();
    assert(find("Project reports disagree. Refresh quality to load a consistent snapshot."));
    assert(!find(evidence)); assert(!find(title)); assert(!find("12.5"));
  }
  override = url => url.endsWith("/quality-matrix") ? [503, {error: "Missing evidence."}] : null;
  await refresh(); assert(find("Missing evidence.")); assert(find("Regressed"));
  patch("dispatch-cycle", {status: "blocked", steps: [], conflicts: [{role: "verification", project_ids: ["alpha", "beta"]}]});
  await refresh(); assert(find("Projects · alpha, beta")); assert(!find(title)); assert(find(evidence));
  patch("quality-trends", {status: "empty", history_revision: 1, historical_count: 1, baseline_id: null, baseline_status: null,
    checks: [], summary: {improved: 0, regressed: 0, unchanged: 0}});
  await refresh(); assert(find("No current-specification capture")); assert(!find("Regressed")); assert(find(evidence));
  patch("specialist-analytics", {status: "unavailable", historical_count: null, handoff_revision: null, roles: [], note: "Ledger unreadable."});
  await refresh(); assert(find("Ledger unreadable.")); assert(!find("12.5"));
  override = undefined; await refresh();
  let finish;
  const wait = new Promise(done => { finish = done; });
  override = url => url.endsWith("alpha/quality-matrix") ? [200, wait] : null;
  const old = find("Refresh quality"), loading = old.events.click();
  assert(old.disabled); assert(!find(evidence));
  const count = requests.length; await old.events.click(); assert.equal(requests.length, count);
  await new Promise(done => setImmediate(done));
  const picker = all().find(node => node.tag === "select");
  picker.value = "beta"; picker.events.change(); await new Promise(done => setImmediate(done));
  assert.equal(state.selected, "beta"); assert(find(evidence));
  finish({...normal("/api/projects/alpha/quality-matrix"), note: "Obsolete note."}); await loading;
  assert(!find("Obsolete note."));
  const after = requests.length; await old.events.click(); assert.equal(requests.length, after);
  override = url => url === "/api/projects" ? [200, []] : null;
  await route(); assert(find("No projects yet")); assert(!find("Refresh quality"));
  override = undefined;
  link.dataset.page = "training"; location.hash = "#training";
  const start = requests.length;
  await route(); assert.deepEqual(requests.slice(start), ["/api/training"]); assert.equal(link.attrs["aria-current"], "page");
  for (const text of [lesson.title, "Modeling practice", lesson.exercise, ...lesson.workflow, ...lesson.deliverables,
    ...lesson.verification, "Major Mayhem · Gameplay", "Curriculum " + curriculum.curriculum_sha256]) assert(find(text), text);
  assert(!all().some(node => ["img", "script", "form", "button"].includes(node.tag)));
  const filter = all().find(node => node.tag === "select");
  assert.equal(filter.id, all().find(node => node.tag === "label").htmlFor);
  filter.value = "gameplay"; filter.events.change(); assert(find(lesson.title)); assert(!find("Modeling practice"));
  assert.equal(requests.length, start + 1);
  for (const malformed of [{version: 2}, {tracks: [lesson, lesson]}, {tracks: [{...lesson, roles: ["unknown"]}]},
    {tracks: [{...lesson, workflow: []}]}, {curriculum_sha256: null}]) {
    patch("training", malformed); await route(); assert(find("Training unavailable")); assert(!find(lesson.exercise));
  }
  let finishTraining;
  override = url => url.endsWith("/training") ? [200, new Promise(done => { finishTraining = done; })] : null;
  const pendingTraining = route();
  location.hash = "#quality"; await route(); assert(find(evidence));
  finishTraining(curriculum); await pendingTraining; assert(!find(lesson.exercise));
  console.log("PASS Training navigation without a project, role filters, safe playbooks, invalid content and late replies.");
  console.log("PASS Read-only Quality route, scope checks, report totals, unsafe markup, partial and empty data, refresh and navigation races.");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
