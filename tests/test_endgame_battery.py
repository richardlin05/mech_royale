import unittest

from example_bot import reserve_arc_energy


class EndgameBatteryTests(unittest.TestCase):
    def setUp(self):
        self.arc = {"kind": "lightning", "stats": {"range": 45}}
        self.mech = {"pos": [0, 0, 0], "stats": {"walk_speed": 12},
                     "weapons": [{"kind": "gun"}, self.arc]}
        self.enemy = {"pos": [55, 0, 0]}

    def test_reserves_only_when_contact_is_close_and_circle_is_small(self):
        self.assertTrue(reserve_arc_energy(self.mech, self.enemy, 70))
        self.assertFalse(reserve_arc_energy(self.mech, self.enemy, 140))
        self.enemy["pos"] = [58, 0, 0]
        self.assertFalse(reserve_arc_energy(self.mech, self.enemy, 70))

    def test_uses_the_equipped_range_after_an_upgrade(self):
        self.enemy["pos"] = [67, 0, 0]
        self.assertFalse(reserve_arc_energy(self.mech, self.enemy, 100))
        self.arc["stats"]["range"] = 60
        self.assertTrue(reserve_arc_energy(self.mech, self.enemy, 100))

    def test_sprints_normally_with_other_loadouts(self):
        for secondary in [None, {"kind": "laser"}, {"kind": "mortar"}]:
            with self.subTest(secondary=secondary):
                self.mech["weapons"][1] = secondary
                self.assertFalse(reserve_arc_energy(self.mech, self.enemy, 70))
