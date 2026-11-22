extends SceneTree

const PROBES := ["decision", "squad", "encounters", "journal", "citizens", "missions"]

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
		var original_children := root.get_child_count()
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
		await process_frame
		if root.get_child_count() != original_children:
			push_error("Living World probe left scene nodes behind: " + domain)
			quit(2)
			return
	print("GRAVEFORGE_WORLD_QA " + JSON.stringify({"schema_version": 1, "source_sha256": args[0], "passed": passed, "reports": reports}))
	quit(0 if passed else 1)
