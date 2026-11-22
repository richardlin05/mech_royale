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


class FirstLoadout:
    """Remember a reachable first secondary during the opening search."""
    def __init__(self):
        self.item = None
        self.seen_at = 0
        self.best_distance = math.inf
        self.progress_at = 0
        self.abandoned = {}

    def goal(self, obs, enemies, arena, urgent):
        me, zone, now = obs["self"], obs["zone"], obs["t"]
        if (None not in me["weapons"] or urgent or not me["in_zone"] or
                now >= zone["shrink_start"] or zone["radius"] < 120 or
                me["hp"] < 0.7 * me["max_hp"] or len(enemies) > 1):
            self.item = None
            return None
        pos = me["pos"]
        separation = min((math.dist(pos[:2], e["pos"][:2]) for e in enemies), default=math.inf)
        if separation < 90:
            self.item = None
            return None
        # A cube underfoot or a capture already in progress takes precedence.
        if any(math.dist(pos, cube["pos"]) < 7 for cube in obs["cubes"]) or any(
                d["holder"] == me["id"] for d in obs.get("drops", [])):
            return None

        visible = {p["id"]: p for p in obs["pickups"] if p["kind"] != "gun"}
        if self.item:
            old_id = self.item["id"]
            travel = math.dist(pos[:2], self.item["pos"][:2])
            if old_id in visible:
                self.seen_at = now
            if travel < self.best_distance - 2:
                self.best_distance, self.progress_at = travel, now
            if now - self.progress_at > 5 or (old_id not in visible and
                    (travel < 8 or now - self.seen_at > 12)):
                self.abandoned[old_id] = now + 10
                self.item = None

        options = dict(visible)
        if self.item:
            options.setdefault(self.item["id"], self.item)
        selected, best_cost = None, math.inf
        for item in options.values():
            spot = item["pos"]
            if now < self.abandoned.get(item["id"], -1):
                continue
            travel = math.dist(pos[:2], spot[:2])
            if travel > 155 or math.dist(spot[:2], zone["center"]) + 6 >= zone["radius"]:
                continue
            if arena:
                cell = arena.cell(spot)
                if not arena.open(cell) or abs(spot[2] - arena.ground[cell]) > 4:
                    continue
            elif abs(spot[2] - pos[2]) > 4:
                continue
            if any(math.dist(spot[:2], e["pos"][:2]) < min(90, 0.85 * separation) for e in enemies):
                continue
            to_safety = max(0, math.dist(spot[:2], zone["next_center"]) - zone["next_radius"] + 10)
            if now + 1.7 * (travel + to_safety) / me["stats"]["walk_speed"] + 5 > zone["shrink_start"]:
                continue
            # An early long-range secondary is worth a small extra walk.
            cost = travel + 0.6 * to_safety + (18 if item["kind"] == "lightning" else 0)
            if self.item and self.item["id"] == item["id"]:
                cost -= 12
            if cost < best_cost:
                selected, best_cost = item, cost
        if selected and (not self.item or selected["id"] != self.item["id"]):
            self.progress_at = self.seen_at = now
            self.best_distance = math.dist(pos[:2], selected["pos"][:2])
        self.item = selected
        return selected["pos"] if selected else None
