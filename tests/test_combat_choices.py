import math
import unittest

from awareness import best_crate
from combat_choices import finish_priority, reload_window
from example_bot import engage


class LoadoutDecisions(unittest.TestCase):
    def setUp(self):
        self.gun = {"kind": "gun", "cooldown": 0, "reload": 0, "ammo": 12,
                    "stats": {"damage": 45, "mag": 12, "speed": 252, "range": 230,
                              "reload": 2.4, "cooldown": 0.24}}
        self.me = {"pos": [0, 0, 0], "aim": [0, 0], "energy": 100,
                   "weapons": [self.gun, None],
                   "stats": {"walk_speed": 11.7, "boost_speed": 19.5, "muzzle_height": 7}}
        self.target = {"kind": "mech", "hp": 160, "id": 2, "pos": [30, 0, 2.5],
                       "vel": [0, 0, 0], "weapons": ["mortar"]}

    def test_laser_releases_when_its_counter_bonus_covers_hp(self):
        self.me["weapons"][1] = {"kind": "laser", "charge": 0.2, "cooldown": 0,
            "stats": {"range": 280, "charge": 0.75, "damage": 315, "min_frac": 0.35,
                      "min_charge": 0.15, "cookoff": 0.6}}
        self.assertFalse(engage(self.me, self.target, False, 1.4)["fire"][1])
        self.target["weapons"] = ["gun"]
        self.assertTrue(engage(self.me, self.target, False, 1.4)["fire"][1])

    def test_arc_and_gun_share_a_valid_command(self):
        self.me["weapons"][1] = {"kind": "lightning", "cooldown": 0,
                                 "stats": {"cone_deg": 30, "range": 45, "energy": 3}}
        self.target["vel"] = [0, 17, 0]
        act = engage(self.me, self.target, False)
        self.assertEqual(act["fire"], [True, True])
        self.assertAlmostEqual(act["aim"][0], math.atan2(17, 252))
        self.assertLess(abs(act["aim"][0]), math.radians(30))

    def test_one_remaining_round_and_live_cube_bonus(self):
        self.target["hp"] = 46
        self.gun["ammo"] = 1
        self.assertEqual(finish_priority(self.me, self.target, 30, 1.4, False), 0)
        self.assertEqual(finish_priority(self.me, self.target, 30, 1, False), 2)
        self.gun["reload"] = 0.8
        self.assertEqual(finish_priority(self.me, self.target, 30, 1.4, False), 2)

    def test_safe_reload_respects_contact_and_current_trigger(self):
        self.gun["ammo"] = 9
        self.assertTrue(reload_window(self.me, self.gun, [], {}, True))
        self.assertFalse(reload_window(self.me, self.gun, [self.target], {}, True))
        self.gun["ammo"] = 2
        self.assertTrue(reload_window(self.me, self.gun, [{"pos": [400,0,0]}], {}))
        self.assertFalse(reload_window(self.me, self.gun, [], {"fire": [True,False]}))

    def test_finishes_collectible_crate_before_reloading_for_another(self):
        self.gun["ammo"] = 1
        near = {"id": 1, "pos": [10,0,0], "hp": 300}
        almost_open = {"id": 2, "pos": [18,0,0], "hp": 40}
        roof = {"id": 3, "pos": [0,0,15], "hp": 1}
        self.assertEqual(best_crate(self.me, [roof, near, almost_open]), almost_open)
        self.assertIsNone(best_crate(self.me, [roof]))
