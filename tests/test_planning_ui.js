"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Run the real hash route and its event handlers. Deferred HTTP replies exercise project switches.
class Node {
  constructor(tag) {
    Object.assign(this, {tag, events: {}, attrs: {}, children: [], textContent: "", classList: {toggle() {}}});
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  *all() { yield this; for (const child of this.children) yield* child.all(); }
  querySelectorAll(selector) { return [...this.all()].filter(node => selector.split(", ").includes(node.tag)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
  addEventListener(event, callback) { this.events[event] = callback; }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  focus() { this.focused = true; }
  click() { downloads.push({filename: this.download, blob: blobs[this.href]}); }
  remove() {}
}
const directory = path.join(__dirname, "../command_center/ui");
assert.match(fs.readFileSync(path.join(directory, "index.html"), "utf8"), /href="#planning" data-page="planning"/);
const script = fs.readFileSync(path.join(directory, "app.js"), "utf8").split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const view = new Node("main"), link = new Node("a"), location = {hash: "#planning"};
link.dataset = {page: "planning"};
const nodes = {"#view": view, "#new-project": new Node("dialog"), "#location": new Node("strong")};
const document = {body: new Node("body"), createElement: tag => new Node(tag), querySelector: key => nodes[key], querySelectorAll: () => [link]};
const requests = [], downloads = [], blobs = [];
let respond;
async function fetch(url, options) {
  const request = {url, method: options.method, headers: options.headers, body: options.body && JSON.parse(options.body)};
  requests.push(request);
  const [status, value] = await respond(request);
  const raw = typeof value === "string" ? value : JSON.stringify(value);
  return {ok: status < 300, status, json: async () => JSON.parse(raw), text: async () => raw};
}
const {route, state} = vm.runInNewContext(script + "\n;({route,state});", {document, location, fetch, Blob,
  setTimeout: () => 0, clearTimeout() {}, URL: {createObjectURL: blob => blobs.push(blob) - 1, revokeObjectURL() {}}});
const sha = "a".repeat(64), planId = "b".repeat(64), project_id = "alpha";
const tasks = [{id: "design", role: "architecture", gate: "manual", priority: 4, title: "Design the level", depends_on: []},
  {id: "build", role: "build_operations", gate: "build", priority: 2, title: "Package the level", depends_on: ["design"]}];
const blocked = [{task_id: "design", role: "architecture", reason: "Awaiting map approval.", affected_task_ids: ["build"], affected_count: 1}];
const checks = [{id: "build", label: "Build evidence", status: "pending", detail: "Run a verified build."}];
const identity = {project_id, spec_sha256: sha}, version = {...identity, board_revision: 0};
const blueprint = {...version, template_id: "world", title: "World production", plan_id: planId, status: "ready", reason: "Empty board.", tasks};
const forecast = {...version, status: "current", waves: [{wave: 1, task_ids: ["art"]}, {wave: 2, task_ids: ["audio"]}],
  unscheduled: ["design", "build"], remaining_tasks: 4, minimum_dependency_waves: null, note: "Assumes each wave completes."};
const impact = {...version, status: "current", blocked, affected_task_ids: ["build"], critical_chain: ["design", "build"], note: "Based on unfinished work."};
function preflight(id = project_id, spec_sha256 = sha, revision = 0) {
  const report = {project_id: id, spec_sha256, status: "pending", checks, board_revision: revision, dossier_sha256: "e".repeat(64), advisory: "Review the release dossier separately.", value: 2};
  return JSON.stringify({project_id: id, spec_sha256, checks, status: report.status, report_sha256: "f".repeat(64), report}, null, 2).replaceAll('"value": 2', '"value": 2.0') + "\n";
}
const sources = {blueprint, forecast, "dependency-impact": impact, preflight: null};
const projects = [{id: project_id, name: "Alpha"}, {id: "beta", name: "Beta"}];
function normal(request) {
  assert.equal(request.method, "GET", "Unexpected mutation");
  if (request.url === "/api/projects") return [200, projects];
  const [, id, source] = /^\/api\/projects\/(alpha|beta)\/(blueprint|forecast|dependency-impact|preflight)$/.exec(request.url);
  return [200, source === "preflight" ? preflight(id) : {...sources[source], project_id: id}];
}
const serve = override => { respond = request => override?.(request) ?? normal(request); };
const find = label => [...view.all()].find(node => node.textContent === label);
const click = label => {const control = find(label); assert(control, label); return control.events.click();};
const refresh = () => click("Refresh planning");
const writes = () => requests.filter(request => request.method !== "GET");
const deferred = () => {let resolve; return {promise: new Promise(done => {resolve = done;}), resolve};};
async function switchProject(id) {
  const picker = view.querySelector("select");
  picker.value = id; picker.events.change();
  await new Promise(done => setImmediate(done));
}
async function run() {
  serve(); await route();
  assert.equal(link.attrs["aria-current"], "page");
  assert.equal(state.selected, project_id);
  assert.deepEqual(requests.map(r => r.url), ["/api/projects", ...Object.keys(sources).map(source => "/api/projects/alpha/" + source)]);
  for (const label of ["Production blueprint", "World production", "Design the level", "Package the level", "Depends on design",
    "Capacity forecast", "Wave 1", "art", "Wave 2", "audio", "Unscheduled tasks", "Dependency impact",
    "Awaiting map approval.", "design → build", "Delivery preflight", "Build evidence", "Run a verified build."]) assert(find(label), label);
  const download = find("Download preflight JSON");
  await download.events.click(); assert.equal(downloads[0].filename, "alpha-preflight.json");
  assert.equal(await downloads[0].blob.text(), preflight());
  await click("Apply blueprint…"); assert(!writes().length); assert(find("Confirm and add 2 tasks"));
  await click("Cancel"); assert(!writes().length); assert(!find("Confirm and add 2 tasks"));
  await click("Apply blueprint…");
  const oldConfirm = find("Confirm and add 2 tasks"), pending = deferred();
  serve(r => r.method === "POST" ? pending.promise : undefined);
  const applying = oldConfirm.events.click(); await oldConfirm.events.click();
  assert.equal(writes().length, 1); assert.equal(writes()[0].url, "/api/projects/alpha/blueprint");
  assert.deepEqual(writes()[0].body, {expected_revision: 0, spec_sha256: sha, plan_id: planId});
  assert.equal(writes()[0].headers["X-Studio-Request"], "1");
  pending.resolve([409, {error: "Preview changed."}]); await applying;
  assert(find("Preview changed. Review the refreshed blueprint before applying."));
  assert.equal(writes().length, 1); assert(!find("Confirm and add 2 tasks")); await oldConfirm.events.click();
  assert.equal(writes().length, 1); await download.events.click(); assert.equal(downloads.length, 1);

  serve(r => r.method === "POST" ? [200, {...identity, revision: 1, tasks}]
    : r.url.endsWith("/blueprint") ? [200, {...blueprint, status: "applied", plan_id: null, board_revision: 1}]
    : r.url.endsWith("/preflight") ? [200, preflight(project_id, sha, 1)]
    : /\/(forecast|dependency-impact)$/.test(r.url) ? [200, {...normal(r)[1], board_revision: 1}] : undefined);
  await click("Apply blueprint…"); await click("Confirm and add 2 tasks");
  assert(find("Blueprint added to task board revision 1.")); assert(!find("Apply blueprint…")); assert.equal(writes().length, 2);

  serve(r => r.url.endsWith("/forecast") ? [503, {error: "Forecast offline."}] : undefined); await refresh();
  assert(find("Forecast offline.")); assert(find("Apply blueprint…")); assert(find("Download preflight JSON"));
  serve(r => r.url.endsWith("/blueprint") ? [200, {...blueprint, status: "blocked", tasks: [], reason: "Board unavailable.", plan_id: null, board_revision: null}] : undefined);
  await refresh(); assert(find("Board unavailable.")); assert(!find("Apply blueprint…")); assert(find("Capacity forecast"));
  serve(r => r.url.endsWith("/blueprint") ? [200, {...blueprint, tasks: [{...tasks[0], gate: "unexpected"}]}] : undefined);
  await refresh(); assert(find("Production blueprint unavailable")); assert(!find("Apply blueprint…"));
  serve(r => r.url.endsWith("/dependency-impact") ? [200, {...impact, project_id: "beta"}] : undefined);
  await refresh(); assert(find("Dependency impact unavailable")); assert(!find("Awaiting map approval."));
  for (const stateName of ["stale", "unavailable", "empty"]) {
    serve(r => r.url.endsWith("/forecast") ? [200, {...forecast, status: stateName, waves: [], unscheduled: [], remaining_tasks: 0,
      minimum_dependency_waves: stateName === "empty" ? 0 : null, board_revision: stateName === "unavailable" ? null : 0}]
      : r.url.endsWith("/dependency-impact") ? [200, {...impact, status: stateName, blocked: [], affected_task_ids: [],
        critical_chain: [], board_revision: stateName === "unavailable" ? null : 0}] : undefined);
    await refresh(); assert(find("Capacity forecast")); assert(find("Dependency impact")); assert(!find("Wave 1"));
    if (stateName !== "empty") assert(!find("Remaining tasks"));
  }
  serve(r => r.url.endsWith("/preflight") ? [200, preflight("alpha", "d".repeat(64))] : undefined); await refresh();
  assert(!find("Apply blueprint…")); assert(!find("Download preflight JSON"));
  serve(r => r.url.endsWith("/forecast") ? [200, {...forecast, board_revision: 3}] : undefined); await refresh();
  assert(!find("Apply blueprint…"));
  serve(r => r.url.endsWith("/preflight") ? [200, preflight(project_id, sha, 8)] : undefined); await refresh();
  assert(!find("Apply blueprint…")); assert(!find("Download preflight JSON"));
  const inconsistent = JSON.parse(preflight());
  inconsistent.status = inconsistent.report.status = "ready";
  serve(r => r.url.endsWith("/preflight") ? [200, inconsistent] : undefined); await refresh();
  assert(find("Delivery preflight unavailable")); assert(!find("Preflight checks passed"));
  const passed = {...checks[0], status: "pass", detail: "Verified bundle."};
  inconsistent.checks = inconsistent.report.checks = [passed];
  await refresh(); assert(find("Preflight checks passed"));
  serve(); await refresh();
  const oldDownload = find("Download preflight JSON"); await click("Apply blueprint…");
  const beforeSwitch = find("Confirm and add 2 tasks"); await switchProject("beta");
  await oldDownload.events.click(); await beforeSwitch.events.click();
  assert.equal(downloads.length, 1); assert.equal(writes().length, 2);
  const waiting = deferred();
  serve(r => r.url === "/api/projects/beta/forecast" ? waiting.promise : undefined);
  const loading = refresh(); await switchProject("alpha");
  waiting.resolve([200, {...forecast, project_id: "beta", note: "Old project response."}]); await loading;
  assert(!find("Old project response.")); assert(find("Apply blueprint…"));
  const lateWrite = deferred();
  serve(r => r.method === "POST" ? lateWrite.promise : undefined);
  await click("Apply blueprint…"); const late = click("Confirm and add 2 tasks");
  location.hash = "#projects"; await route(); const beforeReturn = requests.length;
  lateWrite.resolve([409, {error: "Old conflict."}]); await late;
  assert(!find("Old conflict. Review the refreshed blueprint before applying."));
  assert.equal(requests.length, beforeReturn);
  serve(r => r.url === "/api/projects" ? [200, []] : undefined); location.hash = "#planning"; await route();
  assert(find("A project is required")); assert(!find("Apply blueprint…"));
  console.log("PASS Planning route, blueprint review and CAS, conflict refresh, read-only reports, partial failures, exact downloads and navigation races.");
}
run().catch(error => {console.error(error); process.exitCode = 1;});
