import unittest

from equipment import Equipment
from resource_policy import FirstLoadout, ResourceMemory


class WallEdge:
    step = 5
    ground = {(0, 0): 0, (1, 0): 0}

    def cell(self, pos):
        return round(pos[0] / self.step), round(pos[1] / self.step)

    def open(self, cell):
        return cell == (1, 0)

    def point(self, cell):
        return [v * self.step for v in cell]


class EconomyTests(unittest.TestCase):
    def setUp(self):
        self.me = {"id": 0, "cubes": 10, "pos": [0, 0, 0], "weapons": [{"kind": "gun"}, None],
                   "stats": {"walk_speed": 12}, "in_zone": True, "hp": 1400, "max_hp": 1400}
        self.cube = {"id": 5001, "pos": [25, 5, 0]}
        self.item = {"id": 8001, "kind": "laser", "pos": [40, 0, 0]}
        self.obs = {"t": 50, "self": self.me, "zone": {"center": [0, 0], "radius": 105, "next_center": [0, 0],
                   "next_radius": 80, "shrink_start": 40}, "pickups": [self.item], "cubes": [], "drops": [], "mechs": []}
        self.memory = ResourceMemory({"cubes": {"upgrade_thresholds": [1, 3, 6, 10, 15, 21],
                                               "stat_cap": 10, "pickup_radius": 3.5}})

    def test_safe_shrink_trip_and_dangerous_destination(self):
        self.assertEqual(FirstLoadout().goal(self.obs, [], None, False), self.item["pos"])
        self.item["pos"] = [81, 0, 0]
        self.assertIsNone(FirstLoadout().goal(self.obs, [], None, False))
        self.item["pos"] = [20, 0, 0]
        self.assertIsNone(FirstLoadout().goal(self.obs, [], None, True))

    def test_wallside_floor_slot_and_unreachable_roof(self):
        self.assertEqual(FirstLoadout().approach_point([-10, 0, 0], [2, 0, 1], WallEdge()), [5, 0, 0])
        self.assertIsNone(FirstLoadout().approach_point([-10, 0, 0], [2, 0, 8], WallEdge()))
        self.assertIsNone(FirstLoadout(2).approach_point([-10, 0, 0], [2, 0, 1], WallEdge()))

    def test_post_cap_cube_detours_need_an_offer_or_incidental_pickup(self):
        self.obs["cubes"] = [self.cube]
        self.assertFalse(self.memory.route_view(self.obs)["cubes"])
        self.assertEqual(len(self.obs["cubes"]), 1)
        self.me["cubes"] = 14
        self.assertTrue(self.memory.route_view(self.obs)["cubes"])
        self.me["cubes"] = 10
        self.obs["cubes"] = [dict(self.cube, id=5000+i) for i in range(5)]
        self.assertEqual(len(self.memory.route_view(self.obs)["cubes"]), 5)

    def test_contested_cube_vs_retreating_rival(self):
        self.me["cubes"] = 0
        self.obs["cubes"] = [self.cube]
        enemy = {"kind": "mech", "pos": [32, 5, 0], "vel": [-10, 0, 0]}
        self.obs["mechs"] = [enemy]
        self.assertFalse(self.memory.route_view(self.obs)["cubes"])
        enemy["vel"][0] = 10
        self.assertTrue(self.memory.route_view(self.obs)["cubes"])
        enemy["pos"] = [25, 5, 7]
        self.assertTrue(self.memory.route_view(self.obs)["cubes"])

    def test_counter_swap_repays_equip_delay_only_in_long_encounter(self):
        laser = {"range": 280, "damage": 315, "charge": .75, "cooldown": 1.65, "cookoff": .6}
        arc = {"range": 45, "damage": 60, "cooldown": .25, "energy": 3}
        gun = {"damage": 45, "mag": 12, "cooldown": .24, "reload": 2.4}
        config = {"loot": {"equip_s": 1, "pickup_radius": 4}, "weapons": {"laser": laser, "lightning": arc},
                  "upgrades": []}
        self.me.update(energy=100, upgrades=[], weapons=[{"kind": "gun", "stats": gun},
                       {"kind": "laser", "stats": laser, "cooldown": 0, "charge": 0}])
        self.item.update(kind="lightning", pos=[2, 0, 0])
        enemy = {"pos": [30, 0, 0], "hp": 1400, "weapons": ["gun", "laser"]}
        eq = Equipment(config)
        self.assertEqual(eq.pickup(self.obs, [enemy], False), {"drop": 1, "take": self.item["id"]})
        self.assertEqual(eq.pickup(self.obs, [dict(enemy, hp=55)], False), {})
        self.assertEqual(eq.pickup(self.obs, [dict(enemy, weapons=["gun"])], False), {})
        self.me["weapons"][1]["charge"] = .25
        self.assertEqual(eq.pickup(self.obs, [enemy], False), {})


if __name__ == "__main__":
    unittest.main()
