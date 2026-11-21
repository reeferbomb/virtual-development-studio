extends SceneTree

const Lobby = preload("res://lobby.gd")
var failures := 0
var checks := 0

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		printerr("FAIL ", label)

func _initialize() -> void:
	var lobby := Lobby.new()
	lobby.configure(3, 2)
	for invalid_name in ["", "a".repeat(25), "a/b", "José", "a\nb", "a\n", "<host>"]:
		check(not lobby.join(2, invalid_name), "reject name " + str(invalid_name))
	check(not lobby.join(0, "Zero"), "reject peer zero")
	check(not lobby.join(-4, "Negative"), "reject negative peer")
	check(lobby.join(1, "Headless host"), "host joins")
	check(lobby.members[1] == {"name": "Headless host", "ready": false, "slot": 0}, "initial member fields")
	check(not lobby.join(1, "Impostor"), "reject duplicate peer")
	check(lobby.set_ready(1, true), "host ready")
	check(not lobby.start(1), "enforce minimum")
	check(lobby.join(2, "A".repeat(24)), "accept maximum length")
	check(lobby.join(3, "Z_9-z"), "accept permitted characters")
	check(not lobby.join(4, "Fourth"), "enforce capacity")
	check(lobby.members[2].slot == 1 and lobby.members[3].slot == 2, "unique slots")
	check(not lobby.set_ready(999, true), "unknown peer cannot ready")
	check(not lobby.leave(999), "unknown departure rejected")
	check(lobby.leave(2), "disconnect")
	check(lobby.join(4, "Replacement"), "replace disconnected member")
	check(lobby.members[4].slot == 1 and lobby.members[3].slot == 2, "reuse free slot")
	var copy := lobby.snapshot()
	copy.members[1].name = "Tampered"
	copy.members.erase(3)
	check(lobby.members[1].name == "Headless host" and lobby.members.has(3), "snapshot isolated")
	check(not lobby.start(1), "wait for all members")
	check(lobby.set_ready(3, true) and lobby.set_ready(4, true), "members ready")
	check(not lobby.start(4), "only host starts")
	check(lobby.start(1) and lobby.snapshot().started, "host starts")
	check(not lobby.start(1), "reject second start")
	check(not lobby.set_ready(4, false), "freeze readiness after start")
	check(lobby.leave(4), "allow in-game disconnect")
	check(not lobby.join(5, "Late"), "reject late join despite free slot")
	var hostless := Lobby.new()
	hostless.configure(2, 1)
	check(hostless.join(8, "Guest") and hostless.set_ready(8, true), "guest-only lobby")
	check(not hostless.start(1), "absent host cannot start")
	print("lobby checks=%d failures=%d" % [checks, failures])
	quit(1 if failures else 0)
