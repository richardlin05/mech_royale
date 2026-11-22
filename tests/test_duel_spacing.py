import math
import unittest
from duel_spacing import duel_advance, isolated_opponent


def mech(arc=True):
    slots = [{"kind": "gun", "stats": {"damage": 45, "range": 230}, "ammo": 12, "reload": 0}, None]
    if arc:
        slots[1] = {"kind": "lightning", "stats": {"range": 45}}
    return {"pos": [0, 0, 0], "hp": 1400, "max_hp": 1400, "energy": 100, "max_energy": 100,
            "stats": {"walk_speed": 11.7, "boost_speed": 19.5, "radius": 2.5}, "weapons": slots}


def opponent(x, vel=0, hp=1250, weapons=("gun",)):
    return {"pos": [x, 0, 0], "vel": [vel, 0, 0], "hp": hp, "weapons": list(weapons)}


class Obstructions:
    def cell(self, pos):
        return round(pos[0]), round(pos[1])

    def walkable_step(self, old, new):
        return new[1] <= 0

    def screened(self, own, other):
        return other[1] >= 100


class DuelSpacingTests(unittest.TestCase):
    def test_avoid_counter_to_laser(self):
        me = mech(False)
        me["weapons"][1] = {"kind": "laser"}
        enemy = opponent(40, weapons=["lightning"])
        move, boost = duel_advance(me, enemy, 1, [0, 0], 200, None)
        self.assertLess(move[0], -0.8)
        self.assertTrue(boost)
        self.assertIsNone(duel_advance(me, opponent(90, weapons=["lightning"]), 1, [0, 0], 200, None))

    def test_match_runner_inside_arc(self):
        me = mech()
        moving, _ = duel_advance(me, opponent(33, vel=11.7), -1, [0, 0], 200, None)
        self.assertGreater(moving[0], 0.75)
        self.assertIsNone(duel_advance(me, opponent(33), -1, [0, 0], 200, None))

    def test_last_two_uses_actual_health_and_loaded_slot(self):
        me = mech(False)
        me["hp"] = 850
        weak = opponent(145, hp=150)
        self.assertIsNotNone(duel_advance(me, weak, 1, [0, 0], 200, None, alive=2))
        self.assertIsNone(duel_advance(me, weak, 1, [0, 0], 200, None, alive=4))
        me["weapons"][0]["reload"] = 2
        self.assertIsNone(duel_advance(me, weak, 1, [0, 0], 200, None, alive=2))

    def test_switch_orbit_side_at_a_blocked_edge(self):
        move, _ = duel_advance(mech(), opponent(70), 1, [0, 0], 200, Obstructions())
        self.assertLess(move[1], 0)
        self.assertIsNone(duel_advance(mech(), opponent(70), 1, [0, 0], 9, Obstructions()))

    def test_memory_isolation_with_close_or_exposed_backup(self):
        pos = [0, 0, 0]
        close = opponent(55)
        far = opponent(150)
        far["pos"][1] = 110
        self.assertIs(isolated_opponent([close, far], pos, Obstructions()), close)
        far["pos"] = [60, 105, 0]
        self.assertIsNone(isolated_opponent([close, far], pos, Obstructions()))
        far["pos"] = [170, 0, 0]
        self.assertIsNone(isolated_opponent([close, far], pos, Obstructions()))
