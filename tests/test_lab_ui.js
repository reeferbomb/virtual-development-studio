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
const lab = {version: 2, lab_sha256: digest, exercises: [first, second], note: "Practice with structural checks."};
const failed = {version: 2, lab_sha256: digest, exercise_id: "art", submission_sha256: "b".repeat(64),
  assessment_sha256: "c".repeat(64), status: "fail", summary: {pass: 1, fail: 1}, checks: [
    {id: "asset", label: "Identify asset", status: "pass", detail: "Found <mesh>."},
    {id: "review", label: "Name a reviewer", status: "fail", detail: "Missing reviewer."}], note: "Structural measurements."};
const passed = {...failed, status: "pass", summary: {pass: 2, fail: 0},
  checks: [failed.checks[0], {...failed.checks[1], status: "pass", detail: "Reviewer present."}]};
const emptyRecords = {revision: 0, lab_sha256: digest, records: [], note: "Private workstation practice records."};
const catalogAnd = snapshot => request => [200, request.url === "/api/training-records" ? snapshot : lab];
const byId = id => find(node => node.id === id);
const choose = (input, value) => { input.value = value; input.events.change(); };
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
  respond = catalogAnd(emptyRecords);
  await route();
  assert.deepEqual(requests.map(row => row.url), ["/api/training-lab", "/api/training-records"], "The lab must load without a project");
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
  const oldRecord = text("Record assessed submission"), oldRole = byId("lab-record-role");
  choose(oldRole, "content");
  const download = text("Download assessment JSON");
  assert(download, "Assessed submissions must be explicitly downloadable");
  download.events.click();
  assert.equal(downloads.length, 1);
  assert.match(downloads[0].filename, /assessment.*[.]json$/);
  assert.equal(await downloads[0].blob.text(), JSON.stringify(failed, null, 2));

  edit('{"asset":"edited","reviewer":"Sam"}'); assert(!text("Missing reviewer."));
  download.events.click(); assert.equal(downloads.length, 1, "Stale assessment control must be inactive");
  const countBefore = posts().length; await oldRecord.events.click(); assert.equal(posts().length, countBefore);
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
  await recordsWorkflow();
  await artifactReportWorkflow();
  await actualAcademyWorkflow();
  console.log("PASS Lab assessments, private history and reviews, local artifact report import, invalid files, and stale controls.");
}

async function actualAcademyWorkflow() {
  const {spawnSync} = require("node:child_process");
  const fromPython = (args, input) => {
    const run = spawnSync("python3", args, {cwd: path.join(__dirname, ".."), encoding: "utf8", input, timeout: 20000});
    assert.equal(run.status, 0, run.stderr); return JSON.parse(run.stdout);
  };
  const actual = fromPython(["-m", "command_center.training_lab_cli", "catalog"]);
  assert.equal(actual.version, 3);
  assert.equal(actual.exercises.length, 22);
  const empty = {...emptyRecords, lab_sha256: actual.lab_sha256};
  location.hash = "#lab";
  respond = request => [200, request.url === "/api/training-records" ? empty : actual];
  await route();
  const experienceIds = ["player-enjoyment", "replayability", "player-research", "visual-direction",
    "visual-readability", "experience-iteration"];
  for (const id of ["cutscenes", "game-audio", "multiplayer", "persistence", "ai-encounters", "production-pipeline", ...experienceIds]) {
    const exercise = actual.exercises.find(row => row.id === id);
    assert(exercise, id); change(id); assert(text(exercise.brief));
    assert.equal(Boolean(text("Run a real Godot cutscene")), id === "cutscenes");
    assert.equal(Boolean(text("Apply this to a real game")), experienceIds.includes(id));
    if (id === "cutscenes") {
      assert([...view.all()].some(node => node.tag === "pre" && node.textContent.includes("cinematic.production.runner") && node.textContent.includes("--engine")));
    }
    text("Use example").events.click();
    assert.deepEqual(JSON.parse(tag("textarea").value), exercise.example);
    respond = request => {
      assert.equal(request.url, "/api/training-lab/assess");
      assert.equal(request.body.exercise_id, id);
      return [200, fromPython(["-c", "import json,sys; from command_center.training_lab import assess_submission; r=json.load(sys.stdin); print(json.dumps(assess_submission(r['exercise_id'],r['submission'])))"], request.rawBody)];
    };
    await submit();
    assert(text(`${exercise.criteria.length} passed · 0 failed`), id);
    assert(exercise.criteria.every(check => text(check.label)));
  }
}

