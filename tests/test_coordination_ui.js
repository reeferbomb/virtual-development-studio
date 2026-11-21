"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag) {
    Object.assign(this, {tag, events: {}, attrs: {}, children: [], textContent: ""});
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  *all() { yield this; for (const child of this.children) yield* child.all(); }
  addEventListener(event, handler) { this.events[event] = handler; }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  set innerHTML(value) { throw new Error("Unsafe HTML sink: " + value); }
}
const directory = path.join(__dirname, "../command_center/ui");
assert.match(fs.readFileSync(path.join(directory, "index.html"), "utf8"), /href="#coordination" data-page="coordination"/);
const script = fs.readFileSync(path.join(directory, "app.js"), "utf8").split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const view = new Element("main"), link = new Element("a"), location = {hash: "#coordination"};
link.dataset = {page: "coordination"};
const nodes = {"#view": view, "#new-project": new Element("dialog"), "#location": new Element("strong")};
const document = {createElement: tag => new Element(tag), querySelector: key => nodes[key], querySelectorAll: () => [link]};
const projects = [{id: "alpha", name: "Alpha"}, {id: "beta", name: "Beta"}];
const roles = ["architecture", "gameplay", "verification", "ui", "content", "build_operations"];
const spec = "a".repeat(64), handoff = "b".repeat(32), revision = 9;
const codeSample = "<script>review()</script>", maliciousTitle = "<img src=x onerror=alert(1)>";
const task = {task_id: "design", title: maliciousTitle, role: "architecture", downstream_count: 2, chain_length: 2, priority: 4};
const memory = {handoff_id: handoff, task_id: "test", attempt: 1, outcome: "progress", summary: codeSample,
  evidence: ["Observed input issue."], next_action: "Inspect boundary input.", reviewed_at: "2026-10-01T12:00:00+00:00"};
const advisory = {task_id: "test", role: "verification", title: "Verify input", attempt: 1, reason: "Waiting on input.",
  affected_count: 2, handoff_id: handoff, next_action: "Review the matching report."};
const assignment = {project_id: "alpha", task_id: "design", role: "architecture", title: "Design the layout",
  priority: 4, spec_sha256: spec, board_revision: revision, model_id: "gpt-6.2-astra", reasoning_effort: "ultra"};
const sources = {
  "specialist-memory": {status: "current", handoff_revision: 4, historical_count: 2, note: "Recent accepted reports.",
    roles: roles.map(role => ({role, accepted_count: role === "verification" ? 1 : 0, memories: role === "verification" ? [memory] : []}))},
  priorities: {status: "current", note: "Lead reviews priority.", board_revision: revision,
    candidates: [task, {...task, task_id: "later", title: "Later candidate"}], recommendations: [task]},
  "recovery-advice": {status: "current", note: "Lead decides recovery.", board_revision: revision, handoff_revision: 4,
    items: [advisory, {...advisory, task_id: "log", title: "Inspect log", handoff_id: null}]}
};
const allocation = {status: "current", note: "Shared role suggestions.", summary: {capacity: 6, assigned: 1, idle: 3, conflicts: 1, occupied: 1},
  roles: roles.map(role => {
    if (role === "architecture") return {role, state: "assigned", project_ids: ["alpha"], assignment};
    if (role === "ui") return {role, state: "occupied", project_ids: ["beta"], assignment: null};
    if (role === "gameplay") return {role, state: "conflict", project_ids: ["alpha", "beta"], assignment: null};
    return {role, state: "idle", project_ids: [], assignment: null};
  })};
