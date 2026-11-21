"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Run the actual route and event handlers with a minimal DOM and explicit HTTP fixtures.
class Node {
  constructor(tag) {
    Object.assign(this, {tag, children: [], events: {}, attrs: {}, textContent: "", value: "", classList: {toggle() {}}});
  }
  append(...nodes) {
    for (const node of nodes) {
      if (this.tag === "select" && !this.children.length) this.value = node.value;
      this.children.push(node);
      node.parentElement = this;
    }
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  *all() { yield this; for (const node of this.children) yield* node.all(); }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  addEventListener(type, listener) { this.events[type] = listener; }
  focus() { this.focused = true; }
}

const view = new Node("main"), notice = new Node("p"), location = {hash: "#supervisor"};
const nodes = {"#view": view, "#notice": notice, "#location": new Node("p"), "#new-project": new Node("dialog")};
const document = {createElement: tag => new Node(tag), querySelector: key => nodes[key], querySelectorAll: () => []};
const requests = [];
let responder;
async function fetch(url, options) {
  const request = {url, method: options.method, headers: options.headers, data: options.body && JSON.parse(options.body)};
  requests.push(request);
  const [status, data] = await responder(request);
  return {ok: status < 300, status, json: async () => structuredClone(data)};
}
const ui = path.join(__dirname, "../command_center/ui");
assert.match(fs.readFileSync(path.join(ui, "index.html"), "utf8"), /href="#supervisor" data-page="supervisor"/);
const source = fs.readFileSync(path.join(ui, "app.js"), "utf8")
  .split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const {route, state, taskRoles, renderDispatchPlan} = vm.runInNewContext(source + "\n;({route,state,taskRoles,renderDispatchPlan});",
  {document, location, fetch, setTimeout: () => 0, clearTimeout() {}});
const sha = "a".repeat(64), previous = "b".repeat(64);
const projects = [{id: "alpha", name: "Alpha"}, {id: "beta", name: "Beta"}];
const base = {project_id: "alpha", spec_sha256: sha};
const rec = {id: "inspect", title: "Inspect mesh bounds", detail: "Check the oversized mesh.",
  role: "verification", evidence: ["Mesh report line 10"], severity: "high"};
const audit = {...base, status: "attention", checks: [{id: "size", label: "Mesh bounds", status: "warn", evidence: "Mesh exceeded bounds"}],
  recommendations: [rec]};
const profile = {...base, scope: "current_spec", counts: {total: 1, passed: 1, queued: 0, running: 0, failed: 0, canceled: 0},
  samples: [{job_id: "job-1", created_at: null, status: "passed", queue_seconds: null, build_seconds: 1, verify_seconds: 0, total_seconds: 1}],
  summary: {median_build_seconds: 1, median_verify_seconds: 0, median_total_seconds: 1, latest_total_seconds: null,
    baseline_total_seconds: null, regression_percent: null}, regression: null};
const summary = {current_open: 0, current_resolved: 0, historical_open: 0, historical_resolved: 0};
const empty = {...base, revision: 0, items: [], summary};
const defect = {id: "d1", title: "Mesh too wide", severity: "high", description: "The preview clips.", status: "open",
  spec_sha256: sha, created_at: "2026-11-20T10:00:00Z", updated_at: "2026-11-20T11:00:00Z", evidence: ["Measured edge"]};
let ledger = empty;
const normal = request => {
  if (request.method !== "GET") throw Error("Unexpected mutation");
  if (request.url === "/api/projects") return [200, projects];
  const [, id, source] = /^\/api\/projects\/(alpha|beta)\/(supervisor|performance|defects)$/.exec(request.url);
  return [200, {...{supervisor: audit, performance: profile, defects: ledger}[source], project_id: id}];
};
const serve = override => { responder = request => override?.(request) ?? normal(request); };
const text = (value, parent = view) => [...parent.all()].find(node => node.textContent === value);
const find = (fn, parent = view) => [...parent.all()].find(fn);
const form = (label, parent = view) => find(node => node.tag === "form" &&
  find(child => child.type === "submit" && child.textContent === label, node), parent);
const row = label => find(node => node.tag === "article" && text(label, node));
const field = (name, parent) => find(node => node.name === name, parent);
const submit = item => item.events.submit({preventDefault() {}});
const click = label => text(label).events.click();
const deferred = () => { let resolve; return {promise: new Promise(done => { resolve = done; }), resolve}; };
const mutations = () => requests.filter(request => request.method === "PUT");
const changeProject = async id => {
  const select = find(node => node.id === "active-project");
  select.value = id;
  select.events.change();
  // projectPicker invokes route() without returning its promise.
  await new Promise(done => setImmediate(done));
};

async function run() {
  const roster = renderDispatchPlan({project: {id: "alpha"}, profile: {team_name: "The Midnight Shift", roles: [],
    max_parallel: 6, service_tier: "priority", continuity: {target_duration_seconds: 18000, checkpoint_interval_seconds: 300}}});
  assert(text("The Midnight Shift", roster));
  serve();
  await route();
  assert(text("Mesh exceeded bounds")); assert(text("Mesh report line 10")); assert(text("Doctor Doomcheck · Verification"));
  assert.equal(Object.values(taskRoles).length, 6);
  assert.deepEqual(Object.keys(taskRoles), ["architecture","gameplay","verification","ui","content","build_operations"]);
  assert(text("job-1")); assert(text("Unmeasured")); assert(text("0 s")); assert(text("No timing comparison"));
  assert(text("No defects recorded for this specification.")); assert(text("No historical defects."));
  const add = form("Record defect");
  field("title", add).value = " Mesh too wide ";
  field("description", add).value = " The preview clips. ";
  field("severity", add).value = "high";
  field("evidence", add).value = "   ";
  await submit(add);
  assert(text("Enter 1–8 evidence entries of up to 512 characters each.")); assert.equal(mutations().length, 0);
  field("evidence", add).value = " Measured edge \n\n Screenshot ";
  const old = {...defect, id: "old", title: "Historical bug", spec_sha256: previous};
  ledger = {...empty, revision: 1, items: [defect, old], summary: {...summary, current_open: 1, historical_open: 1}};
  const send = deferred();
  serve(request => request.method === "PUT" ? send.promise : undefined);
  const pending = submit(add);
  await submit(add); assert.equal(mutations().length, 1);
  assert.equal(mutations()[0].url, "/api/projects/alpha/defects"); assert.equal(mutations()[0].headers["X-Studio-Request"], "1");
  assert.deepEqual(mutations()[0].data, {expected_revision: 0, spec_sha256: sha, action: {op: "add", title: "Mesh too wide",
    severity: "high", description: "The preview clips.", evidence: ["Measured edge", "Screenshot"]}});
  send.resolve([200, ledger]); await pending;
  assert(text("Revision 1")); assert(text("Historical defects are read-only.")); assert(!form("Resolve defect", row("Historical bug")));
  const resolve = form("Resolve defect", row("Mesh too wide"));
  field("evidence", resolve).value = "Retested bounds";
  field("title", form("Record defect")).value = "Separate unsaved item";
  serve(request => request.method === "PUT" ? [409, {error: "Revision conflict."}] : undefined);
  await submit(resolve);
  assert.deepEqual(mutations().at(-1).data, {expected_revision: 1, spec_sha256: sha, action: {op: "resolve", defect_id: "d1", evidence: ["Retested bounds"]}});
  assert(text("Revision conflict. Refresh supervisor to review the latest revision.")); assert(find(node => node.tag === "fieldset", resolve).disabled);
  const before = mutations().length;
  await submit(resolve); assert.equal(mutations().length, before);
  ledger = {...ledger, revision: 2};
  serve(); await click("Refresh supervisor");
  assert.equal(field("evidence", form("Resolve defect")).value, "Retested bounds");
  assert.equal(field("title", form("Record defect")).value, "Separate unsaved item");
  ledger = {...ledger, revision: 3, items: [{...defect, status: "resolved", evidence: [...defect.evidence, "Retested bounds"]}, old],
    summary: {...summary, current_resolved: 1, historical_open: 1}};
  serve(request => request.method === "PUT" ? [200, ledger] : undefined);
  await submit(form("Resolve defect")); assert.equal(mutations().at(-1).data.expected_revision, 2);
  assert(text("Retested bounds")); assert(!form("Resolve defect")); assert(form("Reopen defect"));
  assert.equal(field("title", form("Record defect")).value, "Separate unsaved item");
  field("evidence", form("Reopen defect")).value = "Bounds clip again";
  const reopening = deferred(); serve(request => request.method === "PUT" ? reopening.promise : undefined);
  const saving = submit(form("Reopen defect"));
  assert.deepEqual(mutations().at(-1).data, {expected_revision: 3, spec_sha256: sha, action: {op: "reopen", defect_id: "d1", evidence: ["Bounds clip again"]}});
  await changeProject("beta"); assert.equal(state.selected, "beta");
  const oldNotice = notice.textContent;
  reopening.resolve([200, {...ledger, revision: 4}]); await saving;
  assert(!text("Revision 4")); assert.equal(notice.textContent, oldNotice);

  serve(({url}) => url.endsWith("/performance") ? [503, {error: "Timings offline."}] : undefined);
  await route(); assert(text("Timings offline.")); assert(text("Mesh exceeded bounds")); assert(form("Record defect"));
  serve(({url}) => url.endsWith("/defects") ? [200, {...ledger, project_id: "different"}] : undefined);
  await click("Refresh supervisor"); assert(text("Defect ledger unavailable")); assert(!form("Record defect")); assert(text("Build performance"));
  serve(({url}) => url.endsWith("/defects") ? [200, {...ledger, project_id: "beta", spec_sha256: previous}] : undefined);
  await click("Refresh supervisor"); assert(text("The specification changed while loading. Refresh supervisor before editing defects."));
  assert(!form("Record defect")); assert(!form("Resolve defect")); assert(!form("Reopen defect"));

  const late = deferred();
  serve(({url}) => url === "/api/projects/beta/supervisor" ? late.promise : undefined);
  const previousView = click("Refresh supervisor");
  await changeProject("alpha");
  late.resolve([200, {...audit, project_id: "beta", checks: [{id: "late", label: "LATE", evidence: "Unexpected", status: "fail"}]}]); await previousView;
  assert.equal(state.selected, "alpha"); assert(!text("LATE")); assert(text("Mesh exceeded bounds"));
  serve(({url}) => url.endsWith("/supervisor") ? [200, {...audit, checks: [], recommendations: []}]
    : url.endsWith("/performance") ? [200, {...profile, samples: [], regression: true, summary: {...profile.summary, regression_percent: 30}}] : undefined);
  await route(); assert(text("No checks recorded.")); assert(text("No recommendations for this specification."));
  assert(text("Timing regression")); assert(text("30%")); assert(text("No build samples for this specification."));
  serve(({url}) => url === "/api/projects" ? [200, []] : undefined);
  await route(); assert(text("A project is required"));
  console.log("PASS supervisor checks, roles, measured timings, defect lifecycle, concurrency, partial errors, history and route races");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
