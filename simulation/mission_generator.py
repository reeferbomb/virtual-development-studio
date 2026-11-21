"""Generate an ordered Godot objective plan from the IDs available in a level."""

from collections.abc import Sequence
import random


def generate_mission(
    seed: int, *, interact_ids: Sequence[str], drive_ids: Sequence[str], visit_ids: Sequence[str]
) -> list[dict[str, str]]:
    """Choose one interaction, vehicle checkpoint and destination, in that order.

    Use the studio's integer seed range, 0 through 2**31-1. Each pool is a
    nonempty sequence of unique target IDs available for that action. Pool
    order has no effect, and generation never changes the caller's RNG state.
    """
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError("seed must be an integer between 0 and 2147483647")
    randomizer = random.Random(seed)
    stages = []
    for action, ids in (("interact", interact_ids), ("drive", drive_ids), ("visit", visit_ids)):
        if isinstance(ids, (str, bytes)) or not isinstance(ids, Sequence) or not ids:
            raise ValueError(f"{action} requires a nonempty sequence of target IDs")
        if any(not isinstance(target, str) or not target or target.strip() != target for target in ids):
            raise ValueError(f"{action} target IDs must be nonempty strings without outer whitespace")
        if len(set(ids)) != len(ids):
            raise ValueError(f"{action} target IDs must be unique")
        stages.append({"action": action, "target": randomizer.choice(sorted(ids))})
    return stages
