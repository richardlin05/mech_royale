"""Placement-oriented Mech Royale bot. The starter wrapper handles the wire protocol."""
import math

import mechfight as mf
from arena_nav import Arena


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
    items = [(c, -8) for c in obs["cubes"]]
    if None in me["weapons"]:
        items.extend((p, 5) for p in obs["pickups"] if p["kind"] != "gun")
    options = [(distance(pos, item["pos"]) + penalty, item["pos"])
               for item, penalty in items
               if abs(item["pos"][2] - pos[2]) <= 4
               and distance(item["pos"], center) <= radius
               and distance(item["pos"], pos) <= 105]
    for drop in obs.get("drops", []):
        travel = distance(pos, drop["pos"])
        arrival = travel / max(1, me["stats"]["walk_speed"])
        if (drop["lands_in"] <= arrival + 3 and drop["holder"] in (None, me["id"])
                and travel < 150 and distance(drop["pos"], center) <= radius):
            options.append((travel * 0.55 - 32, drop["pos"]))
    if not options:
        for crate in obs["crates"]:
            if distance(pos, crate["pos"]) < 90 and abs(crate["pos"][2] - pos[2]) < 5:
                if distance(crate["pos"], center) <= radius:
                    options.append((distance(pos, crate["pos"]), crate["pos"]))
    return min(options)[1] if options else None


def engage(me, target, mobile):
    """Choose a single aim and use the best ready, in-range slot for it."""
    pos = me["pos"]
    best = None
    for slot, weapon in enumerate(me["weapons"]):
        if not weapon or (weapon["kind"] != "gun" and weapon["cooldown"] > 0):
            continue
        stats, kind = weapon["stats"], weapon["kind"]
        dest = target["pos"]
        dx, dy = dest[0] - pos[0], dest[1] - pos[1]
        dz = dest[2] + target.get("aim_height", 4.5) - pos[2] - me["stats"]["muzzle_height"]
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

    # Both arms can fire together. Use the gun when the shared aim also fits it.
    for i, other in enumerate(me["weapons"]):
        if i == slot or not other or other["kind"] != "gun" or other.get("ammo", 0) <= 0:
            continue
        dx, dy, dz = [target["pos"][j] - pos[j] for j in range(3)]
        flight = math.hypot(dx, dy) / other["stats"]["speed"]
        dx += target["vel"][0] * flight
        dy += target["vel"][1] * flight
        gun_pitch = math.atan2(dz + target.get("aim_height", 4.5) - me["stats"]["muzzle_height"], math.hypot(dx, dy))
        fire[i] = (math.hypot(dx, dy) <= other["stats"]["range"]
                   and abs(math.remainder(math.atan2(dy, dx) - me["aim"][0], math.tau)) < 0.12
                   and abs(gun_pitch - me["aim"][1]) < 0.12)
    return {"aim": [yaw, pitch], "fire": fire}


