"""Decisions based on the two equipment slots, live cooldowns and published HP."""
import math


def charged_damage(weapon, target, multiplier):
    stats = weapon["stats"]
    fraction = min(1.0, weapon.get("charge", 0) / stats["charge"])
    # Both listed bounds are conservative for a charge scaling up from min_frac.
    damage = stats["damage"] * max(stats.get("min_frac", 0), fraction) * multiplier
    if "mortar" in target.get("weapons", []):
        damage *= 1 + stats.get("cookoff", 0)
    return damage * (0.75 if target.get("kind", "mech") == "mech" else 1)


def finish_priority(me, target, dist, multiplier, urgent):
    hp = target.get("hp", math.inf)
    rank = 2
    for w in me["weapons"]:
        if not w or w["cooldown"] > 0.3:
            continue
        stats = w["stats"]
        if dist > stats.get("range", 0):
            continue
        kind = w["kind"]
        damage = 0.75 * multiplier * stats["damage"]
        if kind == "gun" and w.get("reload", 0) <= 0:
            ammo = w.get("ammo", 0)
            if ammo >= 1 and hp <= damage:
                return 0
            if ammo >= 2 and hp <= 2 * damage:
                rank = 1
        elif kind == "lightning" and me["energy"] >= stats["energy"] + 12 and hp <= damage:
            return 0
        elif kind == "laser" and not urgent and w.get("charge", 0) >= stats["min_charge"]:
            if hp <= charged_damage(w, target, multiplier):
                return 0
    return rank


def reload_window(me, gun, contacts, action, calm_travel=False):
    threshold = 0.9 if calm_travel and not contacts else 0.65
    if not gun or gun.get("reload", 0) > 0 or gun["ammo"] >= gun["stats"]["mag"] * threshold:
        return False
    slot = me["weapons"].index(gun)
    if action.get("fire", [False, False])[slot]:
        return False
    # Allow for both mechs closing the gap during the complete reload.
    reach = gun["stats"]["range"] + 2 * me["stats"]["boost_speed"] * gun["stats"]["reload"]
    return all(math.dist(me["pos"], other["pos"]) > reach for other in contacts)
