extends SceneTree

const PROBES := ["npc", "difficulty", "capture", "interface", "presentation", "replay"]

func _initialize() -> void:
	call_deferred("_execute")

func _execute() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1 or args[0].length() != 64:
		quit(2)
		return
	var reports: Array = []
	var passed := true
	for domain in PROBES:
		var script: Script = load("res://" + domain + ".gd")
		if script == null or not script.can_instantiate():
			quit(2)
			return
		var probe = script.new()
		var report: Dictionary = await probe.run(self)
		reports.append(report)
		for check in report["checks"]:
			passed = passed and check["passed"]
		probe = null
		await process_frame
	print("GRAVEFORGE_RUNTIME_QA " + JSON.stringify({"schema_version": 1, "source_sha256": args[0], "passed": passed, "reports": reports}))
	quit(0 if passed else 1)
