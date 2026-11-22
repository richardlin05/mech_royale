"""Routing-only estimates for observed loot and public supply drops."""
import math
from collections import Counter


class ResourceMemory:
    def __init__(self, config):
        self.seen = {"cubes": {}, "pickups": {}}
        self.thresholds = config["cubes"]["upgrade_thresholds"]

    def route_view(self, obs):
        """Remember static items briefly while preserving the raw observation for interaction."""
        now, pos = obs["t"], obs["self"]["pos"]
        view = obs.copy()
        for kind, memory in self.seen.items():
            visible = {item["id"]: item for item in obs[kind]}
            items = list(visible.values())
            for identifier, (seen_at, item) in list(memory.items()):
                if identifier in visible:
                    continue
                spot = item["pos"]
                inspected = abs(spot[2] - pos[2]) <= 4 and math.dist(pos[:2], spot[:2]) < 8
                if inspected or now - seen_at > 6:
                    del memory[identifier]
                else:
                    items.append(item)
            for identifier, item in visible.items():
                memory[identifier] = now, item
            view[kind] = items
        cubes = view["cubes"]
        if not cubes:
            return view
        # Two overlapping partitions avoid splitting most nearby piles at a grid edge.
        # A tile is small enough to traverse in less than one second at walking speed.
        def tile(spot, offset):
            return (math.floor((spot[0] + offset) / 6), math.floor((spot[1] + offset) / 6),
                    math.floor((spot[2] + offset * 0.5) / 4))
        counts = [Counter(tile(c["pos"], offset) for c in cubes) for offset in (0, 3)]
        owned = obs["self"]["cubes"]
        until_offer = next((n - owned for n in self.thresholds if n > owned), math.inf)
        ranked = []
        for cube in cubes:
            size = max(counts[i][tile(cube["pos"], offset)] for i, offset in enumerate((0, 3)))
            bonus = 5 * min(4, size - 1) + (7 if size >= until_offer else 0)
            ranked.append(dict(cube, route_bonus=bonus))
        view["cubes"] = ranked
        return view


def drop_cost(me, drop, travel, speed):
    """Comparable walking distance, including wait, remaining capture time and repair value."""
    arrival = travel / speed
    idle = max(0, drop["lands_in"] - arrival)
    banked = drop["progress"] if drop["holder"] == me["id"] else 0
    dwell = max(0, drop["capture_s"] - banked)
    repair = max(0, 1 - me["hp"] / me["max_hp"])
    recharge = max(0, 1 - me["energy"] / me["max_energy"])
    return (0.7 * travel + 0.35 * speed * (idle + dwell)
            - 22 - 60 * repair - 14 * recharge - 2 * banked)
