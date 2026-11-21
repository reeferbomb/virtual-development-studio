"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Exercise the real route, action callbacks and request bodies without npm dependencies.
class Node {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.events = {};
    this.attrs = {};
    this.dataset = {};
    this.classList = {toggle() {}};
    this.textContent = "";
    this.value = "";
  }
  append(...nodes) {
    for (const node of nodes) {
      if (this.tag === "select" && !this.children.length) this.value = node.value;
      this.children.push(node);
      node.parentElement = this;
    }
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  replaceWith(node) {
    const siblings = this.parentElement.children;
    siblings[siblings.indexOf(this)] = node;
    node.parentElement = this.parentElement;
  }
  remove() { this.parentElement.children = this.parentElement.children.filter(node => node !== this); }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  focus() { document.activeElement = this; }
  click() { if (this.tag === "a") downloads.push(this.download); }
  addEventListener(type, callback) { this.events[type] = callback; }
  get firstElementChild() { return this.children[0]; }
  get lastElementChild() { return this.children.at(-1); }
  get childElementCount() { return this.children.length; }
  *all() { yield this; for (const child of this.children) yield* child.all(); }
  querySelectorAll(tag) { return [...this.all()].filter(node => node.tag === tag); }
  querySelector(tag) { return this.querySelectorAll(tag)[0]; }
}

const view = new Node("main"), notice = new Node("p");
const location = {hash: "#workspace"}, downloads = [], requests = [];
const fixed = {"#view": view, "#notice": notice, "#new-project": new Node("dialog"), "#location": new Node("p")};
const document = {
  body: new Node("body"), createElement: tag => new Node(tag), querySelectorAll: () => [],
  querySelector: key => fixed[key] || [...view.all()].find(node => "#" + node.id === key)
};
let responder;
async function fetch(url, options) {
  const request = {url, method: options.method, headers: options.headers,
    data: options.body ? JSON.parse(options.body) : null};
  requests.push(request);
  const [status, data] = await responder(request);
  return {ok: status < 300, status, json: async () => data};
}
const source = fs.readFileSync(path.join(__dirname, "../command_center/ui/app.js"), "utf8")
  .split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const app = vm.runInNewContext(source + "\n;({state,route,refreshJobs});", {
  document, location, fetch, structuredClone, window: {}, URL, Blob, setTimeout: () => 0, clearTimeout() {}
});
const sha = "a".repeat(64), earlier = "b".repeat(64);
const projects = [{id: "alpha", name: "Alpha", kind: "assets", spec: {}}, {id: "beta", name: "Beta", kind: "assets", spec: {}}];
const job = (id, status, fields = {}) => ({id, status, project_id: "alpha", kind: "assets",
  verified: status === "passed", output: status === "passed" ? "jobs/" + id + "/output" : null,
  spec_sha256: sha, priority: 3, ...fields});
const running = job("running", "running"), waiting = job("waiting", "queued", {priority: 5});
const passed = job("pass", "passed"), failed = job("failed", "failed");
let queue = {running, queued: [waiting], counts: {running: 1, queued: 1}};
let jobs = [passed, failed, running, waiting];
let registry = {project_id: "alpha", spec_sha256: sha, revision: 0, releases: [], active_release_id: null, active_state: "empty"};
const release = (id, jobId, digest = sha) => ({id, job_id: jobId, spec_sha256: digest,
  created_at: "2026-11-20T10:00:00Z", output: "jobs/" + jobId + "/output", manifest_sha256: "f".repeat(64)});
const assignment = {project_id: "alpha", task_id: "draft", title: "Review release notes", role: "ui",
  priority: 4, model_id: "example-model", reasoning_effort: "ultra", board_revision: 7, spec_sha256: sha};
let portfolio = {projects: [{project_id: "alpha", name: "Alpha", state: "current", revision: 7, spec_sha256: sha,
  summary: {ready: 1, running: 1, total: 2}}, {project_id: "beta", name: "Beta", state: "stale", revision: 1,
  spec_sha256: earlier, summary: {ready: 0, running: 1, total: 1}}], assignments: [assignment],
  occupied_roles: ["verification"], conflicts: [{role: "verification", project_ids: ["alpha", "beta"]}],
  summary: {projects: 2, current: 1, stale: 1, empty: 0, unavailable: 0, running: 2, ready: 1},
  dispatch_plan: {execution_mode: "export_only", assignments: [assignment], spawn_args: [{}]}};
