"""Select a useful distance for a favorable single-opponent game encounter."""
import math


def duel_advance(me, enemy, side, center, safe_radius, arena):
    pos, dest = me["pos"], enemy["pos"]
    gap = math.dist(pos[:2], dest[:2])
    if gap <= 1 or me["hp"] < 0.78 * me["max_hp"] or abs(pos[2] - dest[2]) > 15:
        return None
    slots = [w for w in me["weapons"] if w]
    gun = next((w for w in slots if w["kind"] == "gun"), None)
    arc = next((w for w in slots if w["kind"] == "lightning"), None)
    enemy_hp = enemy.get("hp", math.inf)
    # Use one loaded magazine as an upper bound, with a margin for missed shots.
    finishing = gun and gun.get("ammo", 0) * gun["stats"]["damage"] * 0.65 >= enemy_hp
    if (arc and me["energy"] >= 0.35 * me["max_energy"]
            and ("mortar" not in enemy.get("weapons", ()) or finishing)
            and (enemy_hp <= me["hp"] * 1.1 or finishing)):
        preferred = 0.76 * arc["stats"]["range"]
        # Still orbit when fighting inside the effective arc. Running directly
        # through the target would expose the mech's back during the turn.
        lateral = 0.45
    elif finishing:
        preferred = min(95, 0.55 * gun["stats"]["range"])
        lateral = 0.65
    else:
        return None
    if gap <= preferred:
        return None
    if arena is not None and arena.screened(pos, dest):
        return None
    toward = [(dest[k] - pos[k]) / gap for k in (0, 1)]
    lateral_dir = [-side * toward[1], side * toward[0]]
    # Blend into orbit rather than overshooting the desired distance.
    advance = min(1, (gap - preferred) / 12)
    vx, vy = [advance * toward[k] + lateral * lateral_dir[k] for k in (0, 1)]
    norm = math.hypot(vx, vy)
    move = [vx / norm, vy / norm]
    lookahead = me["stats"]["boost_speed"] * 0.75
    future = [pos[k] + lookahead * move[k] for k in (0, 1)]
    if math.dist(future, center) + me["stats"]["radius"] >= safe_radius:
        return None
    if arena is not None:
        previous = arena.cell(pos)
        for n in range(1, 7):
            cell = arena.cell([pos[k] + lookahead * move[k] * n / 6 for k in (0, 1)])
            if cell != previous and not arena.walkable_step(previous, cell):
                return None
            previous = cell
    sprint = gap > preferred + 15 and me["energy"] >= me["max_energy"] * 0.52
    return move, sprint
