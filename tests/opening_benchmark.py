"""Compare bot checkouts on the same seeded, uncontested equipment-search scenarios.

Run from the project root, with the official arena/ and check/stream.jsonl.gz present:
    python3 -B tests/opening_benchmark.py [path/to/another/bot/checkout]
The fixture models walking, turning and observing ground pickups for 20 seconds.
It excludes opponents, damage, step physics and scoring.
"""
import argparse
from copy import copy, deepcopy
import gzip
import json
import math
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]


def make_cases(arena, seed):
    rng = random.Random(seed)
    cells = sorted(arena.ground)
    cases = []
    while len(cases) < 48:
        start = rng.choice(cells)
        if not arena.open(start):
            continue
        x, y = arena.point(start)
        items = []
        for _ in range(16):
            yaw = rng.uniform(-math.pi, math.pi)
            dist = rng.uniform(45, 145)
            cell = arena.cell((x + dist * math.cos(yaw), y + dist * math.sin(yaw)))
            if arena.open(cell):
                items.append({"id": 8000 + len(items), "kind": rng.choice(["laser", "lightning", "mortar"]),
                              "pos": [*arena.point(cell), arena.ground[cell]]})
            if len(items) == 2:
                break
        if len(items) == 2:
            angle = rng.uniform(-math.pi, math.pi)
            cases.append(([x, y, arena.ground[start]], items, angle))
    return cases


def run(arena, hello, template, start, items, angle, planner, bot_class):
    # Reuse immutable map geometry; each episode has a fresh bot and route cache.
    bot = bot_class(hello)
    bot.arena = copy(planner)
    pos = start.copy()
    vel = [0.0, 0.0]
    obs = deepcopy(template)
    me = obs["self"]
    stats = me["stats"]
    yaw = angle
    zone = obs["zone"]
    zone.update(center=start[:2], radius=450, next_center=[start[0] + 90 * math.cos(angle), start[1] + 90 * math.sin(angle)],
                next_radius=70, shrink_start=55, shrink_end=105)
    obs.update(mechs=[], crates=[], cubes=[], drops=[], offer=None, sounds=[], events=[])
    for tick in range(200):
        obs.update(t=tick * 0.1, tick=tick * 2)
        me.update(pos=pos.copy(), vel=[*vel, 0], aim=[yaw, 0], in_zone=True)
        visible = []
        for item in items:
            spot = item["pos"]
            dist = math.dist(pos[:2], spot[:2])
            bearing = math.atan2(spot[1] - pos[1], spot[0] - pos[0])
            vision = hello["config"]["vision"]
            if dist > vision["range"] or (dist > vision["near_range"] and
                    abs(math.remainder(bearing - yaw, math.tau)) > math.radians(vision["fov_deg"] / 2)):
                continue
            if not arena.screened(pos, spot):
                visible.append(item)
        obs["pickups"] = visible
        action = bot.act(obs)
        for item in visible:
            spot = item["pos"]
            if (action.get("take") == item["id"] and math.dist(pos[:2], spot[:2]) <= 4 and abs(pos[2] - spot[2]) <= 4):
                return tick * 0.1
        turn = math.remainder(action["aim"][0] - yaw, math.tau)
        yaw += max(-stats["turn_rate"] * 0.1, min(turn, stats["turn_rate"] * 0.1))
        speed = stats["boost_speed"] if action.get("boost") else stats["walk_speed"]
        desired = [m * speed for m in action["move"]]
        change = math.dist(vel, desired)
        factor = min(1, stats["ground_accel"] * 0.1 / max(change, 1e-9))
        vel = [v + factor * (d - v) for v, d in zip(vel, desired)]
        nxt = [pos[i] + 0.1 * vel[i] for i in (0, 1)]
        cell = arena.cell(nxt)
        if arena.open(cell):
            pos = [*nxt, arena.ground[cell]]
        else:
            vel = [0.0, 0.0]
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--seed", type=int, default=9481)
    args = parser.parse_args()
    sys.path.insert(0, str(args.checkout.resolve()))
    from example_bot import Bot
    from arena_nav import Arena

    with gzip.open(ROOT / "check/stream.jsonl.gz") as stream:
        hello, template = json.loads(next(stream)), json.loads(next(stream))
    # Use the same fixture geometry for every checkout. The bot uses its own planner.
    import importlib.util
    spec = importlib.util.spec_from_file_location("fixture_map", ROOT / "arena_nav.py")
    geometry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geometry)
    arena = geometry.Arena(ROOT / "arena")
    planner = Arena(ROOT / "arena")
    hello["map"]["dir"] = "/absent-in-fixture"
    # Supply each bot's own map to its policy, separately from fixture collisions.
    cases = make_cases(arena, args.seed)
    times = []
    for start, items, angle in cases:
        times.append(run(arena, hello, template, start, items, angle, planner, Bot))
    finished = [t for t in times if t is not None]
    print(f"{len(finished)}/{len(times)} pickups in 20 seconds")
    if finished:
        print(f"Median successful pickup time: {statistics.median(finished):.1f} s")
