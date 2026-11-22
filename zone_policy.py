"""Choose walking destinations inside the game's moving safe circle."""
import math


def forecast(zone, now, seconds):
    start = max(now, zone["shrink_start"])
    remaining = zone["shrink_end"] - start
    fraction = min(1, max(0, now + seconds - start) / max(0.001, remaining))
    center = tuple(a + fraction * (b - a) for a, b in zip(zone["center"], zone["next_center"]))
    return center, zone["radius"] + fraction * (zone["next_radius"] - zone["radius"])


def needs_sprint(obs, radius):
    """Check both the final travel deadline and the nearer moving edge."""
    me, zone, now = obs["self"], obs["zone"], obs["t"]
    if not me["in_zone"]:
        return True
    pos = me["pos"][:2]
    distance_left = math.dist(pos, zone["next_center"]) - radius
    if distance_left <= 0:
        return False
    # Leave time to turn and to walk around obstacles en route.
    speed = me["stats"]["walk_speed"]
    if zone["shrink_end"] - now < 5 + 1.8 * distance_left / speed:
        return True
    if now + 3 <= zone["shrink_start"]:
        return False
    center, edge = forecast(zone, now, 3)
    return math.dist(pos, center) + me["stats"]["radius"] > edge


class ZonePolicy:
    def __init__(self):
        self.patrol_goal = None
        self.patrol_until = 0
        self.patrol_history = []

    @staticmethod
    def entry(obs, radius, arena):
        """Enter the near side of the circle using open ground where available."""
        me, zone = obs["self"], obs["zone"]
        if me["in_zone"]:
            center = zone["next_center"]
        else:
            center, radius = forecast(zone, obs["t"], 2)
        pos = me["pos"][:2]
        radius = max(0, radius - min(12, radius * 0.35))
        if math.dist(pos, center) < radius:
            return center
        angle = math.atan2(pos[1] - center[1], pos[0] - center[0])
        best, best_dist = None, math.inf
        for offset in (0, 0.16, -0.16, 0.4, -0.4, 0.85, -0.85):
            for scale in (1, 0.8, 0.45, 0):
                x = center[0] + radius * scale * math.cos(angle + offset)
                y = center[1] + radius * scale * math.sin(angle + offset)
                if arena is None:
                    return x, y
                cell = arena.cell((x, y))
                if not arena.open(cell):
                    continue
                point = arena.point(cell)
                if math.dist(point, center) > radius:
                    continue
                travel = math.dist(pos, point)
                if travel < best_dist:
                    best_dist, best = travel, point
        return best if best is not None else center

    def patrol(self, obs, center, radius, side, arena):
        """Keep one walkable search destination long enough to route around a wall."""
        pos, now = obs["self"]["pos"][:2], obs["t"]
        if (self.patrol_goal and now < self.patrol_until
                and math.dist(self.patrol_goal, center) < radius
                and math.dist(self.patrol_goal, pos) > 4):
            return self.patrol_goal
        # Vary search depth inside large circles so revisiting the same ring
        # is less attractive than crossing a fresh patch of the loot field.
        angle = math.atan2(pos[1] - center[1], pos[0] - center[0])
        best, best_value = None, -math.inf
        for orbit in (min(0.75 * radius, 165), min(0.42 * radius, 90), min(0.2 * radius, 45)):
            for offset in (0.55, 1.0, -0.65, 1.8, -1.5, math.pi):
                point = (center[0] + orbit * math.cos(angle + side * offset),
                         center[1] + orbit * math.sin(angle + side * offset))
                if arena and not arena.open(arena.cell(point)):
                    continue
                travel = math.dist(pos, point)
                if travel < min(8, radius * 0.3):
                    continue
                novelty = min((math.dist(point, old) for old in self.patrol_history), default=100)
                # Prefer unexplored destinations within one manageable walking leg.
                score = min(novelty, 100) - 0.7 * abs(travel - min(75, radius * 0.7))
                if score > best_value:
                    best, best_value = point, score
        if best:
            self.patrol_goal = best
            self.patrol_until = now + max(8, min(18, 2 + math.dist(pos, best) / obs["self"]["stats"]["walk_speed"]))
            self.patrol_history = (self.patrol_history + [best])[-8:]
            return best
        self.patrol_goal = None
        return center
