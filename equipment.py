"""Choose upgrades and eligible ground items using the current match configuration."""
import math


def cycle_damage(stats):
    shots = stats["mag"]
    return stats["damage"] * shots / (shots * stats["cooldown"] + stats["reload"])


class Equipment:
    def __init__(self, config):
        self.upgrades = {u["id"]: u for u in config["upgrades"]}
        self.weapons = config["weapons"]
        self.pickup_radius = config["loot"]["pickup_radius"]
        self.equip_time = config["loot"]["equip_s"]

    def upgrade(self, choices, me, enemies):
        # Protect an injured mech first; prioritize recovery when out of contact.
        if me["hp"] < 0.60 * me["max_hp"]:
            defensive = ("plating", "armor", "nanites") if enemies else ("nanites", "plating", "armor")
            for name in defensive:
                for i, choice in enumerate(choices):
                    if choice["id"] == name:
                        return i

        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        # These are strategy weights. Gun magazine, reload, damage and fire-rate
        # upgrades are instead valued by their actual marginal sustained output.
        priorities = {"nanites": .20, "plating": .18, "armor": .16, "servos": .14,
                      "gun_velocity": .13, "laser_damage": .12, "lightning_range": .12,
                      "mortar_reload": .11, "laser_charge": .10, "jets": .10,
                      "mortar_splash": .09, "lightning_efficiency": .09, "reactor": .08,
                      "sensors": .07, "mortar_velocity": .06, "gyros": .05,
                      "capacitor": .04, "lightning_chain": .03, "laser_pierce": .02}
        def value(choice):
            name = choice["id"]
            if gun and name in ("gun_mag", "gun_rate", "gun_damage") and name in self.upgrades:
                before = gun["stats"]
                after = before.copy()
                for effect in self.upgrades[name]["effects"]:
                    stat = effect["path"].removeprefix("weapons.gun.")
                    if stat in after:
                        after[stat] = after[stat] * effect.get("mul", 1) + effect.get("add", 0)
                return cycle_damage(after) / cycle_damage(before) - 1
            return priorities.get(name, 0)
        return max(range(len(choices)), key=lambda i: value(choices[i]))

    def pickup(self, obs, enemies, mobile):
        me = obs["self"]
        pos = me["pos"]
        slots = me["weapons"]
        held = {w["kind"] for w in slots if w}
        nearby = [p for p in obs["pickups"] if p["kind"] != "gun" and p["kind"] not in held
                  and math.dist(pos[:2], p["pos"][:2]) <= self.pickup_radius
                  and abs(pos[2] - p["pos"][2]) <= 4]
        if not nearby:
            return {}
        enemy = min(enemies, key=lambda e: math.dist(pos, e["pos"]), default=None)
        # For an empty field, the current circle limits how far the next duel can be.
        separation = math.dist(pos, enemy["pos"]) if enemy else min(110.0, 1.4 * obs["zone"]["radius"])
        def value(kind, stats):
            if kind == "lightning":
                if separation > stats["range"] or me["energy"] < stats["energy"] + 12:
                    return 0
                return stats["damage"] / stats["cooldown"]
            if kind == "laser":
                if separation > stats["range"] or (enemy and mobile):
                    return 0
                counter = 1 + stats["cookoff"] if enemy and "mortar" in enemy.get("weapons", []) else 1
                return counter * stats["damage"] / (stats["charge"] + stats["cooldown"])
            # Approximate effective mortar output on a level field. Travel time
            # discounts slow shells against mobile game actors at longer distances.
            if kind == "mortar" and 2 * stats["splash_radius"] <= separation <= stats["speed"] ** 2 / stats["gravity"]:
                return (stats["damage"] + stats["splash"]) / (stats["cooldown"] + separation / stats["speed"])
            return 0
        # Upgrades on a previously dropped weapon apply again when it is collected.
        def rank(p):
            kind = p["kind"]
            stats = self.weapons[kind].copy()
            for upgrade in me["upgrades"]:
                definition = self.upgrades.get(upgrade, {})
                if definition.get("requires") == kind:
                    for effect in definition["effects"]:
                        stat = effect["path"].split(".")[-1]
                        if stat in stats:
                            stats[stat] = stats[stat] * effect.get("mul", 1) + effect.get("add", 0)
            return value(kind, stats), -math.dist(pos, p["pos"]), -p["id"]

        best = max(nearby, key=rank)
        if None in slots:
            return {"take": best["id"]}
        # Keep the gun. Swaps cost equip time and a charging laser cannot be dropped.
        slot = next((i for i, w in enumerate(slots) if w["kind"] != "gun"), None)
        if slot is None:
            return {}
        current = slots[slot]
        if current.get("charge", 0) > 0 or current["cooldown"] > 0:
            return {}
        old_value = value(current["kind"], current["stats"])
        new_value = rank(best)[0]
        if new_value <= max(20, 1.4 * old_value):
            return {}
        if enemy and old_value > 0:
            # A strong counter can pay for its equip delay during a sustained
            # encounter. Keep the ready item for a short engagement.
            counters_enemy = ((best["kind"] == "laser" and "mortar" in enemy.get("weapons", ())) or
                              (best["kind"] == "lightning" and "laser" in enemy.get("weapons", ())))
            if not counters_enemy:
                return {}
            gun = next((w for w in slots if w and w["kind"] == "gun"), None)
            combined = old_value + (cycle_damage(gun["stats"]) if gun else 0)
            horizon = min(4.0, enemy.get("hp", 0) / max(1, combined))
            delay = max(self.equip_time, self.weapons[best["kind"]]["cooldown"])
            if (horizon - delay) * new_value < 1.15 * horizon * old_value:
                return {}
        return {"drop": slot, "take": best["id"]}
