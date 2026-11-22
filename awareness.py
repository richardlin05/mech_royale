"""Interpret short-lived game cues and decide when it is safe to farm."""
import math


def best_crate(me, crates, arena=None):
    """Choose the earliest collectible cube, allowing travel and opening to overlap."""
    pos = me["pos"]
    gun = next((w for w in me.get("weapons", []) if w and w["kind"] == "gun"), None)
    speed = me.get("stats", {}).get("walk_speed", 11.7)
    options = []
    for c in crates:
        spot = c["pos"]
        dist = math.dist(pos[:2], spot[:2])
        if dist >= 90:
            continue
        if abs(pos[2] - spot[2]) > 4:
            if not arena or any(not arena.open(arena.cell(p)) or abs(p[2] - arena.ground[arena.cell(p)]) > 2.5
                                for p in (pos, spot)):
                continue
        opened = 0
        if gun:
            stats = gun["stats"]
            rounds = max(1, math.ceil(c.get("hp", 300) / stats["damage"]))
            remaining_reload = gun.get("reload", 0)
            available = stats["mag"] if remaining_reload > 0 else gun["ammo"]
            reloads = math.ceil(max(0, rounds - available) / stats["mag"])
            opened = remaining_reload + (rounds - 1) * stats["cooldown"] + reloads * stats["reload"]
        options.append((max(dist / speed, opened), dist, c["id"], c))
    return min(options, key=lambda o: o[:3])[-1] if options else None


class Awareness:
    def __init__(self, config):
        self.npc_range = config["npc"]["aggro_range"]
        self.npc_height = config["npc"]["height"] / 2
        self.crate_height = config["crates"]["height"] / 2
        self.recovering = False
        self.drone_id = None
        self.drone_until = -1
        self.bearing = None
        self.look_until = -1
        self.hit_until = -1

    def update(self, obs):
        me, t = obs["self"], obs["t"]
        fraction = me["hp"] / me["max_hp"]
        if fraction < 0.76:
            self.recovering = True
        elif fraction >= 0.93:
            self.recovering = False

        for event in obs["events"]:
            if event["type"] != "damaged" or event.get("by") == me["id"]:
                continue
            if event["weapon"] == "npc":
                self.drone_id = event.get("by")
                self.drone_until = t + 2.0
            elif event["weapon"] in ("gun", "laser", "lightning", "mortar") and event.get("bearing") is not None:
                self.bearing = event["bearing"]
                self.hit_until = self.look_until = t + 1.2

        if t < self.hit_until:
            return
        # Game audio supplies an approximate yaw only. Use it to turn the
        # field of view; attacks still require an actor in the observation.
        best = None
        for sound in obs["sounds"]:
            kind, band, age = sound["kind"], sound["dist"], sound["age"]
            charging = kind == "laser_charge"
            if band == "far" or age > 0.4 or (band != "near" and not charging):
                continue
            if kind not in ("laser_charge", "lightning", "jet", "boost", "reload", "step"):
                continue
            rank = (charging, band == "near", -age)
            if best is None or rank > best[0]:
                best = rank, sound
        if best is not None:
            sound = best[1]
            self.bearing = sound["bearing"]
            self.look_until = t + 0.6 - sound["age"]

    def farm_target(self, obs, arena=None):
        me, t = obs["self"], obs["t"]
        pos = me["pos"]
        drones = [a for a in obs["mechs"] if a["kind"] == "npc"
                  and math.dist(a["pos"][:2], pos[:2]) < 70
                  and (arena is None or not arena.screened(pos, a["pos"]))]
        active = [a for a in drones if (a["id"] == self.drone_id and t < self.drone_until)
                  or math.dist(a["pos"][:2], pos[:2]) <= self.npc_range]
        if active:
            drone = min(active, key=lambda a: (a["id"] != self.drone_id, math.dist(pos, a["pos"])))
            return dict(drone, aim_height=self.npc_height)
        if self.recovering:
            return None
        crate = best_crate(me, obs["crates"], arena)
        if crate is not None:
            return dict(crate, vel=[0, 0, 0], aim_height=self.crate_height)
        if drones:
            return dict(min(drones, key=lambda a: math.dist(pos, a["pos"])), aim_height=self.npc_height)
        return None
