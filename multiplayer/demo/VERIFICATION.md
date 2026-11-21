# Multiplayer engineering v6 verification

Godot 4.7.2 on Linux, headless ENet over IPv4 loopback. Each match used
independent host and client Godot processes; no simulated transport or mocked
multiplayer was used for these results. All sessions ran for about eight
seconds of authoritative match time. These are functional load tests, not
WAN performance benchmarks.

| Total players | Remote clients | Accepted commands | Rejected invalid commands | PvP damage events | Hits on NPC | NPC attacks | Clean departures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 2 | 460 | 2 | 6 | 6 | 2 | 2 |
| 5 | 4 | 752 | 4 | 13 | 6 | 2 | 4 |
| 9 | 8 | 1329 | 8 | 29 | 6 | 1 | 8 |

All clients independently confirmed match start, full roster visibility,
their own replicated movement, player damage and changed NPC health. All
processes exited successfully; no engine errors or MTU warning appeared in
the final three sessions. Every remote client sent one deliberately excessive
movement vector; the host rejected it. Loopback reports and per-process logs
are under `network_arena/reports/loopback-{2,4,8}`.

## Regression and module evidence

- Python suite: 33/33 passed.
- Godot suites: input guard, lobby (34 checks), scene contract, snapshot codec.
- Configured lobby cap: 16 total slots, tested in the isolated lobby module.
- Full-slot worst-case synthetic snapshot: 1,088 serialized bytes, with all
  16 names at 24 characters; codec round trip passed. This is variant bytes,
  not measured internet traffic. Final 9-player session had no MTU warning.
- The source world, v5 fixed and generated encounters, and the final network
  package passed integrity checks.

During integration, a shutdown packet race was resolved with graceful leave
acknowledgments and disabled automatic client-to-client relay. A larger initial
snapshot generated an MTU warning; compact fixed-width state arrays resolved
that warning in the final headless runs.

## Not proven

16 concurrent players, physical LAN devices, WAN latency/loss, prediction,
lag compensation, listen-host migration, public matchmaking, encrypted or
authenticated sessions, cheat resistance against a malicious host, finished
graphics, and real hardware performance remain open acceptance gates.
