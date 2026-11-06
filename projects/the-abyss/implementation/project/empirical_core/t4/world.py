"""T4 的世界和日子：T3 的世界照旧，随着日子慢慢变（2026-11-03）。

- 旧世界：和 T3 同一个世界（同样的包、成员、数值）。
- 第 new_package_day 天起：出现 new_packages 个从没见过的包（借 T2 C1，KA 层的变更）。
- 第 new_genre_day 天起：一部分题是“档案”体裁，以最早的为准（借 T2 C3，CA 层的变更）。
  其中一部分题在目标链里带链内改口：档案里链内也以最早的为准。规则由 CA 层的体裁决定，落在 EA 层的选择上：
  EA 照旧选后一次，语法上没问题，答案却错了。只靠 EA 自己看不到体裁，这正是要 CA 约束 EA 的地方。
每天来 questions_per_day 道题。日子里的题和评测探针严格分开：
- 旧世界的日常题用 T3 的 train 那些（对象对, 世界）重新出题（新的说话人、干扰项和顺序）；
  旧世界探针就是 T3 的 TEST 题，从不出现在日子里。
- 过去的经历：T3 的 TRAIN 题（past，可以回放），和一份 T3 的 DEV 题（past_check，从不训练，只给系统自检）。
- 新包：含新包的（对象对, 世界）按对象对分成日常用和探针用两份。
- 新体裁（带不带链内改口）：日常题用 T3 的 train 键，探针用 T3 的 test 键。
探针只用于报告（隐藏真值）。答案只在回答以后，作为对整个问答的反馈给出。
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, replace

from ..t2.task import WORLDS, _episode
from ..t3.task import PRESETS as T3_PRESETS, build_t3


@dataclass(frozen=True)
class WorldSpec:
    t3_preset: str = "small"
    t3_overrides: tuple = ()
    new_packages: int = 2
    new_package_day: int = 2
    new_package_fraction: float = 0.3     # 新包出现以后，每天含新包的题的比例
    new_genre_day: int = 4
    new_genre_fraction: float = 0.3       # 新体裁出现以后，每天“档案”体裁的题的比例
    new_genre_dup_fraction: float = 0.5   # “档案”体裁的题里，带链内改口的比例
    days: int = 6
    questions_per_day: int = 256
    probe_size: int = 512                 # 每个探针最多多少题
    new_pair_probe_fraction: float = 0.3  # 含新包的对象对，留作探针的比例
    seed: int = 20261104


def resolve_t4(ep: dict) -> tuple:
    """T4 的理论规则（模型看不到）：体裁 0 对话以最后的为准，体裁 1 档案以最早的为准；链间、链内都一样。"""
    x, ra, y, rb = ep["query"]
    pick = (lambda xs: xs[-1]) if ep["genre"] == 0 else (lambda xs: xs[0])
    chains = ep["chains"]
    world = pick([c["world"] for c in chains if c["kind"] == "setting"])

    def find(speaker, rel):
        chain = pick([c for c in chains if c["kind"] == "say" and c["speaker"] == speaker
                      and any(e[0] == rel for e in c["events"])])
        return tuple(pick([e for e in chain["events"] if e[0] == rel])[1:])
    return find(x, ra), find(y, rb), world


def add_record_dup(ep: dict, pool: list, rng: random.Random) -> None:
    """档案体裁的题：在目标事件后面放一条同关系的事件。按档案的规则，后面这条不算数。"""
    h = ep["hidden"]
    _, ra, _, rb = ep["query"]
    taken = {tuple(e[1:]) for c in ep["chains"] if c["kind"] == "say" for e in c["events"]}
    for side in rng.choice((("a",), ("b",), ("a", "b"))):
        events = ep["chains"][h[f"{side}_chain"]]["events"]
        t = h[f"{side}_event"]
        if t == len(events) - 1:                      # 目标不能在最后，否则后面放不下
            events[0], events[t] = events[t], events[0]
            t = h[f"{side}_event"] = 0
        while True:
            o = pool[rng.randrange(len(pool))]
            if o not in taken:
                taken.add(o)
                break
        events[rng.randrange(t + 1, len(events))] = [ra if side == "a" else rb, *o]
        h["dup_x" if side == "a" else "dup_y"] = True
    h["needs_ea"] = True


def build_world(ws: WorldSpec) -> dict:
    t3spec = replace(T3_PRESETS[ws.t3_preset], **dict(ws.t3_overrides))
    t3 = build_t3(t3spec)
    rng = random.Random(ws.seed)
    P, M = t3spec.n_packages, t3spec.n_members
    values = {tuple(map(int, k.split(","))): v for k, v in t3["hidden_values"].items()}
    taken = set(values.values())
    new_pk = list(range(P, P + ws.new_packages))
    for p in new_pk:                                  # 新包的数值：同 T1–T3 的规则，和已有的全不相同
        while True:
            level = round(rng.uniform(0, t3spec.level_range), 6)
            offs = [0] + rng.sample([d for d in range(-t3spec.offset_range, t3spec.offset_range + 1) if d != 0], M - 1)
            vals = [level + d for d in offs]
            if not taken & set(vals) and len(set(vals)) == M:
                break
        for m, v in enumerate(vals):
            values[(p, m)] = v
            taken.add(v)
    old_objects = [tuple(o) for o in t3["objects"]]
    new_objects = [(p, m) for p in new_pk for m in range(M)]
    all_objects = old_objects + new_objects

    keys = {"train": [], "dev": [], "test": []}
    for ep in t3["episodes"]:
        h = ep["hidden"]
        keys[ep["split"]].append((tuple(sorted((tuple(h["A"]), tuple(h["B"])))), h["world"]))
    keys = {s: sorted(set(v)) for s, v in keys.items()}
    stream_keys, test_keys = keys["train"], keys["test"]
    new_pairs = sorted({tuple(sorted((a, b))) for a in new_objects for b in all_objects if a != b})
    rng.shuffle(new_pairs)
    cut = int(len(new_pairs) * ws.new_pair_probe_fraction)
    new_probe_pairs, new_stream_pairs = new_pairs[:cut], new_pairs[cut:]

    def make(key, kind, cond, pool_objects, split):
        pair, world = key
        ep = _episode(0, split, world, pair, kind, cond, pool_objects, values, t3spec, rng)
        ep["condition"] = "base"
        return ep

    episodes, counter = [], [0]

    def add(ep, split, day, change):
        ep["id"] = f"t4-{counter[0]:06d}"
        ep["split"] = split
        ep["day"] = day
        ep["change"] = change
        counter[0] += 1
        episodes.append(ep)

    for d in range(1, ws.days + 1):
        n = ws.questions_per_day
        n_new = int(n * ws.new_package_fraction) if d >= ws.new_package_day else 0
        n_genre = int(n * ws.new_genre_fraction) if d >= ws.new_genre_day else 0
        for _ in range(n - n_new - n_genre):
            add(make(rng.choice(stream_keys), "stream", "base", old_objects, "x"), f"day{d}", d, "old")
        for _ in range(n_new):
            pair = rng.choice(new_stream_pairs)
            add(make((pair, rng.choice(WORLDS)), "stream", "base", all_objects, "x"), f"day{d}", d, "new_package")
        for _ in range(n_genre):
            ep = make(rng.choice(stream_keys), "stream", "C3", old_objects, "x")
            dup = rng.random() < ws.new_genre_dup_fraction
            if dup:
                add_record_dup(ep, old_objects, rng)
            add(ep, f"day{d}", d, "new_genre_dup" if dup else "new_genre")
        crumbs = [e for e in episodes if e["day"] == d]
        rng.shuffle(crumbs)
        episodes[-len(crumbs):] = crumbs

    for e in t3["episodes"]:
        if e["split"] == "train":
            add(dict(e), "past", 0, "old")
    past_check = [e for e in t3["episodes"] if e["split"] == "dev"]
    rng.shuffle(past_check)
    for e in past_check[:ws.probe_size]:
        add(dict(e), "past_check", 0, "old")
    old_probe = [e for e in t3["episodes"] if e["split"] == "test"]
    rng.shuffle(old_probe)
    for e in old_probe[:ws.probe_size]:
        add(dict(e), "probe_old", 0, "old")
    for _ in range(ws.probe_size):
        pair = rng.choice(new_probe_pairs)
        add(make((pair, rng.choice(WORLDS)), "probe", "base", all_objects, "x"), "probe_new_package", 0, "new_package")
    for _ in range(ws.probe_size):
        add(make(rng.choice(test_keys), "probe", "C3", old_objects, "x"), "probe_new_genre", 0, "new_genre")
    for _ in range(ws.probe_size):
        ep = make(rng.choice(test_keys), "probe", "C3", old_objects, "x")
        add_record_dup(ep, old_objects, rng)
        add(ep, "probe_new_genre_dup", 0, "new_genre_dup")
    spec = {**asdict(t3spec), "n_packages": P + ws.new_packages}
    return {"spec": spec, "world_spec": asdict(ws), "t3_spec": asdict(t3spec), "new_packages": new_pk,
            "indirect_packages": t3["indirect_packages"], "objects": [list(o) for o in all_objects],
            "hidden_values": {f"{p},{m}": v for (p, m), v in values.items()}, "episodes": episodes}
