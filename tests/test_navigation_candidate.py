import json
import math
import tempfile
import unittest
from pathlib import Path

from arena_nav import Arena
from zone_policy import ZonePolicy


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        folder = Path(cls.folder.name) / "v2"
        folder.mkdir()
        # A floor-to-ceiling wall separates the east and west halves. A bridge
        # at 11 m tests the change in clearance as cube collection grows a mech.
        world = {
            "bounds": {"minX": 0, "maxX": 100, "minY": 0, "maxY": 60},
            "terrain": {"file": "terrain.i16", "minX": 0, "minY": 0, "step": 1,
                        "nx": 101, "ny": 61, "scale": 0.01},
            "prisms": [
                {"ring": [39, 0, 41, 0, 41, 60, 39, 60], "holes": [], "base": 0, "top": 30},
                {"ring": [15, 20, 25, 20, 25, 40, 15, 40], "holes": [], "base": 11, "top": 16},
            ],
        }
        (folder / "world.json").write_text(json.dumps(world))
        (folder / "terrain.i16").write_bytes(bytes(101 * 61 * 2))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.arena = Arena(self.folder.name)

    def test_bridge_clearance_changes_with_height(self):
        cell = self.arena.cell((20, 30))
        self.assertTrue(self.arena.open(cell))
        self.arena.body_height = 12
        self.assertFalse(self.arena.open(cell))
        self.assertFalse(self.arena.walkable_step((3, 6), cell))

    def test_precise_goal_cannot_push_cylinder_into_the_wall(self):
        self.assertEqual(self.arena.waypoint((35, 30), (37, 30), 0), (35, 30))
        self.assertEqual(self.arena.waypoint((35, 30), (36, 30), 0), (36, 30))

    def test_disconnected_goal_gets_accessible_side(self):
        self.arena.waypoint((10, 30), (45, 30), 0)
        source_region = self.arena.regions[self.arena.cell((10, 30))]
        self.assertEqual(source_region, self.arena.regions[self.arena.destination])
        self.assertEqual(self.arena.point(self.arena.destination), (35, 30))

    def test_deep_route_uses_more_than_one_planning_budget(self):
        # Long single-lane map; each invocation expands at most 800 nodes.
        arena = self.arena
        n = 1100
        arena.walk_edges = {(i, 0): [((i + 1, 0), 1, 12)] for i in range(n)}
        arena.walk_edges[(n, 0)] = []
        first = arena.route((0, 0), (n, 0))
        self.assertNotEqual(first[0], (n, 0))
        self.assertEqual(arena.route((0, 0), (n, 0))[0], (n, 0))

    def test_patrol_explores_multiple_depths(self):
        patrol = ZonePolicy()
        positions = [(0, 0)]
        for tick in range(10):
            obs = {"t": tick * 20, "self": {"pos": [*positions[-1], 0], "stats": {"walk_speed": 12}}}
            positions.append(patrol.patrol(obs, (0, 0), 200, 1, None))
        radii = {round(math.hypot(*p)) for p in positions[1:]}
        self.assertGreaterEqual(len(radii), 2)
        self.assertLess(max(radii), 200)
