extends SceneTree

const Interactions = preload("res://npc_interactions.gd")
const Civilians = preload("res://civilians.gd")
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(passed: bool, label: String) -> void:
	if not passed:
		failures += 1
		printerr("FAIL NPC interactions: ", label)


func position_for(population: Dictionary, id: String) -> Vector3:
	for row in population.civilians:
		if row.id == id:
			return Vector3(row.position[0], row.position[1], row.position[2])
	return Vector3.INF


func talk(model: Interactions, people: Civilians, id: String) -> Dictionary:
	var population := people.status()
	var reply := model.interact(position_for(population, id), population)
	check(reply.accepted and reply.id == id and not reply.message.is_empty(), "talk to the intended live resident " + id)
	return reply


func test_quest(model: Interactions, people: Civilians) -> void:
	var initial := model.status()
	var giver: String = initial.giver_id
	var recipient: String = initial.recipient_id
	var bystander := "civilian-02"
	check(initial.quest_stage == "available" and initial.target_id == giver and recipient != giver and recipient != bystander,
		"distinct repeatable quest participants")
	var before := model.snapshot()
	var unavailable := model.interact(Vector3(-200, 0, -200), people.status())
	check(not unavailable.accepted and unavailable.id.is_empty() and model.snapshot() == before,
		"a distant player cannot start the errand")
	var early := talk(model, people, recipient)
	check(early.quest_stage == "available" and early.message.contains("Ada"), "early recipient points the player to Ada")
	var first := talk(model, people, bystander)
	var repeat := talk(model, people, bystander)
	check(first.message != repeat.message and repeat.quest_stage == "available", "returning residents remember a conversation")
	var offer := talk(model, people, giver)
	check(offer.quest_stage == "deliver" and model.status().target_id == recipient and offer.message.contains(model.status().target_name),
		"Ada supplies the seed packet and names its recipient")
	var reminder := talk(model, people, giver)
	check(reminder.quest_stage == "deliver" and reminder.message != offer.message, "repeating a conversation cannot hand in the parcel")
	var old_position := position_for(people.status(), recipient)
	people.step(90.0)
	people.position += Vector3(400, 12, -350)
	check(not model.interact(old_position, people.status()).accepted, "interaction follows the moving population's world transform")
	var checkpoint: Dictionary = JSON.parse_string(JSON.stringify(model.snapshot()))
	var twin := Interactions.new()
	check(twin.configure(5, 4) and twin.valid_snapshot(checkpoint) and twin.restore(checkpoint) and twin.status() == model.status(),
		"fresh model restores a JSON checkpoint midway through the errand")
	var delivered := talk(model, people, recipient)
	var replay := talk(twin, people, recipient)
	check(replay == delivered and delivered.quest_stage == "return" and model.status().target_id == giver,
		"live recipient supplies the planting note, including after replay")
	check(talk(model, people, recipient).quest_stage == "return" and talk(model, people, bystander).quest_stage == "return",
		"the note can only be returned to Ada")
	var completed := talk(model, people, giver)
	check(completed.quest_stage == "complete" and completed.message.contains("frost") and model.status().target_id.is_empty(),
		"Ada reads the note and completes the seed exchange")
	check(talk(model, people, giver).quest_stage == "complete" and talk(model, people, recipient).quest_stage == "complete",
		"post-quest conversations remember completion")
	var detached := model.snapshot()
	detached.visits[0] = 0
	check(detached != model.snapshot(), "returned checkpoint arrays are independent")


