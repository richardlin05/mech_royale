"""Coarse navigation grid derived from the match's read-only arena."""
import heapq
import json
import math
from array import array
from pathlib import Path
import sys


def inside(x, y, ring):
    result = False
    ax, ay = ring[-2:]
    for bx, by in zip(ring[::2], ring[1::2]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            result = not result
        ax, ay = bx, by
    return result


class Arena:
    step = 5
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1),
                  (1, 1), (1, -1), (-1, 1), (-1, -1))

    def __init__(self, folder):
        folder = Path(folder) / "v2"
        world = json.loads((folder / "world.json").read_text())
        terrain = world["terrain"]
        elevation = array("h")
        elevation.frombytes((folder / terrain["file"]).read_bytes())
        if sys.byteorder != "little":
            elevation.byteswap()
        bounds = world["bounds"]
        self.x, self.y = bounds["minX"], bounds["minY"]
        self.width = int((bounds["maxX"] - self.x) / self.step) + 1
        self.height = int((bounds["maxY"] - self.y) / self.step) + 1
        self.ground = {}
        self.solids = {}
        self.blocked = set()
        for i in range(self.width):
            for j in range(self.height):
                x, y = self.point((i, j))
                col = round((x - terrain["minX"]) / terrain["step"])
                row = round((y - terrain["minY"]) / terrain["step"])
                self.ground[i, j] = elevation[row * terrain["nx"] + col] * terrain["scale"]
        for prism in world["prisms"]:
            ring = prism["ring"]
            low = self.cell((min(ring[::2]), min(ring[1::2])))
            high = self.cell((max(ring[::2]), max(ring[1::2])))
            for i in range(low[0], high[0] + 1):
                for j in range(low[1], high[1] + 1):
                    cell = i, j
                    x, y = self.point(cell)
                    if cell not in self.ground or not inside(x, y, ring):
                        continue
                    if any(inside(x, y, hole) for hole in prism["holes"]):
                        continue
                    base, top = prism["base"], prism["top"]
                    self.solids.setdefault(cell, []).append((base, top))
                    ground = self.ground[cell]
                    if top > ground + 1.2 and base < ground + 9:
                        self.blocked.add(cell)
        self.path = []
        self.destination = None
        self.replan_at = 0

    def cell(self, pos):
        return (round((pos[0] - self.x) / self.step), round((pos[1] - self.y) / self.step))

    def point(self, cell):
        return self.x + cell[0] * self.step, self.y + cell[1] * self.step

    def open(self, cell):
        return cell in self.ground and cell not in self.blocked

    def screened(self, pos, enemy):
        length = math.dist(pos[:2], enemy[:2])
        steps = max(1, math.ceil(length / self.step))
        for n in range(1, steps):
            f = n / steps
            cell = self.cell((pos[0] + f * (enemy[0] - pos[0]), pos[1] + f * (enemy[1] - pos[1])))
            z = pos[2] + 4.5 + f * (enemy[2] + 7 - pos[2] - 4.5)
            if self.ground.get(cell, -1000) > z or any(a < z < b for a, b in self.solids.get(cell, ())):
                return True
        return False

    def cover(self, pos, enemies, center, radius):
        best, best_cost = None, float("inf")
        enemies = enemies[:3]
        if math.dist(pos[:2], center) <= radius and all(self.screened(pos, e["pos"]) for e in enemies):
            return pos
        start = self.cell(pos)
        for dx, dy in self.directions:
            for stride in (2, 4, 7):
                cell = start[0] + dx * stride, start[1] + dy * stride
                if not self.open(cell):
                    continue
                x, y = self.point(cell)
                if math.hypot(x - center[0], y - center[1]) > radius:
                    continue
                spot = x, y, self.ground[cell]
                hidden = sum(self.screened(spot, e["pos"]) for e in enemies)
                cost = math.dist(pos[:2], spot[:2]) - hidden * 40
                if hidden and cost < best_cost:
                    best, best_cost = spot, cost
        return best

    def waypoint(self, pos, goal, now):
        start, end = self.cell(pos), self.cell(goal)
        if not self.open(start):
            return goal
        if not self.open(end):
            nearby = ((end[0] + dx, end[1] + dy) for dx in range(-4, 5) for dy in range(-4, 5))
            end = min((c for c in nearby if self.open(c)), key=lambda c: math.dist(self.point(c), goal[:2]), default=start)
        if self.destination != end or now >= self.replan_at:
            self.destination, self.replan_at = end, now + 1.5
            self.path = self.route(start, end)
        while self.path and math.dist(pos[:2], self.point(self.path[-1])) < 3.5:
            self.path.pop()
        return self.point(self.path[-1]) if self.path else goal

    def route(self, start, end):
        # Bound work per observation. A partial route still advances toward the goal.
        queue = [(math.dist(start, end), 0, start)]
        cost, parent = {start: 0}, {}
        best = start
        for _ in range(800):
            if not queue:
                break
            _, g, here = heapq.heappop(queue)
            if g != cost[here]:
                continue
            if math.dist(here, end) < math.dist(best, end):
                best = here
            if here == end:
                break
            i, j = here
            for dx, dy in self.directions:
                there = i + dx, j + dy
                if not self.open(there) or (dx and dy and
                        (not self.open((i + dx, j)) or not self.open((i, j + dy)))):
                    continue
                step = math.hypot(dx, dy)
                if abs(self.ground[there] - self.ground[here]) > step * self.step * 1.19:
                    continue
                new = g + step
                if new < cost.get(there, math.inf):
                    cost[there], parent[there] = new, here
                    heapq.heappush(queue, (new + 1.3 * math.dist(there, end), new, there))
        path = []
        while best != start:
            path.append(best)
            best = parent[best]
        return path
