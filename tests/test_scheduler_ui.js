"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Node {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.attrs = {};
    this.events = {};
    this.textContent = "";
    this.value = "";
    this.classList = {toggle() {}};
  }
  append(...children) {
    for (const child of children) {
      if (this.tag === "select" && !this.children.length) this.value = child.value;
      this.children.push(child);
      child.parentElement = this;
    }
  }
  replaceWith(node) {
    const siblings = this.parentElement.children;
    siblings[siblings.indexOf(this)] = node;
    node.parentElement = this.parentElement;
  }
  remove() { this.parentElement.children = this.parentElement.children.filter(child => child !== this); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  *all() { yield this; for (const child of this.children) yield* child.all(); }
  querySelector(tag) { return [...this.all()].find(node => node.tag === tag); }
  get elements() { return [...this.all()].filter(node => ["fieldset", "input", "select", "textarea", "button"].includes(node.tag)); }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  focus() { this.focused = true; }
  click() { if (this.tag === "a") downloads.push(this.download); }
  addEventListener(type, listener) { this.events[type] = listener; }
}

const root = new Node("main"), notice = new Node("p"), body = new Node("body");
const document = {body, createElement: tag => new Node(tag),
  querySelector: selector => selector === "#notice" ? notice : root, querySelectorAll: () => []};
const requests = [], downloads = [];
let respond = () => { throw Error("Unexpected fetch"); };
async function fetch(url, options) {
  const request = {url, method: options.method, headers: options.headers, data: options.body ? JSON.parse(options.body) : null};
  requests.push(request);
  const [status, data] = await respond(request);
  return {ok: status === 200, status, json: async () => data};
}
const location = {hash: "#team"};
const source = fs.readFileSync(path.join(__dirname, "../command_center/ui/app.js"), "utf8")
  .split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const app = vm.runInNewContext(source + "\n;({renderTaskBoard,state,route});",
  {document, location, fetch, setTimeout: () => 0, clearTimeout() {}, console, Blob, URL});
app.state.page = "team"; app.state.route = 1; app.state.selected = "a";
const currentSha = "a".repeat(64), newSha = "b".repeat(64);
const empty = {project_id: "a", revision: 0, state: "empty", spec_sha256: currentSha, board_spec_sha256: null,
  summary: {total:0, ready:0, waiting:0, completed:0, running:0, blocked:0}, tasks: [], ready_task_ids: [], assignments: []};
const base = {id:"x", title:"X task", role:"ui", priority:5, depends_on:[], gate:"build",
  status:"pending", evidence:[], reason:null, job_id:null, attempts:0};
const ready = {...empty, revision:1, state:"current", board_spec_sha256:currentSha, tasks:[base], ready_task_ids:["x"],
  summary:{...empty.summary, total:1, ready:1}, assignments:[{task_id:"x", role:"ui", model_id:"model", reasoning_effort:"ultra"}]};
const running = {...ready, revision:2, tasks:[{...base, status:"running", attempts:1}], ready_task_ids:[], assignments:[],
  summary:{...empty.summary, total:1, running:1}};
const mount = board => root.replaceChildren(app.renderTaskBoard(board, app.state.route));
const matching = (node, fn) => [...node.all()].filter(fn);
const findText = (text, node = root) => matching(node, item => item.textContent === text)[0];
const form = (caption, node = root) => matching(node, n => n.tag === "form" &&
  matching(n, child => child.type === "submit" && child.textContent === caption).length)[0];
const field = (target, name) => target.elements.find(n => n.name === name);
const submit = target => target.events.submit({preventDefault() {}});
const click = caption => findText(caption).events.click();
const last = () => requests.at(-1);
const taskRow = title => matching(root, n => n.tag === "article" && findText(title, n))[0];

