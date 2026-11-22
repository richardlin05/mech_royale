"""A short commitment to verified shelter while the game restores HP."""
import math


class Recovery:
    def __init__(self):
        self.goal = None
        self.until = -1
        self.retry_at = -1

    @staticmethod
    def has_time(obs, spot, inner_radius):
        me, zone = obs["self"], obs["zone"]
        if not me["in_zone"]:
            return False
        pos = me["pos"][:2]
        walk = me["stats"]["walk_speed"]
        travel = 1.8 * math.dist(pos, spot[:2]) / walk
        if math.dist(spot[:2], zone["center"]) + me["stats"]["radius"] >= zone["radius"]:
            return False
        inward = max(0, math.dist(spot[:2], zone["next_center"]) - inner_radius)
        if inward == 0 and math.dist(pos, zone["next_center"]) <= inner_radius:
            return True
        # Outside the next circle, reserve the walk back before shrink starts.
        return obs["t"] + travel + 1.8 * inward / walk + me["stats"]["regen_delay"] + 5 < zone["shrink_start"]

    def remember(self, obs, goal, enemies, arena, inner_radius):
        me = obs["self"]
        if (not goal or self.goal is not None or obs["t"] < self.retry_at
                or me["hp"] >= 0.65 * me["max_hp"] or not self.has_time(obs, goal, inner_radius)):
            return
        if all(arena.screened(goal, e["pos"]) for e in enemies):
            self.goal = tuple(goal)
            travel = 1.8 * math.dist(me["pos"][:2], goal[:2]) / me["stats"]["walk_speed"]
            heal = (0.9 * me["max_hp"] - me["hp"]) / max(1, me["stats"]["regen_per_s"])
            self.until = obs["t"] + min(28, travel + me["stats"]["regen_delay"] + heal + 1)

    def hold(self, obs, enemies, arena, inner_radius, storm_urgent):
        if self.goal is None:
            return None
        me, now = obs["self"], obs["t"]
        arrived = math.dist(me["pos"][:2], self.goal[:2]) < 4
        under_fire = any(e["type"] == "damaged" for e in obs["events"])
        unsafe = (storm_urgent or not self.has_time(obs, self.goal, inner_radius)
                  or any(not arena.screened(self.goal, e["pos"]) for e in enemies))
        drop = any(d["holder"] == me["id"] for d in obs.get("drops", []))
        if (unsafe or drop or now >= self.until or me["hp"] >= 0.90 * me["max_hp"]
                or (arrived and under_fire)):
            self.goal = None
            self.retry_at = now + 2.0
            return None
        return self.goal
