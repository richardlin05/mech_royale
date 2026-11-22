import math
import unittest

from example_bot import crate_position, loot_goal


class Grid:
    step = 1

    def __init__(self):
        self.ground = {(x, y): 0 for x in range(-20, 21) for y in range(-20, 21)}
        self.walls = set()

    def cell(self, pos):
        return round(pos[0]), round(pos[1])

    def point(self, cell):
        return cell

    def open(self, cell):
        return cell in self.ground and cell not in self.walls

    def walkable_step(self, start, end):
        return self.open(end)

    def screened(self, pos, crate):
        return False


class CratePositionTests(unittest.TestCase):
    def setUp(self):
        self.me = {"pos": [3, 0, 0], "energy": 100, "weapons": [{"kind": "gun"}, None],
                   "stats": {"muzzle_height": 7, "min_pitch": -0.7, "walk_speed": 11.7}}
        self.crate = {"pos": [0, 0, 0], "hp": 300}

    def test_close_crate_gives_room_to_tilt_down(self):
        goal = crate_position(self.me, self.crate, [0, 0], 100, None)
        self.assertGreater(goal[0], self.me["pos"][0])
        self.assertGreater(math.atan2(-7, math.hypot(*goal)), -0.7)

    def test_distant_crate_allows_normal_approach(self):
        self.me["pos"] = [80, 0, 0]
        self.assertEqual(crate_position(self.me, self.crate, [0, 0], 100, None), self.crate["pos"])

    def test_close_cube_has_first_priority(self):
        obs = {"self": self.me, "cubes": [{"pos": [4, 0, 0]}], "pickups": [], "crates": [self.crate]}
        self.assertEqual(loot_goal(obs, [0, 0], 100), [4, 0, 0])

    def test_game_lightning_does_not_need_pitch(self):
        self.me["weapons"][1] = {"kind": "lightning", "stats": {"energy": 3}}
        self.assertEqual(crate_position(self.me, self.crate, [0, 0], 100, None), self.crate["pos"])

    def test_stays_in_safe_circle_at_its_edge(self):
        center = [-10, 0]
        goal = crate_position(self.me, self.crate, center, 13, Grid())
        self.assertNotEqual(tuple(goal), tuple(self.crate["pos"]))
        self.assertLessEqual(math.dist(goal[:2], center), 13)

    def test_rejects_blocked_route_to_open_standing_cell(self):
        grid = Grid()
        grid.walls.update((5, y) for y in range(-20, 21))
        goal = crate_position(self.me, self.crate, [0, 0], 100, grid)
        self.assertLess(goal[0], 5)
        self.assertNotEqual(tuple(goal), tuple(self.crate["pos"]))

    def test_falls_back_to_crate_approach_when_all_angles_are_screened(self):
        grid = Grid()
        grid.screened = lambda pos, crate: True
        goal = crate_position(self.me, self.crate, [0, 0], 100, grid)
        self.assertEqual(goal, self.crate["pos"])
