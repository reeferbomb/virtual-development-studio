"use strict";

const titles = {
  projects: "Projects", workspace: "Workspace", catalog: "Asset catalog",
  builds: "Build queue", releases: "Releases", supervisor: "Supervisor", sprint: "Sprint",
  planning: "Planning", operations: "Operations", coordination: "Coordination", quality: "Quality", training: "Training", lab: "Lab", team: "Team", portfolio: "Portfolio"
};
const kinds = {
  assets: "Asset factory", world: "World", gameplay: "Gameplay",
  multiplayer: "Multiplayer", cinematic: "Cinematic", simulation: "World simulation",
  openworld: "Open world", unified: "Unified expedition", living: "Living World", city: "City",
  vertical: "Vertical City", advanced: "Advanced City", frontline: "Frontline City"
};
const filterLabels = {
  assets: "Assets", packages: "Packages", animations: "Animations", audio: "Audio"
};
const state = {
  projects: [], drafts: new Map(), selected: null, project: null,
  page: "", filter: "assets", job: null, log: null, route: 0, refresh: 0, polling: null,
  queue: null, jobs: [], queueError: "", historyError: "", jobActions: new Set()
};
const view = document.querySelector("#view");
const dialog = document.querySelector("#new-project");

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value != null) node.textContent = value;
  return node;
}

function button(label, handler, className) {
  const node = element("button", className, label);
  node.type = "button";
  node.addEventListener("click", handler);
  return node;
}

function badge(label, className = "") {
  return element("span", `badge ${className}`, label);
}

function box(title, description, action, className = "empty") {
  const node = element("div", className);
  node.append(element("h2", null, title), element("p", "dim", description));
  if (action) node.append(action);
  return node;
}

function heading(title, description, ...actions) {
  const wrap = element("div", "page-heading");
  const summary = element("div");
  const h = element("h1", null, title);
  h.id = "page-title";
  summary.append(h, element("p", null, description));
  wrap.append(summary);
  if (actions.length) {
    const group = element("div", "actions");
    group.append(...actions);
    wrap.append(group);
  }
  return wrap;
}

let noticeTimer;
function notify(message, error = false) {
  const notice = document.querySelector("#notice");
  notice.textContent = message;
  notice.classList.toggle("error", error);
  notice.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { notice.hidden = true; }, 5000);
}

async function api(path, method = "GET", data, keepJsonText = false) {
  const body = method === "GET" ? undefined : JSON.stringify(data);
  return apiWithJsonBody(path, method, body, keepJsonText);
}

async function apiWithJsonBody(path, method, body, keepJsonText) {
  const options = { method, cache: "no-store" };
  if (method !== "GET") {
    options.headers = { "Content-Type": "application/json", "X-Studio-Request": "1" };
    options.body = body;
  }
  const response = await fetch(`/api${path}`, options);
  const raw = keepJsonText ? await response.text() : null;
  const result = keepJsonText ? JSON.parse(raw) : await response.json();
  if (!response.ok) {
    const error = new Error(result.error || result.message || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return keepJsonText ? {data: result, raw} : result;
}

function projectPath(id, tail = "") {
  return `/projects/${encodeURIComponent(id)}${tail}`;
}

function fileUrl(path) {
  return `/api/file?path=${encodeURIComponent(path)}`;
}

function navigate(page) {
  if (location.hash === `#${page}`) void route();
  else location.hash = page;
}

function openProject(id) {
  state.selected = id;
  navigate("workspace");
}

function openCreate() {
  const form = document.querySelector("#create-project");
  form.reset();
  document.querySelector("#create-error").hidden = true;
  dialog.showModal();
}

function projectPicker(onChange) {
  const wrap = element("div", "workspace-tools");
  const select = element("select");
  select.id = "active-project";
  const label = element("label", null, "Active project");
  label.htmlFor = select.id;
  for (const project of state.projects) {
    const option = element("option", null, project.name);
    option.value = project.id;
    select.append(option);
  }
  select.value = state.selected;
  select.addEventListener("change", () => {
    state.selected = select.value;
    onChange();
  });
  wrap.append(label, select);
  return wrap;
}

function renderProjects() {
  view.append(heading("Projects", "Create a project or pick up where you left off.",
    button("+ New project", openCreate, "primary")));
  if (!state.projects.length) {
    view.append(box("Start your first project", "Choose a studio template to open its workspace.",
      button("Create project", openCreate)));
    return;
  }
  const group = element("div", "cards");
  for (const project of state.projects) {
    const card = element("article", "card");
    const actions = element("div", "actions");
    actions.append(button("Open workspace", () => openProject(project.id)));
    card.append(element("h2", null, project.name), badge(kinds[project.kind] || project.kind), actions);
    group.append(card);
  }
  view.append(group);
}

function renderWorkspace(project) {
  const id = project.id;
  const routeId = state.route;
  const active = () => state.page === "workspace" && state.route === routeId && state.selected === id;
  const editSpec = state.drafts.get(id) ?? project.spec;
  let saving = false;
  const status = element("p", "dim", state.drafts.has(id) ? "Unsaved changes" : "Saved specification");
  status.setAttribute("role", "status");
  const save = button("Save changes", async () => {
    const changes = state.drafts.get(id);
    saving = true;
    sync();
    try {
      const updated = await api(projectPath(id, "/spec"), "PUT", { spec: changes });
      if (state.drafts.get(id) === changes) state.drafts.delete(id);
      project.spec = updated.spec ?? changes;
      notify("Specification saved.");
    } catch (error) {
      notify(error.message, true);
    } finally {
      saving = false;
      sync();
    }
  });
  const priorityField = element("div");
  const priority = taskField(priorityField, "build_priority", "Build priority", {value: "3"},
    {"1": "1 · Lowest", "2": "2", "3": "3 · Normal", "4": "4", "5": "5 · Highest"});
  const build = button("Queue build", async () => {
    if (!active() || saving || state.drafts.has(id)) return;
    saving = true;
    sync();
    try {
      const job = await api(projectPath(id, "/build"), "POST", {priority: Number(priority.value)});
      if (!active()) return;
      state.job = job.id;
      state.log = null;
      notify("Build queued.");
      navigate("builds");
    } catch (error) {
      if (!active()) return;
      notify(error.message, true);
      saving = false;
      sync();
    }
  }, "primary");
  const sync = () => {
    const dirty = state.drafts.has(id);
    save.disabled = saving || !dirty;
    build.disabled = saving || dirty;
    priority.disabled = saving;
    status.textContent = dirty ? "Unsaved changes · Save before building" : "Saved specification";
  };
  const change = (spec) => {
    state.drafts.set(id, structuredClone(spec));
    sync();
  };
  view.append(heading(project.name, `${kinds[project.kind] || project.kind} workspace`, save, priorityField, build),
    projectPicker(route), status);
  if (project.kind === "world") {
    const generator = element("section", "panel generator");
    generator.append(element("h2", null, "Procedural arena"), element("p", "dim", "Create a reproducible 48 × 48 m arena draft with a clearance-tested objective route. Save the draft before building; the build runs physical traversal QA."));
    const form = element("form", "generator-form");
    const numeric = (label, value, min, max) => {
      const field = element("label", null, label);
      const input = element("input");
      input.type = "number"; input.required = true; input.value = value;
      input.min = min; input.max = max; input.step = 1;
      field.append(input); form.append(field); return input;
    };
    const seed = numeric("Seed", 237, 0, 2147483647);
    const count = numeric("Cover count", 24, 1, 40);
    const generate = element("button", "primary", "Generate draft");
    generate.type = "submit"; form.append(generate);
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (state.drafts.has(id) && !window.confirm("Replace the current unsaved draft?")) return;
      generate.disabled = true;
      try {
        const result = await api(projectPath(id, "/generate"), "POST", {seed: Number(seed.value), count: Number(count.value)});
        state.drafts.set(id, result.spec);
        if (state.page === "workspace" && state.selected === id) await route();
        notify(`Arena draft ready · ${result.route_m.toFixed(1)} m planned route. Save before building.`);
      } catch (error) { notify(error.message, true); }
      finally { generate.disabled = false; }
    });
    generator.append(form); view.append(generator);
  }
  const header = element("div", "section-top");
  header.append(element("h2", null, "Specification"));
  const editor = element("div", "panel");
  editor.id = "editor-host";
  view.append(header, editor);
  if (window.StudioEditor?.mount) {
    window.StudioEditor.mount(editor, project.kind, structuredClone(editSpec), change);
  } else {
    editor.append(element("p", "error", "The project editor could not load."));
  }
  sync();
}

function renderCatalog(catalog) {
  view.replaceChildren(heading("Asset catalog", "Browse reusable assets, verified packages, animations, and audio."));
  const filters = element("div", "filterbar");
  for (const [id, label] of Object.entries(filterLabels)) {
    const filter = button(label, () => {
      state.filter = id;
      renderCatalog(catalog);
      view.querySelector('[aria-pressed="true"]').focus();
    });
    filter.setAttribute("aria-pressed", String(id === state.filter));
    filters.append(filter);
  }
  view.append(filters);
  const entries = catalog[state.filter] || [];
  if (!entries.length) {
    view.append(box(`No ${state.filter} available`, "Entries appear here as they become available on this workstation."));
    return;
  }
  const cards = element("div", "cards");
  for (const item of entries) {
    const card = element("article", "card asset");
    const body = element("div", "card-body");
    body.append(element("h2", null, item.label || item.id));
    if (item.preview) {
      const image = element("img");
      image.src = fileUrl(item.preview);
      image.alt = item.label ? `${item.label} preview` : "Asset preview";
      image.loading = "lazy";
      const link = element("a", "preview-link");
      link.href = image.src;
      link.append(image);
      image.addEventListener("error", () => link.replaceWith(element("div", "asset-visual", "◇")));
      card.append(link);
    } else {
      const visual = element("div", "asset-visual", state.filter === "audio" ? "♪" : "◇");
      visual.setAttribute("aria-hidden", "true");
      card.append(visual);
    }
    if (item.kind) body.append(badge(item.kind));
    if (item.verified != null) body.append(badge(item.verified ? "Verified" : "Pending verification", item.verified ? "good" : ""));
    if (item.files?.length) {
      body.append(element("p", "dim", item.files.map(file => file.name).join(" · ")));
    }
    if (item.path && state.filter === "audio") {
      const audio = element("audio");
      audio.controls = true;
      audio.preload = "none";
      audio.src = fileUrl(item.path);
      audio.setAttribute("aria-label", item.label || "Audio preview");
      body.append(element("p", "dim", typeof item.seconds === "number" ? `${item.seconds} seconds` : "Audio preview"), audio);
    } else if (item.path) {
      body.append(element("p", "dim", item.path));
    }
    card.append(body);
    cards.append(card);
  }
  view.append(cards);
}

function jobBadge(job) {
  const tones = { passed: "good", failed: "bad", running: "progress", queued: "progress" };
  const label = job.verified ? `${job.status} · verified` : job.status;
  return badge(label, tones[job.status]);
}

const scenarioChecks = {
  gameplay: {
    title: "Tactical fixture QA", reportKey: "tactical_qa", marker: "STUDIO_TACTICAL_QA_JSON ", flag: "--tactical-qa",
    moduleCheck: ["Gameplay checks", "Gameplay module tests passed. The full tactical test runs with the dedicated training yard fixture."]
  },
  simulation: {
    title: "Simulation fixture QA", reportKey: "simulation_qa", marker: "STUDIO_SIMULATION_QA_JSON ", flag: "--simulation-qa",
    moduleCheck: ["Simulation checks", "Simulation module tests passed. The full expedition test runs with the default fixture."]
  },
  openworld: {
    title: "Open-world scenario QA", reportKey: "openworld_qa", marker: "STUDIO_OPENWORLD_QA_JSON "
  },
  unified: {
    title: "Unified scenario QA", reportKey: "unified_qa", marker: "STUDIO_UNIFIED_QA_JSON ", flag: "--unified-qa",
    moduleCheck: ["Unified component checks", "Launch and component checks passed. The shipped fixture also runs the full expedition scenario."]
  },
  living: {
    title: "Living World scenario QA", reportKey: "living_qa", marker: "STUDIO_LIVING_QA_JSON ", flag: "--living-qa",
    moduleCheck: ["Living World component checks", "Launch and component checks passed. The shipped fixture also runs the full Living World scenario."]
  },
  city: {
    title: "City scenario QA", reportKey: "city_qa", marker: "STUDIO_CITY_QA_JSON ", flag: "--city-qa",
    moduleCheck: ["City component checks", "Launch and component checks passed. The shipped settings also run the Metropolis scenario."]
  },
  vertical: {
    title: "Vertical City scenario QA", reportKey: "vertical_qa", marker: "STUDIO_VERTICAL_QA_JSON ", flag: "--vertical-qa",
    moduleCheck: ["Vertical City component checks", "Launch and component checks passed. The shipped settings also run the Vertical City scenario."]
  },
  advanced: {
    title: "Advanced City scenario QA", reportKey: "advanced_qa", marker: "STUDIO_ADVANCED_QA_JSON ", flag: "--advanced-qa",
    moduleCheck: ["Advanced City component checks", "Launch and component checks passed. The shipped settings also run the Advanced City scenario."]
  },
  frontline: {
    title: "Frontline City scenario QA", reportKey: "frontline_qa", marker: "STUDIO_FRONTLINE_QA_JSON ", flag: "--frontline-qa",
    moduleCheck: ["Frontline City component checks", "Launch and component checks passed. The shipped settings also run the Frontline City scenario."]
  }
};

function scenarioReport(recorded, log, marker) {
  if (typeof recorded?.pass === "boolean") return recorded;
  const line = log?.split("\n").findLast(entry => entry.startsWith(marker));
  if (!line) return null;
  try {
    const report = JSON.parse(line.slice(marker.length));
    return typeof report?.pass === "boolean" ? report : null;
  } catch {
    return null;
  }
}

function updateBuildChecks(panel, job, log) {
  const scenario = job && Object.hasOwn(scenarioChecks, job.kind) ? scenarioChecks[job.kind] : null;
  const recorded = scenario && job[scenario.reportKey];
  const report = scenario ? scenarioReport(recorded, log, scenario.marker) : null;
  const reportFromLog = report !== null && report !== recorded;
  const fixtureRequested = scenario?.flag && job.commands?.some(command => command.argv?.includes(scenario.flag));
  const moduleCheck = scenario?.moduleCheck && job.status === "passed" && job.verified === true &&
    !fixtureRequested ? scenario.moduleCheck : null;
  const key = JSON.stringify([job?.id, scenario?.title, report, reportFromLog, moduleCheck]);
  if (panel.dataset.result === key) return;
  panel.dataset.result = key;
  panel.replaceChildren();
  panel.hidden = !report && !moduleCheck;
  if (!report) {
    if (moduleCheck) {
      const [title, description] = moduleCheck;
      panel.append(element("h2", null, title), element("p", "dim", description));
    }
    return;
  }

  const summary = element("div", "actions");
  summary.append(element("h2", null, scenario.title),
    badge(report.pass ? "Passed" : "Failed", report.pass ? "good" : "bad"));
  panel.append(summary);
  if (reportFromLog) panel.append(element("p", "dim", "Result reported in the build log."));
  const details = element("details");
  details.append(element("summary", null, "View QA details"));
  if (Array.isArray(report.checks)) {
    const list = element("ul", "build-check-list");
    for (const check of report.checks) {
      if (typeof check?.name !== "string" || !["passed", "failed"].includes(check.status)) continue;
      const row = element("li");
      const result = element("div", "actions");
      const passed = check.status === "passed";
      result.append(element("strong", null, check.name.replaceAll("_", " ")),
        badge(passed ? "Passed" : "Failed", passed ? "good" : "bad"));
      row.append(result);
      if (typeof check.detail === "string") row.append(element("p", "dim", check.detail));
      list.append(row);
    }
    if (list.childElementCount) details.append(list);
  }
  const measurements = element("dl", "build-measurements");
  for (const [name, value] of Object.entries(report.metrics ?? {})) {
    if (!Number.isFinite(value)) continue;
    measurements.append(element("dt", "dim", name.replaceAll("_", " ")), element("dd", null, value));
  }
  if (measurements.childElementCount) details.append(measurements);
  if (details.childElementCount > 1) panel.append(details);
}

function renderBuilds() {
  const queue = element("div", "queue");
  queue.id = "queue";
  queue.append(element("p", "dim", "Loading queue…"));
  const checks = element("section", "panel build-checks");
  checks.id = "build-checks";
  checks.hidden = true;
  const logs = element("section");
  logs.id = "logs";
  view.append(heading("Build queue", "One build runs at a time. Higher priorities run first, with equal priorities in submission order.",
    button("Refresh builds", () => refreshJobs(true))), queue, checks, logs);
}

async function runJobAction(job, op, routeId) {
  const active = () => state.page === "builds" && state.route === routeId;
  if (!active() || state.jobActions.has(job.id)) return;
  state.jobActions.add(job.id);
  updateBuilds();
  try {
    const result = await api(`/jobs/${encodeURIComponent(job.id)}/${op}`, "POST", {});
    if (!active()) return;
    if (op === "retry") {
      state.job = result.id;
      state.log = null;
    }
    notify(op === "cancel" ? "Queued build canceled." : "Retry queued.");
  } catch (error) {
    if (active()) notify(error.message, true);
  } finally {
    if (active()) await refreshJobs(true);
    state.jobActions.delete(job.id);
    if (state.page === "builds") updateBuilds();
  }
}

function updateBuilds() {
  const queue = document.querySelector("#queue");
  const checks = document.querySelector("#build-checks");
  const logs = document.querySelector("#logs");
  if (!queue || !checks || !logs) return;
  const routeId = state.route;
  const running = state.queue?.running;
  const waiting = state.queue?.queued || [];
  const liveIds = new Set([running?.id, ...waiting.map(job => job.id)]);
  const history = state.jobs.filter(job => !liveIds.has(job.id) && !["running", "queued"].includes(job.status));
  const previousFocus = document.activeElement?.dataset?.buildControl;
  const key = JSON.stringify([state.queue, history, state.queueError, state.historyError, state.job, [...state.jobActions]]);
  if (queue.dataset.result !== key) {
    queue.dataset.result = key;
    queue.replaceChildren();
    function row(job, position) {
      const node = element("article", "panel queue-row");
      const summary = element("div");
      const project = state.projects.find(item => item.id === job.project_id);
      summary.append(element("h3", null, project?.name || job.project_name || job.project_id || "Unknown project"),
        element("p", "dim", job.id), element("p", "dim", `${position ? `Position ${position} · ` : ""}Priority ${job.priority ?? 3}`));
      if (job.retry_of) summary.append(element("p", "dim", `Retry of ${job.retry_of}`));
      if (job.error) summary.append(element("p", "dim", job.error));
      const controls = element("div", "actions");
      function addControl(label, suffix, callback) {
        const control = button(label, callback);
        control.dataset.buildControl = `${job.id}/${suffix}`;
        controls.append(control);
        return control;
      }
      const logButton = addControl(state.job === job.id ? "Viewing log" : "View log", "log", () => {
        if (routeId !== state.route) return;
        state.job = job.id;
        state.log = null;
        updateBuilds();
        return refreshJobs(true);
      });
      logButton.setAttribute("aria-pressed", String(state.job === job.id));
      if (job.status === "queued" || (job.project_id && ["failed", "canceled"].includes(job.status))) {
        const cancel = job.status === "queued";
        const op = cancel ? "cancel" : "retry";
        const control = addControl(cancel ? "Cancel build" : "Retry build", op, () => runJobAction(job, op, routeId));
        control.disabled = state.jobActions.has(job.id);
      }
      node.append(summary, jobBadge(job), controls);
      queue.append(node);
    }
    queue.append(element("h2", null, "Running"));
    if (state.queueError) {
      queue.append(box("Build queue unavailable", state.queueError));
    } else {
      if (running) row(running);
      else queue.append(element("p", "dim", "The build worker is idle."));
      queue.append(element("h2", null, `Queued (${waiting.length})`));
      if (!waiting.length) queue.append(element("p", "dim", "No builds are waiting."));
      waiting.forEach((job, index) => row(job, index + 1));
    }
    queue.append(element("h2", null, "Build history"));
    if (state.queue?.counts) {
      const counts = state.queue.counts;
      queue.append(element("p", "dim",
        `${counts.passed ?? 0} passed · ${counts.failed ?? 0} failed · ${counts.canceled ?? 0} canceled`));
    }
    if (state.historyError) queue.append(box("Build history unavailable", state.historyError));
    else if (!history.length) queue.append(element("p", "dim", "No finished builds."));
    else history.forEach(job => row(job));
    if (previousFocus) {
      for (const control of queue.querySelectorAll("button")) {
        if (control.dataset.buildControl === previousFocus) control.focus();
      }
    }
  }
  if (!state.job) return;
  const selected = [running, ...waiting, ...state.jobs].find(job => job?.id === state.job);
  updateBuildChecks(checks, selected, state.log);
  if (!logs.firstElementChild) {
    const header = element("div", "section-top");
    header.append(element("h2", null, "Build log"));
    const log = element("pre", "log");
    log.tabIndex = 0;
    log.setAttribute("aria-label", "Build log output");
    logs.append(header, log);
  }
  const text = state.log === null ? "Loading log…" : state.log || "The build has not written any output yet.";
  if (logs.lastElementChild.textContent !== text) logs.lastElementChild.textContent = text;
}

