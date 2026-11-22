import math
import unittest
from unittest.mock import patch

from zone_policy import ZonePolicy


class Courtyard:
    """A wall separates the two sides except for a passage in the top row."""

    step = 1
    x = y = 0
    body_radius = 0.25
    clearance_limit = 2

    def __init__(self):
        cells = {(x, y) for x in range(12) for y in range(10) if x != 4 or y == 9}
        self.walk_edges = {
            (x, y): [
                ((x + dx, y + dy), 1, 2)
                for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
                if (x + dx, y + dy) in cells
            ]
            for x, y in cells
        }

    @staticmethod
    def point(cell):
        return cell

    @staticmethod
    def cell(pos):
        return tuple(round(value) for value in pos[:2])

    def open(self, cell):
        return cell in self.walk_edges


class CrossingTests(unittest.TestCase):
    def test_enters_at_the_side_reachable_from_the_passage(self):
        entry = ZonePolicy.reachable_entry(Courtyard(), (2, 4), (6, 4), 2.2)
        self.assertLessEqual(math.dist(entry, (6, 4)), 2.2)
        self.assertGreaterEqual(entry[1], 5)

    def test_circle_entirely_inside_wall_uses_fallback(self):
        self.assertIsNone(ZonePolicy.reachable_entry(Courtyard(), (2, 4), (4, 3), 0.1))

    def test_in_zone_search_begins_when_shrink_starts(self):
        policy = ZonePolicy()
        arena = Courtyard()
        obs = {"t": 9, "self": {"pos": [0, 4, 0], "in_zone": True},
               "zone": {"next_center": (6, 4), "shrink_start": 10}}
        with patch.object(policy, "reachable_entry", return_value=(6, 4)) as search:
            policy.entry(obs, 2.2, arena)
            search.assert_not_called()
            obs["t"] = 10
            self.assertEqual(policy.entry(obs, 2.2, arena), (6, 4))
            search.assert_called_once()