const normal = request => {
  const data = new Map([
    ["/api/projects", projects], ["/api/projects/alpha", projects[0]], ["/api/queue", queue], ["/api/jobs", jobs],
    ["/api/projects/alpha/releases", registry], ["/api/release/alpha", {latest_job: passed, verification_gate: {status: "passed"}}],
    ["/api/portfolio", portfolio]
  ]);
  if (request.method === "GET" && data.has(request.url)) return [200, data.get(request.url)];
  if (request.method === "GET" && request.url.endsWith("/log")) return [200, {log: "Build log for " + request.url}];
  throw Error("Unexpected request " + JSON.stringify(request));
};
const serve = override => { responder = request => override?.(request) ?? normal(request); };
const find = (value, root = view) => [...root.all()].find(node => node.textContent === value);
const matches = value => [...view.all()].filter(node => node.textContent === value);
const field = name => [...view.all()].find(node => node.name === name);
const click = (label, root = view) => find(label, root).events.click();
const arrive = async page => { location.hash = "#" + page; await app.route(); };
const pending = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
};
let mutations = [];
const capture = request => {
  assert.equal(request.headers["X-Studio-Request"], "1");
  mutations.push(request);
};

async function testQueue() {
  serve(); await arrive("workspace");
  assert.equal(field("build_priority").value, "3");
  assert.equal(field("build_priority").parentElement.textContent, "Build priority");
  field("build_priority").value = "5";
  const submitting = pending();
  serve(request => {
    if (request.method === "POST") { capture(request); return submitting.promise; }
  });
  const build = click("Queue build");
  await click("Queue build");
  assert.equal(mutations.length, 1); assert.deepEqual(mutations[0].data, {priority: 5});
  assert.equal(mutations[0].url, "/api/projects/alpha/build");
  await arrive("portfolio"); submitting.resolve([202, waiting]); await build;
  assert.equal(location.hash, "#portfolio"); assert.equal(app.state.job, null);
  serve(); await arrive("builds");
  assert(find("Position 1 · Priority 5")); assert.equal(matches("Cancel build").length, 1);
  assert.equal(matches("Retry build").length, 1);
  const cancelRequest = pending();
  serve(request => {
    if (request.method === "POST") { capture(request); return cancelRequest.promise; }
  });
  const cancel = click("Cancel build");
  await click("Cancel build");
  assert.equal(mutations.length, 2); assert.equal(mutations.at(-1).url, "/api/jobs/waiting/cancel");
  assert.deepEqual(mutations.at(-1).data, {});
  const canceled = {...waiting, status: "canceled"};
  jobs = [passed, canceled, running]; queue = {...queue, queued: []};
  cancelRequest.resolve([200, canceled]); await cancel;
  assert(find("No builds are waiting.")); assert(find("canceled"));
  const retry = job("retry", "queued", {retry_of: waiting.id, priority: 5});
  serve(request => {
    if (request.method === "POST") {
      capture(request); queue = {...queue, queued: [retry]}; jobs = [retry, ...jobs]; return [202, retry];
    }
  });
  await click("Retry build"); assert.equal(mutations.at(-1).url, "/api/jobs/waiting/retry");
  assert.deepEqual(mutations.at(-1).data, {}); assert(find("Retry of waiting"));
  assert(find("Build log for /api/jobs/retry/log")); assert(find("Viewing log"));

  const delayedQueue = pending(); let first = true;
  serve(({url}) => {
    if (url === "/api/queue" && first) { first = false; return delayedQueue.promise; }
  });
  const stalePoll = app.refreshJobs(true);
  queue = {running: null, queued: [], counts: {running: 0, queued: 0}};
  await app.refreshJobs(true); assert(find("The build worker is idle."));
  delayedQueue.resolve([200, {running, queued: [waiting]}]); await stalePoll;
  assert(!find("Cancel build")); assert(find("The build worker is idle."));
  serve(({url}) => url === "/api/queue" ? [503, {error: "Queue offline"}] : undefined);
  await app.refreshJobs(true); assert(find("Queue offline")); assert(find("Retry build"));
}