async function refreshJobs(force = false) {
  const routeId = state.route;
  if (state.page !== "builds" || (!force && state.polling === routeId)) return;
  const seq = ++state.refresh;
  state.polling = routeId;
  const job = state.job;
  try {
    const [queue, history, log] = await Promise.allSettled([
      api("/queue"), api("/jobs"), job ? api(`/jobs/${encodeURIComponent(job)}/log`) : null
    ]);
    if (state.route !== routeId || seq !== state.refresh) return;
    state.queue = queue.status === "fulfilled" ? queue.value : null;
    state.queueError = queue.status === "rejected" ? queue.reason.message : "";
    state.jobs = history.status === "fulfilled" ? history.value : [];
    state.historyError = history.status === "rejected" ? history.reason.message : "";
    if (job && state.job === job) {
      state.log = log.status === "fulfilled" ? log.value.log ?? "" : `Log unavailable · ${log.reason.message}`;
    }
    updateBuilds();
  } finally {
    if (seq === state.refresh) state.polling = null;
  }
}

function downloadJson(json, filename) {
  const url = URL.createObjectURL(new Blob([json], {type: "application/json"}));
  const link = element("a");
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function renderDispatchPlan(dispatch) {
  const { profile, project } = dispatch;
  const counts = new Map();
  for (const role of profile.roles) counts.set(role.model, (counts.get(role.model) ?? 0) + 1);
  const models = [...counts].map(([model, count]) => `${count} × ${model}`).join(" · ");
  const json = `${JSON.stringify(dispatch, null, 2)}\n`;
  const section = element("section", "panel team-brief");
  const details = element("details");
  const preview = element("pre", "log", json);
  preview.tabIndex = 0;
  details.append(element("summary", null, "View dispatch JSON"), preview);

  const actions = element("div", "actions");
  actions.append(button("Copy dispatch plan", async () => {
    try {
      await navigator.clipboard.writeText(json);
      notify("Dispatch plan copied.");
    } catch {
      details.open = true;
      preview.focus();
      notify("Clipboard access failed. Copy the JSON from the preview or download it.", true);
    }
  }), button("Download JSON", () => {
    downloadJson(json, `${project.id}-dispatch.json`);
  }));
  section.append(element("h2", null, profile.team_name || "Fast team profile"), element("p", null, models),
    element("p", "dim", `${profile.max_parallel} parallel slots · ${profile.service_tier} service requested`),
    element("p", null, `${profile.continuity.target_duration_seconds / 3600}-hour sustained work target · checkpoint every ${profile.continuity.checkpoint_interval_seconds / 60} minutes`),
    element("p", "dim", "Continue within scope without routine pauses; resume from a valid checkpoint on an authorized restart. Host limits and stop requests still apply."),
    element("p", "dim", "Export the plan to a compatible host to start agent sessions. This is a requested policy, not a running timer."), actions, details);
  return section;
}

const checkpointStatuses = {
  in_progress: "In progress", paused: "Paused", completed: "Completed", blocked: "Blocked"
};
const checkpointLists = {
  completed_work: "Completed work", verification_evidence: "Verification evidence", remaining_work: "Remaining work"
};

function activeDuration(seconds) {
  return `${Math.floor(seconds / 3600)}h ${Math.floor(seconds / 60) % 60}m ${seconds % 60}s`;
}

function renderCheckpoint(snapshot, routeId) {
  const record = snapshot.checkpoint;
  const stale = snapshot.state === "stale";
  const panel = element("section", "panel team-brief checkpoint");
  const title = element("h2", null, "Work checkpoint");
  title.tabIndex = -1;
  panel.append(title);
  if (stale) {
    panel.append(element("p", "checkpoint-warning",
      "The saved specification has changed. The checkpoint below belongs to the earlier specification. Starting a new checkpoint replaces its progress and resets active work to zero."));
  }
  const summary = element("div", "actions");
  summary.append(badge(`Revision ${snapshot.revision}`),
    badge(record ? checkpointStatuses[record.status] : "No checkpoint saved"));
  panel.append(summary);
  const facts = element("dl", "checkpoint-facts");
  const fact = (label, value) => facts.append(element("dt", null, label), element("dd", null, value));
  fact(stale ? "Previous elapsed active work" : "Elapsed active work", activeDuration(record?.elapsed_seconds ?? 0));
  fact("Remaining active work", stale ? "Unavailable until a new checkpoint is saved" : activeDuration(snapshot.remaining_seconds));
  fact("Active work target", activeDuration(snapshot.target_seconds));
  if (record) {
    fact("Last saved", new Date(record.updated_at).toLocaleString(undefined, {timeZoneName: "short"}));
    for (const [key, label] of Object.entries(checkpointLists)) {
      const entries = record[key];
      if (!entries.length) {
        fact(label, "None recorded");
        continue;
      }
      const list = element("ul");
      for (const entry of entries) list.append(element("li", null, entry));
      const value = element("dd");
      value.append(list);
      facts.append(element("dt", null, label), value);
    }
    fact("Next action", record.next_action || "None recorded");
  }
  panel.append(facts);
  const identity = element("details");
  identity.append(element("summary", null, "Specification identity"),
    element("p", "dim", `Project ID · ${snapshot.project_id}`),
    element("p", "dim", `Current SHA-256 · ${snapshot.spec_sha256}`));
  if (stale) identity.append(element("p", "dim", `Previous SHA-256 · ${record.spec_sha256}`));
  panel.append(identity);

  const onSaved = updated => {
    const replacement = renderCheckpoint(updated, routeId);
    panel.replaceWith(replacement);
    replacement.querySelector("h2").focus();
    notify(`Checkpoint saved at revision ${updated.revision}.`);
  };
  panel.append(checkpointEditor(snapshot, routeId, onSaved));
  if (!stale && record?.status === "completed") {
    panel.append(checkpointEditor(snapshot, routeId, onSaved, true));
  }
  return panel;
}

function checkpointEditor(snapshot, routeId, onSaved, newRun = false) {
  const record = snapshot.checkpoint;
  const stale = snapshot.state === "stale";
  const editor = element("details");
  editor.open = !record;
  editor.name = "checkpoint-operation";
  let title = record ? "Edit checkpoint" : "Create checkpoint";
  if (stale) title = "Start a checkpoint for the current specification";
  if (newRun) title = "Start a new sprint";
  editor.append(element("summary", null, title));
  if (newRun) editor.append(element("p", "checkpoint-warning",
    "Starting a new sprint replaces the completed checkpoint for this specification. Elapsed active work and progress entries start over."));
  const form = element("form");
  const fields = element("fieldset", "checkpoint-fields");
  fields.append(element("legend", null, "Checkpoint details"));
  const base = stale || newRun ? null : record;
  function field(name, label, tag) {
    const wrapper = element("label", "checkpoint-field", label);
    const input = element(tag);
    input.name = name;
    wrapper.append(input);
    fields.append(wrapper);
    return input;
  }
  const status = field("status", "Status", "select");
  for (const [value, label] of Object.entries(checkpointStatuses)) {
    const option = element("option", null, label);
    option.value = value;
    status.append(option);
  }
  status.value = base?.status ?? "in_progress";
  const elapsed = field("elapsed_seconds", "Total elapsed active work (seconds)", "input");
  elapsed.type = "number";
  elapsed.min = base?.elapsed_seconds ?? 0;
  elapsed.max = snapshot.target_seconds;
  elapsed.step = 1;
  elapsed.required = true;
  elapsed.value = base?.elapsed_seconds ?? 0;
  elapsed.readOnly = stale || newRun;
  const listInputs = {};
  for (const [key, label] of Object.entries(checkpointLists)) {
    const input = field(key, `${label} (one entry per line)`, "textarea");
    input.rows = 3;
    input.value = (base?.[key] ?? []).join("\n");
    listInputs[key] = input;
  }
  const next = field("next_action", "Next action", "textarea");
  next.rows = 2;
  next.value = base?.next_action ?? "";
  const requireAction = () => { next.required = status.value !== "completed"; };
  requireAction();
  status.addEventListener("change", requireAction);
  if (stale || newRun) {
    const consent = newRun
      ? field("start_new_run", "Replace the completed checkpoint and start a new sprint at zero", "input")
      : field("reset_for_spec_change", "Replace the previous checkpoint and reset active work to zero", "input");
    consent.type = "checkbox";
    consent.required = true;
    consent.parentElement.className = "checkpoint-consent";
  }
  const save = element("button", "primary", newRun ? "Start new sprint" : stale ? "Replace checkpoint" : "Save checkpoint");
  save.type = "submit";
  fields.append(save);
  const error = element("p", "error");
  error.setAttribute("role", "alert");
  const reload = button("Discard edits and reload saved checkpoint", route);
  reload.hidden = true;
  form.append(fields, error, reload);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (fields.disabled || state.route !== routeId || state.selected !== snapshot.project_id) return;
    const data = {
      expected_revision: snapshot.revision, spec_sha256: snapshot.spec_sha256,
      elapsed_seconds: elapsed.valueAsNumber, status: status.value, next_action: next.value.trim()
    };
    for (const [key, input] of Object.entries(listInputs)) {
      const previous = base?.[key] ?? [];
      data[key] = input.value === previous.join("\n") ? previous : input.value.split("\n").map(line => line.trim()).filter(Boolean);
    }
    if (stale) data.reset_for_spec_change = true;
    if (newRun) data.start_new_run = true;
    fields.disabled = true;
    reload.hidden = true;
    error.textContent = "";
    try {
      const updated = await api(projectPath(snapshot.project_id, "/checkpoint"), "PUT", data);
      if (state.route !== routeId || state.selected !== snapshot.project_id) return;
      onSaved(updated);
    } catch (failure) {
      if (state.route !== routeId || state.selected !== snapshot.project_id) return;
      error.textContent = `${failure.message} Your edits are still in the form.`;
      reload.hidden = false;
    } finally {
      fields.disabled = false;
    }
  });
  editor.append(form);
  return editor;
}

const taskRoles = {
  architecture: "Count Blueprint · Architecture", gameplay: "Major Mayhem · Gameplay",
  verification: "Doctor Doomcheck · Verification", ui: "Madame Glitch · UI",
  content: "Grimbrush · Content", build_operations: "Baron Buildgrave · Build operations"
};
const taskGates = {manual: "Manual review", build: "Verified build"};

function taskField(fields, name, label, settings = {}, choices) {
  const wrapper = element("label", "checkpoint-field", label);
  const input = element(choices ? "select" : settings.rows ? "textarea" : "input");
  if (choices) {
    for (const [value, caption] of Object.entries(choices)) {
      const option = element("option", null, caption);
      option.value = value;
      input.append(option);
    }
  }
  Object.assign(input, {name}, settings);
  if (input.type === "checkbox") wrapper.className = "checkpoint-consent";
  wrapper.append(input);
  fields.append(wrapper);
  return input;
}

function renderTaskBoard(board, routeId, drafts = new Map()) {
  const panel = element("section", "panel team-brief task-board");
  const title = element("h2", null, "Task board");
  title.tabIndex = -1;
  const header = element("div", "task-heading");
  const tools = element("div", "actions");
  const refresh = button("Refresh board", () => update());
  tools.append(badge(`Revision ${board.revision}`), refresh);
  header.append(title, tools);
  const error = element("p", "error");
  error.setAttribute("role", "alert");
  panel.append(header, error);
  const forms = new Map();
  let busy = false, replaced = false;
  const active = () => !replaced && state.page === "team" && state.route === routeId && state.selected === board.project_id;

  async function update(action, submittedKey) {
    if (!active() || busy) return;
    busy = true;
    error.textContent = "";
    refresh.disabled = true;
    for (const {fields} of forms.values()) fields.disabled = true;
    panel.setAttribute("aria-busy", "true");
    try {
      const path = projectPath(board.project_id, "/tasks");
      const saved = action
        ? await api(path, "PUT", {expected_revision: board.revision, spec_sha256: board.spec_sha256, action})
        : await api(path);
      if (!active()) return;
      if (saved.project_id !== board.project_id) throw new Error("Received a board for a different project.");
      const remaining = new Map();
      if (saved.spec_sha256 === board.spec_sha256 && saved.state !== "stale") {
        for (const [key, {form, details}] of forms) {
          if (key === submittedKey) continue;
          const values = {};
          for (const input of form.elements) {
            if (input.name && input.type !== "checkbox") values[input.name] = input.value;
          }
          remaining.set(key, {open: details?.open, values});
        }
      }
      const replacement = renderTaskBoard(saved, routeId, remaining);
      panel.replaceWith(replacement);
      replaced = true;
      replacement.querySelector("h2").focus();
      notify(`Task board ${action ? "saved" : "refreshed"} at revision ${saved.revision}.`);
    } catch (failure) {
      if (active()) error.textContent = `${failure.message} Your entries are still here. Refresh the board to review its latest revision.`;
    } finally {
      busy = false;
      refresh.disabled = false;
      for (const {fields} of forms.values()) fields.disabled = false;
      panel.removeAttribute("aria-busy");
    }
  }

  function actionForm(container, key, caption, configure, {expandable = false, open = false} = {}) {
    const form = element("form", "task-action");
    let details;
    if (expandable) {
      details = element("details");
      details.open = drafts.get(key)?.open ?? open;
      details.append(element("summary", null, caption), form);
      container.append(details);
    } else {
      container.append(form);
    }
    const fields = element("fieldset", expandable ? "checkpoint-fields" : "task-quick");
    fields.setAttribute("aria-label", caption);
    form.append(fields);
    const makeAction = configure(fields);
    const submit = element("button", expandable ? "primary" : "", caption);
    submit.type = "submit";
    fields.append(submit);
    const restored = drafts.get(key)?.values;
    if (restored) {
      for (const input of form.elements) {
        if (Object.hasOwn(restored, input.name)) input.value = restored[input.name];
      }
    }
    forms.set(key, {form, fields, details});
    form.addEventListener("submit", event => {
      event.preventDefault();
      const action = makeAction();
      if (action) return update(action, key);
    });
  }

  const stale = board.state === "stale";
  if (stale) {
    panel.append(element("p", "checkpoint-warning", "The specification changed. These tasks belong to the previous specification. Replacing the board clears its tasks and evidence."));
    const identity = element("details");
    identity.append(element("summary", null, "Board specification identity"),
      element("p", "dim", `Previous · ${board.board_spec_sha256}`),
      element("p", "dim", `Current · ${board.spec_sha256}`));
    panel.append(identity);
    actionForm(panel, "reset", "Replace task board", fields => {
      const consent = taskField(fields, "confirm_reset", "Clear the previous tasks and evidence", {type: "checkbox", required: true});
      return () => consent.checked ? {op: "reset"} : null;
    }, {expandable: true});
  }
  const counts = element("dl", "task-counts");
  const labels = {total: "Total", ready: "Ready", running: "Running", waiting: "Waiting", blocked: "Blocked", completed: "Completed"};
  for (const [name, label] of Object.entries(labels)) {
    const pair = element("div");
    pair.append(element("dt", null, label), element("dd", null, board.summary[name]));
    counts.append(pair);
  }
  panel.append(counts);
  const byId = new Map(board.tasks.map(task => [task.id, task]));
  const ready = new Set(board.ready_task_ids);
  const occupied = new Set(board.tasks.filter(task => task.status === "running").map(task => task.role));
  if (!stale) {
    if (board.assignments.length) {
      panel.append(element("h3", null, "Suggested assignments"),
        element("p", "dim", "Export the suggested assignments, then start each task here before launching its assignment in your authorized host."));
      const suggestions = element("ul", "task-suggestions");
      for (const item of board.assignments) {
        suggestions.append(element("li", null,
          `${byId.get(item.task_id).title} (${item.task_id}) · ${taskRoles[item.role]} · ${item.model_id} · ${item.reasoning_effort} effort`));
      }
      const exportPlan = button("Download ready dispatch JSON", async () => {
        if (!active() || busy || exportPlan.disabled) return;
        exportPlan.disabled = true;
        error.textContent = "";
        try {
          const team = await api(`/team/${encodeURIComponent(board.project_id)}`);
          if (!active() || busy) return;
          const plan = team.scheduled_dispatch_plan;
          if (!plan || plan.project?.id !== board.project_id || plan.project.spec_sha256 !== board.spec_sha256 ||
              plan.board_revision !== board.revision || plan.board_state !== board.state) {
            throw new Error("The dispatch plan and the displayed board differ. Refresh the board before exporting.");
          }
          downloadJson(`${JSON.stringify(plan, null, 2)}\n`, `${board.project_id}-tasks-r${board.revision}.json`);
        } catch (failure) {
          if (active()) error.textContent = failure.message;
        } finally {
          exportPlan.disabled = false;
        }
      });
      const exportActions = element("div", "actions");
      exportActions.append(exportPlan);
      panel.append(suggestions, exportActions);
    }
    if (board.tasks.length < 100) {
      actionForm(panel, "add", "Add task", fields => {
        const id = taskField(fields, "id", "Task ID (lowercase letters, numbers and hyphens)", {
          required: true, maxLength: 64, pattern: "[a-z0-9]+(?:-[a-z0-9]+)*"
        });
        const title = taskField(fields, "title", "Title", {required: true, maxLength: 120});
        const role = taskField(fields, "role", "Role", {value: "architecture"}, taskRoles);
        const priority = taskField(fields, "priority", "Priority (5 is highest)", {value: "3"}, {
          1: "1", 2: "2", 3: "3", 4: "4", 5: "5"
        });
        const deps = taskField(fields, "depends_on", "Dependency IDs (comma separated)");
        const gate = taskField(fields, "gate", "Completion gate", {value: "manual"}, taskGates);
        return () => ({op: "add", task: {
          id: id.value.trim(), title: title.value.trim(), role: role.value, priority: Number(priority.value),
          depends_on: deps.value.split(",").map(value => value.trim()).filter(Boolean), gate: gate.value
        }});
      }, {expandable: true, open: !board.tasks.length});
    }
  }
  if (!board.tasks.length) panel.append(element("p", "dim", "No tasks recorded."));
  for (const task of board.tasks) {
    const card = element("article", "task-row");
    const rowHead = element("div", "task-heading");
    const taskTitle = element("h3", null, task.title);
    taskTitle.id = `task-title-${task.id}`;
    card.setAttribute("aria-labelledby", taskTitle.id);
    const status = task.status === "pending" ? (ready.has(task.id) ? "Ready" : "Waiting") :
      {running: "Running", blocked: "Blocked", completed: "Completed"}[task.status];
    rowHead.append(taskTitle,
      badge(stale && task.status === "pending" ? "Pending" : status, {running: "progress", blocked: "bad", completed: "good"}[task.status]));
    card.append(rowHead, element("p", "dim",
      `${task.id} · ${taskRoles[task.role]} · Priority ${task.priority} · ${taskGates[task.gate]} · Attempts ${task.attempts}`));
    if (task.depends_on.length) card.append(element("p", null, `Depends on ${task.depends_on.join(", ")}`));
    if (task.reason) card.append(element("p", "checkpoint-warning", task.reason));
    if (task.job_id) card.append(element("p", null, `Build job · ${task.job_id}`));
    if (task.evidence.length) {
      const list = element("ul", "task-suggestions");
      for (const entry of task.evidence) list.append(element("li", null, entry));
      card.append(element("h4", null, "Completion evidence"), list);
    }
    panel.append(card);
    if (stale || task.status === "completed") continue;
    const actions = element("div", "task-controls");
    card.append(actions);
    const key = `${task.id}/${task.status}/${task.attempts}/${task.role}`;
    const quick = (op, caption) => actionForm(actions, `${key}/${op}`, caption,
      () => () => ({op, task_id: task.id}));
    if (ready.has(task.id)) {
      if (occupied.has(task.role)) actions.append(element("p", "dim", `${taskRoles[task.role]} is already working on another task.`));
      else quick("start", "Start task");
    }
    if (task.status === "running") {
      actionForm(actions, `${key}/complete`, "Complete task", fields => {
        const evidence = taskField(fields, "evidence", "Completion evidence (one entry per line, up to 8)", {required: true, rows: 3});
        const job = task.gate === "build" && taskField(fields, "job_id", "Verified build job ID", {required: true, pattern: "[a-f0-9]{32}", maxLength: 32});
        return () => ({op: "complete", task_id: task.id, evidence: evidence.value.split("\n").map(v => v.trim()).filter(Boolean),
          ...(job ? {job_id: job.value.trim()} : {})});
      }, {expandable: true});
      actionForm(actions, `${key}/block`, "Block task", fields => {
        const reason = taskField(fields, "reason", "Reason for blocking", {required: true, rows: 2, maxLength: 512});
        return () => ({op: "block", task_id: task.id, reason: reason.value.trim()});
      }, {expandable: true});
    }
    if (task.status === "blocked" || task.status === "running") quick("requeue", "Return to pending");
    if (task.status === "pending" || task.status === "blocked") {
      actionForm(actions, `${key}/reassign`, "Change role", fields => {
        const choices = Object.fromEntries(Object.entries(taskRoles).filter(([role]) => role !== task.role));
        const role = taskField(fields, "role", "New role", {}, choices);
        return () => ({op: "reassign", task_id: task.id, role: role.value});
      }, {expandable: true});
    }
  }
  return panel;
}