async function run() {
  mount(empty);
  const add = form("Add task");
  field(add, "id").value = "x"; field(add, "title").value = "X task"; field(add, "role").value = "ui";
  field(add, "priority").value = "5"; field(add, "gate").value = "build";
  respond = () => [200, ready];
  await submit(add);
  assert.equal(last().headers["X-Studio-Request"], "1");
  assert.equal(last().url, "/api/projects/a/tasks");
  assert.deepEqual(last().data, {expected_revision:0, spec_sha256:currentSha, action:{op:"add",
    task:{id:"x", title:"X task", role:"ui", priority:5, depends_on:[], gate:"build"}}});
  assert(findText("X task (x) · Madame Glitch · UI · model · ultra effort"));
  respond = () => [200, {scheduled_dispatch_plan:{project:{id:"a", spec_sha256:currentSha}, board_state:"current", board_revision:1}}];
  await click("Download ready dispatch JSON");
  assert.equal(last().url, "/api/team/a"); assert.deepEqual(downloads, ["a-tasks-r1.json"]);
  respond = () => [200, {scheduled_dispatch_plan:{project:{id:"a", spec_sha256:newSha}, board_state:"current", board_revision:2}}];
  await click("Download ready dispatch JSON"); assert.equal(downloads.length, 1);
  assert(findText("The dispatch plan and the displayed board differ. Refresh the board before exporting."));

  respond = () => [200, running];
  await submit(form("Start task"));
  assert.deepEqual(last().data.action, {op:"start",task_id:"x"});
  assert(!form("Start task")); assert(!form("Change role"));
  let complete = form("Complete task");
  field(complete,"evidence").value = "Output inspected\nTwelve checks passed";
  field(complete,"job_id").value = "b".repeat(32);
  field(form("Add task"), "title").value = "Separate draft";
  respond = () => [409, {error:"Revision conflict."}];
  await submit(complete);
  assert.deepEqual(last().data.action, {op:"complete", task_id:"x",
    evidence:["Output inspected","Twelve checks passed"], job_id:"b".repeat(32)});
  assert(findText("Revision conflict. Your entries are still here. Refresh the board to review its latest revision."));
  assert.equal(field(complete, "evidence").value, "Output inspected\nTwelve checks passed");
  respond = () => [200, {...running, revision:3}];
  await click("Refresh board"); assert.equal(last().method, "GET");
  complete = form("Complete task");
  assert.equal(field(complete,"job_id").value, "b".repeat(32));
  assert.equal(field(form("Add task"),"title").value, "Separate draft");
  const done = {...running, revision:4, tasks:[{...running.tasks[0],status:"completed",
    evidence:["Twelve checks passed"],job_id:"b".repeat(32)}], summary:{...empty.summary,total:1,completed:1}};
  respond = () => [200, done];
  await submit(complete); assert.equal(last().data.expected_revision,3);
  assert(findText("Twelve checks passed")); assert(!form("Complete task")); assert(!form("Change role"));
  assert.equal(field(form("Add task"),"title").value, "Separate draft");

  const blocked = {...running, tasks:[{...running.tasks[0], status:"blocked", reason:"Missing fixture"}]};
  mount(running); field(form("Block task"), "reason").value = "Missing fixture";
  respond = () => [200, blocked]; await submit(form("Block task"));
  assert.deepEqual(last().data.action,{op:"block",task_id:"x",reason:"Missing fixture"}); assert(findText("Missing fixture"));
  field(form("Change role"),"role").value = "verification"; respond = () => [200,blocked];
  await submit(form("Change role")); assert.deepEqual(last().data.action,{op:"reassign",task_id:"x",role:"verification"});
  respond = () => [200, ready]; await submit(form("Return to pending"));
  assert.deepEqual(last().data.action,{op:"requeue", task_id:"x"});

  const sibling = {...base,id:"y",title:"Y task"}, waiter = {...base,id:"z",title:"Z task",depends_on:["y"]};
  mount({...running,tasks:[...running.tasks,sibling,waiter],ready_task_ids:["y"]});
  assert(findText("Madame Glitch · UI is already working on another task.",taskRow("Y task"))); assert(!form("Start task",taskRow("Y task")));
  assert(findText("Waiting",taskRow("Z task"))); assert(findText("Depends on y")); assert(!form("Start task",taskRow("Z task")));

  mount({...done, state:"stale", spec_sha256:newSha});
  assert(findText("Twelve checks passed")); assert(!form("Add task")); assert(!form("Change role")); assert(!form("Start task"));
  const reset = form("Replace task board"); const count = requests.length;
  await submit(reset); assert.equal(count, requests.length);
  field(reset,"confirm_reset").checked = true;
  respond = () => [200, {...empty, spec_sha256:newSha, revision:5}];
  await submit(reset); assert.deepEqual(last().data, {action:{op:"reset"},expected_revision:4,spec_sha256:newSha});

  mount(ready); let release;
  respond = () => new Promise(resolve => { release = () => resolve([200, running]); });
  const beforeStart = requests.length;
  const pending = submit(form("Start task"));
  await submit(form("Start task")); const prior = notice.textContent;
  assert.equal(requests.length, beforeStart + 1);
  app.state.selected = "b"; app.state.route++; release(); await pending;
  assert.equal(notice.textContent, prior); assert(!findText("Revision 2"));
  const after = requests.length; await submit(form("Start task")); assert.equal(requests.length, after);
  for (const input of matching(root,n => ["select","input","textarea"].includes(n.tag))) {
    assert.equal(input.parentElement.tag,"label"); assert(input.parentElement.textContent);
  }

  app.state.selected = "a";
  const checkpoint = {project_id:"a",spec_sha256:currentSha,state:"empty",revision:0,
    checkpoint:null,target_seconds:18000,remaining_seconds:18000};
  respond = ({url}) => {
    if (url === "/api/projects") return [200,[{id:"a",name:"Alpha"}]];
    if (url === "/api/team/a") return [200,{roles:[],gates:[]}];
    if (url === "/api/projects/a/checkpoint") return [200,checkpoint];
    if (url === "/api/projects/a/tasks") return [503,{error:"Store unavailable."}];
    throw Error(url);
  };
  await app.route(); assert(findText("Task board unavailable")); assert(findText("Work checkpoint"));
  console.log("PASS task board actions, evidence, draft recovery, dispatch export, role capacity, stale reset, navigation races and checkpoint isolation");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
