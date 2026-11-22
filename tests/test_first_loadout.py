import unittest

from resource_policy import FirstLoadout


class FirstLoadoutTests(unittest.TestCase):
    def setUp(self):
        self.plan = FirstLoadout()
        self.item = {"id": 8001, "kind": "laser", "pos": [85, 5, 0]}
        self.obs = {"t": 0, "self": {"pos": [0, 0, 0], "id": 3, "weapons": [{"kind": "gun"}, None],
                                    "in_zone": True, "hp": 1400, "max_hp": 1400, "stats": {"walk_speed": 12}},
                    "zone": {"center": [0, 0], "radius": 250, "next_center": [90, 0],
                             "next_radius": 50, "shrink_start": 60},
                    "pickups": [self.item], "cubes": [], "drops": []}

    def goal(self, enemies=(), urgent=False):
        return self.plan.goal(self.obs, enemies, None, urgent)

    def test_follows_a_recently_seen_item_and_abandons_a_blocked_one(self):
        self.assertEqual(self.goal(), self.item["pos"])
        self.obs.update(t=2, pickups=[])
        self.obs["self"]["pos"] = [10, 0, 0]
        self.assertEqual(self.goal(), self.item["pos"])
        self.obs.update(t=8, pickups=[self.item])
        self.assertIsNone(self.goal())

    def test_yields_to_zone_threat_and_completed_loadout(self):
        self.assertIsNone(self.goal(urgent=True))
        self.assertIsNone(self.goal([{"pos": [40, 0, 0]}]))
        self.obs["t"] = 52
        self.assertIsNone(self.goal())
        self.obs["t"] = 0
        self.obs["self"]["weapons"][1] = {"kind": "lightning"}
        self.assertIsNone(self.goal())

    def test_ignores_vanished_item_when_position_is_reached(self):
        self.assertEqual(self.goal(), self.item["pos"])
        self.obs.update(t=4, pickups=[])
        self.obs["self"]["pos"] = [84, 5, 0]
        self.assertIsNone(self.goal())