async function artifactReportWorkflow() {
  location.hash = "#lab";
  respond = catalogAnd(emptyRecords); await route();
  const picker = byId("lab-artifact-file");
  assert(picker, "The Lab must offer a local artifact report file picker");
  assert.equal(picker.type, "file"); assert(find(node => node.tag === "label" && node.htmlFor === picker.id));
  const message = byId("lab-artifact-status");
  assert.equal(message.attrs.role, "status");
  const file = report => new Blob([JSON.stringify(report)], {type: "application/json"});
  const selectFile = selected => { picker.files = selected ? [selected] : []; return picker.events.change(); };
  const check = {id: "triangle_budget", measured: 24, limit: 100, status: "pass"};
  const base = {profile: "static-prop-glb-v1", status: "pass", sha256: digest, measurements: {triangles: 24},
    checks: [check], note: "Use <img onerror=alert(0)> only as report text."};
  const requestCount = requests.length, downloadCount = downloads.length;
  edit('{"in_progress":true}');
  await selectFile(file(base));
  assert(text(base.profile)); assert(text(base.note)); assert(text(check.id)); assert(text(digest));
  assert.equal(byId("lab-submission").value, '{"in_progress":true}'); assert(!text("Record assessed submission"));
  const failure = {...base, profile: "texture", status: "fail", checks: [{...check, status: "fail", measured: 120}]};
  await selectFile(file(failure)); assert(text("texture")); assert(!text(base.profile));
  for (const sha256 of [null, digest]) {
    const missing = {...base, sha256, status: "unavailable", checks: [], measurements: {}, note: "Engine missing"};
    const combined = {...base, profile: "character", status: "unavailable", sha256,
      checks: [{id: "engine", measured: "unavailable", limit: "pass", status: "unavailable"}], reports: [missing]};
    await selectFile(file(combined)); assert(text("character")); assert(text("Engine missing")); assert(text("engine"));
  }
  const componentCheck = {id: "static", measured: "pass", limit: "pass", status: "pass"};
  const bundle = {...base, profile: "artifact-pipeline-static-v1", checks: [componentCheck], reports: [base]};
  for (const invalid of [null, [], passed, {...base, sha256: null}, {...base, sha256: "x"},
    {...base, profile: ""}, {...base, status: "unknown"}, {...base, note: null}, {...base, measurements: []},
    {...base, checks: []}, {...base, checks: [{...check, status: "maybe"}]}, {...base, checks: [check, check]},
    {...base, checks: [{...check, measured: []}]}, {...base, checks: [{id: "budget", measured: 0, status: "pass"}]},
    {...base, status: "fail"}, {...base, reports: [{...base, sha256: null}]}, {...bundle, reports: []},
    {...bundle, reports: [{...base, sha256: "b".repeat(64)}]}, {...bundle, reports: [failure]},
    {...bundle, reports: [bundle]}, {...bundle, reports: [{...base, status: "unavailable", checks: []}]}]) {
    await selectFile(file(invalid)); assert.equal(picker.attrs["aria-invalid"], "true"); assert(!text(base.note));
  }
  await selectFile(new Blob(["1".padEnd(512 * 1024, " ")]));
  assert.match(message.textContent, /report/i);
  const maxSize = new Blob([JSON.stringify(base).padEnd(512 * 1024, " ")]);
  await selectFile(maxSize); assert(text(base.note)); assert(!picker.attrs["aria-invalid"]);
  let oversizedRead = false;
  await selectFile({size: 512 * 1024 + 1, text() { oversizedRead = true; }});
  assert.equal(oversizedRead, false); assert.match(message.textContent, /512 KiB/); assert(!text(base.note));
  for (const malformed of ["{", JSON.stringify(base).replace('"triangles":24', '"triangles":1e999')]) {
    await selectFile(new Blob([malformed])); assert.equal(picker.attrs["aria-invalid"], "true");
  }
  const slow = pending();
  const firstRead = selectFile({size: 20, text: () => slow.promise});
  await selectFile(file(failure)); slow.resolve(JSON.stringify(base)); await firstRead;
  assert(text(failure.profile)); assert(!text(base.profile));
  await selectFile({size: 18, async text() { throw Error("unreadable file"); }});
  assert(!text(failure.profile)); assert.equal(picker.attrs["aria-invalid"], "true");
  await selectFile(null); assert(!picker.attrs["aria-invalid"]); assert(!text(failure.profile));
  assert.equal(requests.length, requestCount, "Opening a local report must never make an API request");
  assert.equal(downloads.length, downloadCount);
  const {spawnSync} = require("node:child_process");
  const commands = [
    ["pass", "artifact_pipeline", "--profile", "static", "demo/first-batch/assets/supply_crate.glb"],
    ["pass", "artifact_pipeline", "--profile", "character", "vertical/demo/character/courier.glb"],
    ["fail", "artifact_pipeline", "--profile", "texture", "demo/asset-preview.png"],
    ["unavailable", "artifact_pipeline", "--profile", "static", "missing-for-ui-test.glb"],
    ["unavailable", "lab_engine_import", "missing-for-ui-test.glb"]
  ];
  for (const [expected, module, ...args] of commands) {
    const run = spawnSync("python3", ["-m", "command_center." + module, ...args],
      {cwd: path.join(__dirname, ".."), encoding: "utf8", timeout: 20000});
    assert.equal(run.status, {pass: 0, fail: 1, unavailable: 2}[expected], run.stderr);
    const generated = JSON.parse(run.stdout);
    assert.equal(generated.status, expected);
    await selectFile(new Blob([run.stdout]));
    assert(!picker.attrs["aria-invalid"], generated.profile); assert(text(generated.profile)); assert(text(generated.note));
    for (const component of generated.reports || []) {
      assert(text(component.profile)); assert(text(component.note));
      await selectFile(file(component)); assert(!picker.attrs["aria-invalid"], component.profile);
      assert(text(component.profile)); assert(text(component.note));
      await selectFile(file(generated));
    }
  }
  assert.equal(requests.length, requestCount);
  const departed = pending();
  const lastRead = selectFile({size: 20, text: () => departed.promise});
  location.hash = "#projects"; respond = () => [200, []]; await route();
  const oldStatus = message.textContent;
  departed.resolve(JSON.stringify(failure)); await lastRead;
  assert.equal(message.textContent, oldStatus); assert(text("Start your first project"));
}
async function recordsWorkflow() {
  const id = "0".repeat(31) + "1";
  const raw = '{"asset":"second","weight":1.2300}';
  const record = {id, role: "content", exercise_id: "art", current: true, reference: false,
    submission: JSON.parse(raw), report: passed, review: null, created_at: "2026-01-01T00:00:00+00:00"};
  const saved = {...emptyRecords, revision: 1, records: [record]};
  const review = {reviewer_role: "lead", decision: "accepted", note: "Checked the mesh.", reviewed_at: "2026-01-02T00:00:00+00:00"};
  const reviewed = {...saved, revision: 2, records: [{...record, review}]};
  const writeCount = () => posts().filter(row => row.url === "/api/training-records").length;
  respond = catalogAnd(emptyRecords); await route();
  assert(text("Private practice history")); assert(!text("Record assessed submission"));
  const ambiguous = '{"asset":"first","asset":"second","weight":1.2300}';
  // Even if an assessment reply was issued in error, the raw source must reach the strict record decoder.
  edit(ambiguous); respond = () => [200, passed]; await submit();
  choose(byId("lab-record-role"), "content");
  respond = () => [400, {error: "Duplicate JSON key."}]; await text("Record assessed submission").events.click();
  assert(posts().at(-1).rawBody.includes(ambiguous)); assert(text("Duplicate JSON key.")); assert(text("History unavailable"));
  assert.equal(byId("lab-submission").value, ambiguous); assert.equal(writeCount(), 1);
  respond = catalogAnd(emptyRecords); await text("Refresh history").events.click();
  edit(raw); respond = () => [200, passed]; await submit();
  const recordButton = text("Record assessed submission"), role = byId("lab-record-role");
  assert.deepEqual(role.children.map(option => option.value), ["", "content"]);
  assert.equal(recordButton.disabled, true); assert.equal(writeCount(), 1);
  choose(role, "content");
  assert.equal(recordButton.disabled, false);
  respond = request => request.method === "POST" ? [409, {error: "The assessed evidence changed."}] : [200, emptyRecords];
  await recordButton.events.click();
  assert.equal(writeCount(), 2); assert.equal(requests.at(-1).method, "GET");
  assert.equal(byId("lab-submission").value, raw); assert(text("2 passed · 0 failed"));
  const started = pending(); respond = () => started.promise;
  const saving = recordButton.events.click();
  await recordButton.events.click(); assert.equal(writeCount(), 3);
  assert.equal(posts().at(-1).headers["X-Studio-Request"], "1");
  assert(posts().at(-1).rawBody.includes(raw), "Recording must send the original JSON lexemes to the strict decoder");
  assert.deepEqual(posts().at(-1).body, {expected_revision: 0, action: {op: "record", role: "content", exercise_id: "art", expected_assessment_sha256: passed.assessment_sha256, submission: record.submission}});
  started.resolve([200, saved]); await saving;
  assert.equal(byId("lab-submission").value, raw);
  assert(!text("Record assessed submission") || text("Record assessed submission").disabled);
  assert(text("Pending review")); assert(!text(JSON.stringify(record.submission, null, 2)));
  const inspector = find(node => node.tag === "details" && node.children.some(child => child.textContent === "Inspect submission and rubric results"));
  inspector.open = true; inspector.events.toggle(); assert(text(JSON.stringify(record.submission, null, 2)));
  const reviewer = byId("lab-reviewer"), decision = byId("lab-decision"), note = byId("lab-review-note");
  assert(reviewer.children.some(option => option.value === "lead"));
  assert(!reviewer.children.some(option => option.value === "content"));
  assert(decision.children.some(option => option.value === "accepted"));
  assert(decision.children.some(option => option.value === "rejected"));
  choose(reviewer, "lead"); choose(decision, "accepted"); note.value = review.note; note.events.input();
  const other = {...record, id: "2".repeat(32), review};
  const changed = {...saved, revision: 3, records: [other, record]};
  respond = request => request.method === "POST" ? [409, {error: "Conflict"}] : [200, changed];
  await text("Save review").events.click();
  assert.equal(writeCount(), 4); assert.equal(requests.at(-1).method, "GET");
  assert.equal(byId("lab-submission").value, raw); assert.equal(byId("lab-review-note").value, review.note);
  respond = () => [200, {...changed, revision: 4, records: [other, {...record, review}]}]; await text("Save review").events.click();
  assert.deepEqual(posts().at(-1).body, {expected_revision: 3, action: {op: "review", record_id: id, reviewer_role: "lead", decision: "accepted", note: review.note}});
  assert(text("Accepted")); assert(text(review.note)); assert(!text("Save review"));

  for (const properties of [{reference: true}, {report: failed}]) {
    respond = catalogAnd({...saved, records: [{...record, ...properties}]}); await route();
    assert(byId("lab-decision").children.some(option => option.value === "rejected"));
    assert(!byId("lab-decision").children.some(option => option.value === "accepted"));
    if (properties.reference) assert(text("Reference example"));
  }
  const historical = {...record, current: false, report: {...passed, version: 1, lab_sha256: "9".repeat(64)}};
  respond = catalogAnd({...saved, records: [historical]}); await route();
  assert(text("Historical catalog")); assert(!text("Save review"));
  for (const invalid of [null, {...saved, revision: 0}, {...saved, lab_sha256: "9".repeat(64)}, {...saved, records: [record, record]},
    {...saved, records: [{...record, reference: true, review}]}, {...saved, records: [{...historical, current: true}]},
    {...saved, records: [{...record, review: {...review, reviewer_role: record.role}}]}]) {
    respond = catalogAnd(invalid); await route();
    assert(text("History unavailable")); assert(!text("Save review"));
    edit(raw); respond = () => [200, passed]; await submit();
    assert(!text("Record assessed submission") || text("Record assessed submission").disabled);
  }
  respond = catalogAnd(saved); await route();
  const stale = text("Save review");
  choose(byId("lab-reviewer"), "lead"); choose(byId("lab-decision"), "accepted");
  byId("lab-review-note").value = review.note; byId("lab-review-note").events.input();
  const late = pending(); respond = () => late.promise;
  const posting = stale.events.click();
  location.hash = "#projects"; respond = () => [200, []]; await route();
  late.resolve([200, reviewed]); await posting;
  assert(text("Start your first project")); assert(!text(review.note));
  const count = writeCount(); await stale.events.click(); assert.equal(writeCount(), count);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