function renderReleases(registry, jobs, legacy, routeId) {
  const id = registry.project_id;
  const isActive = () => state.page === "releases" && state.route === routeId && state.selected === id;
  const panel = element("section", "panel team-brief orchestration");
  const error = element("p", "error");
  error.setAttribute("role", "alert");
  let busy = false, replaced = false;
  const controls = [];

  async function apply(action) {
    if (!isActive() || busy || replaced) return;
    busy = true;
    error.textContent = "";
    controls.forEach(control => { control.disabled = true; });
    panel.setAttribute("aria-busy", "true");
    try {
      const saved = await api(projectPath(id, "/releases"), "PUT", {
        expected_revision: registry.revision, spec_sha256: registry.spec_sha256, action
      });
      if (!isActive()) return;
      if (saved.project_id !== id) throw new Error("Received releases for a different project.");
      const next = renderReleases(saved, jobs, legacy, routeId);
      panel.replaceWith(next);
      replaced = true;
      next.querySelector("h2").focus();
      notify(`Active release updated at revision ${saved.revision}.`);
    } catch (failure) {
      if (isActive()) error.textContent = `${failure.message} Refresh releases before trying again.`;
    } finally {
      busy = false;
      controls.forEach(control => { control.disabled = false; });
      panel.removeAttribute("aria-busy");
    }
  }

  const title = element("h2", null, "Release registry");
  title.tabIndex = -1;
  const header = element("div", "task-heading");
  header.append(title, badge(`Revision ${registry.revision}`));
  panel.append(header, error);
  if (registry.active_release_id) {
    const status = element("div", "actions");
    status.append(element("strong", null, `Active release · ${registry.active_release_id}`),
      badge(registry.active_state, registry.active_state === "current" ? "good" : "bad"));
    panel.append(status);
    if (registry.active_state === "stale") panel.append(element("p", "checkpoint-warning",
      "The active release belongs to an earlier specification. Promote a verified build for the current specification or activate a matching release."));
    if (registry.active_state === "invalid") panel.append(element("p", "checkpoint-warning",
      "The active release failed integrity checks. Review the build output and choose a verified release."));
  } else {
    panel.append(element("p", "dim", "No active release."));
  }
  panel.append(element("p", "dim", `Current specification · ${registry.spec_sha256}`),
    element("h3", null, "Promote a build"));
  if (legacy.status === "fulfilled") {
    const latest = legacy.value.latest_job;
    if (latest) panel.append(element("p", "dim",
      `Latest build · ${latest.id} · verification ${legacy.value.verification_gate.status}`));
  } else {
    panel.append(element("p", "dim", `Latest build summary unavailable · ${legacy.reason.message}`));
  }
  if (jobs.status === "rejected") {
    panel.append(element("p", "error", `Build history unavailable · ${jobs.reason.message}`));
  } else {
    const promoted = new Set(registry.releases.map(entry => entry.job_id));
    const eligible = jobs.value.filter(job => job.project_id === id && job.status === "passed" && job.verified === true &&
      job.spec_sha256 === registry.spec_sha256 && job.output && !promoted.has(job.id));
    if (!eligible.length) {
      panel.append(element("p", "dim", "No unpromoted verified builds match the current specification."));
    } else {
      const fields = element("div", "release-controls");
      const select = taskField(fields, "release_job", "Verified build", {},
        Object.fromEntries(eligible.map(job => [job.id, job.id])));
      const promote = button("Promote and activate", () => apply({op: "promote", job_id: select.value}), "primary");
      controls.push(select, promote);
      fields.append(promote);
      panel.append(fields);
    }
  }

  panel.append(element("h3", null, "Release history"));
  if (!registry.releases.length) panel.append(element("p", "dim", "No releases have been promoted."));
  for (const entry of [...registry.releases].reverse()) {
    const row = element("article", "task-row");
    const summary = element("div", "task-heading");
    summary.append(element("h4", null, entry.id), badge(entry.id === registry.active_release_id ? "Active" : "Historical"));
    const identity = element("details");
    identity.append(element("summary", null, "Release provenance"),
      element("p", "dim", `Specification · ${entry.spec_sha256}`),
      element("p", "dim", `Manifest · ${entry.manifest_sha256}`),
      element("p", "dim", `Output · ${entry.output}`));
    row.append(summary, element("p", "dim", `Build ${entry.job_id} · ${entry.created_at}`), identity);
    if (entry.spec_sha256 !== registry.spec_sha256) {
      row.append(element("p", "dim", "Earlier specification"));
    } else if (entry.id !== registry.active_release_id) {
      const actions = element("div", "actions");
      const activate = button("Activate release", () => apply({op: "activate", release_id: entry.id}));
      controls.push(activate);
      actions.append(activate);
      row.append(actions);
    }
    panel.append(row);
  }
  return panel;
}

const defectSeverities = {critical: "Critical", high: "High", medium: "Medium", low: "Low"};
const auditStates = {
  pass: ["Passed", "good"], warn: ["Warning", "progress"], fail: ["Failed", "bad"],
  blocked: ["Blocked", "bad"], attention: ["Needs attention", "progress"], pending: ["Pending", ""]
};

function auditBadge(status) {
  const [label, tone] = auditStates[status] || [status, ""];
  return badge(label, tone);
}

function evidenceList(entries) {
  const list = element("ul", "task-suggestions");
  for (const entry of entries) list.append(element("li", null, entry));
  return list;
}

function metricList(fields) {
  const list = element("dl", "task-counts");
  for (const [label, value] of fields) {
    const pair = element("div");
    pair.append(element("dt", null, label), element("dd", null, value));
    list.append(pair);
  }
  return list;
}

function supervisorPanel(title) {
  const panel = element("section", "panel team-brief orchestration");
  panel.append(element("h2", null, title));
  return panel;
}

function renderProductionChecks(snapshot) {
  const checks = supervisorPanel("Production checks");
  checks.append(auditBadge(snapshot.status), element("p", "dim", `Specification · ${snapshot.spec_sha256}`));
  if (!snapshot.checks.length) checks.append(element("p", "dim", "No checks recorded."));
  for (const check of snapshot.checks) {
    const row = element("article", "task-row");
    const head = element("div", "task-heading");
    head.append(element("h3", null, check.label), auditBadge(check.status));
    row.append(head, element("p", "dim", check.evidence));
    checks.append(row);
  }
  const next = supervisorPanel("Recommendations");
  if (!snapshot.recommendations.length) next.append(element("p", "dim", "No recommendations for this specification."));
  for (const item of snapshot.recommendations) {
    const row = element("article", "task-row");
    const head = element("div", "task-heading");
    head.append(element("h3", null, item.title), badge(defectSeverities[item.severity] || item.severity));
    row.append(head, element("p", null, item.detail), element("p", "dim", taskRoles[item.role] || item.role),
      evidenceList(item.evidence));
    next.append(row);
  }
  return [checks, next];
}

function renderBuildPerformance(profile) {
  const panel = supervisorPanel("Build performance");
  const duration = seconds => Number.isFinite(seconds) ? `${Number(seconds.toPrecision(4))} s` : "Unmeasured";
  const summary = profile.summary;
  const comparison = profile.regression === true ? "Timing regression"
    : profile.regression === false ? "Within regression threshold" : "No timing comparison";
  panel.append(badge(comparison, profile.regression === true ? "bad" : profile.regression === false ? "good" : ""),
    element("p", "dim", `Specification · ${profile.spec_sha256}`),
    element("p", null, `${profile.counts.total} builds · ${profile.counts.passed} passed · ${profile.counts.failed} failed · ${profile.counts.canceled} canceled · ${profile.counts.queued} queued · ${profile.counts.running} running`),
    metricList([["Median build", duration(summary.median_build_seconds)], ["Median verification", duration(summary.median_verify_seconds)],
      ["Median total", duration(summary.median_total_seconds)], ["Latest total", duration(summary.latest_total_seconds)],
      ["Prior baseline", duration(summary.baseline_total_seconds)], ["Change", Number.isFinite(summary.regression_percent)
        ? `${Number(summary.regression_percent.toFixed(2))}%` : "Unavailable"]]),
    element("p", "dim", "Totals combine build and verification time. Medians use verified, passed builds with both stages measured. A regression requires a slowdown of at least 25% and one second against the median of two or more earlier builds."));
  if (!profile.samples.length) {
    panel.append(element("p", "dim", "No build samples for this specification."));
    return panel;
  }
  const scroll = element("div", "sample-scroll");
  scroll.tabIndex = 0;
  scroll.setAttribute("role", "region");
  scroll.setAttribute("aria-label", "Build timing samples");
  const table = element("table", "sample-table");
  table.append(element("caption", null, `Latest ${profile.samples.length} build samples`));
  const head = element("thead"), header = element("tr");
  for (const label of ["Build", "Created", "Status", "Queue", "Build time", "Verification", "Total"]) {
    const th = element("th", null, label);
    th.scope = "col";
    header.append(th);
  }
  head.append(header);
  const body = element("tbody");
  for (const sample of profile.samples) {
    const row = element("tr"), name = element("th", null, sample.job_id);
    name.scope = "row";
    row.append(name, element("td", null, sample.created_at || "Unknown"), element("td", null, sample.status));
    for (const key of ["queue_seconds", "build_seconds", "verify_seconds", "total_seconds"]) {
      row.append(element("td", null, duration(sample[key])));
    }
    body.append(row);
  }
  table.append(head, body);
  scroll.append(table);
  panel.append(scroll);
  return panel;
}

function renderDefectLedger(ledger, editable, drafts, forms, save) {
  const panel = supervisorPanel("Defect ledger");
  panel.append(badge(`Revision ${ledger.revision}`), element("p", "dim", `Specification · ${ledger.spec_sha256}`),
    metricList([["Current open", ledger.summary.current_open], ["Current resolved", ledger.summary.current_resolved],
      ["Historical open", ledger.summary.historical_open], ["Historical resolved", ledger.summary.historical_resolved]]));

  function defectForm(parent, op, item) {
    const key = item ? `${op}/${item.id}` : op;
    const caption = {add: "Record defect", resolve: "Resolve defect", reopen: "Reopen defect"}[op];
    const details = element("details"), form = element("form"), fields = element("fieldset", "checkpoint-fields");
    fields.setAttribute("aria-label", item ? `${caption} · ${item.title}` : caption);
    const inputs = {};
    if (op === "add") {
      inputs.title = taskField(fields, "title", "Title", {required: true, maxLength: 160});
      inputs.severity = taskField(fields, "severity", "Severity", {value: "medium"}, defectSeverities);
      inputs.description = taskField(fields, "description", "Description", {required: true, rows: 3, maxLength: 2048});
    }
    inputs.evidence = taskField(fields, "evidence", "Evidence (one entry per line)", {required: true, rows: 2});
    const submit = element("button", "primary", caption);
    submit.type = "submit";
    const error = element("p", "error");
    error.setAttribute("role", "alert");
    fields.append(submit);
    form.append(fields, error);
    details.append(element("summary", null, caption), form);
    parent.append(details);

    const draft = drafts.get(key);
    details.open = draft?.open ?? false;
    if (draft) {
      for (const [name, value] of Object.entries(draft.values)) inputs[name].value = value;
    }
    const values = () => Object.fromEntries(Object.entries(inputs).map(([name, node]) => [name, node.value]));
    forms.set(key, {fields, capture: () => ({open: details.open, values: values()})});
    form.addEventListener("submit", event => {
      event.preventDefault();
      if (forms.get(key)?.fields !== fields || fields.disabled) return;
      const data = values(), evidence = data.evidence.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
      if (!evidence.length || evidence.length > 8 || evidence.some(line => line.length > 512)) {
        error.textContent = "Enter 1–8 evidence entries of up to 512 characters each.";
        return;
      }
      const action = item ? {op, defect_id: item.id, evidence}
        : {op, title: data.title.trim(), severity: data.severity, description: data.description.trim(), evidence};
      return save(ledger, key, action, error);
    });
  }

  if (editable && ledger.items.length < 100) defectForm(panel, "add");
  for (const current of [true, false]) {
    panel.append(element("h3", null, current ? "Current specification" : "Earlier specifications"));
    const items = ledger.items.filter(item => (item.spec_sha256 === ledger.spec_sha256) === current);
    if (!items.length) {
      panel.append(element("p", "dim", current ? "No defects recorded for this specification." : "No historical defects."));
      continue;
    }
    if (!current) panel.append(element("p", "dim", "Historical defects are read-only."));
    for (const item of items) {
      const row = element("article", "task-row");
      const title = element("div", "task-heading");
      title.append(element("h4", null, item.title), badge(`${defectSeverities[item.severity]} · ${item.status}`,
        item.status === "resolved" ? "good" : item.severity === "critical" || item.severity === "high" ? "bad" : ""));
      row.append(title, element("p", null, item.description), element("p", "dim", `Defect ${item.id} · Updated ${item.updated_at}`));
      if (!current) row.append(element("p", "dim", `Specification · ${item.spec_sha256}`));
      row.append(evidenceList(item.evidence));
      if (current && editable) defectForm(row, item.status === "open" ? "resolve" : "reopen", item);
      panel.append(row);
    }
  }
  return panel;
}

async function renderSupervisor(id, routeId) {
  const active = () => state.page === "supervisor" && state.route === routeId && state.selected === id;
  const refresh = button("Refresh supervisor", () => load());
  const panels = element("div", "queue supervisor");
  view.replaceChildren(heading("Supervisor", "Review production checks, measured build times and defects for the selected project.", refresh),
    projectPicker(route), panels);
  panels.append(element("p", "dim", "Loading project evidence…"));
  let busy = false, conflict = false, currentLedger = null, draftSha = null;
  const forms = new Map(), drafts = new Map();

  function lock(value) {
    busy = value;
    refresh.disabled = value;
    for (const {fields} of forms.values()) fields.disabled = value || conflict;
    panels.setAttribute("aria-busy", String(value));
  }

  async function save(ledger, key, action, error) {
    if (!active() || busy || conflict || ledger !== currentLedger) return;
    lock(true);
    error.textContent = "";
    try {
      const updated = await api(projectPath(id, "/defects"), "PUT",
        {expected_revision: ledger.revision, spec_sha256: ledger.spec_sha256, action});
      if (!active()) return;
      if (updated.project_id !== id || updated.spec_sha256 !== ledger.spec_sha256 ||
          !Number.isInteger(updated.revision) || updated.revision <= ledger.revision) {
        conflict = true;
        throw new Error("Unexpected defect ledger response.");
      }
      forms.delete(key);
      drafts.delete(key);
      await load(updated);
      if (active()) {
        refresh.focus();
        notify(`Defect ledger saved at revision ${updated.revision}.`);
      }
    } catch (failure) {
      if (!active()) return;
      if (failure.status === 409) conflict = true;
      error.textContent = conflict ? `${failure.message} Refresh supervisor to review the latest revision.` : failure.message;
    } finally {
      if (active()) lock(false);
    }
  }

  async function load(saved) {
    if (!active() || (busy && !saved)) return;
    lock(true);
    try {
      const sources = ["supervisor", "performance", "defects"];
      const results = await Promise.allSettled(sources.map(async source => {
        const data = source === "defects" && saved ? saved : await api(projectPath(id, "/" + source));
        if (data?.project_id !== id || typeof data.spec_sha256 !== "string" || !data.spec_sha256.length) {
          throw new Error("The response does not match the selected project and specification.");
        }
        return data;
      }));
      if (!active()) return;
      for (const [key, form] of forms) drafts.set(key, form.capture());
      forms.clear();
      currentLedger = null;
      panels.replaceChildren();
      const digests = new Set(results.filter(result => result.status === "fulfilled").map(result => result.value.spec_sha256));
      conflict = digests.size > 1;
      if (conflict) panels.append(element("p", "checkpoint-warning", "The specification changed while loading. Refresh supervisor before editing defects."));
      const titles = ["Production checks unavailable", "Build performance unavailable", "Defect ledger unavailable"];
      results.forEach((result, index) => {
        try {
          if (result.status === "rejected") throw result.reason;
          const data = result.value;
          if (index === 0) panels.append(...renderProductionChecks(data));
          if (index === 1) panels.append(renderBuildPerformance(data));
          if (index === 2) {
            if (!Number.isInteger(data.revision) || data.revision < 0) throw new Error("The ledger revision is unavailable.");
            if (draftSha !== data.spec_sha256) drafts.clear();
            draftSha = data.spec_sha256;
            const ledgerPanel = renderDefectLedger(data, !conflict, drafts, forms, save);
            currentLedger = data;
            panels.append(ledgerPanel);
          }
        } catch (failure) {
          panels.append(box(titles[index], failure.message, null, "panel team-brief"));
        }
      });
    } finally {
      if (active()) lock(false);
    }
  }
  await load();
}

function sprintPlanPanel(plan, apply) {
  const panel = supervisorPanel("Sprint plan");
  const statuses = {ready: ["Ready to apply", "good"], blocked: ["Blocked", "bad"], empty: ["No proposed tasks", ""]};
  if (!Object.hasOwn(statuses, plan.status) || !Array.isArray(plan.tasks) || !Array.isArray(plan.rationale)
      || !/^[a-f0-9]{64}$/.test(plan.plan_id) || (plan.status === "ready" && !plan.tasks.length)) {
    throw new Error("Incomplete sprint proposal.");
  }
  const identity = element("details");
  identity.append(element("summary", null, "Plan identity"), element("p", "dim", `Plan ID · ${plan.plan_id}`),
    element("p", "dim", `Specification · ${plan.spec_sha256}`));
  panel.append(badge(...statuses[plan.status]), element("p", "dim", `Board revision · ${plan.board_revision ?? "Unavailable"}`), identity);
  if (plan.reason) panel.append(element("p", null, plan.reason));
  const reasons = new Map(plan.rationale.map(item => [item.task_id, item]));
  for (const task of plan.tasks) {
    const row = element("article", "task-row");
    const head = element("div", "task-heading");
    head.append(element("h3", null, task.title), badge(`Priority ${task.priority}`));
    row.append(head, element("p", "dim", `${task.id} · ${taskRoles[task.role] || task.role} · ${taskGates[task.gate] || task.gate}`),
      element("p", "dim", task.depends_on.length ? `Depends on ${task.depends_on.join(", ")}` : "No dependencies"));
    const reason = reasons.get(task.id);
    if (reason) row.append(element("p", null, reason.detail), evidenceList(reason.evidence));
    panel.append(row);
  }
  const actions = element("div", "actions");
  if (plan.status === "ready" && apply) {
    actions.append(button("Apply plan to task board", () => apply({plan_id: plan.plan_id}), "primary"));
  }
  actions.append(button("Open task board", () => navigate("team")));
  panel.append(actions);
  return panel;
}

