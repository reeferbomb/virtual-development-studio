"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const downloads = [];
const objects = new Map();
class Node {
  constructor(tag) {
    Object.assign(this, {tag, children: [], attrs: {}, events: {}, value: "", textContent: ""});
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  *all() { yield this; for (const child of this.children) yield* child.all(); }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  addEventListener(type, listener) { this.events[type] = listener; }
  focus() { this.focused = true; }
  click() { if (this.tag === "a") downloads.push({filename: this.download, blob: objects.get(this.href)}); }
  remove() { document.body.children = document.body.children.filter(node => node !== this); }
  set innerHTML(value) { throw Error("Lab content must be rendered as text"); }
}

const view = new Node("main"), location = {hash: "#lab"};
const nodes = {"#view": view, "#new-project": new Node("dialog"), "#location": new Node("p")};
const document = {body: new Node("body"), createElement: tag => new Node(tag), querySelector: id => nodes[id], querySelectorAll: () => []};
const requests = [];
let respond;
async function fetch(url, options) {
  const request = {url, method: options.method, headers: options.headers, rawBody: options.body, body: options.body && JSON.parse(options.body)};
  requests.push(request);
  const [status, data] = await respond(request);
  return {ok: status < 300, status, json: async () => structuredClone(data), text: async () => JSON.stringify(data, null, 2)};
}
const directory = path.join(__dirname, "../command_center/ui");
const script = fs.readFileSync(path.join(directory, "app.js"), "utf8")
  .split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const URL = {createObjectURL(blob) { objects.set("blob:download", blob); return "blob:download"; },
  revokeObjectURL(url) { objects.delete(url); }};
const route = vm.runInNewContext(script + "\n;route", {document, location, fetch, Blob, URL, setTimeout});
const digest = "a".repeat(64);
const sample = {asset: "<img src='no-file'>"};
const first = {id: "art", title: "Art review", brief: "Review the <mesh> package.", roles: ["content"],
  criteria: [{id: "asset", label: "Identify asset"}, {id: "review", label: "Name a reviewer"}], example: sample};
const second = {id: "review", title: "Interface review", brief: "Inspect the interface.", roles: ["ui"],
  criteria: [{id: "items", label: "List controls"}], example: {items: ["Menu"]}};
const lab = {version: 1, lab_sha256: digest, exercises: [first, second], note: "Practice with structural checks."};
const failed = {version: 1, lab_sha256: digest, exercise_id: "art", submission_sha256: "b".repeat(64),
  assessment_sha256: "c".repeat(64), status: "fail", summary: {pass: 1, fail: 1}, checks: [
    {id: "asset", label: "Identify asset", status: "pass", detail: "Found <mesh>."},
    {id: "review", label: "Name a reviewer", status: "fail", detail: "Missing reviewer."}], note: "Structural measurements."};
const passed = {...failed, status: "pass", summary: {pass: 2, fail: 0},
  checks: [failed.checks[0], {...failed.checks[1], status: "pass", detail: "Reviewer present."}]};
const posts = () => requests.filter(request => request.method === "POST");
const find = fn => [...view.all()].find(fn);
const tag = name => find(node => node.tag === name);
const text = value => find(node => node.textContent === value);
const edit = value => {
  const input = tag("textarea");
  input.value = value;
  input.events.input();
};
const change = value => {
  const select = tag("select");
  select.value = value;
  select.events.change();
};
const submit = () => tag("form").events.submit({preventDefault() {}});
function pending() {
  let resolve;
  return {promise: new Promise(done => { resolve = done; }), resolve};
}

async function run() {
  respond = () => [200, lab];
  await route();
  assert.deepEqual(requests.map(row => row.url), ["/api/training-lab"], "The lab must load without a project");
  assert.match(fs.readFileSync(path.join(directory, "index.html"), "utf8"), /href="#lab" data-page="lab"/);
  assert(text(first.brief)); assert(text(first.criteria[0].label)); assert(text("Grimbrush · Content"));
  assert(text(JSON.stringify(sample, null, 2))); assert.equal(tag("textarea").value, "");
  for (const control of [tag("select"), tag("textarea")]) {
    assert(control.id && find(node => node.tag === "label" && node.htmlFor === control.id));
  }
  for (const input of ["{", "false", "null", "[]", '{"value":1e999}']) {
    edit(input); await submit();
    assert.equal(tag("textarea").attrs["aria-invalid"], "true"); assert.equal(posts().length, 0);
  }
  text("Use example").events.click();
  assert.deepEqual(JSON.parse(tag("textarea").value), sample); assert.equal(posts().length, 0);
  const duplicate = '{"asset":"first","asset":"second","weight":1.2300}';
  edit(duplicate);
  respond = request => request.rawBody.includes(duplicate) ? [400, {error: "Duplicate JSON key."}] : [200, passed];
  await submit();
  assert(posts().at(-1).rawBody.includes(duplicate), "Preserve duplicate fields and original numeric literals for the server");
  assert(text("Duplicate JSON key.")); assert.equal(tag("textarea").value, duplicate);
  text("Use example").events.click();
  const reply = pending(); respond = () => reply.promise;
  const firstRequest = submit();
  await submit();
  assert.equal(posts().length, 2); assert.equal(posts().at(-1).url, "/api/training-lab/assess");
  assert.equal(posts().at(-1).headers["X-Studio-Request"], "1");
  assert.deepEqual(posts().at(-1).body, {exercise_id: "art", submission: sample});
  reply.resolve([200, failed]); await firstRequest;
  assert(text("1 passed · 1 failed")); assert(text("Missing reviewer.")); assert(text("Found <mesh>."));
  assert(text(failed.note)); assert.equal(downloads.length, 0);
  const download = text("Download assessment JSON");
  assert(download, "Assessed submissions must be explicitly downloadable");
  download.events.click();
  assert.equal(downloads.length, 1);
  assert.match(downloads[0].filename, /assessment.*[.]json$/);
  assert.equal(await downloads[0].blob.text(), JSON.stringify(failed, null, 2));

  edit('{"asset":"edited","reviewer":"Sam"}'); assert(!text("Missing reviewer."));
  download.events.click(); assert.equal(downloads.length, 1, "Stale assessment control must be inactive");
  respond = () => [400, {error: "Exercise fields are invalid."}];
  await submit();
  assert(text("Exercise fields are invalid.")); assert.match(tag("textarea").value, /edited/);
  const obsolete = pending(); respond = () => obsolete.promise;
  const earlier = submit();
  edit('{"asset":"newer","reviewer":"Sam"}');
  respond = () => [200, passed]; await submit();
  assert(text("2 passed · 0 failed"));
  obsolete.resolve([200, failed]); await earlier;
  assert(text("Reviewer present.")); assert(!text("Missing reviewer."));

  for (const invalid of [{...passed, exercise_id: "other"}, {...passed, lab_sha256: "d".repeat(64)},
    {...passed, status: "fail"}, {...passed, checks: [passed.checks[0], passed.checks[0]]},
    {...passed, summary: {pass: 1, fail: 1}}, {...passed, assessment_sha256: null}]) {
    respond = () => [200, invalid]; await submit();
    assert(!text("Reviewer present.")); assert(text("The assessment could not be matched to this exercise."));
  }
  const switched = pending(); respond = () => switched.promise;
  const beforeSelection = submit();
  change("review");
  assert(text(second.brief)); assert(text("Madame Glitch · UI")); assert.equal(tag("textarea").value, "");
  switched.resolve([400, {error: "Late error"}]); await beforeSelection;
  assert(!text("Late error")); assert(!text("Reviewer present."));

  text("Use example").events.click();
  const departed = pending(); respond = () => departed.promise;
  const beforeLeaving = submit();
  location.hash = "#projects"; respond = () => [200, []]; await route();
  departed.resolve([400, {error: "Departed error"}]); await beforeLeaving;
  assert(text("Start your first project")); assert(!text("Departed error"));
  const beforeLoading = pending();
  location.hash = "#lab"; respond = () => beforeLoading.promise; const loading = route();
  location.hash = "#projects"; respond = () => [200, []]; await route();
  beforeLoading.resolve([200, lab]); await loading;
  assert(text("Start your first project")); assert(!tag("textarea"));

  location.hash = "#lab";
  respond = () => [200, {...lab, exercises: [first, first]}];
  await route(); assert(!tag("form")); assert(text("Lab unavailable"));
  respond = () => [200, lab]; await route();
  assert.equal(tag("textarea").value, "");
  console.log("PASS project-independent Lab, accessible controls, explicit examples/assessment, JSON validation, structural evidence, identity, and stale responses.");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
