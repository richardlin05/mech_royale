import unittest

from example_bot import supply_waypoint
from resource_policy import SupplyRun


class SupplyRunTests(unittest.TestCase):
    def setUp(self):
        self.policy = SupplyRun({"cubes": {"stat_cap": 10}})
        self.drop = {"id": 20000, "pos": [80, 0, 0], "lands_in": 8, "holder": None,
                     "radius": 8, "capture_s": 4, "progress": 0}
        self.me = {"id": 1, "pos": [0, 0, 0], "hp": 1000, "max_hp": 1400, "cubes": 1,
                   "weapons": [{"kind": "gun"}, {"kind": "laser"}], "in_zone": True,
                   "stats": {"walk_speed": 12, "boost_speed": 20, "radius": 2.5}}
        self.obs = {"self": self.me, "t": 75, "drops": [self.drop], "cubes": [], "pickups": [],
                    "zone": {"center": [50, 0], "radius": 200, "next_center": [50, 0], "next_radius": 60}}

    def test_departs_in_time_for_landing_and_holds_until_collected(self):
        self.drop["lands_in"] = 20
        self.assertIsNone(self.policy.select(self.obs, [], False))
        self.drop["lands_in"] = 8
        self.assertEqual(self.policy.select(self.obs, [], False), self.drop)
        self.me["pos"] = [78, 0, 0]
        self.drop.update(lands_in=0, holder=1, progress=2.5)
        self.obs["t"] += 8
        self.assertEqual(self.policy.select(self.obs, [], False), self.drop)
        self.obs["drops"] = []
        self.assertIsNone(self.policy.select(self.obs, [], False))

    def test_rejects_contested_drop_or_urgent_storm(self):
        self.assertIsNone(self.policy.select(self.obs, [{"pos": [84, 2, 0]}], False))
        self.assertIsNone(self.policy.select(self.obs, [], True))
        self.drop["holder"] = 2
        self.assertIsNone(self.policy.select(self.obs, [], False))

    def test_keeps_gear_search_unless_health_is_critical(self):
        self.me["weapons"][1] = None
        self.assertIsNone(self.policy.select(self.obs, [], False))
        self.me["hp"] = 500
        self.assertEqual(self.policy.select(self.obs, [], False), self.drop)

    def test_yields_after_four_seconds_without_progress(self):
        self.assertEqual(self.policy.select(self.obs, [], False), self.drop)
        self.obs["t"] += 4.2
        self.drop["lands_in"] = 3.8
        self.assertIsNone(self.policy.select(self.obs, [], False))
        self.obs["t"] += 1
        self.assertIsNone(self.policy.select(self.obs, [], False))

    def test_collects_cube_along_the_route_and_keeps_capture_progress(self):
        self.obs["cubes"] = [{"id": 5000, "pos": [10, 0, 0]}]
        self.assertEqual(supply_waypoint(self.obs, self.drop, None), [10, 0, 0])
        self.me["pos"] = [79, 0, 0]
        self.obs["cubes"][0]["pos"] = [85, 2, 0]
        self.assertEqual(supply_waypoint(self.obs, self.drop, None), self.drop["pos"])
