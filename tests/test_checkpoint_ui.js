const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
class Node {
  constructor(tag) {
    this.tag = tag; this.children = []; this.events = {}; this.attrs = {}; this.textContent = "";
    this.classList = {toggle() {}}; this.value = "";
  }
  append(...children) { for (const n of children) { this.children.push(n); n.parentElement = this; } }
  replaceWith(node) {
    this.parentElement.children[this.parentElement.children.indexOf(this)] = node;
    node.parentElement = this.parentElement;
  }
  *all() { yield this; for (const child of this.children) yield* child.all(); }
  querySelector(tag) { return [...this.all()].find(n => n.tag === tag); }
  setAttribute(key, value) { this.attrs[key] = value; }
  focus() { this.focused = true; }
  addEventListener(event, callback) { this.events[event] = callback; }
  get valueAsNumber() { return Number(this.value); }
}
const root = new Node("main"), notice = new Node("p");
const document = {createElement: tag => new Node(tag), querySelector: selector => selector === "#notice" ? notice : root};
let responder = async () => { throw Error("Unexpected request"); };
const requests = [];
async function fetch(path, options) {
  requests.push({path, ...options, data:JSON.parse(options.body)});
  const [code, data] = await responder(requests.at(-1).data);
  return {ok: code < 300, json:async () => data};
}
const script = fs.readFileSync(path.join(__dirname, "../command_center/ui/app.js"),"utf8")
  .split('const form = document.querySelector("#create-project");\nconst kindSelect')[0];
const context = vm.createContext({document,fetch,setTimeout:()=>0,clearTimeout:()=>{},console});
const {renderCheckpoint,state} = vm.runInContext(script + "\n;({renderCheckpoint,state});", context);
state.route = 1; state.selected = "a"; state.page = "team";
const empty = {project_id:"a",spec_sha256:"a".repeat(64),state:"empty",revision:0,checkpoint:null,target_seconds:18000,remaining_seconds:18000};
const mount = snapshot => { root.children=[]; root.append(renderCheckpoint(snapshot,1)); };
const forms = () => [...root.all()].filter(n=>n.tag==="form");
const named=(form,key) => [...form.all()].find(n=>n.name===key);
const textExists=(text) => [...root.all()].some(n=>n.textContent===text);
async function submit(form) {
  // Mirror native HTML required validation for a user-triggered submission.
  if ([...form.all()].some(n=>n.required && (n.type==="checkbox" ? !n.checked : String(n.value).trim()===""))) return;
  await form.events.submit({preventDefault(){}});
}
async function run() {
  mount(empty);
  assert(textExists("No checkpoint saved")); assert(textExists("5h 0m 0s"));
  let form=forms()[0]; await submit(form); assert.equal(requests.length,0);
  named(form,"elapsed_seconds").value=1830;
  named(form,"completed_work").value="First task\nSecond task";
  named(form,"verification_evidence").value="Four tests passed";
  named(form,"next_action").value="Run the build";
  named(form,"status").value="paused";
  const envelope=(data,rev,spec)=>({
    ...empty,revision:rev,state:"current",spec_sha256:spec,remaining_seconds:18000-data.elapsed_seconds,
    checkpoint:{...data,project_id:"a",revision:rev, spec_sha256:spec,updated_at:"2026-11-20T12:00:00+00:00"}
  });
  let saved;
  responder=async data=>[200,saved=envelope(data,1,empty.spec_sha256)];
  await submit(form);
  assert.deepEqual(requests.at(-1).data.completed_work,["First task","Second task"]);
  assert.equal(requests.at(-1).data.expected_revision,0);
  assert.equal(requests.at(-1).headers["X-Studio-Request"],"1");
  for (const t of ["Revision 1","4h 29m 30s","0h 30m 30s","Four tests passed","Run the build","Paused"]) assert(textExists(t),t);
  form=forms()[0]; named(form,"next_action").value="Keep this draft";
  responder=async ()=>[409,{error:"Revision conflict."}];
  await submit(form); assert.equal(named(form,"next_action").value,"Keep this draft");
  assert(textExists("Revision conflict. Your edits are still in the form."));
  assert.equal([...form.all()].find(n=>n.textContent.startsWith("Discard edits")).hidden,false);
  const currentSha="b".repeat(64);
  const stale={...saved,state:"stale",remaining_seconds:null,spec_sha256:currentSha};
  mount(stale); form=forms()[0];
  assert(textExists("Unavailable until a new checkpoint is saved"));
  assert.equal(named(form,"next_action").value,"");
  assert.equal(named(form,"elapsed_seconds").value,0);
  assert(named(form,"elapsed_seconds").readOnly);
  named(form,"next_action").value="Rebuild changed spec";
  let previous=requests.length; await submit(form); assert.equal(requests.length,previous);
  named(form,"reset_for_spec_change").checked=true;
  responder=async data=>[200,saved=envelope(data,2,currentSha)];
  await submit(form);
  assert.equal(requests.at(-1).data.reset_for_spec_change,true);
  assert.equal(requests.at(-1).data.spec_sha256,currentSha);
  assert.equal(requests.at(-1).data.elapsed_seconds,0);
  assert.deepEqual(requests.at(-1).data.verification_evidence,[]);
  form=forms()[0]; named(form,"status").value="completed"; named(form,"status").events.change();
  assert.equal(named(form,"next_action").required,false);
  named(form,"next_action").value=""; named(form,"elapsed_seconds").value=18000;
  responder=async data=>[200,saved=envelope(data,3,currentSha)];
  await submit(form);
  assert(textExists("Completed")); assert.equal(forms().length,2);
  const [edit,restart]=forms();
  assert.equal(named(edit,"elapsed_seconds").value,18000);
  assert.equal(named(restart,"elapsed_seconds").value,0); assert(named(restart,"elapsed_seconds").readOnly);
  assert.equal(named(restart,"status").value,"in_progress");
  assert(textExists("Start a new sprint"));
  named(restart,"next_action").value="Start sprint two";
  previous=requests.length; await submit(restart); assert.equal(requests.length,previous);
  named(restart,"start_new_run").checked=true;
  responder=async data=>[200,saved=envelope(data,4,currentSha)];
  await submit(restart); assert.equal(requests.at(-1).data.start_new_run,true);
  assert.equal(requests.at(-1).data.expected_revision,3); assert.equal(requests.at(-1).data.reset_for_spec_change,undefined);
  assert.equal(forms().length,1);
  form=forms()[0]; let release;
  responder= data=> new Promise(resolve=>{release=()=>resolve([200,envelope(data,5,currentSha)]);});
  const pending=submit(form);
  state.route=2; state.selected="b";
  release(); await pending; assert(!textExists("Revision 5")); assert.equal(notice.textContent,"Checkpoint saved at revision 4.");
  for (const n of root.all()) if (["input","select","textarea"].includes(n.tag)) {
    assert.equal(n.parentElement.tag,"label"); assert(n.parentElement.textContent.length);
  }
  console.log("PASS empty/current/stale renders, bounded active time fields, accessible labels, PUT payload and header, preserved conflict edits, explicit stale/new-sprint confirmations, regular completed edit, delayed response across project switch.");
}
run().catch(e=>{console.error(e);process.exitCode=1;});
