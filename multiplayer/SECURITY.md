# Multiplayer prototype security boundary

Scope: trusted local host and local/LAN direct-address sessions only. The
default bind is loopback. No internet service, accounts, secrets, or external
identity providers are configured. ENet's transport identity is a connection
identifier, not proof of an authenticated human identity.

| Abuse case | Implemented control | Residual risk |
|---|---|---|
| Client impersonates another actor | Server derives peer ID from RPC sender; no client-selected actor ID in requests | Connection identity is not user authentication |
| Client teleports or claims hits | Only movement vector, direction and button intents accepted; server applies fixed speed, physics, collision and raycast damage | No lag compensation, prediction, or client integrity enforcement |
| Excessive/non-finite movement or aim | Bound dimensions and finite values; invalid commands rejected | Transport-level CPU/packet floods are not fully mitigated |
| Replay or stale controls | Monotonic sequence per peer; 40 accepted commands per rolling second; input expiry after 300ms | Session-level sequence counters are not cryptographic replay protection |
| Client starts or modifies match | Lobby start is host-only and all members must be ready; late/duplicate joins rejected | Malicious host remains authoritative |
| Unbounded snapshot size | Compact packed arrays bounded to 16 roster entries and 24-character names; decoder checks structure | WAN latency/loss behavior not yet tested |
| Client-to-client relay abuse | Server relay disabled; clients exchange RPCs with host only | No encrypted transport, identity verification, NAT traversal or IP privacy guarantees |
| Disconnect leaves stale authority | Membership, actor, weapon, input and guard entries removed; graceful leave acknowledgment | Abrupt network failure and host migration remain future work |

Do not present this as anti-cheat completion. A public release requires a
separate threat model, authenticated sessions, encryption, relay/NAT strategy,
WAN stress and loss tests, independent security review, and a decision about
player-host authority versus trusted dedicated servers.
