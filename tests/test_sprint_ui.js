"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Exercise the production hash route and handlers with deterministic, delayed HTTP responses.
class Node {
  constructor(tag) {
    Object.assign(this, {tag, children: [], events: {}, attrs: {}, textContent: "", value: "", classList: {toggle() {}}});
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  *all() { yield this; for (const node of this.children) yield* node.all(); }
  querySelectorAll(selector) { return [...this.all()].filter(node => selector.split(", ").includes(node.tag)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  addEventListener(type, handle) { this.events[type] = handle; }
  focus() { this.focused = true; }
}
const view = new Node("main"), location = {hash: "#sprint"}, link = new Node("a");
link.dataset = {page: "sprint"};
const nodes = {"#view": view, "#location": new Node("span"), "#notice": new Node("div"), "#new-project": new Node("dialog")};
const document = {createElement: tag => new Node(tag), querySelector: key => nodes[key], querySelectorAll: () => [link]};
const requests = [];
let responder;
async function fetch(url, options) {
  const request = {url, method: options.method, data: options.body && JSON.parse(options.body), headers: options.headers};
  requests.push(request);
  const [status, data] = await responder(request);
  return {ok: status < 300, status, json: async () => structuredClone(data)};
}
const ui = path.join(__dirname, "../command_center/ui");
assert.match(fs.readFileSync(path.join(ui, "index.html"), "utf8"), /href="#sprint" data-page="sprint"/);
const script = fs.readFileSync(path.join(ui, "app.js"), "utf8")
  .split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const {route, state} = vm.runInNewContext(script + "\n;({route,state});",
  {document, location, fetch, setTimeout: () => 0, clearTimeout() {}});
const sha = "a".repeat(64), past = "b".repeat(64), planId = "f".repeat(64);
const projects = [{id: "alpha", name: "Alpha"}, {id: "beta", name: "Beta"}];
const base = {project_id: "alpha", spec_sha256: sha};
const tasks = [{id: "verify", title: "Verify build", priority: 4, gate: "build", role: "build_operations", depends_on: []},
  {id: "review", title: "Review the release", priority: 2, gate: "manual", role: "verification", depends_on: ["verify"]}];
const preview = {...base, plan_id: planId, board_revision: 0, status: "ready", reason: "Review the proposed tasks.", tasks,
  rationale: [{task_id: "verify", detail: "Confirm the current build.", evidence: ["Missing build"]},
    {task_id: "review", detail: "Review after verification.", evidence: ["No active release"]}]};
const applied = {...base, revision: 1, tasks};
const acceptance = {...base, status: "pending", summary: "Manual review is pending.", gates: [
  {id: "build", label: "Verified build", status: "pass", evidence: "Verified build 24."},
  {id: "manual_review", label: "Manual review", status: "pending", evidence: "No review evidence."}]};
const old = {id: "capture-1", spec_sha256: past, created_at: "2026-11-19T10:00:00Z", status: "blocked", note: "Old snapshot",
  checks: [{id: "build", label: "Build package", status: "fail", evidence: "Previously failed"}]};
const history = {...base, revision: 1, items: [old]};
const captured = {...old, id: "capture-2", spec_sha256: sha, created_at: "2026-11-20T10:00:00Z",
  note: "Check after run", checks: [{id: "build", label: "Build package", status: "pass", evidence: "Passed at capture"}]};
const normal = request => {
  assert.equal(request.method, "GET", "A mutation requires an explicit fixture");
  if (request.url === "/api/projects") return [200, projects];
  const [, id, source] = /^\/api\/projects\/(alpha|beta)\/(sprint|acceptance|evidence-history)$/.exec(request.url);
  return [200, {...{sprint: preview, acceptance, "evidence-history": history}[source], project_id: id}];
};
const serve = override => { responder = request => override?.(request) ?? normal(request); };
const text = value => [...view.all()].find(node => node.textContent === value);
const apply = () => text("Apply plan to task board");
const capture = () => view.querySelector("form");
const note = () => view.querySelector("textarea");
const submit = form => form.events.submit({preventDefault() {}});
const refresh = () => text("Refresh sprint").events.click();
const mutations = () => requests.filter(request => request.method === "POST");
const deferred = () => { let resolve; return {promise: new Promise(done => {resolve = done;}), resolve}; };
const switchProject = async id => {
  const select = view.querySelector("select");
  select.value = id;
  select.events.change();
  await new Promise(done => setImmediate(done));
};

async function run() {
  serve(); await route();
  assert.equal(link.attrs["aria-current"], "page"); assert.equal(state.selected, "alpha");
  assert.equal(requests.length, 4); assert.equal(mutations().length, 0);
  for (const label of ["Sprint plan", "Verify build", "Missing build", "Depends on verify", "Review after verification.",
    "Acceptance report", "No review evidence.", "Passed", "Earlier specification", "Previously failed",
    `Snapshot capture-1 · Captured specification · ${past}`]) assert(text(label), label);
  assert(text("Advisory assessment for the saved specification. Release promotion is a separate action in Releases."));
  assert(note().required); assert.equal(note().name, "note"); assert.equal(text("Capture note (1–512 characters)").tag, "label");
  note().value = " "; await submit(capture()); assert.equal(mutations().length, 0);
  note().value = "𝄞".repeat(513); await submit(capture()); assert(text("Enter a capture note of 1–512 characters."));
  note().value = "Keep working note";
  const waitApply = deferred();
  const empty = {...preview, board_revision: 1, reason: "All proposals already have tasks.", status: "empty", tasks: [], rationale: []};
  serve(r => r.method === "POST" ? waitApply.promise : r.url.endsWith("/sprint") ? [200, empty] : undefined);
  const firstApply = apply();
  const savingPlan = firstApply.events.click();
  assert(firstApply.disabled); await firstApply.events.click(); await submit(capture());
  assert.equal(mutations().length, 1);
  assert.deepEqual(mutations()[0], {url: "/api/projects/alpha/sprint", method: "POST",
    data: {expected_revision: 0, spec_sha256: sha, plan_id: planId},
    headers: mutations()[0].headers});
  assert.equal(mutations()[0].headers["X-Studio-Request"], "1");
  waitApply.resolve([200, applied]); await savingPlan;
  assert(text("Applied the plan to task board revision 1.")); assert(!apply()); assert.equal(note().value, "Keep working note");
  await firstApply.events.click(); assert.equal(mutations().length, 1);

  const saved = {...history, revision: 2, items: [captured, old]};
  note().value = "  Check after run  ";
  const waitCapture = deferred(), firstForm = capture();
  serve(r => r.method === "POST" ? waitCapture.promise : undefined);
  const savingHistory = submit(firstForm); await submit(firstForm); assert.equal(mutations().length, 2);
  const captureRequest = mutations().at(-1);
  assert.equal(captureRequest.url, "/api/projects/alpha/evidence-history"); assert.equal(captureRequest.headers["X-Studio-Request"], "1");
  assert.deepEqual(captureRequest.data, {expected_revision: 1, spec_sha256: sha, note: "Check after run"});
  waitCapture.resolve([200, saved]); await savingHistory;
  assert(text("Captured evidence at history revision 2.")); assert.equal(note().value, "");
  assert(text("Matches saved specification")); assert(text("Earlier specification")); assert(text("Passed at capture"));
  const times = view.querySelectorAll("time"); assert.deepEqual(times.map(node => node.dateTime), [captured.created_at, old.created_at]);

  note().value = "Preserve on conflict";
  serve(r => r.method === "POST" ? [409, {error: "History revision changed."}]
    : r.url.endsWith("/evidence-history") ? [200, {...saved, revision: 3}] : undefined);
  await submit(capture()); assert.equal(mutations().length, 3);
  assert(text("History revision changed. Review the refreshed sprint before submitting again."));
  assert(text(`History revision 3 · Saved specification · ${sha}`)); assert.equal(note().value, "Preserve on conflict");
  const stalePlan = apply();
  serve(r => r.method === "POST" ? [409, {error: "Preview changed."}]
    : r.url.endsWith("/sprint") ? [200, {...empty, board_revision: null, status: "blocked", reason: "The board is unreadable."}] : undefined);
  await stalePlan.events.click(); assert.equal(mutations().length, 4); assert(!apply());
  assert(text("The board is unreadable.")); assert(text("Board revision · Unavailable"));
  assert(text("Preview changed. Review the refreshed sprint before submitting again."));
  await stalePlan.events.click(); assert.equal(mutations().length, 4);

  serve(r => r.url.endsWith("/sprint") ? [503, {error: "Planner offline."}] : undefined); await refresh();
  assert(text("Planner offline.")); assert(text("Acceptance report")); assert(capture()); assert(!apply());
  serve(r => r.url.endsWith("/evidence-history") ? [500, {error: "History offline."}] : undefined); await refresh();
  assert(text("History offline.")); assert(apply()); assert(text("Verified build 24.")); assert(!capture());
  serve(r => r.url.endsWith("/acceptance") ? [200, {...acceptance, project_id: "beta"}] : undefined); await refresh();
  assert(text("Acceptance report unavailable")); assert(apply()); assert(capture());
  serve(r => r.url.endsWith("/acceptance") ? [200, {...acceptance, spec_sha256: past}] : undefined); await refresh();
  assert(text("The specification changed while loading. Refresh sprint before applying a plan or capturing evidence."));
  assert(!apply()); assert(!capture());
  serve(r => r.url.endsWith("/evidence-history") ? [200, {...history, items: Array.from({length: 100}, () => old)}] : undefined);
  await refresh(); assert(!capture()); assert(text("This project has reached its limit of 100 snapshots."));

  serve(); await refresh(); note().value = "Previous spec draft";
  serve(r => r.url !== "/api/projects" ? [200, {...normal(r)[1], spec_sha256: past}] : undefined); await refresh();
  assert.equal(note().value, ""); assert(apply());
  note().value = "Late capture";
  const late = deferred(); serve(r => r.method === "POST" ? late.promise : undefined);
  const saving = submit(capture()); await switchProject("beta"); assert.equal(state.selected, "beta");
  late.resolve([200, {...saved, spec_sha256: past}]); await saving;
  assert(!text("Captured evidence at history revision 2.")); assert.equal(note().value, "");
  const lateReport = deferred();
  serve(r => r.url === "/api/projects/beta/acceptance" ? lateReport.promise : undefined);
  const loading = refresh(); await switchProject("alpha");
  lateReport.resolve([200, {...acceptance, project_id: "beta", summary: "Stale report from beta"}]); await loading;
  assert(!text("Stale report from beta")); assert(text(acceptance.summary));
  serve(r => r.url === "/api/projects" ? [200, []] : undefined); await route();
  assert(text("A project is required")); assert(!apply()); assert(!capture());
  console.log("PASS sprint route, explicit plan and evidence writes, conflicts, acceptance gates, historical provenance, partial outages and project races");
}
run().catch(error => {console.error(error); process.exitCode = 1;});