function sprintAcceptancePanel(report) {
  const panel = supervisorPanel("Acceptance report");
  const statuses = {ready: ["Ready", "good"], blocked: ["Blocked", "bad"], pending: ["Pending", ""]};
  if (!Object.hasOwn(statuses, report.status) || !Array.isArray(report.gates) || !report.gates.length
      || report.gates.some(gate => !["pass", "fail", "pending"].includes(gate.status))) {
    throw new Error("Incomplete acceptance report.");
  }
  panel.append(badge(...statuses[report.status]), element("p", null, report.summary),
    element("p", "dim", "Advisory assessment for the saved specification. Release promotion is a separate action in Releases."),
    element("p", "dim", `Specification · ${report.spec_sha256}`));
  for (const gate of report.gates) {
    const item = element("article", "task-row");
    const head = element("div", "task-heading");
    head.append(element("h3", null, gate.label), auditBadge(gate.status));
    item.append(head, element("p", "dim", gate.evidence));
    panel.append(item);
  }
  return panel;
}

function sprintHistoryPanel(history, note, capture) {
  const panel = supervisorPanel("Evidence history");
  panel.append(element("p", "dim", "Each snapshot records the checks and their results at the time of capture."),
    element("p", "dim", `History revision ${history.revision} · Saved specification · ${history.spec_sha256}`));
  if (!Array.isArray(history.items)) throw new Error("Incomplete evidence history.");
  if (history.items.length >= 100) {
    panel.append(element("p", "checkpoint-warning", "This project has reached its limit of 100 snapshots."));
  } else if (capture) {
    const form = element("form", "sprint-capture");
    const input = taskField(form, "note", "Capture note (1–512 characters)", {required: true, rows: 2, value: note});
    const submit = element("button", null, "Capture evidence");
    submit.type = "submit";
    const error = element("p", "error");
    error.setAttribute("role", "alert");
    form.append(submit, error);
    form.addEventListener("submit", event => {
      event.preventDefault();
      const value = input.value.trim();
      if (!value || [...value].length > 512) {
        error.textContent = "Enter a capture note of 1–512 characters.";
        input.focus();
        return;
      }
      error.textContent = "";
      return capture({note: value});
    });
    panel.append(form);
  }
  if (!history.items.length) panel.append(element("p", "dim", "No evidence snapshots captured."));
  for (const item of history.items) {
    const entry = element("article", "task-row");
    const head = element("div", "task-heading");
    const time = element("time", null, item.created_at);
    time.dateTime = item.created_at;
    const title = element("h3");
    title.append(time);
    head.append(title, badge(item.spec_sha256 === history.spec_sha256 ? "Matches saved specification" : "Earlier specification"));
    const checks = element("details", "sprint-checks");
    checks.append(element("summary", null, `Captured checks (${item.checks.length})`));
    for (const check of item.checks) {
      const row = element("div", "sprint-check");
      const checkHead = element("div", "task-heading");
      checkHead.append(element("h4", null, check.label), auditBadge(check.status));
      row.append(checkHead, element("p", "dim", check.evidence));
      checks.append(row);
    }
    entry.append(head, element("p", null, item.note), auditBadge(item.status),
      element("p", "dim", `Snapshot ${item.id} · Captured specification · ${item.spec_sha256}`), checks);
    panel.append(entry);
  }
  return panel;
}

async function renderSprint(id, routeId) {
  const active = () => state.page === "sprint" && state.route === routeId && state.selected === id;
  const refresh = button("Refresh sprint", () => { if (!busy) return load(); });
  const message = element("p", "sprint-message");
  message.setAttribute("role", "status");
  const panels = element("div", "queue sprint");
  view.replaceChildren(heading("Sprint", "Review proposed work, acceptance gates and captured evidence for the selected project.", refresh),
    projectPicker(route), message, panels);
  const sources = ["sprint", "acceptance", "evidence-history"];
  const panelTitles = ["Sprint plan unavailable", "Acceptance report unavailable", "Evidence history unavailable"];
  const current = new Map();
  let busy = false, noteDraft = "", noteSpec = "";

  function lock(value) {
    busy = value;
    refresh.disabled = value;
    panels.setAttribute("aria-busy", String(value));
    for (const control of panels.querySelectorAll("button, textarea")) control.disabled = value;
  }

  function validate(source, data) {
    if (data?.project_id !== id || !/^[a-f0-9]{64}$/.test(data.spec_sha256)) {
      throw new Error("The response does not identify the selected project and its specification.");
    }
    if (source !== "acceptance") {
      const revision = source === "sprint" ? data.board_revision : data.revision;
      const unknownBoard = source === "sprint" && data.status === "blocked" && revision === null;
      if (!unknownBoard && (!Number.isSafeInteger(revision) || revision < 0)) {
        throw new Error("Invalid revision in the response.");
      }
    }
    return data;
  }

  async function load(savedHistory, announcement = "", clearNote = false) {
    if (!active()) return;
    lock(true);
    const oldNote = panels.querySelector("textarea");
    if (clearNote) noteDraft = "";
    else if (oldNote) noteDraft = oldNote.value;
    message.textContent = "";
    try {
      const results = await Promise.allSettled(sources.map(async source =>
        validate(source, source === "evidence-history" && savedHistory ? savedHistory : await api(projectPath(id, "/" + source)))));
      if (!active()) return;
      const digests = new Set(results.filter(r => r.status === "fulfilled").map(r => r.value.spec_sha256));
      const coherent = digests.size <= 1;
      current.clear();
      panels.replaceChildren();
      if (!coherent) {
        panels.append(element("p", "checkpoint-warning", "The specification changed while loading. Refresh sprint before applying a plan or capturing evidence."));
      }
      results.forEach((result, index) => {
        try {
          if (result.status === "rejected") throw result.reason;
          const data = result.value, source = sources[index];
          const save = coherent ? payload => mutate(source, data, payload) : null;
          if (source === "sprint") panels.append(sprintPlanPanel(data, save));
          if (source === "acceptance") panels.append(sprintAcceptancePanel(data));
          if (source === "evidence-history") {
            if (noteSpec !== data.spec_sha256) noteDraft = "";
            noteSpec = data.spec_sha256;
            panels.append(sprintHistoryPanel(data, noteDraft, save));
          }
          if (coherent) current.set(source, data);
        } catch (error) {
          panels.append(box(panelTitles[index], error.message));
        }
      });
      message.textContent = announcement;
    } finally {
      if (active()) lock(false);
    }
  }

  async function mutate(source, data, payload) {
    if (!active() || busy || current.get(source) !== data) return;
    lock(true);
    const revision = source === "sprint" ? data.board_revision : data.revision;
    try {
      const saved = await api(projectPath(id, "/" + source), "POST", {
        expected_revision: revision, spec_sha256: data.spec_sha256, ...payload
      });
      if (!active()) return;
      if (saved?.project_id !== id || saved.spec_sha256 !== data.spec_sha256 || !Number.isSafeInteger(saved.revision)
          || saved.revision !== revision + 1) {
        await load(null, "The save response could not be verified. Review the refreshed project before trying again.");
      } else if (source === "sprint") {
        await load(null, `Applied the plan to task board revision ${saved.revision}.`);
      } else {
        await load(saved, `Captured evidence at history revision ${saved.revision}.`, true);
      }
      if (active()) refresh.focus();
    } catch (error) {
      if (!active()) return;
      if (error.status === 409) {
        await load(null, `${error.message} Review the refreshed sprint before submitting again.`);
        if (active()) refresh.focus();
      } else {
        message.textContent = error.message;
      }
    } finally {
      if (active()) lock(false);
    }
  }
  await load();
}

const operationTitles = {
  "work-orders": "Claimed work orders", handoffs: "Handoff ledger", dossier: "Release dossier"
};
const isDigest = value => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const isRevision = value => Number.isSafeInteger(value) && value >= 0;
const operationOutcomes = {progress: "In progress", completed: "Completed", blocked: "Blocked"};
const operationReviews = {pending: "Awaiting review", accepted: "Accepted", rejected: "Rejected"};

function checkOperationResponse(source, data, id) {
  if (data?.project_id !== id || !isDigest(data.spec_sha256)) {
    throw new Error("The response does not identify this project and its specification.");
  }
  let valid;
  if (source === "work-orders") {
    valid = ["current", "empty", "stale", "unavailable"].includes(data.state)
      && (isRevision(data.board_revision) || (data.state === "unavailable" && data.board_revision === null))
      && Array.isArray(data.orders) && (data.state === "current" || !data.orders.length)
      && data.orders.every(order => isDigest(order?.order_id) && order.task_id && order.title
        && order.board_revision === data.board_revision && Number.isSafeInteger(order.attempt) && order.attempt > 0
        && Object.hasOwn(taskRoles, order.role) && Array.isArray(order.depends_on) && order.spawn_args?.message
        && order.spawn_args.task_name && order.spawn_args.model && order.spawn_args.reasoning_effort);
  } else if (source === "handoffs") {
    valid = isRevision(data.revision) && Array.isArray(data.items) && data.items.every(item =>
      item?.id && item.task_id && isDigest(item.spec_sha256) && isDigest(item.order_id)
      && Object.hasOwn(operationReviews, item.review) && Object.hasOwn(operationOutcomes, item.outcome)
      && Array.isArray(item.changed_paths) && Array.isArray(item.evidence));
  } else if (source === "dossier") {
    valid = ["ready", "pending", "blocked"].includes(data.status) && isDigest(data.report_sha256)
      && data.report?.project_id === id && data.report.spec_sha256 === data.spec_sha256 && data.report.status === data.status;
  } else {
    valid = data.format === "studio-project-recovery-v1" && isDigest(data.bundle_sha256)
      && data.records?.["project.json"] && data.records["spec.json"]?.sha256 === data.spec_sha256;
  }
  if (!valid) throw new Error("The server returned an incomplete " + (operationTitles[source] || "recovery bundle").toLowerCase() + " response.");
  return data;
}

function operationForm(caption, definitions, draft, commit) {
  const details = element("details", "operations-form");
  const form = element("form", "checkpoint-fields");
  const inputs = {};
  details.open = draft.open || false;
  for (const [name, label, settings, choices] of definitions) {
    inputs[name] = taskField(form, name, label, {...settings, value: draft[name] ?? settings.value ?? ""}, choices);
  }
  const submit = element("button", "primary", caption);
  submit.type = "submit";
  const error = element("p", "error");
  error.setAttribute("role", "alert");
  form.append(error, submit);
  details.append(element("summary", null, caption), form);
  form.addEventListener("submit", event => {
    event.preventDefault();
    const values = Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value.trim()]));
    for (const [name, input] of Object.entries(inputs)) {
      if (input.required && !values[name]) {
        error.textContent = "Complete the required fields.";
        input.focus();
        return;
      }
    }
    try {
      error.textContent = "";
      return commit(values);
    } catch (failure) {
      error.textContent = failure.message;
    }
  });
  return {details, read: () => ({
    ...Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value])), open: details.open
  })};
}

function operationsOrders(data, ops) {
  const panel = supervisorPanel(operationTitles["work-orders"]);
  panel.append(element("p", "dim", "The task board supplies one order for each running claim. Export an order for the host that will run it."));
  if (data.board_revision !== null) panel.append(badge("Board revision " + data.board_revision));
  if (!data.orders.length) {
    const messages = {current: "No running claims.", empty: "The task board is empty.",
      stale: "The task board belongs to an earlier specification.", unavailable: "The task board is unavailable."};
    panel.append(element("p", data.state === "stale" || data.state === "unavailable" ? "checkpoint-warning" : "", messages[data.state]),
      button("Open task board", () => navigate("team")));
  }
  for (const order of data.orders) {
    const row = element("article", "task-row");
    const head = element("div", "task-heading");
    head.append(element("h3", null, order.title), badge("Running claim", "progress"));
    row.append(head, element("p", null, taskRoles[order.role]),
      element("p", "dim", [order.task_id, "Attempt " + order.attempt, taskGates[order.gate] || order.gate].join(" · ")));
    if (order.depends_on.length) row.append(element("p", "dim", "Depends on " + order.depends_on.join(", ")));
    const packet = JSON.stringify({project_id: data.project_id, spec_sha256: data.spec_sha256, ...order}, null, 2) + "\n";
    const preview = element("details");
    const code = element("pre", "log", packet);
    code.tabIndex = 0;
    preview.append(element("summary", null, "View work order JSON"), code);
    row.append(preview);
    if (ops.coherent) {
      const actions = element("div", "actions");
      actions.append(button("Copy work order", async () => {
        if (!ops.current()) return;
        try {
          await navigator.clipboard.writeText(packet);
          if (ops.current()) notify("Work order copied.");
        } catch {
          if (!ops.current()) return;
          preview.open = true;
          code.focus();
          notify("Clipboard access failed. Select the JSON in the open preview.", true);
        }
      }), button("Download work order", () => {
        if (ops.current()) downloadJson(packet, data.project_id + "-" + order.task_id + "-attempt-" + order.attempt + ".json");
      }));
      row.append(actions);
      if (ops.canSubmit) {
        const key = "submit:" + order.order_id;
        const form = operationForm("Submit handoff", [
          ["outcome", "Reported outcome", {required: true, value: "progress"}, operationOutcomes],
          ["summary", "Summary", {rows: 2, required: true}],
          ["evidence", "Verification evidence (one entry per line)", {rows: 3, required: true}],
          ["changed_paths", "Changed paths (optional, one relative path per line)", {rows: 2}],
          ["next_action", "Next action", {rows: 2, required: true}]
        ], ops.draft(key), values => {
          const lines = value => value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
          const evidence = lines(values.evidence), paths = lines(values.changed_paths);
          if (!evidence.length || evidence.length > 8 || paths.length > 16
              || [values.summary, values.next_action, ...evidence].some(line => [...line].length > 512)
              || paths.some(line => [...line].length > 256)) {
            throw new Error("Use 1–8 evidence entries and up to 16 paths. Each text entry allows 512 characters and each path allows 256.");
          }
          return ops.save(key, {op: "submit", task_id: order.task_id, order_id: order.order_id,
            outcome: values.outcome, summary: values.summary, evidence, changed_paths: paths, next_action: values.next_action});
        });
        ops.track(key, form);
        row.append(form.details);
      }
    }
    panel.append(row);
  }
  return panel;
}

function operationsLedger(ledger, ops) {
  const panel = supervisorPanel(operationTitles.handoffs);
  panel.append(element("p", "dim", "Review a specialist’s evidence and next action. The lead manages task status on the Team board."),
    badge("Ledger revision " + ledger.revision));
  if (!ledger.items.length) panel.append(element("p", null, "No handoffs recorded."));
  if (ledger.items.length >= 100) panel.append(element("p", "checkpoint-warning", "This ledger has reached its limit of 100 handoffs."));
  for (const item of ledger.items) {
    const row = element("article", "task-row"), head = element("div", "task-heading");
    const historical = item.spec_sha256 !== ledger.spec_sha256;
    head.append(element("h3", null, item.task_id + " · Attempt " + item.attempt),
      badge(operationReviews[item.review], {accepted: "good", pending: "progress", rejected: "bad"}[item.review]));
    row.append(head, element("p", null, item.summary), element("p", "dim",
      (taskRoles[item.role] || item.role) + " · Reported outcome · " + operationOutcomes[item.outcome]));
    if (historical) row.append(badge("Earlier specification · Read-only"));
    const record = element("details", "operations-record");
    const time = element("time", null, item.created_at);
    time.dateTime = item.created_at;
    record.append(element("summary", null, "Evidence and record details"), element("h4", null, "Verification evidence"), evidenceList(item.evidence));
    if (item.changed_paths.length) record.append(element("h4", null, "Changed paths"), evidenceList(item.changed_paths));
    record.append(element("h4", null, "Next action"), element("p", null, item.next_action),
      element("h4", null, "Recorded"), time, element("p", "dim", "Handoff · " + item.id),
      element("p", "dim", "Board revision " + item.board_revision + " · Order " + item.order_id),
      element("p", "dim", "Specification · " + item.spec_sha256));
    if (item.review !== "pending") record.append(element("h4", null, "Review note"), element("p", null, item.review_note),
      element("p", "dim", "Reviewed · " + item.reviewed_at));
    row.append(record);
    if (!historical && item.review === "pending" && ops.coherent) {
      const key = "review:" + item.id;
      const form = operationForm("Review handoff", [
        ["decision", "Review decision", {required: true, value: ""}, {"": "Choose a decision", accepted: "Accept", rejected: "Reject"}],
        ["note", "Review note", {required: true, rows: 2}]
      ], ops.draft(key), values => {
        if ([...values.note].length > 512) throw new Error("Use up to 512 characters for the review note.");
        return ops.save(key, {op: "review", handoff_id: item.id, decision: values.decision, note: values.note});
      });
      ops.track(key, form);
      row.append(form.details);
    }
    panel.append(row);
  }
  return panel;
}

function operationsDossier(snapshot, raw, ops) {
  const panel = supervisorPanel(operationTitles.dossier);
  const status = {ready: ["Ready", "good"], pending: ["Pending", "progress"], blocked: ["Blocked", "bad"]};
  panel.append(badge(...status[snapshot.status]),
    element("p", "dim", "Review acceptance gates and verified build evidence. Handoff coverage is advisory."));
  const {gates, handoffs} = snapshot.report;
  const errors = Object.values(snapshot.report.source_errors || {});
  if (errors.length) panel.append(evidenceList(errors));
  if (Array.isArray(gates)) {
    const outstanding = gates.filter(gate => gate.status !== "pass");
    if (outstanding.length) {
      const details = element("details");
      details.append(element("summary", null, "Outstanding gates (" + outstanding.length + ")"),
        evidenceList(outstanding.map(gate => gate.label + " · " + gate.evidence)));
      panel.append(details);
    }
  }
  if (Number.isSafeInteger(handoffs?.covered_attempts) && Number.isSafeInteger(handoffs.completed_attempts)) {
    panel.append(element("p", null, "Accepted handoff coverage · " + handoffs.covered_attempts + " of " + handoffs.completed_attempts + " completed attempts"));
  }
  const identity = element("details");
  identity.append(element("summary", null, "Report identity"), element("p", "dim", "Report SHA-256 · " + snapshot.report_sha256),
    element("p", "dim", "Specification · " + snapshot.spec_sha256));
  panel.append(identity);
  if (ops.coherent) panel.append(button("Download dossier JSON", () => {
    if (ops.current()) downloadJson(raw, snapshot.project_id + "-dossier.json");
  }));
  return panel;
}

