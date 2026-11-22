import unittest

from example_bot import EliminationRewards


class EliminationRewardTests(unittest.TestCase):
    def setUp(self):
        self.policy = EliminationRewards({"cubes": {"pickup_radius": 3.5, "stat_cap": 10}})
        self.actor = {"id": 4, "pos": [35, 5, 0]}
        self.cube = {"id": 5000, "pos": [35, 6, 0]}
        self.obs = {
            "t": 10, "cubes": [self.cube], "events": [], "drops": [],
            "self": {"id": 0, "in_zone": True, "pos": [0, 0, 0], "cubes": 1,
                     "stats": {"walk_speed": 12, "boost_speed": 20, "radius": 2.5}},
            "zone": {"center": [0, 0], "radius": 200, "next_center": [80, 0],
                     "next_radius": 60, "shrink_start": 30, "shrink_end": 80},
        }
        self.policy.update(self.obs, [self.actor])

    def goal(self, enemies=()):
        return self.policy.goal(self.obs, enemies, 50, None)

    def kill(self, other_events=()):
        self.obs.update(t=10.1, events=[{"type": "kill", "target": 4}, *other_events])
        self.policy.update(self.obs, [])

    def test_only_confirmed_kill_and_matching_cube_trigger_trip(self):
        self.assertIsNone(self.goal())
        self.kill()
        self.assertEqual(self.goal(), self.cube["pos"])
        self.obs["cubes"] = [{"id": 5010, "pos": [0, 0, 0]}]
        self.assertIsNone(self.goal())

    def test_final_hit_from_defeated_actor_allows_collection(self):
        self.kill([{"type": "damaged", "by": 4}])
        self.assertEqual(self.goal(), self.cube["pos"])
        self.obs.update(t=10.2, events=[{"type": "damaged", "by": 7}])
        self.policy.update(self.obs, [])
        self.assertIsNone(self.goal())

    def test_abandons_contested_expired_or_already_consumed_reward(self):
        self.kill()
        self.assertIsNone(self.goal([{"id": 8, "pos": [40, 4, 0]}]))
        self.obs["cubes"] = []
        self.assertIsNone(self.goal())
        self.obs.update(t=21, cubes=[self.cube], events=[])
        self.policy.update(self.obs, [])
        self.assertIsNone(self.goal())

    def test_declines_when_storm_closes_over_pile(self):
        self.kill()
        self.obs["zone"].update(next_center=[-90, -10], next_radius=10,
                                shrink_start=9, shrink_end=12)
        self.assertIsNone(self.goal())

    def test_yields_to_supply_capture_and_stat_cap(self):
        self.kill()
        self.obs["drops"] = [{"holder": 0}]
        self.assertIsNone(self.goal())
        self.obs["drops"] = []
        self.obs["self"]["cubes"] = 10
        self.assertIsNone(self.goal())
