"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Run the production hash route and its handlers against a small DOM and deterministic HTTP fixtures.
class Node {
  constructor(tag) {
    Object.assign(this, {tag, textContent: "", value: "", children: [], events: {}, attrs: {}, classList: {toggle() {}}});
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  *all() { yield this; for (const node of this.children) yield* node.all(); }
  querySelectorAll(selector) { return [...this.all()].filter(node => selector.split(", ").includes(node.tag)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
  addEventListener(event, callback) { this.events[event] = callback; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  focus() { this.focused = true; }
  click() { downloads.push({filename: this.download, blob: blobs[this.href]}); }
  remove() {}
}
const ui = path.join(__dirname, "../command_center/ui");
const html = fs.readFileSync(path.join(ui, "index.html"), "utf8");
assert.match(html, /href="#operations" data-page="operations"/);
const source = fs.readFileSync(path.join(ui, "app.js"), "utf8")
  .split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const view = new Node("main"), nav = new Node("a"), location = {hash: "#operations"};
nav.dataset = {page: "operations"};
const nodes = {"#view": view, "#location": new Node("strong"), "#new-project": new Node("dialog"), "#notice": new Node("p")};
const document = {querySelector: key => nodes[key], createElement: tag => new Node(tag), querySelectorAll: () => [nav], body: new Node("body")};
const blobs = [], downloads = [], copies = [], requests = [];
const clipboard = {writeText: async value => {copies.push(value);}};
let respond;
async function fetch(url, options) {
  const request = {url, method: options.method, headers: options.headers, body: options.body && JSON.parse(options.body)};
  requests.push(request);
  const [status, value] = await respond(request);
  const raw = typeof value === "string" ? value : JSON.stringify(value);
  return {status, ok: status < 300, json: async () => JSON.parse(raw), text: async () => raw};
}
const {route, state} = vm.runInNewContext(source + "\n;({route,state});", {document, location, fetch,
  setTimeout: () => 0, clearTimeout() {}, navigator: {clipboard}, Blob,
  URL: {createObjectURL: blob => blobs.push(blob) - 1, revokeObjectURL() {}}});
const sha = "a".repeat(64), past = "b".repeat(64), orderId = "c".repeat(64);
const projects = [{id: "alpha", name: "Alpha"}, {id: "beta", name: "Beta"}];
const order = {order_id: orderId, task_id: "inspect", title: "Inspect the build", role: "verification",
  codename: "Doctor Doomcheck", gate: "manual", depends_on: ["build"], attempt: 2, board_revision: 4,
  spawn_args: {task_name: "doctor_doomcheck", fork_turns: "none", model: "gpt-6.2-astra", reasoning_effort: "ultra", message: "Work only on the claimed task."}};
const orders = {state: "current", board_revision: 4, orders: [order]};
const item = {id: "1".repeat(32), order_id: orderId, task_id: order.task_id, attempt: 2, role: order.role,
  board_revision: 4, spec_sha256: sha, created_at: "2026-11-01T10:00:00+00:00", outcome: "progress",
  summary: "Inspected one build", evidence: ["Build log"], changed_paths: ["src/game.py"], next_action: "Run second check",
  review: "pending", review_note: null, reviewed_at: null};
const historical = {...item, id: "2".repeat(32), spec_sha256: past, summary: "Earlier inspection"};
const ledger = {revision: 2, items: [item, historical]};
const dossier = {status: "pending", report_sha256: "d".repeat(64), report: {status: "pending", acceptance_status: "pending",
  gates: [{status: "pending", label: "Manual review", evidence: "Review outstanding"}], source_errors: {},
  handoffs: {covered_attempts: 1, completed_attempts: 2}, duration: 1}};
const bundle = {format: "studio-project-recovery-v1", bundle_sha256: "e".repeat(64), records: {
  "project.json": {data: {id: "alpha"}}, "spec.json": {sha256: sha, data: {scale: 1}}}};
const scope = (project_id = "alpha", spec_sha256 = sha) => ({project_id, spec_sha256});
const rawDossier = (id = "alpha", spec = sha) => JSON.stringify({...scope(id, spec), ...dossier,
  report: {...scope(id, spec), ...dossier.report}}).replace('"duration":1', '"duration":1.0') + "\n";
const rawBundle = JSON.stringify({...scope(), ...bundle}).replace('"scale":1', '"scale":1.0') + "\n";
function normal(request) {
  assert.equal(request.method, "GET", "Unexpected mutation");
  if (request.url === "/api/projects") return [200, projects];
  const [, id, name] = /^\/api\/projects\/(alpha|beta)\/(work-orders|handoffs|dossier|recovery)$/.exec(request.url);
  if (name === "dossier") return [200, rawDossier(id)];
  if (name === "recovery") return [200, rawBundle];
  return [200, {...scope(id), ...(name === "handoffs" ? ledger : orders)}];
}
const serve = override => { respond = request => override?.(request) ?? normal(request); };
const find = (label, node = view, tag) => [...node.all()].find(child => child.textContent === label && (!tag || tag === child.tag));
const named = (node, name) => [...node.all()].find(child => child.name === name);
const form = label => view.querySelectorAll("form").find(f => find(label, f, "button"));
const submit = f => f.events.submit({preventDefault() {}});
const click = label => find(label, view, "button").events.click();
const writes = () => requests.filter(request => request.method !== "GET");
const defer = () => {let resolve; return {promise: new Promise(done => {resolve = done;}), resolve};};
async function selectProject(id) {
  const picker = view.querySelector("select");
  picker.value = id;
  picker.events.change();
  await new Promise(done => setImmediate(done));
}

async function run() {
  serve(); await route();
  assert.equal(nav.attrs["aria-current"], "page"); assert.equal(state.selected, "alpha");
  assert.deepEqual(requests.map(r => r.url), ["/api/projects", "/api/projects/alpha/work-orders", "/api/projects/alpha/handoffs", "/api/projects/alpha/dossier"]);
  for (const label of ["Claimed work orders", "Running claim", "Inspect the build", "Doctor Doomcheck · Verification",
    "Depends on build", "Handoff ledger", "Earlier specification · Read-only", "Release dossier", "Pending",
    "Manual review · Review outstanding", "Accepted handoff coverage · 1 of 2 completed attempts", "Recovery bundle",
    "Records only. Back up build jobs, build outputs and release packages separately."]) assert(find(label), label);
  assert.equal(view.querySelectorAll("form").length, 2, "The historical handoff has no review form");
  const staleCopy = find("Copy work order");
  await click("Copy work order"); assert.deepEqual(JSON.parse(copies[0]), {...scope(), ...order});
  await click("Download work order"); assert.equal(downloads.at(-1).filename, "alpha-inspect-attempt-2.json");
  assert.deepEqual(JSON.parse(await downloads.at(-1).blob.text()), {...scope(), ...order});
  await click("Download dossier JSON"); assert.equal(await downloads.at(-1).blob.text(), rawDossier());
  await click("Download recovery JSON"); assert.equal(await downloads.at(-1).blob.text(), rawBundle);
  assert.equal(requests.filter(r => r.url.endsWith("/recovery")).length, 1); assert.equal(writes().length, 0);

  const send = form("Submit handoff");
  await submit(send); assert.equal(writes().length, 0); assert(find("Complete the required fields."));
  for (const [key, value] of Object.entries({summary: " Finished work ", outcome: "completed", changed_paths: "src/report.py\n",
    next_action: " Inspect report ", evidence: "a\n".repeat(9)})) named(send, key).value = value;
  await submit(send); assert.equal(writes().length, 0);
  named(send, "evidence").value = " First check \n\n Second check ";
  const oldReview = form("Review handoff");
  named(oldReview, "note").value = "Keep this review draft";
  const delayed = defer(); serve(r => r.method === "POST" ? delayed.promise : undefined);
  const pending = submit(send); await submit(send); await submit(oldReview);
  assert(find("Refresh operations").disabled); assert.equal(writes().length, 1);
  const sent = writes()[0];
  assert.equal(sent.url, "/api/projects/alpha/handoffs"); assert.equal(sent.headers["X-Studio-Request"], "1");
  assert.deepEqual(sent.body, {expected_revision: 2, spec_sha256: sha, action: {op: "submit", task_id: "inspect", order_id: orderId,
    outcome: "completed", summary: "Finished work", evidence: ["First check", "Second check"], changed_paths: ["src/report.py"], next_action: "Inspect report"}});
  const newItem = {...item, ...sent.body.action, id: "3".repeat(32)};
  const saved = {...scope(), revision: 3, items: [newItem, ...ledger.items]};
  delayed.resolve([200, saved]); await pending;
  assert(find("Handoff submitted at ledger revision 3.")); assert(find("Second check"));
  assert.equal(named(form("Submit handoff"), "summary").value, "");
  assert(view.querySelectorAll("textarea").some(node => node.value === "Keep this review draft"));
  await submit(send); await staleCopy.events.click(); assert.equal(writes().length, 1); assert.equal(copies.length, 1);

  const review = form("Review handoff");
  named(review, "decision").value = "rejected"; named(review, "note").value = " Missing test output ";
  serve(r => r.method === "POST" ? [409, {error: "Ledger changed."}]
    : r.url.endsWith("/handoffs") ? [200, {...saved, revision: 4}] : undefined);
  await submit(review); assert(find("Ledger changed. Review the refreshed records before submitting again."));
  const retry = form("Review handoff");
  assert.equal(named(retry, "note").value, " Missing test output ");
  assert.equal(writes().length, 2); await submit(review); assert.equal(writes().length, 2);
  const decided = {...newItem, review: "rejected", review_note: "Missing test output", reviewed_at: "2026-11-01T12:00:00+00:00"};
  serve(r => r.method === "POST" ? [200, {...saved, revision: 5, items: [decided, ...ledger.items]}] : undefined);
  await submit(retry);
  assert.deepEqual(writes().at(-1).body, {expected_revision: 4, spec_sha256: sha,
    action: {op: "review", handoff_id: newItem.id, decision: "rejected", note: "Missing test output"}});
  assert(find("Rejected")); assert(find("Missing test output")); assert(!find("Complete task"));
  assert.equal(view.querySelectorAll("form").length, 2);

  const refresh = () => click("Refresh operations");
  serve(r => r.url.endsWith("/work-orders") ? [503, {error: "Board offline."}] : undefined); await refresh();
  assert(find("Claimed work orders unavailable")); assert(find("Board offline.")); assert(form("Review handoff"));
  assert(!form("Submit handoff")); assert(find("Download dossier JSON")); assert(find("Download recovery JSON"));
  serve(r => r.url.endsWith("/handoffs") ? [500, {error: "History offline."}] : undefined); await refresh();
  assert(find("Handoff ledger unavailable")); assert(find("Copy work order")); assert(!form("Submit handoff"));
  serve(r => r.url.endsWith("/dossier") ? [200, rawDossier("beta")] : undefined); await refresh();
  assert(find("Release dossier unavailable")); assert(form("Submit handoff")); assert(!find("Download dossier JSON"));
  serve(r => r.url.endsWith("/dossier") ? [200, rawDossier("alpha", past)] : undefined); await refresh();
  assert(!form("Submit handoff")); assert(!form("Review handoff")); assert(!find("Copy work order")); assert(!find("Download recovery JSON"));
  assert(find("The specification changed while loading. Refresh operations before editing or exporting."));
  for (const state of ["empty", "stale", "unavailable"]) {
    serve(r => r.url.endsWith("/work-orders") ? [200, {...scope(), state, board_revision: state === "unavailable" ? null : 0, orders: []}] : undefined);
    await refresh(); assert(!find("Copy work order")); assert(!form("Submit handoff")); assert(form("Review handoff"));
  }
  serve(); await refresh();
  const late = defer(), priorDownloads = downloads.length;
  serve(r => r.url.endsWith("/recovery") ? late.promise : undefined);
  const recovering = click("Download recovery JSON");
  await selectProject("beta"); late.resolve([200, rawBundle]); await recovering;
  assert.equal(downloads.length, priorDownloads); assert.equal(state.selected, "beta"); assert(!find("Recovery bundle downloaded."));
  const waiting = defer();
  serve(r => r.url === "/api/projects/beta/handoffs" ? waiting.promise : undefined);
  const loading = refresh(); await selectProject("alpha");
  waiting.resolve([200, {...scope("beta"), revision: 1, items: [{...item, summary: "Late beta result"}]}]); await loading;
  assert(!find("Late beta result")); assert.equal(state.selected, "alpha");
  const lateWrite = defer(); serve(r => r.method === "POST" ? lateWrite.promise : undefined);
  const finalReview = form("Review handoff");
  named(finalReview, "decision").value = "accepted"; named(finalReview, "note").value = "Verified.";
  const reviewing = submit(finalReview);
  await selectProject("beta");
  lateWrite.resolve([409, {error: "Late alpha conflict."}]); await reviewing;
  assert(!find("Late alpha conflict. Review the refreshed records before submitting again."));
  serve(r => r.url === "/api/projects" ? [200, []] : undefined); await route(); assert(find("A project is required"));
  assert(!find("Download recovery JSON")); assert(writes().every(r => r.url.endsWith("/handoffs")));
  console.log("PASS Operations route, explicit exports, byte-preserving downloads, CAS submit/review, conflict drafts, historical records, partial outages and project switches.");
}
run().catch(error => {console.error(error); process.exitCode = 1;});