async function renderOperations(id, routeId) {
  const active = () => state.page === "operations" && state.route === routeId && state.selected === id;
  let busy = false, generation = 0, draftSpec = null;
  const drafts = new Map(), forms = new Map();
  const refresh = button("Refresh operations", () => { if (!busy && active()) return load(); });
  const message = element("p", "sprint-message");
  message.setAttribute("role", "status");
  const panels = element("div", "operations-grid");
  view.replaceChildren(heading("Operations", "Export claimed assignments, review specialist handoffs and collect project records.", refresh),
    projectPicker(route), message, panels);

  function lock(value) {
    busy = value;
    refresh.disabled = value;
    panels.setAttribute("aria-busy", String(value));
    for (const control of panels.querySelectorAll("button, select, textarea")) control.disabled = value;
  }

  async function recovery(expectedSpec, current) {
    if (!current()) return;
    lock(true);
    message.textContent = "Preparing recovery bundle…";
    try {
      const {data, raw} = await api(projectPath(id, "/recovery"), "GET", undefined, true);
      if (!active()) return;
      checkOperationResponse("recovery", data, id);
      if (expectedSpec && expectedSpec !== data.spec_sha256) throw new Error("The specification changed. Refresh operations before downloading.");
      downloadJson(raw, id + "-recovery.json");
      message.textContent = "Recovery bundle downloaded.";
    } catch (error) {
      if (active()) message.textContent = error.message;
    } finally {
      if (active()) lock(false);
    }
  }

  async function save(key, action, ledger, current) {
    if (!current()) return;
    lock(true);
    try {
      const saved = await api(projectPath(id, "/handoffs"), "POST", {
        expected_revision: ledger.revision, spec_sha256: ledger.spec_sha256, action
      });
      if (!active()) return;
      let recorded;
      try {
        checkOperationResponse("handoffs", saved, id);
        recorded = action.op === "review" ? saved.items.some(item => item.id === action.handoff_id
          && item.review === action.decision && item.review_note === action.note)
          : saved.items.some(item => item.order_id === action.order_id && item.task_id === action.task_id
            && item.summary === action.summary && item.outcome === action.outcome && !ledger.items.some(previous => previous.id === item.id));
      } catch {
        recorded = false;
      }
      if (!recorded || saved.spec_sha256 !== ledger.spec_sha256 || saved.revision !== ledger.revision + 1) {
        await load("The save response could not be verified. Review the refreshed ledger.");
        return;
      }
      await load("Handoff " + (action.op === "submit" ? "submitted" : action.decision) + " at ledger revision " + saved.revision + ".", key, saved);
      if (active()) refresh.focus();
    } catch (error) {
      if (!active()) return;
      if (error.status === 409) {
        await load(error.message + " Review the refreshed records before submitting again.");
        if (active()) refresh.focus();
      } else {
        message.textContent = error.message;
      }
    } finally {
      if (active()) lock(false);
    }
  }

  async function load(announcement = "", savedKey, savedLedger) {
    if (!active()) return;
    const version = ++generation;
    lock(true);
    message.textContent = "Loading operations…";
    for (const [key, form] of forms) drafts.set(key, form.read());
    if (savedKey) drafts.delete(savedKey);
    forms.clear();
    const sources = Object.keys(operationTitles);
    const results = await Promise.allSettled(sources.map(async source => {
      const path = projectPath(id, "/" + source);
      const result = source === "dossier" ? await api(path, "GET", undefined, true)
        : {data: source === "handoffs" && savedLedger ? savedLedger : await api(path)};
      checkOperationResponse(source, result.data, id);
      return result;
    }));
    if (!active() || version !== generation) return;
    const snapshots = new Map(sources.map((source, i) => [source, results[i].value?.data]));
    const digests = new Set([...snapshots.values()].filter(Boolean).map(data => data.spec_sha256));
    const coherent = digests.size <= 1, spec = digests.values().next().value;
    if (spec && draftSpec !== spec) drafts.clear();
    if (spec && coherent) draftSpec = spec;
    const ledger = snapshots.get("handoffs");
    const current = () => active() && !busy && generation === version;
    const ops = {current, coherent, canSubmit: ledger && ledger.items.length < 100,
      draft: key => drafts.get(key) || {}, track: (key, form) => forms.set(key, form),
      save: (key, action) => save(key, action, ledger, current)};
    panels.replaceChildren();
    for (const [i, source] of sources.entries()) {
      try {
        if (results[i].status === "rejected") throw results[i].reason;
        const data = snapshots.get(source);
        if (source === "work-orders") panels.append(operationsOrders(data, ops));
        if (source === "handoffs") panels.append(operationsLedger(data, ops));
        if (source === "dossier") panels.append(operationsDossier(data, results[i].value.raw, ops));
      } catch (error) {
        panels.append(box(operationTitles[source] + " unavailable", error.message, null, "panel team-brief orchestration"));
      }
    }
    const bundle = supervisorPanel("Recovery bundle");
    bundle.append(element("p", null, "Download the project specification and saved workstation records."),
      element("p", "checkpoint-warning", "Records only. Back up build jobs, build outputs and release packages separately."));
    if (coherent) bundle.append(button("Download recovery JSON", () => recovery(spec, current)));
    panels.append(bundle);
    message.textContent = coherent ? announcement : "The specification changed while loading. Refresh operations before editing or exporting.";
    lock(false);
  }
  await load();
}

const planningTitles = {
  blueprint: "Production blueprint", forecast: "Capacity forecast",
  "dependency-impact": "Dependency impact", preflight: "Delivery preflight"
};
const boardStates = {
  current: ["Current board", ""], empty: ["Empty board", ""],
  stale: ["Earlier specification", "progress"], unavailable: ["Unavailable", "bad"]
};
const textList = values => Array.isArray(values) && values.every(value => typeof value === "string" && value.length > 0);

function checkPlanningResponse(source, data, projectId) {
  if (data?.project_id !== projectId || !isDigest(data.spec_sha256)) {
    throw new Error("The response could not be matched to this project and its specification.");
  }
  let valid;
  if (source === "blueprint") {
    const tasks = data.tasks;
    valid = ["ready", "applied", "blocked"].includes(data.status) && Array.isArray(tasks)
      && typeof data.title === "string" && typeof data.reason === "string" && typeof data.template_id === "string"
      && tasks.every(task => task?.id && task.title && Object.hasOwn(taskRoles, task.role)
        && Object.hasOwn(taskGates, task.gate) && Number.isInteger(task.priority)
        && task.priority >= 1 && task.priority <= 5 && textList(task.depends_on))
      && (data.status === "blocked" ? tasks.length === 0 : tasks.length > 0 && isRevision(data.board_revision))
      && (data.status !== "ready" || isDigest(data.plan_id));
  } else if (source === "preflight") {
    const report = data.report;
    const statuses = new Set(Array.isArray(data.checks) ? data.checks.map(check => check?.status) : []);
    const expected = statuses.has("fail") ? "blocked" : statuses.has("pending") ? "pending" : "ready";
    valid = ["ready", "pending", "blocked"].includes(data.status) && isDigest(data.report_sha256)
      && report?.project_id === projectId && report.spec_sha256 === data.spec_sha256 && report.status === data.status
      && data.status === expected && (isRevision(report.board_revision) || report.board_revision === null)
      && (isDigest(report.dossier_sha256) || report.dossier_sha256 === null)
      && (data.status === "blocked" || isRevision(report.board_revision) && isDigest(report.dossier_sha256))
      && Array.isArray(data.checks) && data.checks.length > 0 && Array.isArray(report.checks)
      && data.checks.length === report.checks.length && data.checks.every((check, i) =>
        check?.id && check.label && typeof check.detail === "string" && ["pass", "fail", "pending"].includes(check.status)
        && ["id", "label", "detail", "status"].every(key => check[key] === report.checks[i]?.[key]));
  } else {
    valid = Object.hasOwn(boardStates, data.status) && typeof data.note === "string"
      && (isRevision(data.board_revision) || data.status === "unavailable" && data.board_revision === null);
    if (source === "forecast") {
      valid = valid && isRevision(data.remaining_tasks) && (data.minimum_dependency_waves === null || isRevision(data.minimum_dependency_waves))
        && Array.isArray(data.waves) && textList(data.unscheduled) && data.waves.every((wave, index) =>
          wave?.wave === index + 1 && textList(wave.task_ids) && wave.task_ids.length > 0);
    } else {
      valid = valid && Array.isArray(data.blocked) && textList(data.affected_task_ids) && textList(data.critical_chain)
        && data.blocked.every(blocker => blocker?.task_id && Object.hasOwn(taskRoles, blocker.role)
          && typeof blocker.reason === "string" && textList(blocker.affected_task_ids)
          && blocker.affected_count === blocker.affected_task_ids.length);
    }
  }
  if (!valid) throw new Error("The server returned an incomplete " + planningTitles[source].toLowerCase() + " response.");
}

function planningBlueprint(plan, apply, current) {
  const panel = supervisorPanel(planningTitles.blueprint);
  const labels = {ready: ["Ready to review", ""], applied: ["Already on task board", "good"], blocked: ["Blocked", "bad"]};
  const head = element("div", "task-heading");
  head.append(element("h3", null, plan.title), badge(...labels[plan.status]));
  const identity = element("details");
  identity.append(element("summary", null, "Blueprint identity"),
    element("p", "dim", "Specification · " + plan.spec_sha256),
    element("p", "dim", "Board revision · " + (plan.board_revision ?? "Unavailable")));
  if (plan.template_id) identity.append(element("p", "dim", "Template · " + plan.template_id));
  if (plan.plan_id) identity.append(element("p", "dim", "Plan ID · " + plan.plan_id));
  panel.append(head, element("p", null, plan.reason), identity);

  if (plan.tasks.length) {
    const tasks = element("div", "planning-tasks");
    for (const task of plan.tasks) {
      const item = element("article", "task-row");
      item.append(element("h4", null, task.title), element("p", null, taskRoles[task.role]),
        element("p", "dim", task.id + " · Priority " + task.priority + " · " + taskGates[task.gate]),
        element("p", "dim", task.depends_on.length ? "Depends on " + task.depends_on.join(", ") : "No dependencies"));
      tasks.append(item);
    }
    if (plan.status === "applied") {
      const details = element("details");
      details.append(element("summary", null, "View milestone tasks (" + plan.tasks.length + ")"), tasks);
      panel.append(details);
    } else panel.append(tasks);
  }

  if (apply && plan.status === "ready") {
    const controls = element("div", "planning-confirm");
    let confirmation;
    const review = button("Apply blueprint…", () => {
      if (!current()) return;
      const group = element("div", "actions");
      const confirm = button("Confirm and add " + plan.tasks.length + " tasks", () => {
        if (current() && confirm === confirmation) return apply(plan);
      }, "primary");
      const cancel = button("Cancel", () => {
        if (!current() || confirm !== confirmation) return;
        confirmation = null;
        controls.replaceChildren(review);
        review.focus();
      });
      confirmation = confirm;
      group.append(confirm, cancel);
      controls.replaceChildren(element("p", null, "Add the reviewed tasks to board revision " + plan.board_revision
        + "? They will be available to claim on the Team tab."), group);
      cancel.focus();
    }, "primary");
    controls.append(review);
    panel.append(controls);
  }
  return panel;
}

function planningBoardHeader(source, data) {
  const panel = supervisorPanel(planningTitles[source]);
  const head = element("div", "task-heading");
  head.append(badge(...boardStates[data.status]));
  if (isRevision(data.board_revision)) head.append(element("p", "dim", "Board revision " + data.board_revision));
  panel.append(head, element("p", "dim", data.note));
  return panel;
}

function planningForecast(data) {
  const panel = planningBoardHeader("forecast", data);
  if (!["current", "empty"].includes(data.status)) return panel;
  panel.append(metricList([["Remaining tasks", data.remaining_tasks], ["Scheduled waves", data.waves.length],
    ["Dependency minimum (waves)", data.minimum_dependency_waves ?? "Unavailable"]]));
  if (data.waves.length) {
    const list = element("ol", "planning-waves");
    for (const wave of data.waves) {
      const item = element("li");
      item.append(element("strong", null, "Wave " + wave.wave), element("span", null, wave.task_ids.join(", ")));
      list.append(item);
    }
    panel.append(list);
  }
  if (data.unscheduled.length) panel.append(element("h3", null, "Unscheduled tasks"), evidenceList(data.unscheduled));
  return panel;
}

function planningImpact(data) {
  const panel = planningBoardHeader("dependency-impact", data);
  if (data.status !== "current") return panel;
  panel.append(metricList([["Blockers", data.blocked.length], ["Affected tasks", data.affected_task_ids.length]]));
  if (data.critical_chain.length) panel.append(element("h3", null, "Longest remaining dependency chain"),
    element("p", null, data.critical_chain.join(" → ")));
  if (data.affected_task_ids.length) panel.append(element("h3", null, "All affected tasks"), evidenceList(data.affected_task_ids));
  for (const blocker of data.blocked) {
    const item = element("article", "task-row");
    item.append(element("h3", null, blocker.task_id), element("p", "dim", taskRoles[blocker.role]),
      element("p", null, blocker.reason), element("p", "dim", "Affected downstream tasks · " + blocker.affected_count));
    if (blocker.affected_task_ids.length) item.append(evidenceList(blocker.affected_task_ids));
    panel.append(item);
  }
  return panel;
}

function planningPreflight(data, download) {
  const panel = supervisorPanel(planningTitles.preflight);
  const labels = {ready: ["Preflight checks passed", "good"], pending: ["Evidence pending", "progress"], blocked: ["Blocked", "bad"]};
  panel.append(badge(...labels[data.status]), element("p", "dim", data.report.advisory || "Advisory checks for the saved project."));
  for (const check of data.checks) {
    const item = element("article", "task-row");
    const head = element("div", "task-heading");
    head.append(element("h3", null, check.label), auditBadge(check.status));
    item.append(head, element("p", null, check.detail));
    panel.append(item);
  }
  const identity = element("details");
  identity.append(element("summary", null, "Report identity"), element("p", "dim", "Report SHA-256 · " + data.report_sha256),
    element("p", "dim", "Specification · " + data.spec_sha256),
    element("p", "dim", "Board revision · " + (data.report.board_revision ?? "Unavailable")));
  if (data.report.dossier_sha256) identity.append(element("p", "dim", "Dossier SHA-256 · " + data.report.dossier_sha256));
  panel.append(identity);
  if (download) panel.append(button("Download preflight JSON", download));
  return panel;
}

async function renderPlanning(id, routeId) {
  const active = () => state.page === "planning" && location.hash === "#planning" && state.route === routeId && state.selected === id;
  let generation = 0, busy = false;
  const refresh = button("Refresh planning", () => { if (active() && !busy) return load(); });
  const message = element("p", "sprint-message");
  message.setAttribute("role", "status");
  const panels = element("div", "planning-grid operations-grid");
  view.replaceChildren(heading("Planning", "Review the first milestone, task dependencies and delivery checks for this project.", refresh),
    projectPicker(route), message, panels);

  function lock(value) {
    busy = value;
    refresh.disabled = value;
    panels.setAttribute("aria-busy", String(value));
    for (const control of panels.querySelectorAll("button")) control.disabled = value;
  }

  async function apply(plan) {
    lock(true);
    message.textContent = "Adding blueprint tasks…";
    let announcement;
    try {
      const board = await api(projectPath(id, "/blueprint"), "POST", {
        expected_revision: plan.board_revision, spec_sha256: plan.spec_sha256, plan_id: plan.plan_id
      });
      if (!active()) return;
      const verified = board?.project_id === id && board.spec_sha256 === plan.spec_sha256
        && board.revision === plan.board_revision + 1 && Array.isArray(board.tasks) && plan.tasks.every(draft =>
          board.tasks.some(task => task?.id === draft.id && task.title === draft.title && task.priority === draft.priority
            && task.role === draft.role && task.gate === draft.gate && textList(task.depends_on)
            && task.depends_on.length === draft.depends_on.length && draft.depends_on.every((parent, i) => parent === task.depends_on[i])));
      announcement = verified ? "Blueprint added to task board revision " + board.revision + "."
        : "The save response could not be verified. Review the refreshed blueprint.";
    } catch (error) {
      if (!active()) return;
      announcement = error.message + " Review the refreshed blueprint before applying.";
    }
    await load(announcement);
    if (active()) refresh.focus();
  }

  async function load(announcement = "") {
    const version = ++generation;
    lock(true);
    message.textContent = "Loading planning reports…";
    const current = () => active() && !busy && generation === version;
    const sources = Object.keys(planningTitles);
    const results = await Promise.allSettled(sources.map(async source => {
      const path = projectPath(id, "/" + source);
      const snapshot = source === "preflight" ? await api(path, "GET", undefined, true) : {data: await api(path)};
      checkPlanningResponse(source, snapshot.data, id);
      return snapshot;
    }));
    if (!active() || generation !== version) return;
    const data = results.filter(result => result.status === "fulfilled").map(result => result.value.data);
    const specs = new Set(data.map(snapshot => snapshot.spec_sha256));
    const revisions = new Set(data.map(snapshot => snapshot.report?.board_revision ?? snapshot.board_revision).filter(isRevision));
    const coherent = specs.size <= 1 && revisions.size <= 1;
    panels.replaceChildren();
    results.forEach((result, i) => {
      const source = sources[i];
      if (result.status === "rejected") {
        panels.append(box(planningTitles[source] + " unavailable", result.reason.message, null, "panel team-brief orchestration"));
        return;
      }
      const {data, raw} = result.value;
      if (source === "blueprint") panels.append(planningBlueprint(data, coherent && apply, current));
      if (source === "forecast") panels.append(planningForecast(data));
      if (source === "dependency-impact") panels.append(planningImpact(data));
      if (source === "preflight") panels.append(planningPreflight(data, coherent && (() => {
        if (current()) downloadJson(raw, id + "-preflight.json");
      })));
    });
    if (!coherent) {
      const warning = "Project data changed while loading. Refresh planning to review a consistent snapshot.";
      announcement = announcement ? announcement + " " + warning : warning;
    }
    message.textContent = announcement;
    lock(false);
  }
  await load();
}

const coordinationTitles = {
  "specialist-memory": "Specialist memory", priorities: "Task priorities",
  "recovery-advice": "Recovery advice", allocation: "Shared role allocation"
};
const coordinationText = value => typeof value === "string" && value.trim().length > 0;
const coordinationRole = value => typeof value === "string" && Object.hasOwn(taskRoles, value);
const handoffId = value => typeof value === "string" && /^[0-9a-f]{32}$/.test(value);

function fullRoleList(rows) {
  return Array.isArray(rows) && rows.every(row => coordinationRole(row?.role))
    && rows.length === Object.keys(taskRoles).length && new Set(rows.map(row => row.role)).size === rows.length;
}

function validPriority(row) {
  return row && coordinationText(row.task_id) && coordinationRole(row.role) && coordinationText(row.title)
    && Number.isInteger(row.priority) && row.priority >= 1 && row.priority <= 5
    && isRevision(row.downstream_count) && Number.isSafeInteger(row.chain_length) && row.chain_length >= 1;
}

function validCoordinationReport(source, data, id) {
  if (!data || typeof data.status !== "string" || !coordinationText(data.note)) return false;
  const unavailable = data.status === "unavailable";
  if (source === "allocation") {
    const counts = data.summary;
    if (!["current", "empty", "unavailable"].includes(data.status) || counts?.capacity !== Object.keys(taskRoles).length
      || !["assigned", "occupied", "conflicts", "idle"].every(key => isRevision(counts[key]))) return false;
    if (unavailable) return Array.isArray(data.roles) && !data.roles.length
      && !counts.assigned && !counts.occupied && !counts.conflicts && !counts.idle;
    if (!fullRoleList(data.roles)) return false;
    const observed = {assigned: 0, occupied: 0, conflicts: 0, idle: 0};
    for (const row of data.roles) {
      const owners = row.project_ids, work = row.assignment;
      if (!textList(owners) || new Set(owners).size !== owners.length) return false;
      if (row.state === "assigned") {
        if (owners.length !== 1 || work?.project_id !== owners[0] || work.role !== row.role || !coordinationText(work.task_id)
          || !coordinationText(work.title) || !isDigest(work.spec_sha256) || !isRevision(work.board_revision)) return false;
      } else if (work !== null || !(row.state === "idle" && !owners.length || row.state === "occupied" && owners.length === 1
        || row.state === "conflict" && owners.length >= 2)) return false;
      observed[row.state === "conflict" ? "conflicts" : row.state]++;
    }
    return Object.keys(observed).every(key => counts[key] === observed[key])
      && (data.status !== "empty" || counts.idle === counts.capacity);
  }

  if (data.project_id !== id && !(unavailable && data.project_id === null)) return false;
  if (!isDigest(data.spec_sha256) && !(unavailable && data.spec_sha256 === null)) return false;
  if (source === "specialist-memory") {
    if (!["current", "empty", "unavailable"].includes(data.status)) return false;
    if (unavailable) return data.handoff_revision === null && data.historical_count === null
      && Array.isArray(data.roles) && !data.roles.length;
    return isRevision(data.handoff_revision) && isRevision(data.historical_count) && fullRoleList(data.roles)
      && (data.status === "current") === data.roles.some(row => isRevision(row.accepted_count) && row.accepted_count > 0)
      && data.roles.every(row => isRevision(row.accepted_count) && Array.isArray(row.memories)
        && row.memories.length === Math.min(row.accepted_count, 5) && row.memories.every(memory =>
          handoffId(memory?.handoff_id) && coordinationText(memory.task_id) && Number.isSafeInteger(memory.attempt)
          && memory.attempt > 0 && typeof memory.outcome === "string" && Object.hasOwn(operationOutcomes, memory.outcome) && coordinationText(memory.summary)
          && textList(memory.evidence) && coordinationText(memory.next_action) && coordinationText(memory.reviewed_at)));
  }
  if (!Object.hasOwn(boardStates, data.status) || !(isRevision(data.board_revision) || unavailable && data.board_revision === null)) return false;
  if (source === "priorities") {
    if (!Array.isArray(data.candidates) || !Array.isArray(data.recommendations)) return false;
    if (data.status !== "current") return !data.candidates.length && !data.recommendations.length;
    const candidates = new Map(data.candidates.map(row => [row?.task_id, row]));
    return candidates.size === data.candidates.length && data.candidates.every(validPriority)
      && new Set(data.recommendations.map(row => row?.role)).size === data.recommendations.length
      && data.recommendations.every(row => validPriority(row) && ["role", "title", "priority", "downstream_count", "chain_length"]
        .every(key => candidates.get(row.task_id)?.[key] === row[key]));
  }
  return (isRevision(data.handoff_revision) || unavailable && data.handoff_revision === null) && Array.isArray(data.items)
    && (data.status === "current" || !data.items.length) && data.items.every(row =>
      coordinationText(row?.task_id) && coordinationText(row.title) && coordinationRole(row.role) && isRevision(row.attempt)
      && coordinationText(row.reason) && isRevision(row.affected_count) && (row.handoff_id === null || handoffId(row.handoff_id))
      && coordinationText(row.next_action));
}

