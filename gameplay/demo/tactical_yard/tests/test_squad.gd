extends SceneTree

const Squad = preload("res://squad.gd")
const IDLE = {"active": false, "target": Vector3.ZERO, "role": "support"}

var failures := 0

func check(condition: bool, description: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL ", description)

func test_shared_sighting() -> void:
	var squad := Squad.new()
	var other := Squad.new()
	squad.configure(["charlie", "bravo", "alpha", "alpha"])
	other.configure(["alpha", "charlie", "bravo"])
	check(squad.intel("alpha") == IDLE, "A new squad starts unaware")
	squad.report("outsider", Vector3.ONE)
	check(squad.intel("alpha") == IDLE, "Only a living squad member can start an alert")
	var sighting := Vector3(3, 1, -4)
	for team in [squad, other]:
		team.report("bravo", sighting)
	check(squad.intel("bravo").role == "pursuer", "First observer pursues")
	check(squad.intel("alpha").role == "flanker", "First remaining ID flanks")
	check(squad.intel("charlie").role == "support", "Remaining guard supports")
	check(squad.intel("outsider") == IDLE, "Only a living squad member can receive the location")
	for id in ["alpha", "bravo", "charlie"]:
		var info := squad.intel(id)
		check(info.active and info.target == sighting, "Everyone receives the observed position")
		check(info == other.intel(id), "Roles are independent of roster order")
		info.target = Vector3.ONE
	check(squad.intel("bravo").target == sighting, "A reader cannot mutate shared memory")

	squad.tick(4.75)
	var next_sighting := Vector3(-2, 0, 4)
	squad.report("charlie", next_sighting)
	squad.tick(4.75)
	check(squad.intel("alpha").target == next_sighting, "Fresh sightings replace and renew the shared location")
	check(squad.intel("bravo").role == "pursuer", "Another observer does not displace a living pursuer")
	squad.report("outsider", sighting)
	squad.report("alpha", Vector3(INF, 0, 0))
	squad.tick(0.25)
	for id in ["alpha", "bravo", "charlie", "outsider"]:
		check(squad.intel(id) == IDLE, "All roles lose the exact location after five seconds")
	squad.report("charlie", Vector3.ZERO)
	check(squad.intel("charlie") == {"active": true, "target": Vector3.ZERO, "role": "pursuer"},
		"The next fresh observer can lead a new alert even at the origin")

func test_survivors_and_reset() -> void:
	var squad := Squad.new()
	squad.configure(["c", "d", "b", "a"])
	var seen := Vector3(2, 1, 3)
	squad.report("c", seen)
	squad.forget("a")
	check(squad.intel("b").role == "flanker", "Another live guard replaces the old flanker")
	squad.tick(4.0)
	squad.forget("c")
	check(squad.intel("b") == {"active": true, "target": seen, "role": "pursuer"}, "Flanker succeeds the lost pursuer")
	check(squad.intel("d").role == "flanker", "Next survivor takes the flank")
	squad.forget("c")
	squad.report("c", Vector3.ONE)
	check(squad.intel("c") == IDLE and squad.intel("b").target == seen, "Eliminated guards cannot report or read intel")
	squad.tick(1.0)
	check(squad.intel("b") == IDLE, "Role reassignment does not refresh the sighting")
	squad.forget("b")
	squad.report("d", seen)
	check(squad.intel("d").role == "pursuer", "A lone survivor can pursue")
	squad.configure(["a", "c"])
	check(squad.intel("a") == IDLE and squad.intel("d") == IDLE, "Mission reconfiguration clears old contacts")
	squad.report("a", seen)
	squad.forget("a")
	squad.forget("c")
	squad.report("d", seen)
	check(squad.intel("d") == IDLE, "An empty squad cannot be alerted")

func test_physics_clock() -> void:
	var squad := Squad.new()
	squad.configure(["a"])
	squad.report("a", Vector3.ONE)
	for frame in range(299):
		squad.tick(1.0 / 60.0)
	check(squad.intel("a").active, "Contact survives the first 299 physics frames")
	squad.tick(1.0 / 60.0)
	check(squad.intel("a") == IDLE, "Contact expires on the 300th frame at 60 Hz")

func _initialize() -> void:
	test_shared_sighting()
	test_survivors_and_reset()
	test_physics_clock()
	print("squad assertions finished, failures=", failures)
	quit(int(failures != 0))
