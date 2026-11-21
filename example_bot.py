"""Placement-oriented Mech Royale bot. The starter wrapper handles the wire protocol."""
import math

import mechfight as mf


UPGRADES = ("armor", "nanites", "servos", "plating", "reactor", "gun_damage", "gun_rate")


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def direction(a, b):
    length = distance(a, b)
    if length < 0.5:
        return [0.0, 0.0]
    return [(b[i] - a[i]) / length for i in range(2)]


def loot_goal(obs, center, radius):
    me = obs["self"]
    pos = me["pos"]
    items = [(c, 0) for c in obs["cubes"]]
    if None in me["weapons"]:
        items.extend((p, 5) for p in obs["pickups"] if p["kind"] != "gun")
    options = [(distance(pos, item["pos"]) + penalty, item["pos"])
               for item, penalty in items
               if abs(item["pos"][2] - pos[2]) <= 4
               and distance(item["pos"], center) <= radius
               and distance(item["pos"], pos) <= 45]
    for drop in obs.get("drops", []):
        if (drop["lands_in"] == 0 and drop["holder"] in (None, me["id"])
                and distance(pos, drop["pos"]) < 45 and distance(drop["pos"], center) <= radius):
            options.append((distance(pos, drop["pos"]) - 12, drop["pos"]))
    return min(options)[1] if options else None


def engage(me, target, mobile):
    """Choose a single aim and use the best ready, in-range slot for it."""
    pos = me["pos"]
    best = None
    for slot, weapon in enumerate(me["weapons"]):
        if not weapon or weapon["cooldown"] > 0:
            continue
        stats, kind = weapon["stats"], weapon["kind"]
        dest = target["pos"]
        dx, dy = dest[0] - pos[0], dest[1] - pos[1]
        dz = dest[2] + 4.5 - pos[2] - me["stats"]["muzzle_height"]
        horizontal = math.hypot(dx, dy)
        if kind == "mortar":
            if horizontal < stats["splash_radius"] * 2:
                continue
        elif math.hypot(horizontal, dz) > stats["range"]:
            continue
        if kind == "gun" and (weapon.get("ammo", 0) <= 0 or weapon.get("reload", 0) > 0):
            continue
        if kind == "lightning" and me["energy"] < stats["energy"] + 12:
            continue
        if kind == "laser" and mobile:
            continue
        if kind in ("mortar", "gun"):
            lead = horizontal / stats["speed"]
            dx += target["vel"][0] * lead
            dy += target["vel"][1] * lead
            horizontal = math.hypot(dx, dy)
        pitch = math.atan2(dz, horizontal)
        if kind == "mortar":
            speed2 = stats["speed"] ** 2
            gravity = stats["gravity"]
            disc = speed2 ** 2 - gravity * (gravity * horizontal ** 2 + 2 * dz * speed2)
            if disc < 0:
                continue
            pitch = math.atan2(gravity * horizontal ** 2 + 2 * dz * speed2,
                               horizontal * (speed2 + math.sqrt(disc)))
        yaw = math.atan2(dy, dx)
        priority = {"gun": 1, "mortar": 2, "laser": 3, "lightning": 4}[kind]
        if best is None or priority > best[0]:
            best = priority, slot, weapon, yaw, pitch

    if best is None:
        return {}
    _, slot, weapon, yaw, pitch = best
    yaw_error = abs(math.remainder(yaw - me["aim"][0], math.tau))
    aligned = yaw_error < 0.12 and abs(pitch - me["aim"][1]) < 0.15
    fire = [False, False]
    if weapon["kind"] == "laser":
        fire[slot] = weapon.get("charge", 0) < weapon["stats"]["charge"] or not aligned
    else:
        fire[slot] = aligned
    return {"aim": [yaw, pitch], "fire": fire}


class Bot:
    name = "Oval Rover"

    def __init__(self, hello: mf.Hello):
        self.pickup_radius = hello["config"]["loot"]["pickup_radius"]
        self.side = 1 if hello["slot"] % 2 else -1
        self.sample = None
        self.detour_until = -1
        self.last_moving = False

    def act(self, obs: mf.Observation) -> mf.Action:
        me, zone, t = obs["self"], obs["zone"], obs["t"]
        pos, center = me["pos"], zone["next_center"]
        radius = max(0, zone["next_radius"] - min(15, zone["next_radius"] * 0.2))
        enemies = sorted((e for e in obs["mechs"] if e["kind"] == "mech"),
                         key=lambda e: distance(pos, e["pos"]))
        close = [e for e in enemies if distance(pos, e["pos"]) < 95]
        hurt = me["hp"] < 0.65 * me["max_hp"]
        retreat = bool(close) and (hurt or len(close) >= 2)
        rotate = not me["in_zone"] or distance(pos, center) > radius
        goal = center if rotate else None
        if not rotate and not enemies:
            goal = loot_goal(obs, center, radius)
        move = direction(pos, goal) if goal is not None else [0.0, 0.0]
        if close and not rotate:
            toward = direction(pos, close[0]["pos"])
            side = self.side * (1 if int(t / 2) % 2 else -1)
            lateral = [-side * toward[1], side * toward[0]]
            away = 1.4 if retreat else 0.35
            move = direction((0, 0), [lateral[i] - away * toward[i] for i in range(2)])
            projected = [pos[i] + move[i] * 10 for i in range(2)]
            if distance(projected, center) > radius:
                move = direction(pos, center)

        if self.sample is None or t - self.sample[0] >= 0.8:
            if self.sample and self.last_moving and any(move) and distance(pos, self.sample[1]) < 1.2:
                self.detour_until = t + 0.75
                self.side *= -1
            self.sample = t, pos
        detour = any(move) and t < self.detour_until
        if detour:
            move = [-self.side * move[1], self.side * move[0]]
        self.last_moving = any(move)
        action = {"tick": obs["tick"], "move": move, "jump": bool(detour and me["grounded"]),
                  "boost": me["energy"] > 28 and (retreat or not me["in_zone"] or detour),
                  "aim": [math.remainder(t * 0.75, math.tau), 0.0]}
        if obs["offer"] and obs["offer"]["choices"]:
            choices = obs["offer"]["choices"]
            action["pick"] = min(range(len(choices)), key=lambda i: (
                UPGRADES.index(choices[i]["id"]) if choices[i]["id"] in UPGRADES else len(UPGRADES)))
        if None in me["weapons"]:
            for p in obs["pickups"]:
                if p["kind"] != "gun" and math.dist(pos, p["pos"]) <= self.pickup_radius:
                    action["take"] = p["id"]
                    break
        target = enemies[0] if enemies else None
        if not target and not hurt and not rotate:
            crates = [c for c in obs["crates"] if distance(pos, c["pos"]) < 40]
            if crates:
                target = dict(min(crates, key=lambda c: distance(pos, c["pos"])), vel=[0, 0, 0])
        if target:
            action["aim"] = [math.atan2(target["pos"][1] - pos[1], target["pos"][0] - pos[0]), 0.0]
            if not (hurt and retreat and distance(pos, target["pos"]) > 45):
                action.update(engage(me, target, rotate or retreat))
        else:
            gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
            action["reload"] = bool(gun and gun["ammo"] < gun["stats"]["mag"] * 0.65)
        return action


if __name__ == "__main__":
    mf.run(Bot)