function coordinationPanel(source, data) {
  const panel = supervisorPanel(coordinationTitles[source]);
  panel.setAttribute("aria-label", coordinationTitles[source]);
  const status = {current: "Current", empty: "Empty", stale: "Earlier specification", unavailable: "Unavailable"};
  panel.append(badge(status[data.status], data.status === "unavailable" ? "bad" : data.status === "stale" ? "progress" : ""),
    element("p", "dim", data.note));
  if (data.spec_sha256) {
    const details = element("details");
    details.append(element("summary", null, "Report identity"), element("p", "dim", "Specification · " + data.spec_sha256));
    if (isRevision(data.board_revision)) details.append(element("p", "dim", "Board revision " + data.board_revision));
    if (isRevision(data.handoff_revision)) details.append(element("p", "dim", "Handoff revision " + data.handoff_revision));
    panel.append(details);
  }
  if (data.status === "unavailable" || data.status === "stale") return panel;
  if (source === "specialist-memory") {
    panel.append(element("p", "dim", "Earlier-specification reports excluded · " + data.historical_count));
    for (const role of data.roles) {
      const details = element("details", "coordination-memory");
      details.append(element("summary", null, taskRoles[role.role] + " · " + role.accepted_count + " accepted"));
      if (!role.memories.length) details.append(element("p", "dim", "No accepted reports for this specification."));
      for (const memory of role.memories) {
        const item = element("article", "task-row");
        item.append(element("h3", null, memory.task_id + " · Attempt " + memory.attempt),
          badge(operationOutcomes[memory.outcome]), element("p", null, memory.summary),
          element("h4", null, "Reported evidence"), evidenceList(memory.evidence),
          element("p", null, "Recorded next action · " + memory.next_action),
          element("p", "dim", "Handoff " + memory.handoff_id + " · Reviewed " + memory.reviewed_at));
        details.append(item);
      }
      panel.append(details);
    }
  } else if (source === "priorities") {
    const recommended = new Set(data.recommendations.map(row => row.task_id));
    if (!data.candidates.length) panel.append(element("p", "dim", "No ready candidates for this project."));
    const list = element("ol", "coordination-priorities");
    for (const row of data.candidates) {
      const item = element("li"), head = element("div", "task-heading");
      head.append(element("h3", null, row.title));
      if (recommended.has(row.task_id)) head.append(badge("Recommended"));
      item.append(head, element("p", "dim", row.task_id + " · " + taskRoles[row.role]),
        element("p", null, "Priority " + row.priority + " · Downstream tasks " + row.downstream_count + " · Chain length " + row.chain_length));
      list.append(item);
    }
    if (data.candidates.length) panel.append(list);
  } else if (source === "recovery-advice") {
    if (!data.items.length) panel.append(element("p", "dim", "No blocked tasks to review."));
    for (const row of data.items) {
      const item = element("article", "task-row");
      item.append(element("h3", null, row.title), element("p", "dim", row.task_id + " · " + taskRoles[row.role] + " · Attempt " + row.attempt),
        element("p", null, row.reason), element("p", "dim", "Affected tasks · " + row.affected_count),
        element("p", null, row.next_action));
      if (row.handoff_id) item.append(element("p", "dim", "Handoff " + row.handoff_id));
      panel.append(item);
    }
  } else {
    const labels = {assigned: "Suggested", occupied: "Occupied", conflict: "Conflict", idle: "Idle"};
    panel.append(metricList([["Capacity", data.summary.capacity], ["Suggested", data.summary.assigned], ["Occupied", data.summary.occupied],
      ["Conflicts", data.summary.conflicts], ["Idle", data.summary.idle]]));
    for (const row of data.roles) {
      const item = element("article", "task-row"), head = element("div", "task-heading");
      head.append(element("h3", null, taskRoles[row.role]), badge(labels[row.state], row.state === "conflict" ? "bad" : ""));
      item.append(head);
      if (row.project_ids.length) item.append(element("p", "dim", "Projects · " + row.project_ids.join(", ")));
      if (row.assignment) item.append(element("p", null, row.assignment.title),
        element("p", "dim", row.assignment.task_id + " · Board revision " + row.assignment.board_revision));
      panel.append(item);
    }
  }
  return panel;
}