func test_validation(model: Interactions, people: Civilians) -> void:
	var stable := model.snapshot()
	var broken: Array = [null, [], false, {}]
	var edits := [
		{"seed": 6}, {"seed": "5"}, {"version": true}, {"count": 4.5}, {"quest_stage": "bogus"},
		{"visits": [1, 2, 3]}, {"visits": {}}, {"visits": [1, 2, 3, -1]},
		{"visits": [1, 2, 3, INF]}, {"visits": [2, 2, 3, 1.5]}, {"visits": [2, 2, 3, false]},
		{"visits": [2, 2, 3, 2_147_483_648]}, {"visits": [1, 0, 0, 1]}, {"visits": [2, 0, 0, 0]},
		{"quest_stage": "available"}, {"quest_stage": "unavailable"}, {"extra": "data"},
	]
	for edit in edits:
		var malformed := stable.duplicate(true)
		malformed.merge(edit, true)
		broken.append(malformed)
	for malformed in broken:
		check(not model.valid_snapshot(malformed) and not model.restore(malformed) and model.snapshot() == stable,
			"reject malformed or unreachable snapshots atomically")
	var population := people.status()
	var origin := position_for(population, model.status().giver_id)
	for corrupt_row in [{"id": null}, {"id": "civilian-01"}, {"position": null}, {"position": [0, 0]},
			{"position": [0, NAN, 0]}, {"position": [0, INF, 0]}, {"position": [false, 0, 0]}, {"position": ["4", 0, 0]}]:
		var malformed := population.duplicate(true)
		malformed.civilians[1].merge(corrupt_row, true)
		check(not model.interact(origin, malformed).accepted and model.snapshot() == stable,
			"invalid population feed leaves state intact even when a valid resident is close")
	check(not model.interact(Vector3(NAN, 0, 0), population).accepted and model.snapshot() == stable, "reject non-finite player coordinates")
	for configuration in [[-1, 4], [2_147_483_648, 4], [5, -1], [5, 41]]:
		check(not model.configure(configuration[0], configuration[1]) and model.snapshot() == stable, "reject invalid settings atomically")


func test_proximity() -> void:
	var model := Interactions.new()
	model.configure(0, 2)
	var pair := {"count": 2, "civilians": [
		{"id": "civilian-02", "position": [0, 0, 3]},
		{"id": "civilian-01", "position": [0, 0, -3]},
	]}
	var first := model.interact(Vector3.ZERO, pair)
	check(first.accepted and first.id == "civilian-01", "radius is inclusive and ties use stable resident ID")
	pair.civilians.reverse()
	check(model.interact(Vector3.ZERO, pair).id == first.id, "tie-breaking ignores feed order")
	check(model.interact(Vector3(0, 0, 1), pair).id == "civilian-02", "nearer resident wins")
	check(not model.interact(Vector3(0, 3.01, 3), pair).accepted, "a different floor lies outside the talk radius")


func _run() -> void:
	var model := Interactions.new()
	var people := Civilians.new()
	root.add_child(people)
	check(model.snapshot().is_empty() and not model.restore({}) and not model.interact(Vector3.ZERO, {}).accepted,
		"unconfigured dialogue is inert")
	check(people.configure(5, 4, 48, 4) and model.configure(5, 4), "configure four actual civilian walkers")
	test_quest(model, people)
	test_validation(model, people)
	test_proximity()
	for count in [0, 1, 2, 40]:
		check(people.configure(2_147_483_647, 4, 48, count) and model.configure(2_147_483_647, count), "supported sizes including extremes")
		var info := model.status()
		check(info.conversations == 0 and model.valid_snapshot(model.snapshot()), "reconfiguration resets all earlier conversations")
		if count == 0:
			check(info.quest_stage == "unavailable" and not model.interact(Vector3.ZERO, people.status()).accepted, "empty city has no contacts")
		elif count == 1:
			var greeting := talk(model, people, "civilian-01")
			check(info.target_id == "" and greeting.quest_stage == "unavailable" and model.valid_snapshot(model.snapshot()),
				"lone resident offers chatter without an impossible two-person errand")
		else:
			check(info.quest_stage == "available" and info.giver_id != info.recipient_id and people.has_node(info.recipient_id),
				"quest recipient exists at minimum and maximum participating population")
	people.free()
	if failures == 0:
		print("PASS advanced NPC interactions: live walkers, seed exchange, repeat dialogue, proximity, checkpoint replay and population bounds")
	quit(int(failures > 0))
