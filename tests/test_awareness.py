import unittest

from awareness import Awareness


class AwarenessTests(unittest.TestCase):
    def setUp(self):
        self.senses = Awareness({"npc": {"aggro_range": 45, "height": 3.5}, "crates": {"height": 2.4}})
        self.obs = {
            "t": 10, "events": [], "sounds": [], "mechs": [],
            "self": {"id": 0, "pos": [0, 0, 0], "hp": 1400, "max_hp": 1400},
            "crates": [{"id": 1000, "pos": [10, 0, 0]}],
        }

    def test_noisy_cues_expire_and_direct_hit_takes_precedence(self):
        self.obs["sounds"] = [{"kind": "laser_charge", "dist": "mid", "bearing": 2, "age": 0.1}]
        self.senses.update(self.obs)
        self.assertEqual(self.senses.bearing, 2)
        self.assertAlmostEqual(self.senses.look_until, 10.5)
        self.obs["events"] = [{"type": "damaged", "weapon": "gun", "by": 1, "bearing": -1}]
        self.senses.update(self.obs)
        self.assertEqual(self.senses.bearing, -1)
        self.obs.update(t=12, events=[])
        self.obs["sounds"][0]["dist"] = "far"
        self.senses.update(self.obs)
        self.assertLess(self.senses.look_until, self.obs["t"])

    def test_regeneration_survives_intermediate_health(self):
        for hp in (900, 1150, 1280):
            self.obs["self"]["hp"] = hp
            self.senses.update(self.obs)
            self.assertIsNone(self.senses.farm_target(self.obs))
        self.obs["self"]["hp"] = 1310
        self.senses.update(self.obs)
        self.assertEqual(self.senses.farm_target(self.obs)["id"], 1000)

    def test_hostile_drone_during_recovery(self):
        drone = {"id": 102, "kind": "npc", "pos": [55, 0, 0], "vel": [0, 0, 0]}
        self.obs["mechs"] = [drone]
        self.obs["self"]["hp"] = 750
        self.obs["events"] = [{"type": "damaged", "weapon": "npc", "by": 102}]
        self.senses.update(self.obs)
        self.assertEqual(self.senses.farm_target(self.obs)["id"], 102)
        self.obs.update(t=13, events=[])
        self.senses.update(self.obs)
        self.assertIsNone(self.senses.farm_target(self.obs))


if __name__ == "__main__":
    unittest.main()