async function renderCoordination(id, routeId) {
  const active = () => state.page === "coordination" && location.hash === "#coordination" && state.route === routeId && state.selected === id;
  const refresh = button("Refresh coordination", () => { if (active() && !refresh.disabled) return load(); });
  const message = element("p", "sprint-message"), panels = element("div", "operations-grid");
  message.setAttribute("role", "status");
  view.replaceChildren(heading("Coordination", "Review project evidence and task advice alongside shared specialist availability.", refresh),
    projectPicker(route), message, panels);

  async function load() {
    refresh.disabled = true;
    panels.replaceChildren();
    panels.setAttribute("aria-busy", "true");
    message.textContent = "Loading coordination reports…";
    const sources = Object.keys(coordinationTitles);
    const results = await Promise.allSettled(sources.map(source => api(source === "allocation" ? "/allocation" : projectPath(id, "/" + source))));
    if (!active()) return;
    const specs = new Set(), boards = new Set(), handoffs = new Set(), boardStatesSeen = new Set();
    let wrongProject = false, localAssignment = false;
    const reports = results.map((result, index) => {
      if (result.status === "rejected") return {error: result.reason.message};
      const data = result.value, source = sources[index];
      if (source !== "allocation" && data) {
        if (data.project_id !== id && !(data.status === "unavailable" && data.project_id === null)) wrongProject = true;
        if (isDigest(data.spec_sha256)) specs.add(data.spec_sha256);
        if (isRevision(data.board_revision)) boards.add(data.board_revision);
        if (isRevision(data.handoff_revision)) handoffs.add(data.handoff_revision);
        if (source !== "specialist-memory" && typeof data.status === "string" && Object.hasOwn(boardStates, data.status)
          && data.status !== "unavailable") boardStatesSeen.add(data.status);
      }
      if (!validCoordinationReport(source, data, id)) return {error: "The report could not be verified."};
      if (source === "allocation") {
        for (const row of data.roles) {
          if (row.assignment?.project_id === id) {
            localAssignment = true;
            specs.add(row.assignment.spec_sha256);
            boards.add(row.assignment.board_revision);
            boardStatesSeen.add("current");
          }
        }
      }
      return {data};
    });
    const inconsistent = wrongProject || specs.size > 1 || boards.size > 1 || handoffs.size > 1 || boardStatesSeen.size > 1;
    const warning = "Project reports disagree. Refresh coordination to load a consistent snapshot.";
    reports.forEach(({data, error}, index) => {
      const source = sources[index];
      if (inconsistent && (source !== "allocation" || localAssignment)) error = "Refresh to verify this report against the selected project.";
      panels.append(error ? box(coordinationTitles[source] + " unavailable", error, null, "panel team-brief orchestration")
        : coordinationPanel(source, data));
    });
    const partial = reports.some(report => report.error || report.data.status === "unavailable");
    message.textContent = inconsistent ? warning : partial ? "Some coordination reports are unavailable." : "Coordination reports refreshed.";
    panels.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
  await load();
}

const qualityTitles = {
  "quality-matrix": "Quality matrix", "quality-trends": "Quality trends",
  "specialist-analytics": "Specialist analytics", "dispatch-cycle": "Workspace dispatch cycle"
};
const qualityGates = ["build", "release", "task_board", "manual_review", "defects", "performance"];
const gateOrder = ["fail", "warn", "pending", "pass"];
const auditOverall = ["blocked", "attention", "pending", "pass"];
const trendLabels = {improved: "Improved", regressed: "Regressed", unchanged: "Unchanged"};

function matchingCounts(summary, rows, field, keys) {
  return keys.every(key => isRevision(summary?.[key]) && summary[key] === rows.filter(row => row?.[field] === key).length);
}

function completeChecks(checks, gates) {
  return checks.length === gates.length && gates.every(id => checks.some(row => row?.id === id && coordinationText(row.label)));
}

function validMatrix(data) {
  const checks = data.checks;
  if (!Array.isArray(checks) || !matchingCounts(data.summary, checks, "status", ["pass", "pending", "fail"])) return false;
  if (data.status === "unavailable") return !checks.length;
  const expected = data.summary.fail ? "blocked" : data.summary.pending ? "pending" : "ready";
  return data.status === expected && completeChecks(checks, [...qualityGates, "audit_history"])
    && checks.every(row => ["pass", "pending", "fail"].includes(row.status) && coordinationText(row.evidence)
      && coordinationText(row.next_action) && coordinationRole(row.role));
}

function validTrends(data) {
  const checks = data.checks;
  if (!Array.isArray(checks) || !matchingCounts(data.summary, checks, "trend", Object.keys(trendLabels))) return false;
  if (data.status === "unavailable") return !checks.length && ["history_revision", "historical_count", "live_status",
    "baseline_status", "baseline_id"].every(key => data[key] === null);
  if (!isRevision(data.history_revision) || !isRevision(data.historical_count) || !auditOverall.includes(data.live_status)) return false;
  if (data.status === "empty") return data.history_revision === data.historical_count && data.baseline_id === null
    && data.baseline_status === null && !checks.length;
  if (data.status !== "current" || data.history_revision <= data.historical_count || !handoffId(data.baseline_id)
    || !completeChecks(checks, qualityGates)) return false;
  const consistent = checks.every(row => {
    const before = gateOrder.indexOf(row.baseline_status), after = gateOrder.indexOf(row.live_status);
    return before >= 0 && after >= 0 && row.trend === (after > before ? "improved" : after < before ? "regressed" : "unchanged");
  });
  return consistent && ["baseline_status", "live_status"].every(key =>
    data[key] === auditOverall[Math.min(...checks.map(row => gateOrder.indexOf(row[key])))]);
}

function validAnalytics(data) {
  if (data.status === "unavailable") return data.handoff_revision === null && data.historical_count === null
    && Array.isArray(data.roles) && !data.roles.length;
  if (!["empty", "current"].includes(data.status) || !fullRoleList(data.roles)
    || !isRevision(data.handoff_revision) || !isRevision(data.historical_count)) return false;
  return (data.status === "current") === data.roles.some(row => row.submitted > 0) && data.roles.every(row => {
    const reviewed = row.accepted + row.rejected;
    return ["submitted", "accepted", "rejected", "pending", "unique_orders", "completed", "blocked", "progress"].every(key => isRevision(row[key]))
      && row.submitted === reviewed + row.pending && row.accepted === row.completed + row.blocked + row.progress
      && row.unique_orders <= row.submitted && Boolean(row.unique_orders) === Boolean(row.submitted)
      && (reviewed ? Number.isFinite(row.median_review_seconds) && row.median_review_seconds >= 0 : row.median_review_seconds === null);
  });
}

function validCycle(data, projects) {
  const {steps, conflicts} = data;
  if (!Array.isArray(steps) || !Array.isArray(conflicts)) return false;
  if (data.status === "unavailable") return data.cycle_id === null && !steps.length && !conflicts.length;
  if (!isDigest(data.cycle_id)) return false;
  if (data.status === "idle") return !steps.length && !conflicts.length;
  const known = new Set(projects.map(project => project.id));
  if (data.status === "blocked") return !steps.length && conflicts.length > 0
    && new Set(conflicts.map(row => row?.role)).size === conflicts.length && conflicts.every(row => coordinationRole(row?.role)
      && Array.isArray(row.project_ids) && row.project_ids.length >= 2 && new Set(row.project_ids).size === row.project_ids.length
      && row.project_ids.every(id => known.has(id)));
  if (data.status !== "ready" || !steps.length || conflicts.length || new Set(steps.map(row => row?.role)).size !== steps.length) return false;
  const seen = new Map();
  return steps.every(row => {
    if (!known.has(row?.project_id) || !coordinationRole(row.role) || !coordinationText(row.title) || !coordinationText(row.task_id)
      || !isDigest(row.spec_sha256) || !isRevision(row.expected_revision) || !Number.isInteger(row.priority) || row.priority < 1 || row.priority > 5
      || row.action?.op !== "start" || row.action.task_id !== row.task_id || Object.keys(row.action).length !== 2) return false;
    const previous = seen.get(row.project_id);
    if (previous && (previous.spec !== row.spec_sha256 || previous.revision !== row.expected_revision || previous.tasks.has(row.task_id))) return false;
    const scope = previous || {spec: row.spec_sha256, revision: row.expected_revision, tasks: new Set()};
    scope.tasks.add(row.task_id);
    seen.set(row.project_id, scope);
    return true;
  });
}

function qualityTable(caption, columns, rows) {
  const wrap = element("div", "quality-table-wrap"), table = element("table", "sample-table");
  const head = element("thead"), header = element("tr"), body = element("tbody");
  for (const column of columns) {
    const cell = element("th", null, column);
    cell.scope = "col";
    header.append(cell);
  }
  head.append(header);
  for (const values of rows) {
    const row = element("tr");
    values.forEach((value, index) => {
      const cell = element(index ? "td" : "th", null, value);
      if (!index) cell.scope = "row";
      row.append(cell);
    });
    body.append(row);
  }
  table.append(element("caption", null, caption), head, body);
  wrap.append(table);
  return wrap;
}

function qualityIdentity(panel, data, fields) {
  const detail = element("details");
  detail.append(element("summary", null, "Report identity"));
  for (const [label, value] of fields) if (value != null) detail.append(element("p", "dim", label + " " + value));
  if (data.spec_sha256) detail.append(element("p", "dim", "Specification " + data.spec_sha256));
  panel.append(detail);
}

function qualityPanel(source, data) {
  const panel = supervisorPanel(qualityTitles[source]);
  const labels = {ready: "Ready for review", blocked: "Blocked", pending: "Pending", current: "Current", empty: "Empty",
    idle: "Idle", unavailable: "Unavailable"};
  panel.setAttribute("aria-label", qualityTitles[source]);
  panel.append(badge(labels[data.status], ["blocked", "unavailable"].includes(data.status) ? "bad" : ""),
    element("p", "dim", data.note));
  if (data.status === "unavailable") return panel;
  if (source === "quality-matrix") {
    panel.append(metricList([["Passed", data.summary.pass], ["Pending", data.summary.pending], ["Failed", data.summary.fail]]));
    for (const row of data.checks) {
      const item = element("details", "quality-gate"), summary = element("summary");
      summary.append(element("span", null, row.label), auditBadge(row.status));
      item.append(summary, element("p", "dim", taskRoles[row.role]), element("p", null, row.evidence),
        element("h3", null, "Next action"), element("p", null, row.next_action));
      panel.append(item);
    }
    qualityIdentity(panel, data, []);
  } else if (source === "quality-trends") {
    panel.append(element("p", null, "Live audit · " + auditStates[data.live_status][0]));
    if (data.status === "empty") panel.append(element("h3", null, "No current-specification capture"));
    else {
      panel.append(element("p", null, "Baseline audit · " + auditStates[data.baseline_status][0]),
        metricList(Object.entries(trendLabels).map(([key, label]) => [label, data.summary[key]])),
        qualityTable("Gate changes since the latest current-specification capture", ["Gate", "Baseline", "Live", "Change"],
          data.checks.map(row => [row.label, auditStates[row.baseline_status][0], auditStates[row.live_status][0], trendLabels[row.trend]])));
    }
    qualityIdentity(panel, data, [["Capture", data.baseline_id], ["History revision", data.history_revision],
      ["Earlier-specification captures excluded ·", data.historical_count]]);
  } else if (source === "specialist-analytics") {
    panel.append(qualityTable("Handoffs for the selected specification", ["Specialist", "Submitted", "Accepted", "Rejected",
      "Pending", "Work orders", "Accepted completed", "Accepted blocked", "Accepted progress", "Median review (seconds)"],
    data.roles.map(row => [taskRoles[row.role], row.submitted, row.accepted, row.rejected, row.pending, row.unique_orders,
      row.completed, row.blocked, row.progress, row.median_review_seconds ?? "No reviews"])));
    qualityIdentity(panel, data, [["Handoff revision", data.handoff_revision], ["Earlier-specification handoffs excluded ·", data.historical_count]]);
  } else {
    if (data.status === "ready") {
      const steps = element("ol", "coordination-priorities");
      for (const row of data.steps) {
        const item = element("li");
        item.append(element("h3", null, row.title), element("p", null, row.project_id + " · " + taskRoles[row.role]),
          element("p", "dim", "Priority " + row.priority + " · Board revision " + row.expected_revision),
          element("p", "dim", "Proposed action · Start task " + row.action.task_id),
          element("p", "dim", "Specification " + row.spec_sha256));
        steps.append(item);
      }
      panel.append(steps);
    }
    for (const conflict of data.conflicts) {
      const item = element("article", "task-row");
      item.append(element("h3", null, taskRoles[conflict.role]), element("p", null, "Projects · " + conflict.project_ids.join(", ")));
      panel.append(item);
    }
    qualityIdentity(panel, data, [["Cycle", data.cycle_id]]);
  }
  return panel;
}

async function renderQuality(id, routeId) {
  const active = () => state.page === "quality" && location.hash === "#quality" && state.route === routeId && state.selected === id;
  const refresh = button("Refresh quality", () => {
    if (!active() || refresh.disabled) return;
    refresh.disabled = true;
    return route();
  });
  refresh.disabled = true;
  const panels = element("div", "operations-grid quality-grid"), message = element("p", "sprint-message", "Loading quality reports…");
  message.setAttribute("role", "status");
  view.replaceChildren(heading("Quality", "Review release gates, changes since the last capture, specialist handoffs, and proposed assignments.", refresh),
    projectPicker(route), message, panels);
  const sources = Object.keys(qualityTitles);
  const results = await Promise.allSettled(sources.map(source => api(source === "dispatch-cycle" ? "/dispatch-cycle" : projectPath(id, "/" + source))));
  if (!active()) return;
  const specs = new Set();
  let mismatched = false;
  const validators = {"quality-matrix": validMatrix, "quality-trends": validTrends, "specialist-analytics": validAnalytics, "dispatch-cycle": validCycle};
  const reports = results.map((result, index) => {
    if (result.status === "rejected") return {error: result.reason.message};
    const data = result.value, source = sources[index];
    if (!data || !coordinationText(data.note)) return {error: "The report could not be verified."};
    if (source !== "dispatch-cycle") {
      if (data.project_id !== id && !(data.status === "unavailable" && data.project_id === null)) mismatched = true;
      if (isDigest(data.spec_sha256)) specs.add(data.spec_sha256);
      else if (data.status !== "unavailable" || data.spec_sha256 !== null) return {error: "The report specification could not be verified."};
    }
    if (!validators[source](data, state.projects)) return {error: "The report could not be verified."};
    if (source === "dispatch-cycle") {
      for (const step of data.steps) if (step.project_id === id) specs.add(step.spec_sha256);
    }
    return {data};
  });
  const inconsistent = mismatched || specs.size > 1;
  reports.forEach(({data, error}, index) => {
    const source = sources[index];
    if (inconsistent) error = "Refresh to verify this report against the selected project.";
    panels.append(error ? box(qualityTitles[source] + " unavailable", error, null, "panel team-brief orchestration") : qualityPanel(source, data));
  });
  const partial = reports.some(report => report.error || report.data.status === "unavailable");
  message.textContent = inconsistent ? "Project reports disagree. Refresh quality to load a consistent snapshot."
    : partial ? "Some quality reports are unavailable." : "Quality reports refreshed.";
  refresh.disabled = false;
}

function validCurriculum(data) {
  if (![1, 2, 3, 4].includes(data?.version) || !isDigest(data.curriculum_sha256) || !coordinationText(data.note)
    || !Array.isArray(data.tracks) || !data.tracks.length) return false;
  return new Set(data.tracks.map(track => track?.id)).size === data.tracks.length && data.tracks.every(track =>
    coordinationText(track?.id) && coordinationText(track.title) && coordinationText(track.exercise)
    && Array.isArray(track.roles) && track.roles.length > 0 && track.roles.every(coordinationRole)
    && new Set(track.roles).size === track.roles.length && ["workflow", "deliverables", "verification"].every(key =>
      Array.isArray(track[key]) && track[key].length > 0 && track[key].every(coordinationText)));
}

function trainingTrack(track) {
  const panel = supervisorPanel(track.title), roles = element("div", "actions"), details = element("details", "training-lesson");
  for (const role of track.roles) roles.append(badge(taskRoles[role]));
  details.append(element("summary", null, "Read playbook"));
  for (const [key, title] of [["workflow", "Workflow"], ["deliverables", "Deliverables"], ["verification", "Verification"]]) {
    const list = element(key === "workflow" ? "ol" : "ul", "task-suggestions");
    for (const item of track[key]) list.append(element("li", null, item));
    details.append(element("h3", null, title), list);
  }
  details.append(element("h3", null, "Practice exercise"), element("p", null, track.exercise));
  panel.append(roles, details);
  return panel;
}

function renderTraining(data) {
  if (!validCurriculum(data)) {
    view.replaceChildren(heading("Training", "Game production playbooks for the specialist team."),
      box("Training unavailable", "The curriculum could not be verified.", button("Reload training", route)));
    return;
  }
  const controls = element("div", "workspace-tools"), label = element("label", null, "Specialist role");
  const select = element("select"), all = element("option", null, "All specialists");
  select.id = "training-role";
  label.htmlFor = select.id;
  all.value = "";
  select.append(all);
  for (const [id, title] of Object.entries(taskRoles)) {
    const option = element("option", null, title);
    option.value = id;
    select.append(option);
  }
  select.value = "";
  controls.append(label, select);
  const count = element("p", "dim training-count"), tracks = element("div", "operations-grid");
  count.setAttribute("role", "status");
  function filter() {
    const selected = data.tracks.filter(track => !select.value || track.roles.includes(select.value));
    tracks.replaceChildren(...selected.map(trainingTrack));
    count.textContent = selected.length + (selected.length === 1 ? " playbook" : " playbooks");
  }
  filter();
  select.addEventListener("change", filter);
  const identity = element("details", "training-identity");
  identity.append(element("summary", null, "Curriculum version " + data.version), element("p", "dim", "Curriculum " + data.curriculum_sha256));
  view.replaceChildren(heading("Training", data.note), controls, count, tracks, identity);
}

function labObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

const artifactStatuses = ["pass", "fail", "unavailable"];

function validArtifactReport(report) {
  if (!labObject(report) || !coordinationText(report.profile) || !artifactStatuses.includes(report.status)
    || !(isDigest(report.sha256) || report.status === "unavailable" && report.sha256 === null)
    || !coordinationText(report.note) || !labObject(report.measurements) || !Array.isArray(report.checks)) return false;
  const value = item => typeof item === "string" || typeof item === "boolean" || Number.isFinite(item);
  const ids = new Set();
  for (const check of report.checks) {
    if (!coordinationText(check?.id) || ids.has(check.id) || !artifactStatuses.includes(check.status)
      || !value(check.measured) || !value(check.limit)) return false;
    ids.add(check.id);
  }
  if (report.status === "pass" && (!report.checks.length || report.checks.some(check => check.status !== "pass"))) return false;
  if (report.status === "fail" && !report.checks.some(check => check.status === "fail")) return false;
  if (!Object.hasOwn(report, "reports")) return true;
  const parts = report.reports;
  if (!Array.isArray(parts) || !parts.length || parts.length > report.checks.length) return false;
  for (const [index, part] of parts.entries()) {
    if (!labObject(part) || Object.hasOwn(part, "reports") || !validArtifactReport(part)) return false;
    const check = report.checks[index];
    if (check.status !== part.status || check.measured !== part.status || check.limit !== "pass") return false;
  }
  const digest = parts.every(part => part.sha256 === parts[0].sha256) ? parts[0].sha256 : null;
  if (report.sha256 !== digest) return false;
  if (digest === null) return report.status === "unavailable";
  if (report.checks.some(check => check.status === "fail")) return report.status === "fail";
  const unavailable = report.checks.some(check => check.status === "unavailable");
  return report.status === (unavailable ? "unavailable" : "pass");
}

function artifactReportContents(report) {
  const body = element("div", "lab-artifact-result");
  const header = element("div", "task-heading");
  header.append(element("h3", null, report.profile), auditBadge(report.status));
  const identity = element("dl", "checkpoint-facts");
  identity.append(element("dt", null, "Reported file SHA-256"), element("dd", null, report.sha256 ?? "Unavailable"));
  body.append(header, identity, element("p", null, report.note));
  if (report.checks.length) {
    const wrap = element("div", "quality-table-wrap"), table = element("table", "sample-table");
    const head = element("thead"), row = element("tr"), rows = element("tbody");
    for (const label of ["Check", "Measured", "Limit", "Reported status"]) {
      const cell = element("th", null, label);
      cell.scope = "col";
      row.append(cell);
    }
    head.append(row);
    for (const check of report.checks) {
      const line = element("tr"), name = element("th", null, check.id);
      name.scope = "row";
      line.append(name, element("td", null, String(check.measured)), element("td", null, String(check.limit)),
        element("td", null, check.status));
      rows.append(line);
    }
    table.append(element("caption", null, "Reported checks"), head, rows);
    wrap.append(table);
    body.append(wrap);
  }
  const measurements = Object.entries(report.measurements);
  if (measurements.length) {
    const details = element("details"), facts = element("dl", "checkpoint-facts");
    for (const [name, measured] of measurements) {
      facts.append(element("dt", null, name), element("dd", null, typeof measured === "string" ? measured : JSON.stringify(measured)));
    }
    details.append(element("summary", null, "All measurements"), facts);
    body.append(details);
  }
  for (const component of report.reports || []) {
    const details = element("details");
    details.append(element("summary", null, component.profile + " · " + component.status), artifactReportContents(component));
    body.append(details);
  }
  return body;
}

function labArtifactViewer(active) {
  const panel = supervisorPanel("Local artifact report");
  panel.className += " lab-artifact";
  const guide = element("details");
  guide.append(element("summary", null, "Create a report from the command line"),
    element("p", "dim", "Run one command from the Studio directory. Replace the asset path and save the JSON outside the checkout. The character profile checks the rig and animations. Add --engine to include the Godot import check."),
    element("pre", "log", [
      "python3 -m command_center.artifact_pipeline --profile static prop.glb > ../prop-report.json",
      "python3 -m command_center.artifact_pipeline --profile character --engine character.glb > ../character-report.json",
      "python3 -m command_center.artifact_pipeline --profile texture texture.png > ../texture-report.json"
    ].join("\n")));
  const picker = element("input"), label = element("label", null, "Open a report JSON file (up to 512 KiB)");
  picker.id = "lab-artifact-file";
  picker.type = "file";
  picker.accept = ".json,application/json";
  label.htmlFor = picker.id;
  const status = element("p", "dim"), result = element("div");
  status.id = "lab-artifact-status";
  status.setAttribute("role", "status");
  picker.setAttribute("aria-describedby", status.id);
  let selection = 0;
  picker.addEventListener("change", async () => {
    if (!active()) return;
    const chosen = ++selection, file = picker.files[0];
    const current = () => active() && chosen === selection;
    result.replaceChildren();
    picker.removeAttribute("aria-invalid");
    status.textContent = "";
    if (!file) return;
    if (file.size > 512 * 1024) {
      picker.setAttribute("aria-invalid", "true");
      status.textContent = "Choose a report of 512 KiB or less.";
      return;
    }
    status.textContent = "Reading report…";
    try {
      const source = await file.text();
      if (!current()) return;
      const report = JSON.parse(source, (key, value) => {
        if (typeof value === "number" && !Number.isFinite(value)) throw new Error("Non-finite measurement");
        return value;
      });
      if (!validArtifactReport(report)) throw new Error("Invalid report");
      result.append(artifactReportContents(report));
      status.textContent = "Local report opened.";
    } catch {
      if (!current()) return;
      picker.setAttribute("aria-invalid", "true");
      status.textContent = "Could not read an artifact report. Choose a JSON report generated by the inspection CLI.";
    }
  });
  panel.append(element("p", "dim", "The selected file stays in this tab. Anyone can edit report values and hashes. Release approval requires independent verification."),
    guide, label, picker, status, result);
  return panel;
}

function validLab(data) {
  if (![1, 2, 3, 4].includes(data?.version) || !isDigest(data.lab_sha256) || !coordinationText(data.note)
    || !Array.isArray(data.exercises) || !data.exercises.length) return false;
  const uniqueIds = rows => new Set(rows.map(row => row?.id)).size === rows.length;
  return uniqueIds(data.exercises) && data.exercises.every(exercise =>
    coordinationText(exercise?.id) && coordinationText(exercise.title) && coordinationText(exercise.brief)
    && labObject(exercise.example) && Array.isArray(exercise.roles) && exercise.roles.length > 0
    && exercise.roles.every(coordinationRole) && Array.isArray(exercise.criteria) && exercise.criteria.length > 0
    && uniqueIds(exercise.criteria) && exercise.criteria.every(row => coordinationText(row?.id) && coordinationText(row.label)));
}

function validPracticeReport(report) {
  if (!Number.isSafeInteger(report?.version) || report.version < 1 || !isDigest(report.lab_sha256)
    || !coordinationText(report.exercise_id) || !isDigest(report.submission_sha256) || !isDigest(report.assessment_sha256)
    || !coordinationText(report.note) || !Array.isArray(report.checks) || !report.checks.length) return false;
  const ids = new Set();
  let passed = 0;
  for (const check of report.checks) {
    if (!coordinationText(check?.id) || ids.has(check.id) || !coordinationText(check.label) || !coordinationText(check.detail)
      || !["pass", "fail"].includes(check.status)) return false;
    ids.add(check.id);
    if (check.status === "pass") passed++;
  }
  const failed = report.checks.length - passed;
  return report.summary?.pass === passed && report.summary.fail === failed && report.status === (failed ? "fail" : "pass");
}

function matchesLabRubric(report, lab, exercise) {
  return report.version === lab.version && report.lab_sha256 === lab.lab_sha256 && report.exercise_id === exercise.id
    && report.checks.length === exercise.criteria.length && report.checks.every((check, i) =>
      check.id === exercise.criteria[i].id && check.label === exercise.criteria[i].label);
}

function validLabAssessment(report, lab, exercise) {
  return validPracticeReport(report) && matchesLabRubric(report, lab, exercise);
}

const labReviewerRoles = {lead: "Studio lead", ...taskRoles};
const practiceDecisions = {accepted: "Accepted", rejected: "Rejected"};

function validTrainingRecords(data, lab) {
  if (!isRevision(data?.revision) || data.lab_sha256 !== lab.lab_sha256 || !coordinationText(data.note)
    || !Array.isArray(data.records)) return false;
  const ids = new Set();
  let expectedRevision = data.records.length, previousTime = Infinity;
  return data.records.every(row => {
    const created = typeof row?.created_at === "string" ? Date.parse(row.created_at) : NaN;
    if (typeof row?.id !== "string" || !/^[a-f0-9]{32}$/.test(row.id) || ids.has(row.id) || !coordinationRole(row.role)
      || !Number.isFinite(created) || created > previousTime || typeof row.reference !== "boolean" || !labObject(row.submission)
      || !validPracticeReport(row.report) || row.exercise_id !== row.report.exercise_id
      || row.current !== (row.report.lab_sha256 === lab.lab_sha256)) return false;
    ids.add(row.id);
    previousTime = created;
    const exercise = lab.exercises.find(item => item.id === row.exercise_id);
    if (row.current && (!exercise?.roles.includes(row.role) || !matchesLabRubric(row.report, lab, exercise))) return false;
    const review = row.review;
    if (review === null) return true;
    expectedRevision++;
    return labObject(review) && coordinationText(review.reviewer_role) && Object.hasOwn(labReviewerRoles, review.reviewer_role)
      && review.reviewer_role !== row.role && coordinationText(review.decision) && Object.hasOwn(practiceDecisions, review.decision)
      && coordinationText(review.note) && [...review.note].length <= 512 && typeof review.reviewed_at === "string"
      && Date.parse(review.reviewed_at) >= created && (review.decision !== "accepted" || (!row.reference && row.report.status === "pass"));
  }) && data.revision === expectedRevision;
}

function labAssessmentPanel(report, download) {
  const panel = supervisorPanel("Assessment results");
  panel.append(auditBadge(report.status), element("p", null, report.note));
  for (const check of report.checks) {
    const row = element("div", "task-row"), title = element("div", "task-heading");
    title.append(element("h3", null, check.label), auditBadge(check.status));
    row.append(title, element("p", null, check.detail));
    panel.append(row);
  }
  const identity = element("details");
  identity.append(element("summary", null, "Assessment identity"), element("p", "dim", "Lab SHA-256 · " + report.lab_sha256),
    element("p", "dim", "Submission SHA-256 · " + report.submission_sha256),
    element("p", "dim", "Assessment SHA-256 · " + report.assessment_sha256));
  panel.append(identity, button("Download assessment JSON", download));
  return panel;
}

function labHistory(lab, active) {
  const panel = supervisorPanel("Private practice history"), message = element("p", "sprint-message");
  const body = element("div", "lab-history-body");
  const refresh = button("Refresh history", () => update());
  message.setAttribute("role", "status");
  panel.append(refresh, message, body);
  const reviewDrafts = new Map();
  let snapshot = null, selectedId = null, busy = false;
  let syncReview = null, syncRecord = null;

  function lock(value) {
    busy = value;
    refresh.disabled = busy;
    if (syncReview) syncReview();
    if (syncRecord) syncRecord();
  }

  async function update(rawAction, confirmChange) {
    if (!active() || busy || (rawAction && !snapshot)) return;
    const previous = snapshot;
    lock(true);
    message.textContent = rawAction ? "Saving…" : "Loading history…";
    try {
      let data;
      if (rawAction) {
        const request = '{"expected_revision":' + previous.revision + ',"action":' + rawAction + '}';
        data = await apiWithJsonBody("/training-records", "POST", request);
      } else data = await api("/training-records");
      if (!active()) return;
      if (!validTrainingRecords(data, lab)) throw new Error("The practice history could not be verified.");
      if (rawAction && (data.revision !== previous.revision + 1 || !confirmChange(data, previous))) {
        throw new Error("The saved change could not be verified. Refresh history before trying again.");
      }
      snapshot = data;
      message.textContent = rawAction ? "Saved to private practice history." : "";
    } catch (error) {
      if (!active()) return;
      snapshot = null;
      message.textContent = error.message;
      if (rawAction && error.status === 409) {
        try {
          const latest = await api("/training-records");
          if (!active()) return;
          if (!validTrainingRecords(latest, lab)) throw new Error("The practice history could not be verified.");
          snapshot = latest;
          message.textContent = error.message + " History refreshed. Check the saved evidence or reassess your draft before submitting again.";
        } catch (failure) {
          if (active()) message.textContent = failure.message;
        }
      }
    } finally {
      if (active()) {
        renderHistory();
        lock(false);
      }
    }
  }

  function reviewFields(target, record) {
    const draft = reviewDrafts.get(record.id) || {role: "", decision: "", note: ""};
    const fields = element("div", "checkpoint-fields");
    const roles = {...labReviewerRoles};
    delete roles[record.role];
    const choices = {"": "Choose a decision"};
    if (!record.reference && record.report.status === "pass") choices.accepted = "Accept";
    choices.rejected = "Reject";
    const role = taskField(fields, "reviewer_role", "Reviewer role", {id: "lab-reviewer", value: draft.role}, {"": "Choose a reviewer role", ...roles});
    const decision = taskField(fields, "decision", "Review decision", {id: "lab-decision", value: draft.decision}, choices);
    const note = taskField(fields, "note", "Review note (up to 512 characters)", {id: "lab-review-note", value: draft.note, rows: 3});
    const bound = snapshot;
    const valid = () => active() && !busy && snapshot === bound && selectedId === record.id
      && Object.hasOwn(roles, role.value) && decision.value && Object.hasOwn(choices, decision.value)
      && note.value.trim().length > 0 && [...note.value].length <= 512;
    const save = button("Save review", () => {
      if (!valid() || syncReview !== sync) return;
      const action = {op: "review", record_id: record.id, reviewer_role: role.value, decision: decision.value, note: note.value.trim()};
      return update(JSON.stringify(action), data => {
        const review = data.records.find(row => row.id === record.id)?.review;
        if (review?.reviewer_role !== action.reviewer_role || review.decision !== action.decision || review.note !== action.note) return false;
        reviewDrafts.delete(record.id);
        return true;
      });
    });
    function sync() {
      save.disabled = !valid();
      role.disabled = decision.disabled = note.disabled = busy;
    }
    function edited() {
      if (syncReview !== sync || !active() || busy) return;
      reviewDrafts.set(record.id, {role: role.value, decision: decision.value, note: note.value});
      sync();
    }
    role.addEventListener("change", edited);
    decision.addEventListener("change", edited);
    note.addEventListener("input", edited);
    fields.append(save);
    target.append(fields);
    syncReview = sync;
    sync();
  }

  function renderHistory() {
    syncReview = null;
    body.replaceChildren();
    if (!snapshot) {
      body.append(element("h3", null, "History unavailable"));
      return;
    }
    body.append(element("p", "dim", snapshot.note));
    if (!snapshot.records.length) {
      body.append(element("p", null, "No practice submissions recorded."));
      return;
    }
    const record = snapshot.records.find(row => row.id === selectedId) || snapshot.records[0];
    selectedId = record.id;
    const titles = new Map(lab.exercises.map(exercise => [exercise.id, exercise.title]));
    const options = Object.fromEntries(snapshot.records.map(row => [row.id,
      (titles.get(row.exercise_id) || row.exercise_id) + " · " + taskRoles[row.role] + " · " + row.created_at + " · " + row.id.slice(-8)]));
    const picker = taskField(body, "record_id", "Recorded submission (newest first)", {id: "lab-history-record", value: selectedId}, options);
    picker.addEventListener("change", () => {
      if (!active() || busy) { picker.value = selectedId; return; }
      selectedId = picker.value;
      renderHistory();
    });
    const tags = element("div", "actions");
    tags.append(auditBadge(record.report.status), badge(record.current ? "Current catalog" : "Historical catalog"));
    tags.append(badge(record.reference ? "Reference example" : "Non-reference submission"));
    tags.append(badge(record.review ? practiceDecisions[record.review.decision] : record.current ? "Pending review" : "Unreviewed"));
    body.append(tags);
    const details = element("details"), contents = element("div");
    details.append(element("summary", null, "Inspect submission and rubric results"), contents);
    details.addEventListener("toggle", () => {
      if (!active() || !details.open || contents.children.length) return;
      for (const check of record.report.checks) {
        contents.append(element("h4", null, check.label + " · " + check.status), element("p", null, check.detail));
      }
      contents.append(element("p", "dim", "Lab SHA-256 · " + record.report.lab_sha256),
        element("p", "dim", "Submission SHA-256 · " + record.report.submission_sha256),
        element("p", "dim", "Assessment SHA-256 · " + record.report.assessment_sha256),
        element("pre", "log", JSON.stringify(record.submission, null, 2)));
    });
    body.append(details);
    if (record.review) {
      body.append(element("p", "dim", labReviewerRoles[record.review.reviewer_role] + " · " + record.review.reviewed_at),
        element("p", null, record.review.note));
    } else if (record.current) reviewFields(body, record);
  }

  function recordFields(exercise, source, report, current) {
    const fields = element("div", "checkpoint-fields");
    const options = Object.fromEntries(exercise.roles.map(id => [id, taskRoles[id]]));
    const role = taskField(fields, "role", "Submitting role", {id: "lab-record-role", value: ""}, {"": "Choose a submitting role", ...options});
    let saved = false;
    const enabled = () => active() && current() && syncRecord === sync && snapshot && !busy && !saved && Object.hasOwn(options, role.value);
    const record = button("Record assessed submission", () => {
      if (!enabled()) return;
      const roleId = role.value;
      // Embed the unmodified assessed text so repeated fields and numeric literals reach the strict decoder.
      const action = '{"op":"record","exercise_id":' + JSON.stringify(exercise.id)
        + ',"role":' + JSON.stringify(roleId) + ',"expected_assessment_sha256":' + JSON.stringify(report.assessment_sha256)
        + ',"submission":' + source + '}';
      return update(action, (data, previous) => {
        const row = data.records[0];
        if (!row?.current || row.role !== roleId || row.exercise_id !== exercise.id || row.review !== null
          || previous.records.some(old => old.id === row.id) || row.report.assessment_sha256 !== report.assessment_sha256
          || row.report.submission_sha256 !== report.submission_sha256) return false;
        saved = true;
        selectedId = row.id;
        return true;
      });
    });
    function sync() {
      record.disabled = !enabled();
      role.disabled = busy || saved || !snapshot;
    }
    syncRecord = sync;
    role.addEventListener("change", sync);
    fields.append(record);
    sync();
    return fields;
  }
  return {panel, refresh: () => update(), recordFields, clearAssessment() { syncRecord = null; }};
}

function renderLab(lab, routeId) {
  if (!validLab(lab)) {
    view.replaceChildren(heading("Lab", "Practice game production exercises."),
      box("Lab unavailable", "The exercise catalog could not be verified.", button("Reload lab", route)));
    return;
  }
  const active = () => state.route === routeId && state.page === "lab" && location.hash === "#lab";
  const controls = element("div", "workspace-tools"), selector = element("select");
  const label = element("label", null, "Exercise");
  selector.id = "lab-exercise";
  label.htmlFor = selector.id;
  for (const exercise of lab.exercises) {
    const option = element("option", null, exercise.title);
    option.value = exercise.id;
    selector.append(option);
  }
  controls.append(label, selector);
  const workspace = element("div", "operations-grid lab-workspace");
  const status = element("p", "sprint-message"), result = element("div");
  status.setAttribute("role", "status");
  const drafts = new Map();
  const history = labHistory(lab, active);
  let revision = 0;

  function showExercise() {
    const exercise = lab.exercises.find(item => item.id === selector.value);
    if (!exercise || !active()) return;
    revision++;
    history.clearAssessment();
    status.textContent = "";
    result.replaceChildren();
    const brief = supervisorPanel(exercise.title), roles = element("div", "actions");
    for (const role of exercise.roles) roles.append(badge(taskRoles[role]));
    const example = JSON.stringify(exercise.example, null, 2), preview = element("details");
    preview.append(element("summary", null, "Example JSON"), element("pre", "log lab-example", example));
    brief.append(element("p", null, exercise.brief), roles, element("h3", null, "Criteria"),
      evidenceList(exercise.criteria.map(row => row.label)), preview);
    if (exercise.id === "cutscenes") {
      const production = element("details");
      production.append(element("summary", null, "Run a real Godot cutscene"),
        element("p", "dim", "The Lab checks your edit plan as data. The separate local production runner uses that plan with camera and actor bindings to create a playable Godot project and test playback and handoff. Try the bundled production example from the Studio source directory:"),
        element("pre", "log", "python3 -m cinematic.production.runner cinematic/production/examples/nightfall_plan.json cinematic/production/examples/nightfall_bindings.json --output ../nightfall-production --engine"),
        element("p", "dim", "Keep the output outside the checkout. Runtime checks do not assess picture quality or recorded dialogue; the sample uses placeholder sound. The dashboard never launches the engine or records this as practice evidence."));
      brief.append(production);
    }
    if (["player-enjoyment", "replayability", "player-research", "visual-direction",
      "visual-readability", "experience-iteration"].includes(exercise.id)) {
      const guide = element("details");
      guide.append(element("summary", null, "Apply this to a real game"),
        element("p", null, "Choose the audience, intended experience, platform and exact build. Test a concrete hypothesis, compare observations against a baseline, and check for regression or unintended tradeoffs."),
        element("p", "dim", "The Lab measures structured practice only. Record real player reactions only with consent and separately from simulated data. Review actual gameplay visuals and responsiveness on target devices; no rubric can certify fun or artistic quality. See command_center/PLAYER_EXPERIENCE.md."));
      brief.append(guide);
    }

    if (["motion-design", "character-performance", "environmental-storytelling", "diegetic-narrative",
      "voice-direction", "voice-integration"].includes(exercise.id)) {
      const guide = element("details");
      guide.append(element("summary", null, "From practice to performance review"),
        element("p", null, "Study documented game-production techniques, then design an original scene. Inspect gameplay camera motion, contact, visible and audible cues, alternate paths, and speech timing in the exact build."),
        element("p", "dim", "Structured checks do not verify actual animation quality, story comprehension or audible performance. Use only authorized recordings and assets; no audio uploads or voice imitation. See command_center/STORY_AND_PERFORMANCE.md."));
      brief.append(guide);
    }

    const form = element("form", "panel team-brief orchestration lab-form");
    const input = element("textarea"), inputLabel = element("label", null, "Submission JSON");
    input.id = "lab-submission";
    inputLabel.htmlFor = input.id;
    input.rows = 12;
    input.required = true;
    input.spellcheck = false;
    input.value = drafts.get(exercise.id) || "";
    const error = element("p", "error");
    error.id = "lab-error";
    error.setAttribute("role", "alert");
    input.setAttribute("aria-describedby", error.id);
    const assess = element("button", "primary", "Assess submission");
    assess.type = "submit";
    const selected = () => active() && selector.value === exercise.id;
    function edited() {
      if (!selected()) return;
      drafts.set(exercise.id, input.value);
      revision++;
      history.clearAssessment();
      assess.disabled = false;
      status.textContent = "";
      error.textContent = "";
      input.removeAttribute("aria-invalid");
      result.replaceChildren();
    }
    input.addEventListener("input", edited);
    const useExample = button("Use example", () => {
      if (!selected()) return;
      input.value = example;
      edited();
      input.focus();
    });
    const actions = element("div", "actions");
    actions.append(useExample, assess);
    form.append(element("h2", null, "Your submission"), inputLabel, input, error, actions);
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (!selected() || assess.disabled) return;
      const source = input.value;
      try {
        const submission = JSON.parse(source, (key, value) => {
          if (typeof value === "number" && !Number.isFinite(value)) throw new RangeError("Non-finite number");
          return value;
        });
        if (!labObject(submission)) throw new TypeError("Expected an object");
      } catch {
        error.textContent = "Enter a JSON object with valid syntax and finite numbers.";
        input.setAttribute("aria-invalid", "true");
        input.focus();
        return;
      }
      const requestId = ++revision;
      const current = () => selected() && requestId === revision && source === input.value;
      history.clearAssessment();
      assess.disabled = true;
      error.textContent = "";
      input.removeAttribute("aria-invalid");
      status.textContent = "Checking submission…";
      result.replaceChildren();
      try {
        // Keep repeated keys and numeric literals intact for the server's JSON validator.
        const body = '{"exercise_id":' + JSON.stringify(exercise.id) + ',"submission":' + source + '}';
        const {data: report, raw} = await apiWithJsonBody("/training-lab/assess", "POST", body, true);
        if (!current()) return;
        if (!validLabAssessment(report, lab, exercise)) throw new Error("The assessment could not be matched to this exercise.");
        const panel = labAssessmentPanel(report, () => {
          if (current()) downloadJson(raw, "assessment-" + report.assessment_sha256 + ".json");
        });
        panel.append(history.recordFields(exercise, source, report, current));
        result.replaceChildren(panel);
        status.textContent = report.summary.pass + " passed · " + report.summary.fail + " failed";
      } catch (failure) {
        if (!current()) return;
        status.textContent = "";
        error.textContent = failure.message;
        if (failure.status === 400) input.setAttribute("aria-invalid", "true");
      } finally {
        if (current()) assess.disabled = false;
      }
    });
    workspace.replaceChildren(brief, form);
  }
  selector.value = lab.exercises[0].id;
  selector.addEventListener("change", showExercise);
  view.replaceChildren(heading("Lab", "Assess structured submissions against the exercise rubric. Record an assessment explicitly to keep it in private practice history."),
    controls, workspace, status, result, history.panel, labArtifactViewer(active));
  showExercise();
  return history.refresh();
}

