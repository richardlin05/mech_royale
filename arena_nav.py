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
        self.body_radius = 2.5
        self.body_height = 9.0
        self.headroom = {}
        self.bounds = bounds
        self.prisms_by_tile = {}
        # Distances within one grid step of even a large mech's hull are
        # computed at startup, so route expansion only needs a dictionary lookup.
        self.clearance = {}
        self.clearance_limit = 12.0
        for i in range(self.width):
            for j in range(self.height):
                x, y = self.point((i, j))
                col = round((x - terrain["minX"]) / terrain["step"])
                row = round((y - terrain["minY"]) / terrain["step"])
                self.ground[i, j] = elevation[row * terrain["nx"] + col] * terrain["scale"]
                self.clearance[i, j] = min(x - self.x, y - self.y, bounds["maxX"] - x, bounds["maxY"] - y,
                                           self.clearance_limit)
        for prism in world["prisms"]:
            ring = prism["ring"]
            # Physical footprints near the final goal can differ from the tile center.
            pad = self.clearance_limit
            for tx in range(math.floor((min(ring[::2]) - pad) / 30), math.floor((max(ring[::2]) + pad) / 30) + 1):
                for ty in range(math.floor((min(ring[1::2]) - pad) / 30), math.floor((max(ring[1::2]) + pad) / 30) + 1):
                    self.prisms_by_tile.setdefault((tx, ty), []).append(prism)
            for boundary in (ring, *prism["holes"]):
                self.add_wall_clearance(boundary, prism["base"], prism["top"])
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
                    if top > ground + 1.2:
                        if base < ground + 9:
                            self.blocked.add(cell)
                        else:
                            self.headroom[cell] = min(base - ground, self.headroom.get(cell, math.inf))
        self.walk_edges = self.build_walk_edges(terrain, elevation)
        self.regions = self.build_regions()
        self.pending = None
        self.path = []
        self.destination = None
        self.anchor = None
        self.route_radius = self.body_radius
        self.route_height = self.body_height
        self.replan_at = 0

    def build_walk_edges(self, terrain, elevation):
        """Sample each walking edge at the native terrain spacing before play."""
        nx, ny = terrain["nx"], terrain["ny"]
        def height(x, y):
            tx = (x - terrain["minX"]) / terrain["step"]
            ty = (y - terrain["minY"]) / terrain["step"]
            col = min(nx - 2, max(0, int(tx)))
            row = min(ny - 2, max(0, int(ty)))
            fx, fy = tx - col, ty - row
            i = row * nx + col
            south = elevation[i] * (1 - fx) + elevation[i + 1] * fx
            north = elevation[i + nx] * (1 - fx) + elevation[i + nx + 1] * fx
            return terrain["scale"] * (south * (1 - fy) + north * fy)

        edges = {cell: [] for cell in self.ground if cell not in self.blocked}
        samples = max(1, math.ceil(self.step / terrain["step"]))
        for here, links in edges.items():
            i, j = here
            x, y = self.point(here)
            initial = height(x, y)
            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                there = i + dx, j + dy
                if there not in edges:
                    continue
                clearance = min(self.clearance[here], self.clearance[there])
                if dx and dy:
                    if (i + dx, j) not in edges or (i, j + dy) not in edges:
                        continue
                    clearance = min(clearance, self.clearance[i + dx, j], self.clearance[i, j + dy])
                length = math.hypot(dx, dy)
                max_rise = self.step * length / samples * 1.19
                last = initial
                forward, reverse = True, True
                for n in range(1, samples + 1):
                    offset = n * self.step / samples
                    now = height(x + dx * offset, y + dy * offset)
                    forward = forward and now - last <= max_rise
                    reverse = reverse and last - now <= max_rise
                    last = now
                if forward:
                    links.append((there, length, clearance))
                if reverse:
                    edges[there].append((here, length, clearance))
        return edges

    def build_regions(self):
        # Weak connectivity at spawn size rules out permanently disconnected goals.
        # A label match is necessary; the directed planner still checks slope and size.
        parent = {c: c for c in self.walk_edges}
        def root(cell):
            while parent[cell] != cell:
                parent[cell] = parent[parent[cell]]
                cell = parent[cell]
            return cell
        for cell, edges in self.walk_edges.items():
            leader = root(cell)
            for neighbor, _, gap in edges:
                if gap >= self.body_radius:
                    other = root(neighbor)
                    if other != leader:
                        parent[other] = leader
        return {cell: root(cell) for cell in parent}

    def point_fits(self, point):
        cell = self.cell(point)
        x, y = point[:2]
        r = self.body_radius
        b = self.bounds
        if min(x-b["minX"], b["maxX"]-x, y-b["minY"], b["maxY"]-y) < r or cell not in self.ground:
            return False
        ground = self.ground[cell]
        for prism in self.prisms_by_tile.get((math.floor(x / 30), math.floor(y / 30)), ()):
            if prism["top"] <= ground + 1.2 or prism["base"] >= ground + self.body_height:
                continue
            ring, holes = prism["ring"], prism["holes"]
            if inside(x, y, ring) and not any(inside(x, y, h) for h in holes):
                return False
            for boundary in (ring, *holes):
                ax, ay = boundary[-2:]
                for bx, by in zip(boundary[::2], boundary[1::2]):
                    dx, dy = bx-ax, by-ay
                    length2 = dx*dx + dy*dy
                    u = max(0, min(1, ((x-ax)*dx + (y-ay)*dy) / length2)) if length2 else 0
                    if (x-ax-u*dx)**2 + (y-ay-u*dy)**2 < r*r:
                        return False
                    ax, ay = bx, by
        return True

    def add_wall_clearance(self, ring, base, top):
        """Find nearby grid points where the edge can collide with a walking mech."""
        ax, ay = ring[-2:]
        for bx, by in zip(ring[::2], ring[1::2]):
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            if length2:
                low = self.cell((min(ax, bx) - self.clearance_limit, min(ay, by) - self.clearance_limit))
                high = self.cell((max(ax, bx) + self.clearance_limit, max(ay, by) + self.clearance_limit))
                for i in range(max(0, low[0]), min(self.width, high[0] + 1)):
                    for j in range(max(0, low[1]), min(self.height, high[1] + 1)):
                        cell = i, j
                        ground = self.ground[cell]
                        if top <= ground + 1.2 or base >= ground + 9:
                            continue
                        x, y = self.point(cell)
                        fraction = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / length2))
                        gap = math.hypot(x - ax - fraction * dx, y - ay - fraction * dy)
                        if gap < self.clearance[cell]:
                            self.clearance[cell] = gap
            ax, ay = bx, by

    def cell(self, pos):
        return (round((pos[0] - self.x) / self.step), round((pos[1] - self.y) / self.step))

    def point(self, cell):
        return self.x + cell[0] * self.step, self.y + cell[1] * self.step

    def open(self, cell):
        return (cell not in self.blocked and self.clearance.get(cell, -1) >= min(self.body_radius, self.clearance_limit)
                and self.headroom.get(cell, math.inf) >= self.body_height)

    def walkable_step(self, start, end):
        required = min(self.body_radius, self.clearance_limit)
        if self.body_height > 9 and self.headroom.get(end, math.inf) < self.body_height:
            return False
        return any(cell == end and gap >= required for cell, _, gap in self.walk_edges.get(start, ()))

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
        enemies = enemies[:3]
        if not enemies:
            return None
        if math.dist(pos[:2], center) <= radius and all(self.screened(pos, e["pos"]) for e in enemies):
            return pos
        start = self.cell(pos)
        if start not in self.walk_edges:
            return None
        # Explore in walking-distance order. A wall can make a spot ten meters
        # away take much longer to reach than a nearby doorway on the same side.
        required = min(self.body_radius, self.clearance_limit)
        queue = [(0.0, start)]
        paths = {start: 0.0}
        best, best_cost = None, math.inf
        while queue:
            steps, cell = heapq.heappop(queue)
            meters = steps * self.step
            if meters > 40 or meters - 40 * len(enemies) >= best_cost:
                break
            if steps != paths[cell]:
                continue
            x, y = self.point(cell)
            # Check nearby cells densely, then use a ten-meter lattice to keep
            # sight-line sampling bounded during a crowded observation.
            dx, dy = cell[0] - start[0], cell[1] - start[1]
            candidate = meters <= 12 or (dx % 2 == 0 and dy % 2 == 0)
            if cell != start and candidate and math.hypot(x - center[0], y - center[1]) <= radius:
                spot = x, y, self.ground[cell]
                hidden = sum(self.screened(spot, e["pos"]) for e in enemies)
                cost = meters - 40 * hidden
                if hidden and cost < best_cost:
                    best, best_cost = spot, cost
            for neighbor, length, gap in self.walk_edges[cell]:
                new = steps + length
                if gap >= required and self.headroom.get(neighbor, math.inf) >= self.body_height and new < paths.get(neighbor, math.inf):
                    paths[neighbor] = new
                    heapq.heappush(queue, (new, neighbor))
        return best

    def waypoint(self, pos, goal, now):
        start, requested = self.cell(pos), self.cell(goal)
        if start not in self.ground or start in self.blocked:
            return goal  # The ground grid does not describe travel on a roof.
        if not self.open(start):
            # The actor's actual position can legally clear a wall even when
            # the nearest grid center does not. Its graph edges all inherit
            # that center's inadequate clearance. Step back onto the graph.
            # Preserve slope and wall-corner checks from the original graph.
            points = (self.point(cell) for cell, _, _ in self.walk_edges.get(start, ())
                      if self.open(cell))
            return min(points, key=lambda p: math.dist(pos[:2], p), default=pos)
        end = requested
        region = self.regions[start]
        if not self.open(end) or self.regions.get(end) != region:
            nearby = ((end[0] + dx, end[1] + dy) for dx in range(-4, 5) for dy in range(-4, 5))
            end = min((c for c in nearby if self.open(c) and self.regions.get(c) == region),
                      key=lambda c: math.dist(self.point(c), goal[:2]), default=requested)
        if start == end:
            # A blocked goal such as a zone center inside a building has a safe
            # substitute. Stay at that point once reached.
            return goal if end == requested and self.point_fits(goal) else self.point(end)

        off_path = start != self.anchor and (not self.path or start != self.path[-1])
        continuing = not self.path and self.pending is not None
        if (self.destination != end or now >= self.replan_at or off_path or continuing
                or self.route_radius != self.body_radius or self.route_height != self.body_height):
            self.route_height = self.body_height
            self.route_radius = self.body_radius
            self.destination, self.replan_at = end, now + 1.5
            self.anchor = start
            self.path = self.route(start, end)
        if self.path and start == self.path[-1]:
            self.anchor = self.path.pop()
        # The search may end at the closest reachable point, for example across
        # a wall. Wait here for a replan instead of driving into the wall.
        return self.point(self.path[-1]) if self.path else pos

    def route(self, start, end):
        # Bound work per observation. A partial route still advances toward the goal.
        key = (start, end, self.body_radius, self.body_height)
        if self.pending is not None and self.pending[0] == key:
            _, queue, cost, parent, best = self.pending
        else:
            queue = [(math.dist(start, end), 0, start)]
            cost, parent = {start: 0}, {}
            best = start
        self.pending = None
        required = min(self.body_radius, self.clearance_limit)
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
            for there, step, gap in self.walk_edges.get(here, ()):
                if gap < required or self.headroom.get(there, math.inf) < self.body_height:
                    continue
                new = g + step
                if new < cost.get(there, math.inf):
                    cost[there], parent[there] = new, here
                    heapq.heappush(queue, (new + 1.3 * math.dist(there, end), new, there))
        if queue and best != end:
            self.pending = (key, queue, cost, parent, best)
        path = []
        while best != start:
            path.append(best)
            best = parent[best]
        return path
