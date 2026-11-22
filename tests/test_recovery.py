import unittest

from recovery import Recovery


class ShelterMap:
    def screened(self, spot, opponent):
        return opponent[0] < 0


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.policy = Recovery()
        self.arena = ShelterMap()
        self.obs = {
            "t": 0, "events": [], "drops": [],
            "self": {"id": 1, "pos": [0, 0, 0], "hp": 700, "max_hp": 1400,
                     "in_zone": True, "stats": {"radius": 2.5, "regen_delay": 5,
                     "regen_per_s": 45, "walk_speed": 11.7}},
            "zone": {"center": [0, 0], "radius": 250, "next_center": [0, 0],
                     "shrink_start": 50},
        }
        self.enemies = [{"pos": [-50, 0, 0]}]
        self.policy.remember(self.obs, [0, 0, 0], self.enemies, self.arena, 100)

    def hold(self, enemies=(), urgent=False):
        return self.policy.hold(self.obs, enemies, self.arena, 100, urgent)

    def test_stays_when_sight_memory_expires_then_resumes(self):
        self.obs["t"] = 5.1
        self.assertEqual(self.hold(), (0, 0, 0))
        self.obs["self"]["hp"] = 1260
        self.assertIsNone(self.hold())

    def test_unsafe_returns_interrupt_recovery(self):
        self.assertIsNone(self.hold([{"pos": [15, 0, 0]}]))

    def test_storm_and_deadline_take_priority(self):
        self.assertIsNone(self.hold(urgent=True))
        self.obs["zone"].update(next_center=[160, 0], shrink_start=55)
        self.obs["t"] = 50
        self.assertFalse(self.policy.has_time(self.obs, (0, 0, 0), 100))
        self.obs["t"] = 0
        self.assertTrue(self.policy.has_time(self.obs, (0, 0, 0), 100))

    def test_new_hit_at_shelter_breaks_wait(self):
        self.obs["events"] = [{"type": "damaged", "weapon": "npc"}]
        self.assertIsNone(self.hold())
        self.obs["t"] = 0.5
        self.policy.remember(self.obs, [0, 0, 0], self.enemies, self.arena, 100)
        self.assertIsNone(self.policy.goal)

    def test_leaves_shelter_to_finish_a_supply_capture(self):
        self.obs["drops"] = [{"holder": self.obs["self"]["id"]}]
        self.assertIsNone(self.hold())

    def test_shelter_must_screen_every_opponent_before_committing(self):
        other_policy = Recovery()
        opponents = self.enemies + [{"pos": [20, 0, 0]}]
        other_policy.remember(self.obs, [0, 0, 0], opponents, self.arena, 100)
        self.assertIsNone(other_policy.goal)

    def test_stalled_regeneration_eventually_times_out(self):
        self.obs["t"] = 30
        self.assertIsNone(self.hold())
