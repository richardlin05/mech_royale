import math
import unittest

from arena_nav import Arena
from zone_policy import ZonePolicy


class PatrolTests(unittest.TestCase):
    def destination(self, radius, position):
        policy = ZonePolicy()
        obs = {"self": {"pos": [position, 0, 0]}, "t": 10}
        return policy.patrol(obs, (0, 0), radius, 1, None)

    def test_large_circle_keeps_the_search_on_our_side(self):
        point = self.destination(300, 230)
        self.assertAlmostEqual(math.hypot(*point), 230)
        self.assertGreater(point[0], 0)

    def test_large_circle_patrol_stays_clear_of_the_edge(self):
        self.assertAlmostEqual(math.hypot(*self.destination(300, 299)), 255)

    def test_small_circle_keeps_original_patrol_radius(self):
        self.assertAlmostEqual(math.hypot(*self.destination(70, 59)), 49)


class TwoCellArena(Arena):
    def __init__(self, farther_shelter):
        self.x = self.y = 0
        self.ground = {(0, 0): 0, (1, 0): 0}
        self.body_radius = 2.5
        self.clearance_limit = 12
        self.walk_edges = {(0, 0): [((1, 0), 1, 10)], (1, 0): []}
        self.farther_shelter = farther_shelter

    def screened(self, spot, opponent):
        return opponent[0] < 40 or (self.farther_shelter and spot[0] == 5)


class CoverTests(unittest.TestCase):
    start = (0, 0, 0)
    enemies = [{"pos": (x, 0, 0)} for x in (10, 20, 30, 40)]

    def test_checks_past_the_three_nearest_before_staying_still(self):
        arena = TwoCellArena(True)
        self.assertEqual(arena.cover(self.start, self.enemies[:3], (0, 0), 60), self.start)
        self.assertEqual(arena.cover(self.start, self.enemies, (0, 0), 60), (5, 0, 0))

    def test_keeps_partial_shelter_when_neither_cell_screens_everyone(self):
        arena = TwoCellArena(False)
        self.assertEqual(arena.cover(self.start, self.enemies, (0, 0), 60), self.start)