async function testReleases() {
  jobs = [passed, job("stale", "passed", {spec_sha256: earlier}), job("foreign", "passed", {project_id: "beta"}),
    job("unverified", "passed", {verified: false}), failed];
  serve(); await arrive("releases");
  assert(find("No releases have been promoted.")); assert(find("Latest build · pass · verification passed"));
  assert.deepEqual(field("release_job").children.map(n => n.value), ["pass"]);
  const onPromote = pending();
  serve(request => {
    if (request.method === "PUT") { capture(request); return onPromote.promise; }
  });
  const before = mutations.length;
  const promoting = click("Promote and activate"); await click("Promote and activate");
  assert.equal(mutations.length, before + 1);
  assert.deepEqual(mutations.at(-1).data, {expected_revision: 0, spec_sha256: sha, action: {op: "promote", job_id: "pass"}});
  registry = {...registry, active_release_id: "r2", revision: 3, active_state: "current",
    releases: [release("r0", "historic", earlier), release("r1", "another"), release("r2", "pass")]};
  onPromote.resolve([200, registry]); await promoting;
  assert(find("Revision 3")); assert(!find("Promote and activate")); assert(find("Earlier specification"));
  assert.equal(matches("Activate release").length, 1); assert(find("Manifest · " + "f".repeat(64)));
  serve(request => {
    if (request.method === "PUT") { capture(request); return [409, {error: "Revision conflict."}]; }
  });
  await click("Activate release");
  assert.deepEqual(mutations.at(-1).data, {expected_revision: 3, spec_sha256: sha, action: {op: "activate", release_id: "r1"}});
  assert(find("Revision conflict. Refresh releases before trying again.")); assert(find("Active release · r2"));
  registry = {...registry, revision: 4, active_state: "invalid"};
  serve(); await click("Refresh releases"); assert(find("invalid")); assert(find("Revision 4"));
  const activation = pending();
  serve(request => { if (request.method === "PUT") { capture(request); return activation.promise; } });
  const delayed = click("Activate release"); await arrive("portfolio");
  activation.resolve([200, {...registry, revision: 5, active_release_id: "r1"}]); await delayed;
  assert(!find("Revision 5")); assert(find("Portfolio overview"));
  registry = {...registry, spec_sha256: "c".repeat(64), active_state: "stale"};
  serve(({url}) => url === "/api/jobs" ? [500, {error: "History offline"}] : undefined);
  await arrive("releases"); assert(find("stale")); assert(!find("Activate release")); assert(!find("Promote and activate"));
  assert(find("Build history unavailable · History offline")); assert(find("Active release · r2"));
}

async function testPortfolio() {
  serve(); let before = requests.length; await arrive("portfolio");
  assert.deepEqual(requests.slice(before).map(request => request.url), ["/api/portfolio"]);
  assert(find("Review release notes")); assert(find("Doctor Doomcheck · Verification has overlapping work in Alpha, Beta."));
  assert(find("example-model · ultra effort · Board revision 7")); assert(find("Task draft · Specification " + sha));
  before = mutations.length; await click("Download portfolio dispatch JSON");
  assert.deepEqual(downloads, ["portfolio-dispatch.json"]); assert.equal(mutations.length, before);
  serve(request => request.url === "/api/portfolio" ? [200, {...portfolio, assignments: []}] : undefined);
  await click("Download portfolio dispatch JSON");
  assert(find("Recommendations have changed. Refresh the portfolio before exporting.")); assert.equal(downloads.length, 1);
  const exportRequest = pending();
  serve(request => request.url === "/api/portfolio" ? exportRequest.promise : undefined);
  const exportResult = click("Download portfolio dispatch JSON"); await arrive("builds");
  exportRequest.resolve([200, portfolio]); await exportResult; assert.equal(downloads.length, 1);
  portfolio = {...portfolio, projects: [...portfolio.projects, {project_id: "gamma", name: "Gamma", state: "unavailable",
    summary: null, revision: null, spec_sha256: null, error: "Unreadable board"}], assignments: [],
    summary: {...portfolio.summary, unavailable: 1, projects: 3}};
  serve(); await arrive("portfolio"); assert(find("Unreadable board"));
  assert(find("Recommendations are paused until all project boards are readable.")); assert(!find("Download portfolio dispatch JSON"));
  portfolio = {...portfolio, projects: []};
  await click("Refresh portfolio"); assert(find("No projects yet"));
  serve(request => request.url === "/api/portfolio" ? [503, {error: "Portfolio offline"}] : undefined);
  await arrive("portfolio"); assert(find("Portfolio offline")); assert(find("Try again"));
}

async function run() {
  await testQueue(); await testReleases(); await testPortfolio();
  console.log("PASS build priorities, queue actions and polling, release eligibility and revision guards, portfolio recommendations, export safety and navigation races");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
