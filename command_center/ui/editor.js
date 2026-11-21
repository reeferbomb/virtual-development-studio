(() => {
  "use strict";

  const SVG = "http://www.w3.org/2000/svg";
  const CLIPS = ["Idle", "Walk", "Run", "Aim", "Crouch", "Reload"];
  const AXES = ["X", "Y", "Z"];
  const STREAMED_TITLES = {
    openworld: "Frontier generation",
    unified: "Expedition settings",
    living: "Living World settings"
  };
  const STREAMED_FIELDS = [
    ["seed", "World seed", [0, 2147483647]],
    ["chunk_size", "Chunk width (m)", [16, 64]],
    ["radius", "Chunk radius", [1, 2]],
    ["capacity", "Inventory capacity", [1, 120]]
  ];
  const LIVING_FIELDS = STREAMED_FIELDS.map(([key, label, limits]) =>
    [key, label, key === "capacity" ? [3, limits[1]] : limits]);
  const CITY_FIELDS = [
    ["seed", "City seed", [0, 2147483647]],
    ["blocks", "Blocks per side", [3, 8]],
    ["block_size", "Block size (m)", [32, 64]],
    ["traffic", "Traffic vehicles", [0, 24]],
    ["civilians", "Civilians", [0, 40]]
  ];
  const CITY_TITLES = {
    city: "City settings",
    vertical: "Vertical City settings",
    advanced: "Advanced City settings",
    frontline: "Frontline City settings"
  };
  const CITY_CHECKS = {
    city: "Every build checks launch, traffic, civilians and networking. The shipped settings also run the Metropolis scenario.",
    vertical: "Every build checks launch, city components, interiors, transit, demolition and shared world state. The shipped settings also run the Vertical City scenario.",
    advanced: "Every build checks launch, inherited city systems, tower, vehicle, NPC interactions and session state. The shipped settings also run the Advanced City scenario.",
    frontline: "Every build checks launch, inherited city systems, shared vehicles, lifts, cover, mission progression and squad behavior. The shipped settings also run the Frontline City scenario."
  };
  const TRAINING_YARD_BLOCKS = new Map([
    ["qa_wall", "Training wall"],
    ["cover_nw", "Northwest cover"],
    ["cover_ne", "Northeast cover"],
    ["obstacle_sw", "Southwest obstacle"]
  ]);

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function svg(tag, attrs, parent) {
    const node = document.createElementNS(SVG, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (parent) parent.append(node);
    return node;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function button(text, selected, click) {
    const control = element("button", "se-choice", text);
    control.type = "button";
    control.setAttribute("aria-pressed", String(selected));
    control.addEventListener("click", click);
    return control;
  }

  function numberField(label, value, limits, change, step = "any") {
    const field = element("label", "se-field");
    const input = element("input");
    input.type = "number";
    input.step = step;
    if (limits) [input.min, input.max] = limits;
    input.value = value;
    input.addEventListener("change", () => {
      const next = input.valueAsNumber;
      if (!Number.isFinite(next) || !input.checkValidity()) {
        change(null, `${label} requires ${step === 1 ? "an integer" : "a number"}${limits ? ` from ${limits[0]} to ${limits[1]}` : ""}.`);
      } else {
        change(next);
      }
    });
    field.append(element("span", "", label), input);
    return field;
  }

  function isObject(input) {
    return input !== null && typeof input === "object" && !Array.isArray(input);
  }

  function streamedFields(kind) {
    return kind === "living" ? LIVING_FIELDS : STREAMED_FIELDS;
  }

  function isVector(input) {
    return Array.isArray(input) && input.length === 3 && input.every(Number.isFinite);
  }

  function worldPositionError(spec, selected) {
    const {width, depth, flat_radius: radius} = spec.terrain;
    for (const name of ["spawn", "goal"]) {
      const [x, y, z] = spec[name];
      if (y !== 0 || Math.max(Math.abs(x), Math.abs(z)) + 0.6 > radius) {
        return "Spawn and goal need ground clearance inside the flat core.";
      }
    }
    if (Math.hypot(...spec.spawn.map((value, i) => value - spec.goal[i])) < 3) {
      return "Spawn and goal must be at least 3 m apart.";
    }
    const fixtures = [
      ...(spec.blocks || []).map(row => ({position: row.position, size: row.size, id: row.id})),
      ...(spec.placements || []).map(row => {
        const size = row.collider_size;
        if (!size) return row;
        const yaw = (row.yaw_deg || 0) * Math.PI / 180;
        const [w, h, d] = size;
        const c = Math.abs(Math.cos(yaw));
        const s = Math.abs(Math.sin(yaw));
        const [x, y, z] = row.position;
        return {position: [x, y + h / 2, z], size: [c * w + s * d, h, s * w + c * d], id: row.id};
      })
    ];
    for (const {position: [x, y, z], size, id} of fixtures) {
      if (selected.id && selected.id !== id) continue;
      const [w, h, d] = size || [0, 0, 0];
      if (Math.abs(x) + w / 2 > width / 2 - 0.5 || Math.abs(z) + d / 2 > depth / 2 - 0.5) {
        return `${id} extends beyond the playable terrain.`;
      }
      if (size && [spec.spawn, spec.goal].some(point =>
        Math.abs(x - point[0]) < w / 2 + 0.45 && Math.abs(z - point[2]) < d / 2 + 0.45 &&
        y + h / 2 > point[1] && y - h / 2 < point[1] + 1.8)) {
        return `${id} intersects spawn or goal clearance.`;
      }
    }
    return "";
  }

  function validateShape(kind, spec) {
    if (!isObject(spec)) return "The spec must be a JSON object.";
    if (kind === "world") {
      const terrain = spec.terrain;
      if (!isObject(terrain) || !["width", "depth", "flat_radius"].every(key =>
        Number.isFinite(terrain[key]) && terrain[key] > 0)) {
        return "World terrain needs positive width, depth, and flat_radius values.";
      }
      if (!isVector(spec.spawn) || !isVector(spec.goal)) return "Spawn and goal each need three numeric coordinates.";
      for (const key of ["blocks", "placements"]) {
        if (!(key in spec)) continue;
        if (!Array.isArray(spec[key]) || !spec[key].every(row =>
          isObject(row) && typeof row.id === "string" && isVector(row.position) &&
          (key === "blocks" ? isVector(row.size) : !("collider_size" in row) || isVector(row.collider_size)))) {
          return `${key} must be an array of objects with IDs and numeric coordinates and dimensions.`;
        }
      }
    }
    if (kind === "cinematic") {
      const paths = ["camera_from", "camera_to", "look_from", "look_to", "actor_from", "actor_to"];
      if (!Array.isArray(spec.shots) || !spec.shots.length || !spec.shots.every(row =>
        isObject(row) && typeof row.id === "string" && CLIPS.includes(row.clip) &&
        Number.isFinite(row.duration) && row.duration > 0 && Number.isFinite(row.rain) &&
        Number.isFinite(row.light) && paths.every(key => isVector(row[key])))) {
        return "A cinematic needs shots with IDs, clips, positive durations, rain, light, and complete path coordinates.";
      }
    }
    if (kind === "gameplay") {
      if (!Array.isArray(spec.enemies) || !spec.enemies.length || !spec.enemies.every(row =>
        isObject(row) && typeof row.id === "string" && isVector(row.position) &&
        Array.isArray(row.patrol) && row.patrol.every(isVector))) {
        return "Gameplay needs enemies with IDs, positions, and patrol coordinates.";
      }
      if ("tactical" in spec && typeof spec.tactical !== "boolean") {
        return "Set tactical to true or false.";
      }
      if ("destructible_blocks" in spec) {
        const blocks = spec.destructible_blocks;
        if (!Array.isArray(blocks) || !blocks.every(id => TRAINING_YARD_BLOCKS.has(id)) ||
          new Set(blocks).size !== blocks.length) {
          return "Use a list of unique training yard block IDs for destructible_blocks.";
        }
      }
    }
    if (kind === "simulation") {
      if (!isVector(spec.vehicle_spawn) || !isVector(spec.checkpoint) ||
          !["clear", "rain", "fog"].includes(spec.weather) ||
          !Number.isFinite(spec.cycle_seconds) || spec.cycle_seconds <= 0 ||
          !Number.isFinite(spec.start_hour) || spec.start_hour < 0 || spec.start_hour >= 24 ||
          !Array.isArray(spec.interactables) || !spec.interactables.every(row =>
            isObject(row) && typeof row.id === "string" && isVector(row.position) &&
            ["beacon", "supply", "switch"].includes(row.kind)) ||
          !Array.isArray(spec.stages) || !spec.stages.length || !spec.stages.every(row =>
            isObject(row) && ["interact", "drive", "visit"].includes(row.action) && typeof row.target === "string")) {
        return "Simulation needs vehicle and checkpoint coordinates, weather/time, interactive objects, and ordered stages.";
      }
    }
    if (Object.hasOwn(STREAMED_TITLES, kind)) {
      for (const [key, , [min, max]] of streamedFields(kind)) {
        if (!Number.isInteger(spec[key]) || spec[key] < min || spec[key] > max) return `${key} must be an integer from ${min} to ${max}.`;
      }
      if (Object.keys(spec).length !== STREAMED_FIELDS.length) return "Specify seed, chunk_size, radius and capacity.";
    }
    if (Object.hasOwn(CITY_TITLES, kind)) {
      for (const [key, , [min, max]] of CITY_FIELDS) {
        if (!Number.isInteger(spec[key]) || spec[key] < min || spec[key] > max) return `${key} must be an integer from ${min} to ${max}.`;
      }
      if (Object.keys(spec).length !== CITY_FIELDS.length) return "Specify seed, blocks, block_size, traffic and civilians.";
    }
    return "";
  }

  function drawWorld(spec, selectedIndex, select) {
    const {width, depth, flat_radius: radius} = spec.terrain;
    const objects = [
      {key: "spawn", label: "Spawn", position: spec.spawn},
      {key: "goal", label: "Goal", position: spec.goal},
      ...(spec.blocks || []).map((row, index) => ({...row, key: "blocks", index, label: row.id})),
      ...(spec.placements || []).map((row, index) => ({...row, key: "placements", index, label: row.id}))
    ];
    const selected = objects[selectedIndex] || objects[0];
    const map = svg("svg", {
      viewBox: `${-width / 2 - 1} ${-depth / 2 - 1} ${width + 2} ${depth + 2}`,
      class: "se-map", role: "group", "aria-label": "Top-down world map"
    });
    svg("rect", {x: -width / 2, y: -depth / 2, width, height: depth, class: "se-terrain"}, map);
    svg("rect", {x: -radius, y: -radius, width: radius * 2, height: radius * 2, class: "se-region"}, map);
    svg("path", {d: `M ${-width / 2} 0 H ${width / 2} M 0 ${-depth / 2} V ${depth / 2}`, class: "se-axis"}, map);

    for (const [index, item] of objects.entries()) {
      const [x, , z] = item.position;
      const group = svg("g", {
        class: `se-marker se-${item.key}${selected === item ? " se-selected" : ""}`,
        role: "button", tabindex: "0", "aria-label": item.label, "aria-pressed": String(selected === item)
      }, map);
      svg("title", {}, group).textContent = item.label;
      group.addEventListener("click", () => select(index, ".se-marker"));
      group.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select(index, ".se-marker");
        }
      });
      const size = item.size || item.collider_size;
      if (size) {
        svg("rect", {
          x: x - size[0] / 2, y: z - size[2] / 2, width: size[0], height: size[2],
          transform: `rotate(${-(item.yaw_deg || 0)} ${x} ${z})`
        }, group);
      } else {
        svg("circle", {cx: x, cy: z, r: Math.max(0.3, Math.min(width, depth) / 60)}, group);
      }
    }
    return {map, objects, selected};
  }

  function drawPaths(paths, label, bounds) {
    const points = paths.flatMap(path => path.points);
    const xs = points.map(point => point[0]);
    const zs = points.map(point => point[2]);
    const minX = Math.min(0, bounds?.[0] || 0, ...xs) - 1;
    const maxX = Math.max(0, bounds?.[1] || 0, ...xs) + 1;
    const minZ = Math.min(0, bounds?.[2] || 0, ...zs) - 1;
    const maxZ = Math.max(0, bounds?.[3] || 0, ...zs) + 1;
    const map = svg("svg", {
      viewBox: `${minX} ${minZ} ${maxX - minX} ${maxZ - minZ}`,
      class: "se-map", role: "img", "aria-label": label
    });
    svg("path", {d: `M ${minX} 0 H ${maxX} M 0 ${minZ} V ${maxZ}`, class: "se-axis"}, map);
    for (const {points: positions, style, name} of paths) {
      const group = svg("g", {class: `se-path se-${style}`}, map);
      svg("title", {}, group).textContent = name;
      svg("polyline", {points: positions.map(([x, , z]) => `${x},${z}`).join(" ")}, group);
      for (const [index, [x, , z]] of positions.entries()) {
        svg("circle", {cx: x, cy: z, r: Math.max((maxX - minX) / 90, 0.1), class: index === 0 ? "se-start" : ""}, group);
      }
    }
    return map;
  }

  function mount(container, kind, spec, onChange) {
    let draft = clone(spec);
    let selectedIndex = 0;
    let jsonDirty = false;
    const root = element("div", "se-editor");
    const visual = element("div", "se-visual");
    const visualStatus = element("p", "se-status");
    const jsonStatus = element("p", "se-status");
    for (const status of [visualStatus, jsonStatus]) status.setAttribute("aria-live", "polite");
    const details = element("details", "se-json");
    const textarea = element("textarea", "se-source");
    textarea.setAttribute("aria-label", "Spec JSON");
    textarea.spellcheck = false;
    textarea.value = JSON.stringify(draft, null, 2);
    const apply = element("button", "se-apply", "Apply JSON");
    apply.type = "button";
    const visualKind = ["world", "cinematic", "gameplay", "simulation"].includes(kind) ||
      Object.hasOwn(STREAMED_TITLES, kind) || Object.hasOwn(CITY_TITLES, kind);
    details.open = !visualKind;
    details.append(element("summary", "", "JSON editor"), textarea, apply, jsonStatus);
    root.append(visual, visualStatus, details);
    container.replaceChildren(root);

    function choose(index, focusSelector) {
      selectedIndex = index;
      visualStatus.textContent = "";
      render();
      if (focusSelector) visual.querySelectorAll(focusSelector)[index]?.focus();
    }

    function store(next) {
      draft = next;
      jsonDirty = false;
      textarea.value = JSON.stringify(draft, null, 2);
      jsonStatus.textContent = "";
      onChange(clone(draft));
    }

    function edit(update, error, check, repaint = render) {
      if (jsonDirty) error = "Apply the pending JSON edits before editing visual fields.";
      if (!error) {
        const next = clone(draft);
        update(next);
        error = check ? check(next) : "";
        if (!error) {
          store(next);
          repaint();
        }
      }
      visualStatus.textContent = error || "";
    }

    function renderWorld() {
      const section = element("section", "se-layout");
      const {map, objects, selected} = drawWorld(draft, selectedIndex, choose);
      const canvas = element("div", "se-canvas");
      canvas.append(map, element("p", "se-legend", "X → · Z ↓ · dashed area = flat core"));
      const inspector = element("div", "se-inspector");
      inspector.append(element("h3", "", selected.label));
      const fields = element("div", "se-fields");
      for (const [index, axis] of AXES.entries()) {
        fields.append(numberField(axis, selected.position[index], [-128, 128], (value, error) => {
          edit(next => {
            const vector = selected.index === undefined ? next[selected.key] : next[selected.key][selected.index].position;
            vector[index] = value;
          }, error, next => worldPositionError(next, selected), () => {
            const result = drawWorld(draft, selectedIndex, choose);
            canvas.firstElementChild.replaceWith(result.map);
          });
        }));
      }
      inspector.append(fields);
      const list = element("div", "se-choices");
      for (const [i, item] of objects.entries()) list.append(button(item.label, selected === item, () => choose(i, ".se-choice")));
      inspector.append(list);
      section.append(canvas, inspector);
      visual.append(section);
    }

    function renderCinematic() {
      const timeline = element("div", "se-timeline");
      timeline.setAttribute("aria-label", "Shot timeline");
      const shot = draft.shots[selectedIndex] || draft.shots[0];
      const index = draft.shots.indexOf(shot);
      let time = 0;
      for (const [i, row] of draft.shots.entries()) {
        const choice = button(`${row.id} · ${time.toFixed(2)}–${(time + row.duration).toFixed(2)} s`, row === shot,
          () => choose(i, ".se-choice"));
        choice.style.flexGrow = String(row.duration);
        timeline.append(choice);
        time += row.duration;
      }
      const section = element("section", "se-layout");
      const canvas = element("div", "se-canvas");
      canvas.append(drawPaths([
        {name: "Camera", points: [shot.camera_from, shot.camera_to], style: "camera"},
        {name: "Actor", points: [shot.actor_from, shot.actor_to], style: "actor"},
        {name: "Look target", points: [shot.look_from, shot.look_to], style: "look"}
      ], `Camera, actor, and look target paths for ${shot.id}`, [-3, 3, -5, 5]));
      canvas.append(element("p", "se-legend", "Camera · Actor · Look target | X → · Z ↓"));
      const inspector = element("div", "se-inspector");
      inspector.append(element("h3", "", shot.id));
      const fields = element("div", "se-fields");
      for (const [key, label, limits] of [
        ["duration", "Duration (s)", [0.25, 30]], ["rain", "Rain", [0, 1]], ["light", "Light", [0, 4]]
      ]) {
        fields.append(numberField(label, shot[key], limits, (value, error) =>
          edit(next => { next.shots[index][key] = value; }, error, next =>
            next.shots.reduce((total, row) => total + row.duration, 0) > 120 ? "The timeline cannot exceed 120 seconds." : "",
          () => {
            if (key === "duration") render();
          })));
      }
      const clipLabel = element("label", "se-field");
      const select = element("select");
      for (const clip of CLIPS) select.append(element("option", "", clip));
      select.value = shot.clip;
      select.addEventListener("change", () => edit(next => { next.shots[index].clip = select.value; }, "", null, () => {}));
      clipLabel.append(element("span", "", "Clip"), select);
      fields.append(clipLabel);
      inspector.append(fields);
      section.append(canvas, inspector);
      visual.append(timeline, section);
    }

    function gameplayCheckbox(label, isChecked, update) {
      const field = element("label", "se-checkbox");
      const input = element("input");
      input.type = "checkbox";
      input.checked = isChecked(draft);
      input.addEventListener("change", () => {
        edit(next => update(next, input.checked), "", null, () => {});
        input.checked = isChecked(draft);
      });
      field.append(input, label);
      return field;
    }

    function renderGameplay() {
      const options = element("section", "se-inspector se-gameplay-options");
      options.append(element("h3", "", "Gameplay options"), gameplayCheckbox("Enable tactical gameplay",
        spec => spec.tactical === true, (next, checked) => { next.tactical = checked; }),
        element("p", "se-help", "Guards coordinate and use cover during combat."));
      const cover = element("fieldset", "se-breakable");
      cover.append(element("legend", "", "Breakable blocks"),
        element("p", "se-help", "Choose which training yard blocks can break during play."));
      const blockOptions = element("div", "se-block-options");
      for (const [id, name] of TRAINING_YARD_BLOCKS) {
        const label = element("span", "se-block-label");
        label.append(element("span", "", name), element("code", "", id));
        blockOptions.append(gameplayCheckbox(label,
          spec => spec.destructible_blocks?.includes(id) ?? false,
          (next, checked) => {
            const selected = new Set(next.destructible_blocks);
            if (checked) selected.add(id);
            else selected.delete(id);
            next.destructible_blocks = [...selected];
          }));
      }
      cover.append(blockOptions);
      options.append(cover, element("p", "se-help se-qa-note",
        "On the default encounter, enable tactical gameplay and select only the training wall to run the full tactical test. Custom configurations run gameplay module tests."));

      const enemy = draft.enemies[selectedIndex] || draft.enemies[0];
      const list = element("div", "se-choices");
      for (const [index, row] of draft.enemies.entries()) list.append(button(row.id, row === enemy, () => choose(index, ".se-choice")));
      const canvas = element("div", "se-canvas");
      canvas.append(drawPaths([
        {name: enemy.id, points: [enemy.position, ...enemy.patrol], style: "actor"}
      ], `Patrol for ${enemy.id}`), element("p", "se-legend", "Enemy start and patrol route · X → · Z ↓"));
      visual.append(options, list, canvas);
    }

    function renderSimulation() {
      const section = element("section", "se-layout");
      const canvas = element("div", "se-canvas");
      const paths = [{name: "Vehicle route", points: [draft.vehicle_spawn, draft.checkpoint], style: "actor"}];
      for (const row of draft.interactables) paths.push({name: row.id, points: [row.position], style: "look"});
      canvas.append(drawPaths(paths, "Expedition vehicle and interaction markers", [-48, 48, -48, 48]),
        element("p", "se-legend", "Vehicle / checkpoint · Interaction markers | X → · Z ↓"));
      const options = element("div", "se-inspector");
      options.append(element("h3", "", "Expedition climate"));
      const fields = element("div", "se-fields");
      const label = element("label", "se-field");
      const select = element("select");
      for (const weather of ["clear", "rain", "fog"]) select.append(element("option", "", weather));
      select.value = draft.weather;
      select.addEventListener("change", () => {
        edit(next => { next.weather = select.value; }, "", next => validateShape(kind, next), () => {});
        select.value = draft.weather;
      });
      label.append(element("span", "", "Weather"), select);
      fields.append(label);
      for (const [key, name, bounds] of [["start_hour", "Start hour", [0, 23.99]], ["cycle_seconds", "Day length (s)", [1, 86400]]]) {
        fields.append(numberField(name, draft[key], bounds, (value, error) =>
          edit(next => { next[key] = value; }, error, next => validateShape(kind, next), () => {})));
      }
      options.append(fields, element("h3", "", "Mission stages"));
      const steps = element("ol", "");
      for (const stage of draft.stages) steps.append(element("li", "", `${stage.action} · ${stage.target}`));
      options.append(steps, element("p", "se-help", "Edit the JSON for coordinates, markers, and stage order. Only the original fixture runs the full expedition acceptance test."));
      section.append(canvas, options);
      visual.append(section);
    }

    function renderStreamedWorld() {
      const section = element("section", "se-layout");
      const canvas = element("div", "se-canvas");
      const side = 2 * draft.radius + 1;
      const size = draft.chunk_size;
      const map = svg("svg", {viewBox:`0 0 ${side * size} ${side * size}`,class:"se-map",role:"img","aria-label":"Active streamed terrain window"});
      for (let x = 0; x < side; x++) for (let z = 0; z < side; z++) {
        const active = x === draft.radius && z === draft.radius;
        svg("rect",{x:x*size+0.25,y:z*size+0.25,width:size-0.5,height:size-0.5,fill:active?"#219c8c":"#34564c",stroke:"#8ca8a0","stroke-width":0.4},map);
      }
      canvas.append(map,element("p","se-legend",`${side*side} active chunks · ${side*size} × ${side*size} m active window · Center chunk highlighted`));
      const options = element("div", "se-inspector");
      options.append(element("h3", "", STREAMED_TITLES[kind]));
      const fields = element("div", "se-fields");
      for (const [key, label, limits] of streamedFields(kind)) {
        fields.append(numberField(label, draft[key], limits, (value, error) => {
          edit(next => { next[key] = value; }, error, next => validateShape(kind, next));
        }));
      }
      const notes = {
        openworld: `Up to ${side*side*2} NPCs in the active window. Every build checks launch and components. The shipped settings also run full scenario QA.`,
        unified: "Every build checks launch and components. The shipped settings also run the full expedition scenario.",
        living: "Every build checks launch and components. The shipped settings also verify encounters, diplomacy, contracts and checkpoint recovery."
      };
      options.append(fields, element("p", "se-help", notes[kind]));
      section.append(canvas,options);
      visual.append(section);
    }

    function renderCity() {
      const section = element("section", "se-layout");
      const canvas = element("div", "se-canvas");
      const options = element("div", "se-inspector");
      const fields = element("div", "se-fields");

      function drawGrid() {
        const {blocks, block_size: size} = draft;
        const extent = blocks * size;
        const map = svg("svg", {
          viewBox: `-4 -4 ${extent + 8} ${extent + 8}`,
          class: "se-map", role: "img", "aria-label": `${blocks} by ${blocks} city block grid`
        });
        svg("rect", {x: 0, y: 0, width: extent, height: extent, class: "se-city-blocks"}, map);
        let roads = "";
        for (let i = 0; i <= blocks; i++) {
          const offset = i * size;
          roads += ` M ${offset} 0 V ${extent} M 0 ${offset} H ${extent}`;
        }
        svg("path", {d: roads, class: "se-city-roads"}, map);
        canvas.replaceChildren(map, element("p", "se-legend",
          `${blocks ** 2} blocks · ${extent} × ${extent} m between outer street centers`));
      }

      for (const [key, label, limits] of CITY_FIELDS) {
        fields.append(numberField(label, draft[key], limits, (value, error) =>
          edit(next => { next[key] = value; }, error, next => validateShape(kind, next), drawGrid), 1));
      }
      options.append(element("h3", "", CITY_TITLES[kind]), fields, element("p", "se-help", CITY_CHECKS[kind]));
      section.append(canvas, options);
      visual.append(section);
      drawGrid();
    }

    function render() {
      visual.replaceChildren();
      const error = validateShape(kind, draft);
      if (error) {
        visualStatus.textContent = error;
        details.open = true;
      } else if (kind === "world") {
        renderWorld();
      } else if (kind === "cinematic") {
        renderCinematic();
      } else if (kind === "gameplay") {
        renderGameplay();
      } else if (kind === "simulation") {
        renderSimulation();
      } else if (Object.hasOwn(CITY_TITLES, kind)) {
        renderCity();
      } else if (Object.hasOwn(STREAMED_TITLES, kind)) {
        renderStreamedWorld();
      }
    }

    textarea.addEventListener("input", () => {
      jsonDirty = textarea.value !== JSON.stringify(draft, null, 2);
      jsonStatus.textContent = "";
    });
    apply.addEventListener("click", () => {
      let next;
      try {
        next = JSON.parse(textarea.value);
      } catch (error) {
        jsonStatus.textContent = `Invalid JSON. ${error.message}`;
        return;
      }
      const error = validateShape(kind, next) ||
        (kind === "world" ? worldPositionError(next, {}) : "");
      if (error) {
        jsonStatus.textContent = error;
        return;
      }
      visualStatus.textContent = "";
      store(next);
      render();
      jsonStatus.textContent = "JSON applied.";
    });
    render();
  }

  window.StudioEditor = {mount};
})();