const requests = [];
let override;
function usual(url) {
  if (url === "/api/projects") return projects;
  if (url === "/api/allocation") return allocation;
  const [, id, source] = /^\/api\/projects\/(alpha|beta)\/(specialist-memory|priorities|recovery-advice)$/.exec(url);
  return {...sources[source], project_id: id, spec_sha256: spec};
}
async function fetch(url, options) {
  assert.equal(options.method, "GET"); assert.equal(options.body, undefined);
  requests.push(url);
  const [status, value] = override?.(url) || [200, usual(url)];
  return {ok: status === 200, status, json: async () => structuredClone(await value)};
}
const {route, state} = vm.runInNewContext(script + "\n;({route,state});", {document, location, fetch});
const all = () => [...view.all()];
const find = text => all().find(node => node.textContent === text);
const refresh = () => find("Refresh coordination").events.click();
const changeReport = (source, patch) => { override = url => url.endsWith("/" + source) ? [200, {...usual(url), ...patch}] : null; };
const switchTo = async id => {
  const select = all().find(node => node.tag === "select");
  select.value = id; select.events.change();
  await new Promise(done => setImmediate(done));
};
const warning = "Project reports disagree. Refresh coordination to load a consistent snapshot.";
async function run() {
  await route();
  assert.equal(link.attrs["aria-current"], "page");
  assert.equal(document.title, "Coordination · Graveforge Studios Command Center");
  assert.equal(all().find(node => node.tag === "label").htmlFor, all().find(node => node.tag === "select").id);
  assert.deepEqual(requests, ["/api/projects", ...Object.keys(sources).map(key => "/api/projects/alpha/" + key), "/api/allocation"]);
  const panels = all().filter(node => node.tag === "section");
  assert.equal(panels.length, 4);
  assert(panels.every(node => node.children[0].tag === "h2"));
  for (const text of ["Specialist memory", codeSample, "Observed input issue.", "Task priorities", maliciousTitle, "Later candidate",
    "Recommended", "Recovery advice", "Waiting on input.", "Review the matching report.", "Shared role allocation",
    "Projects · alpha, beta", "Conflict", "Design the layout"]) assert(find(text), text);
  assert.equal(all().filter(node => node.tag === "button").length, 1);
  assert.equal(all().filter(node => node.tag === "img" || node.tag === "script").length, 0);
  assert(all().some(node => node.attrs.role === "status"));
  for (const [source, patch] of [["priorities", {project_id: "beta"}], ["specialist-memory", {spec_sha256: "c".repeat(64)}],
    ["recovery-advice", {handoff_revision: 5}], ["priorities", {board_revision: revision + 1}],
    ["allocation", {roles: allocation.roles.map(row => row.assignment ? {...row, assignment: {...assignment, board_revision: 10}} : row)}]]) {
    changeReport(source, patch); await refresh();
    assert(find(warning)); assert(!find(codeSample)); assert(!find(maliciousTitle)); assert(!find("Design the layout"));
  }
  changeReport("allocation", {summary: {...allocation.summary, idle: 6}}); await refresh();
  assert(find("Shared role allocation unavailable")); assert(!find("Design the layout")); assert(find(codeSample));
  changeReport("priorities", {recommendations: [{...task, task_id: "missing"}]}); await refresh();
  assert(find("Task priorities unavailable")); assert(!find("Recommended"));
  override = url => url.endsWith("/specialist-memory") ? [503, {error: "Handoff source offline."}] : null;
  await refresh(); assert(find("Handoff source offline.")); assert(find("Review the matching report."));
  changeReport("specialist-memory", {status: "unavailable", roles: [], historical_count: null, handoff_revision: null, note: "Unreadable ledger."});
  await refresh(); assert(find("Unreadable ledger.")); assert(!find(codeSample));
  override = url => {
    if (url.endsWith("/priorities")) return [200, {...usual(url), status: "stale", candidates: [], recommendations: [], note: "Board predates this spec."}];
    if (url.endsWith("/recovery-advice")) return [200, {...usual(url), status: "stale", items: [], note: "Review the current board."}];
    if (url.endsWith("/allocation")) return [200, {...allocation, status: "unavailable", roles: [], summary: {capacity: 6, assigned: 0, occupied: 0, idle: 0, conflicts: 0}, note: "Unreadable portfolio."}];
  };
  await refresh(); assert(find("Earlier specification")); assert(!find(maliciousTitle)); assert(!find("Idle")); assert(find("Unreadable portfolio."));
  override = undefined; await refresh();
  let resolve;
  const delayed = new Promise(done => { resolve = done; });
  override = url => url === "/api/projects/alpha/priorities" ? [200, delayed] : null;
  const old = find("Refresh coordination"), pending = old.events.click();
  assert(old.disabled); assert(!find(maliciousTitle));
  const count = requests.length;
  await old.events.click(); assert.equal(requests.length, count);
  await switchTo("beta"); assert.equal(state.selected, "beta"); assert(find(maliciousTitle));
  resolve({...usual("/api/projects/alpha/priorities"), note: "Outdated response."}); await pending;
  assert(!find("Outdated response."));
  const after = requests.length; await old.events.click(); assert.equal(requests.length, after);
  override = url => url === "/api/projects" ? [200, []] : null;
  await route(); assert(find("No projects yet")); assert(!find("Refresh coordination")); assert(!view.attrs["aria-busy"]);
  console.log("PASS Coordination route, safe read-only panels, project and revision checks, unavailable data, refresh and switching races.");
}
run().catch(error => {console.error(error); process.exitCode = 1;});
