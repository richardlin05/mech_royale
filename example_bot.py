"""Placement-oriented Mech Royale bot. The starter wrapper handles the wire protocol."""
import math

import mechfight as mf
from arena_nav import Arena
from equipment import Equipment


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def direction(a, b):
    length = distance(a, b)
    if length < 0.5:
        return [0.0, 0.0]
    return [(b[i] - a[i]) / length for i in range(2)]


def reachable_loot_level(pos, spot, arena):
    """Keep pickup-height limits near the mech, but allow travel along sloping ground."""
    if abs(pos[2] - spot[2]) <= 4:
        return True
    if arena is None or distance(pos, spot) <= 4:
        return False
    # Ground height changes across the map. A weapon 6 m higher on a hillside
    # can be collected at arrival; one 6 m above the ground on a roof cannot.
    for point in (pos, spot):
        cell = arena.cell(point)
        if not arena.open(cell) or abs(point[2] - arena.ground[cell]) > 2.5:
            return False
    return True


def loot_goal(obs, center, radius, arena=None):
    me = obs["self"]
    pos = me["pos"]
    items = [(c, -8) for c in obs["cubes"]]
    if None in me["weapons"]:
        items.extend((p, 5) for p in obs["pickups"] if p["kind"] != "gun")
    options = [(distance(pos, item["pos"]) + penalty, item["pos"])
               for item, penalty in items
               if reachable_loot_level(pos, item["pos"], arena)
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
            if distance(pos, crate["pos"]) < 90 and reachable_loot_level(pos, crate["pos"], arena):
                if distance(crate["pos"], center) <= radius:
                    options.append((distance(pos, crate["pos"]), crate["pos"]))
    return min(options)[1] if options else None


def early_loot(obs, center, radius, arena=None):
    """Allow a short detour only when we can still walk to safety before shrink starts."""
    me, zone = obs["self"], obs["zone"]
    remaining = zone["shrink_start"] - obs["t"]
    if remaining <= 8 or not me["in_zone"]:
        return None
    pos = me["pos"]
    options = []
    items = list(obs["cubes"])
    if None in me["weapons"]:
        items.extend(p for p in obs["pickups"] if p["kind"] != "gun")
    for item in items:
        spot = item["pos"]
        outward = distance(pos, spot)
        if outward > 24 or not reachable_loot_level(pos, spot, arena):
            continue
        if distance(spot, zone["center"]) + 6 > zone["radius"]:
            continue
        inward = max(0, distance(spot, center) - radius)
        # Allow twice the direct walking time for buildings, plus an eight-second buffer.
        if 2 * (outward + inward) / me["stats"]["walk_speed"] + 8 < remaining:
            options.append((outward, item["id"], spot))
    return min(options)[2] if options else None


def duel_loot_goal(obs, enemy, arena):
    """Collect a reward along a short, safe flank while keeping the torso free to aim."""
    me, zone = obs["self"], obs["zone"]
    pos, speed = me["pos"], me["stats"]["walk_speed"]
    if not me["in_zone"]:
        return None
    opponent = enemy["pos"]
    separation = distance(pos, opponent)
    if separation < 35:
        return None

    options = []
    for item in obs["cubes"]:
        options.append((item["pos"], 0.0, 0.0))
    if None in me["weapons"]:
        for item in obs["pickups"]:
            if item["kind"] != "gun":
                options.append((item["pos"], 0.0, -5.0))
    for drop in obs.get("drops", []):
        if drop["lands_in"] > 0 or drop["holder"] not in (None, me["id"]):
            continue
        left = drop["capture_s"] - drop["progress"] if drop["holder"] == me["id"] else drop["capture_s"]
        arrival = distance(pos, drop["pos"]) / speed
        if distance(opponent, drop["pos"]) <= drop["radius"] + (arrival + left) * me["stats"]["boost_speed"]:
            continue
        # Stay moving inside the ring while the capture clock runs.
        spot = drop["pos"]
        if distance(pos, spot) < drop["radius"] * 0.85:
            angle = obs["t"] * 1.5
            spot = [spot[0] + math.cos(angle) * drop["radius"] * 0.5,
                    spot[1] + math.sin(angle) * drop["radius"] * 0.5, spot[2]]
        options.append((spot, left, -16.0))

    best, best_cost = None, float("inf")
    toward_enemy = direction(pos, opponent)
    for spot, dwell, bonus in options:
        travel = distance(pos, spot)
        if travel > speed * 1.8 or not reachable_loot_level(pos, spot, arena):
            continue
        approach = direction(pos, spot)
        if sum(a * b for a, b in zip(approach, toward_enemy)) > 0.38:
            # A close-range head-on chase gives up our lateral movement.
            if separation < 100 or distance(spot, opponent) < 85:
                continue
        if distance(spot, zone["center"]) + 3 > zone["radius"]:
            continue
        excess = distance(spot, zone["next_center"]) + 4 - zone["next_radius"]
        if excess > 0:
            # Outside the next circle, require time to collect and walk back before shrink.
            time_needed = 2 * (travel + excess) / speed + dwell + 4
            if zone["shrink_start"] - obs["t"] <= time_needed:
                continue
        if arena:
            # Only divert on a locally walkable line; keep the existing route around walls.
            steps = max(1, math.ceil(travel / (arena.step * 0.5)))
            here = arena.cell(pos)
            clear = arena.open(here)
            for n in range(1, steps + 1):
                cell = arena.cell((pos[0] + n / steps * (spot[0] - pos[0]),
                                   pos[1] + n / steps * (spot[1] - pos[1])))
                if not clear or not arena.open(cell):
                    clear = False
                    break
                if cell != here and abs(arena.ground[cell] - arena.ground[here]) > arena.step * math.dist(cell, here) * 1.19:
                    clear = False
                    break
                here = cell
            if not clear:
                continue
        cost = travel + bonus
        if cost < best_cost:
            best_cost, best = cost, spot
    return best


def can_finish_drop(obs, enemies):
    me = obs["self"]
    for drop in obs.get("drops", []):
        if drop["holder"] != me["id"] or drop["progress"] <= 0:
            continue
        if drop["lands_in"] > 0 or distance(me["pos"], drop["pos"]) >= drop["radius"]:
            continue
        left = max(0, drop["capture_s"] - drop["progress"])
        if left > 1.5 or not me["in_zone"]:
            continue
        zone = obs["zone"]
        shrink_from = max(obs["t"], zone["shrink_start"])
        shrinking_for = max(0, obs["t"] + left - shrink_from)
        fraction = min(1, shrinking_for / max(0.001, zone["shrink_end"] - shrink_from))
        center = [a + fraction * (b - a) for a, b in zip(zone["center"], zone["next_center"])]
        radius = zone["radius"] + fraction * (zone["next_radius"] - zone["radius"])
        if distance(me["pos"], center) + 1 > radius:
            continue
        # Leave if an observed mech could contest the ring before the reward arrives.
        clearance = drop["radius"] + left * me["stats"]["boost_speed"]
        if all(distance(e["pos"], drop["pos"]) > clearance for e in enemies):
            return True
    return False


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
        stats = weapon["stats"]
        charged = weapon.get("charge", 0)
        # The game publishes target HP. Release early only if the accumulated
        # charge suffices even with a 25% discount for armor.
        charged_damage = stats["damage"] * min(1, charged / stats["charge"])
        sufficient = (charged >= stats["min_charge"]
                      and target.get("hp", math.inf) <= charged_damage * 0.75)
        fire[slot] = not (aligned and (charged >= stats["charge"] or sufficient))
    elif weapon["kind"] == "lightning":
        # This slot uses a yaw cone and ignores pitch under mechfight/1.
        fire[slot] = yaw_error <= math.radians(weapon["stats"]["cone_deg"])
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
        self.equipment = Equipment(hello["config"])
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
        self.last_hit_bearing = None
        self.watch_bearing_until = -1
        self.sample = None
        self.detour_until = -1
        self.last_moving = False
        self.recharging = False

    def act(self, obs: mf.Observation) -> mf.Action:
        me, zone, t = obs["self"], obs["zone"], obs["t"]
        pos, center = me["pos"], zone["next_center"]
        if self.arena is not None:
            self.arena.body_radius = me["stats"]["radius"]
        radius = max(0, zone["next_radius"] - min(15, zone["next_radius"] * 0.2))
        enemies = sorted((e for e in obs["mechs"] if e["kind"] == "mech"),
                         key=lambda e: distance(pos, e["pos"]))
        hurt = me["hp"] < 0.65 * me["max_hp"]
        crowded = sum(distance(pos, e["pos"]) < 110 for e in enemies) >= 2
        retreat = bool(enemies) and (hurt or crowded)
        rotate = not me["in_zone"] or distance(pos, center) > radius
        # Traveling toward a future circle can start a full minute before
        # the shrink. Reserve full speed for escapes and imminent closures.
        urgent = (not me["in_zone"] or retreat
                  or (rotate and zone["shrink_end"] - t <
                      5 + 1.8 * max(0, distance(pos, center) - radius) / me["stats"]["walk_speed"]))
        goal = center if rotate else loot_goal(obs, center, radius, self.arena)
        if rotate and not enemies:
            detour_goal = early_loot(obs, center, radius, self.arena)
            if detour_goal is not None:
                goal = detour_goal
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
        if len(enemies) == 1 and self.cover_goal is None:
            reward = duel_loot_goal(obs, enemies[0], self.arena)
            if reward is not None:
                move = direction(pos, reward)
        if self.sample is None or t - self.sample[0] >= 0.8:
            if self.sample and self.last_moving and any(move) and distance(pos, self.sample[1]) < 1.2:
                self.detour_until = t + 0.75
                self.side *= -1
            self.sample = t, pos
        detour = any(move) and t < self.detour_until
        if detour:
            move = [-self.side * move[1], self.side * move[0]]
        if can_finish_drop(obs, enemies):
            move = [0.0, 0.0]
            detour = False
        self.last_moving = any(move)
        # Starting another sprint resets the regeneration delay. Bank enough energy
        # for a sustained sprint before resuming after depletion.
        if me["energy"] <= me["max_energy"] * 0.28:
            self.recharging = True
        elif me["energy"] >= me["max_energy"] * 0.65:
            self.recharging = False
        # In the air the same input jets upward. Save it for obstacle recovery.
        sprint = me["grounded"] and (retreat or not me["in_zone"])
        action = {"tick": obs["tick"], "move": move, "jump": bool(detour and me["grounded"]),
                  "boost": self.last_moving and not self.recharging and (sprint or detour),
                  "aim": [math.remainder(t * 0.75, math.tau), 0.0]}
        if obs["offer"] and obs["offer"]["choices"]:
            action["pick"] = self.equipment.upgrade(obs["offer"]["choices"], me, enemies)
        action.update(self.equipment.pickup(obs, enemies, urgent))
        # Commit to a reachable, damaged opponent to finish eliminations.
        weapons = [w for w in me["weapons"] if w]
        gun = next((w for w in weapons if w["kind"] == "gun"), None)
        gun_range = max((w["stats"].get("range", 0) for w in weapons), default=0)
        exposed = [e for e in enemies if not self.arena or not self.arena.screened(pos, e["pos"])]

        def target_cost(enemy):
            dist = distance(pos, enemy["pos"])
            hp = enemy.get("hp", math.inf)
            # Prioritize a possible elimination with the loaded arm gun. Spending
            # a magazine on a healthy opponent can let the damaged one regenerate.
            finish = (gun and gun.get("ammo", 0) >= 2 and gun.get("reload", 0) <= 0
                      and dist <= gun["stats"]["range"]
                      and hp <= gun["stats"]["damage"] * 1.5)
            hp_fraction = hp / max(1, enemy.get("max_hp", 1400)) if math.isfinite(hp) else 1
            return (dist > gun_range, not finish,
                    dist + 85 * hp_fraction - 20 * (enemy["id"] == self.target_id))

        target = min(exposed or enemies, key=target_cost, default=None)
        self.target_id = target["id"] if target else None
        # Damage bearings point toward the source even when it is outside our field of view.
        for event in obs["events"]:
            if (event["type"] == "damaged" and event.get("bearing") is not None
                    and event["weapon"] in ("gun", "laser", "lightning", "mortar")
                    and event.get("by") != me["id"]):
                self.last_hit_bearing = event["bearing"]
                self.watch_bearing_until = t + 1.2
        watch_bearing = not exposed and t < self.watch_bearing_until
        if not target and not watch_bearing and not hurt and me["in_zone"]:
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
            behind_cover = bool(enemies and not exposed)
            if not behind_cover:
                action.update(engage(me, target, urgent))
        if watch_bearing:
            action["aim"] = [self.last_hit_bearing, 0.0]
        # The game's five-second sight memory can outlast a whole reload.
        # Top up while the remembered opponent is behind a building.
        if not target or (enemies and not exposed):
            gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
            action["reload"] = bool(gun and gun.get("reload", 0) <= 0
                                    and gun["ammo"] < gun["stats"]["mag"] * 0.65)
        return action


if __name__ == "__main__":
    mf.run(Bot)