function renderPortfolio(portfolio) {
  view.replaceChildren(heading("Portfolio", "Review task boards and available specialist roles across projects.",
    button("Refresh portfolio", route)));
  const {projects, summary, occupied_roles: occupied, assignments, conflicts} = portfolio;
  if (!projects.length) {
    view.append(box("No projects yet", "Create a project to start its task board.", button("View projects", () => navigate("projects"))));
    return;
  }
  const names = new Map(projects.map(project => [project.project_id, project.name]));
  const sections = element("div", "queue");
  const overview = element("section", "panel team-brief orchestration");
  overview.append(element("h2", null, "Portfolio overview"));
  const counts = element("dl", "task-counts");
  for (const [key, label] of Object.entries({projects: "Projects", current: "Current", stale: "Stale", empty: "Empty",
    unavailable: "Unavailable", running: "Running tasks", ready: "Ready tasks"})) {
    const pair = element("div");
    pair.append(element("dt", null, label), element("dd", null, summary[key]));
    counts.append(pair);
  }
  overview.append(counts, element("p", "dim", `Occupied roles · ${occupied.map(role => taskRoles[role] || role).join(", ") || "None"}`));
  for (const conflict of conflicts) {
    overview.append(element("p", "checkpoint-warning",
      `${taskRoles[conflict.role] || conflict.role} has overlapping work in ${conflict.project_ids.map(id => names.get(id) || id).join(", ")}.`));
  }
  sections.append(overview);

  const suggestions = element("section", "panel team-brief orchestration");
  suggestions.append(element("h2", null, "Recommended assignments"));
  if (assignments.length) {
    suggestions.append(element("p", "dim", "Review the board revision and claim the task on its project board before dispatch."));
    for (const item of assignments) {
      const row = element("article", "task-row");
      row.append(element("h3", null, item.title),
        element("p", null, `${names.get(item.project_id) || item.project_id} · ${taskRoles[item.role] || item.role} · Priority ${item.priority}`),
        element("p", "dim", `${item.model_id} · ${item.reasoning_effort} effort · Board revision ${item.board_revision}`),
        element("p", "dim", `Task ${item.task_id} · Specification ${item.spec_sha256}`));
      suggestions.append(row);
    }
    const routeId = state.route;
    const error = element("p", "error");
    error.setAttribute("role", "alert");
    const exportPlan = button("Download portfolio dispatch JSON", async () => {
      if (state.route !== routeId || exportPlan.disabled) return;
      exportPlan.disabled = true;
      error.textContent = "";
      try {
        const fresh = await api("/portfolio");
        if (state.route !== routeId) return;
        if (JSON.stringify(fresh.assignments) !== JSON.stringify(assignments)) {
          throw new Error("Recommendations have changed. Refresh the portfolio before exporting.");
        }
        if (fresh.dispatch_plan?.execution_mode !== "export_only" ||
            fresh.dispatch_plan.spawn_args?.length !== assignments.length) {
          throw new Error("Portfolio dispatch plan unavailable.");
        }
        downloadJson(`${JSON.stringify(fresh.dispatch_plan, null, 2)}\n`, "portfolio-dispatch.json");
      } catch (failure) {
        if (state.route === routeId) error.textContent = failure.message;
      } finally {
        exportPlan.disabled = false;
      }
    });
    const controls = element("div", "actions");
    controls.append(exportPlan);
    suggestions.append(controls, error);
  } else {
    suggestions.append(element("p", "dim", summary.unavailable
      ? "Recommendations are paused until all project boards are readable."
      : "No ready tasks can be assigned to an available role."));
  }
  sections.append(suggestions);

  const boards = element("section", "panel team-brief orchestration");
  boards.append(element("h2", null, "Project boards"));
  for (const project of projects) {
    const row = element("article", "task-row");
    const header = element("div", "task-heading");
    header.append(element("h3", null, project.name), badge(project.state, project.state === "current" ? "good" : ""));
    row.append(header);
    if (project.summary) {
      row.append(element("p", "dim", `Revision ${project.revision} · ${project.summary.total} tasks · ${project.summary.ready} ready · ${project.summary.running} running`),
        element("p", "dim", `Specification · ${project.spec_sha256}`));
    }
    if (project.state === "stale") row.append(element("p", "dim", "Review the previous specification on the project board."));
    if (project.state === "unavailable") row.append(element("p", "error", project.error || "Project board could not be read."));
    const actions = element("div", "actions");
    actions.append(button("Open project board", () => {
      state.selected = project.project_id;
      navigate("team");
    }));
    row.append(actions); boards.append(row);
  }
  sections.append(boards); view.append(sections);
}

function renderTeam(team, project, checkpointPanel, taskPanel) {
  view.append(heading("Team", `${team.dispatch_plan?.profile?.team_name || "Specialist team"} · roles and review gates for ${project.name}.`), projectPicker(route));
  const overview = element("div", "queue");
  overview.append(taskPanel, checkpointPanel);
  if (team.dispatch_plan) overview.append(renderDispatchPlan(team.dispatch_plan));
  if (typeof team.brief === "string" && team.brief) {
    overview.append(box("Project brief", team.brief, null, "panel team-brief"));
  }
  view.append(overview);
  const rolesHeading = element("div", "section-top");
  rolesHeading.append(element("h2", null, "Planned roles"));
  const roles = element("div", "cards");
  for (const role of team.roles || []) {
    const card = element("article", "card");
    card.append(element("h3", null, taskRoles[role.id] || role.name), badge(role.model), element("p", "dim", role.task));
    roles.append(card);
  }
  const gatesHeading = element("div", "section-top");
  gatesHeading.append(element("h2", null, "Review gates"));
  const gates = element("div", "cards");
  for (const gate of team.gates || []) {
    const card = element("article", "card");
    const tone = /passed|verified|complete/i.test(gate.status) ? "good" : /failed|blocked/i.test(gate.status) ? "bad" : "";
    card.append(element("h3", null, gate.name), badge(gate.status, tone));
    gates.append(card);
  }
  view.append(rolesHeading, roles, gatesHeading, gates);
}

async function route() {
  const target = location.hash.slice(1);
  const page = Object.hasOwn(titles, target) ? target : "projects";
  const routeId = ++state.route;
  state.page = page;
  for (const link of document.querySelectorAll("[data-page]")) {
    if (link.dataset.page === page) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  document.querySelector("#location").textContent = titles[page];
  document.title = `${titles[page]} · Graveforge Studios Command Center`;
  view.replaceChildren(heading(titles[page], "Loading workstation data…"));
  view.setAttribute("aria-busy", "true");
  try {
    if (page === "lab") {
      const lab = await api("/training-lab");
      if (routeId === state.route && location.hash === "#lab") await renderLab(lab, routeId);
      return;
    }
    if (page === "training") {
      const curriculum = await api("/training");
      if (routeId === state.route) renderTraining(curriculum);
      return;
    }
    if (page !== "catalog" && page !== "portfolio") {
      const projects = await api("/projects");
      if (routeId !== state.route) return;
      state.projects = projects;
      if (!projects.some(project => project.id === state.selected)) state.selected = projects[0]?.id ?? null;
    }
    if (page === "catalog") {
      const catalog = await api("/catalog");
      if (routeId === state.route) renderCatalog(catalog);
      return;
    }
    if (page === "portfolio") {
      const portfolio = await api("/portfolio");
      if (routeId === state.route) renderPortfolio(portfolio);
      return;
    }
    if (page === "builds") {
      view.replaceChildren();
      renderBuilds();
      await refreshJobs(true);
      return;
    }
    if (page === "releases" && state.selected) {
      const id = state.selected;
      const [registry, jobs, legacy] = await Promise.allSettled([
        api(projectPath(id, "/releases")), api("/jobs"), api(`/release/${encodeURIComponent(id)}`)
      ]);
      if (routeId !== state.route) return;
      view.replaceChildren(heading("Releases", "Promote a verified build or activate a previous release for the saved specification.",
        button("Refresh releases", route)), projectPicker(route));
      if (registry.status === "fulfilled" && registry.value.project_id === id) {
        view.append(renderReleases(registry.value, jobs, legacy, routeId));
      } else {
        const reason = registry.status === "rejected" ? registry.reason.message : "Received releases for a different project.";
        view.append(box("Release registry unavailable", reason));
      }
      return;
    }
    if (page === "projects") {
      view.replaceChildren();
      renderProjects();
      return;
    }
    if (page === "quality" && !state.selected) {
      view.replaceChildren(heading("Quality", "Review project quality and workspace dispatch proposals."),
        box("No projects yet", "Quality reports will appear after the first project is created."));
      return;
    }
    if (page === "coordination" && !state.selected) {
      view.replaceChildren(heading("Coordination", "Project advice and shared specialist availability."),
        box("No projects yet", "Coordination reports will appear after the first project is created."));
      return;
    }
    if (!state.selected) {
      view.replaceChildren(heading(titles[page], "Choose a project to continue."),
        box("A project is required", "Create a project to open its workspace and review its team.",
          button("Create project", openCreate, "primary")));
      return;
    }
    const id = state.selected;
    if (page === "workspace") {
      const project = await api(projectPath(id));
      if (routeId !== state.route) return;
      state.project = project;
      view.replaceChildren();
      renderWorkspace(project);
    } else if (page === "supervisor") {
      await renderSupervisor(id, routeId);
    } else if (page === "planning") {
      await renderPlanning(id, routeId);
    } else if (page === "sprint") {
      await renderSprint(id, routeId);
    } else if (page === "operations") {
      await renderOperations(id, routeId);
    } else if (page === "quality") {
      await renderQuality(id, routeId);
    } else if (page === "coordination") {
      await renderCoordination(id, routeId);
    } else {
      const [team, checkpoint, board] = await Promise.allSettled([
        api(`/team/${encodeURIComponent(id)}`), api(projectPath(id, "/checkpoint")), api(projectPath(id, "/tasks"))
      ]);
      if (routeId !== state.route) return;
      if (team.status === "rejected") throw team.reason;
      const checkpointPanel = checkpoint.status === "fulfilled" ? renderCheckpoint(checkpoint.value, routeId)
        : box("Checkpoint unavailable", checkpoint.reason.message, button("Reload checkpoint", route), "panel team-brief");
      const taskPanel = board.status === "fulfilled" ? renderTaskBoard(board.value, routeId)
        : box("Task board unavailable", board.reason.message, button("Retry task board", route), "panel team-brief");
      view.replaceChildren();
      renderTeam(team.value, state.projects.find(project => project.id === id), checkpointPanel, taskPanel);
    }
  } catch (error) {
    if (routeId === state.route) {
      view.replaceChildren(heading(titles[page], "Workstation data could not load."),
        box("Request failed", error.message, button("Try again", route)));
    }
  } finally {
    if (routeId === state.route) view.removeAttribute("aria-busy");
  }
}

async function loadStatus() {
  const tools = document.querySelector("#tool-status");
  try {
    const status = await api("/status");
    if (status.version) document.querySelector("#version").textContent = status.version;
    for (const [key, label] of Object.entries({ blender: "Blender", godot: "Godot" })) {
      const value = status.tools?.[key];
      const available = typeof value === "string"
        ? !/unavailable|not installed/i.test(value) && value.length > 0
        : typeof value === "object" && value !== null ? value.available : Boolean(value);
      const tool = badge(`${label} ${available ? "ready" : "unavailable"}`, available ? "good" : "");
      if (typeof value === "string") tool.title = value;
      tools.append(tool);
    }
    const tests = status.tests;
    if (typeof tests === "string") tools.append(badge(tests));
    if (typeof tests === "number") tools.append(badge(`${tests} tests`));
  } catch {
    tools.append(badge("Workstation status unavailable"));
  }
}

const form = document.querySelector("#create-project");
const kindSelect = document.querySelector("#project-kind");
for (const [value, label] of Object.entries(kinds)) {
  const option = element("option", null, label);
  option.value = value;
  kindSelect.append(option);
}
for (const close of dialog.querySelectorAll(".close, .cancel")) {
  close.addEventListener("click", () => dialog.close());
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const error = document.querySelector("#create-error");
  const submit = form.querySelector("[type=submit]");
  error.hidden = true;
  submit.disabled = true;
  try {
    const project = await api("/projects", "POST", { name: data.get("name").trim(), kind: data.get("kind") });
    dialog.close();
    openProject(project.id);
    notify("Project created.");
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    submit.disabled = false;
  }
});

window.addEventListener("hashchange", route);
setInterval(() => { if (!document.hidden) void refreshJobs(); }, 2500);
void loadStatus();
void route();
