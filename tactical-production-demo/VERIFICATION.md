# Procedural tactical production — seed 240

The example was generated as a 48 × 48 m world with 32 cover blocks and six
reused prop placements. The generated encounter has six guards, tactical squad
mode enabled, and eight selected destructible blocks (the central barrier and
seven generated cover blocks).

`seed-240/world` was built with physical route QA. The real Godot player drove
37.7334 m in 566 physics ticks at 60 Hz, visited all five waypoints, triggered
the goal, and recorded zero horizontal collision contacts. See
`seed-240/world/reports/route-qa.json` for measurements.

`seed-240/gameplay` was built from that verified world and the generated
`seed-240/encounter.json`. It passed scene import, launch, and six Godot module
test scripts: combat, mission, navigation, squad, tactical enemy, destruction.
Both package integrity verifiers passed.

The original training fixture is the only controlled full tactical scenario.
This generated battle is a different build with real runtime import, launch
and module QA; it has not undergone an end-to-end combat completion test,
human visual review or target-device benchmark.