class Bot:
    name = "Oval Rover"

    def __init__(self, hello: mf.Hello):
        self.pickup_radius = hello["config"]["loot"]["pickup_radius"]
        self.side = 1 if hello["slot"] % 2 else -1
        try:
            self.arena = Arena(hello["map"]["dir"])
        except (OSError, ValueError, KeyError, IndexError):
            self.arena = None
        self.crate_height = hello["config"]["crates"]["height"] / 2
        self.npc_height = hello["config"]["npc"]["height"] / 2
        self.cover_goal = None
        self.next_cover_search = 0
        self.target_id = None
        self.sample = None
        self.detour_until = -1
        self.last_moving = False

    def act(self, obs: mf.Observation) -> mf.Action:
        me, zone, t = obs["self"], obs["zone"], obs["t"]
        pos, center = me["pos"], zone["next_center"]
        radius = max(0, zone["next_radius"] - min(15, zone["next_radius"] * 0.2))
        enemies = sorted((e for e in obs["mechs"] if e["kind"] == "mech"),
                         key=lambda e: distance(pos, e["pos"]))
        hurt = me["hp"] < 0.65 * me["max_hp"]
        crowded = sum(distance(pos, e["pos"]) < 110 for e in enemies) >= 2
        retreat = bool(enemies) and (hurt or crowded)
        rotate = not me["in_zone"] or distance(pos, center) > radius
        goal = center if rotate else loot_goal(obs, center, radius)
        move = direction(pos, goal) if goal is not None else [0.0, 0.0]
        if enemies:
            toward = direction(pos, enemies[0]["pos"])
            side = self.side
            if not rotate and int(t / 3) % 2:
                side *= -1
            lateral = [-side * toward[1], side * toward[0]]
            if rotate:
                # Choose the tangent that still makes progress toward safety.
                if sum(lateral[i] * move[i] for i in range(2)) < 0:
                    lateral = [-n for n in lateral]
                move = direction((0, 0), [move[i] + 0.6 * lateral[i] for i in range(2)])
            else:
                away = 1.4 if retreat else 0.25
                move = direction((0, 0), [lateral[i] - away * toward[i] for i in range(2)])
                if distance([pos[i] + 10 * move[i] for i in range(2)], center) > radius:
                    inward = direction(pos, center)
                    move = direction((0, 0), [inward[i] + 0.45 * lateral[i] for i in range(2)])
        elif goal is None and radius > 8:
            # Search for resources along a circuit inside the next circle.
            orbit = min(radius * 0.7, 85)
            angle = math.atan2(pos[1] - center[1], pos[0] - center[0]) + self.side * 0.5
            move = direction(pos, [center[0] + orbit * math.cos(angle),
                                   center[1] + orbit * math.sin(angle)])

        # Use physical cover to buy time for regeneration under pressure.
        if self.arena and retreat and not rotate:
            if t >= self.next_cover_search:
                self.cover_goal = self.arena.cover(pos, enemies, center, radius)
                self.next_cover_search = t + 1.0
            if self.cover_goal:
                goal = self.cover_goal
        else:
            self.cover_goal = None
        # Commit to the next waypoint for travel. Keep free strafing in a duel.
        if self.arena and goal is not None and (rotate or not enemies or self.cover_goal):
            waypoint = self.arena.waypoint(pos, goal, t)
            move = direction(pos, waypoint)
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
        # Commit to a reachable, damaged opponent to finish eliminations.
        gun_range = max((w["stats"].get("range", 0) for w in me["weapons"] if w), default=0)
        def target_cost(enemy):
            dist = distance(pos, enemy["pos"])
            hp_fraction = enemy.get("hp", 1400) / max(1, enemy.get("max_hp", 1400))
            return (dist > gun_range, dist + 85 * hp_fraction - 20 * (enemy["id"] == self.target_id))

        target = min(enemies, key=target_cost, default=None)
        self.target_id = target["id"] if target else None
        if not target and not hurt and me["in_zone"]:
            crates = [c for c in obs["crates"] if distance(pos, c["pos"]) < 90]
            if crates:
                target = dict(min(crates, key=lambda c: distance(pos, c["pos"])), vel=[0, 0, 0],
                              aim_height=self.crate_height)
            else:
                drones = [e for e in obs["mechs"] if e["kind"] == "npc" and distance(pos, e["pos"]) < 70]
                if drones:
                    target = dict(min(drones, key=lambda e: distance(pos, e["pos"])), aim_height=self.npc_height)
        if target:
            action["aim"] = [math.atan2(target["pos"][1] - pos[1], target["pos"][0] - pos[0]), 0.0]
            behind_cover = self.arena and retreat and self.arena.screened(pos, target["pos"])
            if not behind_cover:
                action.update(engage(me, target, rotate or retreat))
        else:
            gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
            action["reload"] = bool(gun and gun["ammo"] < gun["stats"]["mag"] * 0.65)
        return action


if __name__ == "__main__":
    mf.run(Bot)
