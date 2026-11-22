"""Use loadout, remaining HP, and playable space to choose movement in a game duel."""
import math


def isolated_opponent(enemies, pos, arena, sight_memory_distance=150):
    """Allow one nearby encounter when every additional mech is distant behind game geometry."""
    if not enemies:
        return None
    if len(enemies) == 1:
        return enemies[0]
    nearby = enemies[0]  # caller sorts by distance
    if (arena is None or math.dist(pos[:2], nearby["pos"][:2]) > 100
            or arena.screened(pos, nearby["pos"])):
        return None
    for other in enemies[1:]:
        if (math.dist(pos[:2], other["pos"][:2]) < sight_memory_distance
                or not arena.screened(pos, other["pos"])):
            return None
    return nearby


def _legal_move(pos, toward, advance, lateral, side, lookahead, center, radius, arena):
    """Try both sides of the requested orbit, then a more tangential walk."""
    for radial, tangential in ((advance, lateral), (0.45 * advance, 1.0)):
        for turn in (side, -side):
            vx = radial * toward[0] - tangential * turn * toward[1]
            vy = radial * toward[1] + tangential * turn * toward[0]
            norm = math.hypot(vx, vy)
            move = [vx / norm, vy / norm]
            future = [pos[k] + lookahead * move[k] for k in (0, 1)]
            if math.dist(future, center) >= radius:
                continue
            if arena is not None:
                previous = arena.cell(pos)
                for n in range(1, 7):
                    cell = arena.cell([pos[k] + lookahead * move[k] * n / 6 for k in (0, 1)])
                    if cell != previous and not arena.walkable_step(previous, cell):
                        break
                    previous = cell
                else:
                    return move
            else:
                return move
    return None


def duel_advance(me, enemy, side, center, safe_radius, arena, alive=16, enemy_arc_range=45):
    pos, dest = me["pos"], enemy["pos"]
    gap = math.dist(pos[:2], dest[:2])
    if gap <= 1 or abs(pos[2] - dest[2]) > 15:
        return None
    slots = [w for w in me["weapons"] if w]
    gun = next((w for w in slots if w["kind"] == "gun"), None)
    arc = next((w for w in slots if w["kind"] == "lightning"), None)
    hp = enemy.get("hp", math.inf)
    gun_ready = gun and gun.get("reload", 0) <= 0
    finishing = gun_ready and gun.get("ammo", 0) * gun["stats"]["damage"] * 0.65 >= hp
    # The final opponent cannot be overtaken in placement by waiting for another
    # elimination. Use a clear HP and loaded-ammo advantage even below 78% HP.
    last_two = (alive == 2 and finishing and hp * 3 <= me["hp"]
                and me["hp"] >= 0.4 * me["max_hp"])
    own_arc_ready = arc and me["energy"] >= 0.35 * me["max_energy"]
    avoid_arc = ("lightning" in enemy.get("weapons", ()) and not own_arc_ready
                 and not finishing and gap < 1.35 * enemy_arc_range)
    if not avoid_arc and not last_two and me["hp"] < 0.78 * me["max_hp"]:
        return None
    if arena is not None and arena.screened(pos, dest):
        return None

    toward = [(dest[k] - pos[k]) / gap for k in (0, 1)]
    enemy_vel = enemy.get("vel", (0, 0))
    radial_speed = sum(enemy_vel[k] * toward[k] for k in (0, 1))
    walk = me["stats"]["walk_speed"]
    if avoid_arc:
        # Arc shorts a charging laser. Create enough separation to use our
        # ranged slot again, retaining room for the next decision interval.
        advance, lateral = -1.0, 0.35
        sprint = gap < 1.15 * enemy_arc_range and me["energy"] > 0.35 * me["max_energy"]
    elif (own_arc_ready and ("mortar" not in enemy.get("weapons", ()) or finishing)
          and (hp <= me["hp"] * 1.1 or finishing)):
        preferred = 0.76 * arc["stats"]["range"]
        # A retreating opponent can outrun a pure orbit even when it initially
        # starts inside the ring. Match its outward motion as we settle.
        speed_bias = max(0, min(1, radial_speed / walk))
        if gap <= preferred and speed_bias <= 0.15:
            return None
        advance = min(1.6, max(0, (gap - preferred) / 12 + speed_bias))
        lateral = 0.45
        sprint = me["energy"] >= me["max_energy"] * 0.52 and (
            gap > preferred + 15 or (gap > preferred and radial_speed > walk * 0.8))
    elif finishing:
        preferred = min(95, 0.55 * gun["stats"]["range"])
        if gap <= preferred:
            return None
        advance = min(1, (gap - preferred) / 12)
        lateral = 0.65
        sprint = gap > preferred + 15 and me["energy"] >= me["max_energy"] * 0.52
    else:
        return None

    move = _legal_move(pos, toward, advance, lateral, side, me["stats"]["boost_speed"] * 0.75,
                       center, safe_radius - me["stats"]["radius"], arena)
    return (move, sprint) if move is not None else None
