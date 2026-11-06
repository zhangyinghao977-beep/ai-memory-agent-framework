"""T2 出题器：多条事件链＋条件变更（2026-11-02）。

依据：
- 名词解释 v0.55 第 2 节：P／NP 类比指“如果某一个条件存在变更，那么要找到最小的变更有效方案，全局重构和局部重构的问题”；
  本实验以仅修复遗漏包相关单元作为局部修复情形。
- 图谱讨论版 0.45 第 09 图（网站增补，2026-11-02）：KA 包内、EA 链内、CA 链间；使用入口由 CA 先做语义判断；
  “回修是否止于 EA”待验证。
- 同一实验包含 KA、EA、CA，以比较修复范围及回修层级。

一道题是一小段“对话”，由若干条链按顺序组成：
- 设定链：说明当前世界（物理世界大的赢；故事世界有前提“小的赢”）。
- 陈述链：某个说话人说的一串事件（关系, 包, 成员）。
- 查询 (x, r_A, y, r_B)：说话人 x 用关系 r_A 提到的东西，和说话人 y 用关系 r_B 提到的东西，按当前世界谁赢。答案 1＝A 赢。

三层规则，各由一层学习：
- KA（包内参考系）：对象数值＝包的参考水平＋成员相对首成员的偏差，同 T1。
- EA（链内关系）：同一条链里同一关系出现两次时，后一次是改口，以后一次为准。
- CA（链间关系）：体裁 0“对话”以同一说话人最后一句、最后一条设定为准；体裁 1“档案”以最早的为准。

条件：
- base：体裁 0，没有链内改口，“遗漏的包”不出现（连干扰项也不出现）。
- C1 遗漏的包（KA 层的变更）：遗漏的包第一次出现，题目分布同 base。
- C2 链内改口（EA 层的变更）：目标链里至少有一边出现同一关系两次。
- C3 新体裁（CA 层的变更）：体裁 1，每题都带链间覆盖（照“最后一句为准”会选错链）。

划分同 T1：按（无序对象对, 当前世界）分 train／dev／test。四个条件共用一张划分表，
所以任一条件 test 里的（对象对, 世界）都没有在任何条件的 train 里出现过。
模型可见的：链的种类、说话人是否等于 x／y（CPU 的身份判断）、设定内容、链和事件的位置、体裁、
事件的关系是否等于 r_A／r_B、包和成员编号。答案、A／B 是谁、当前世界等只在 hidden 里，用于评分和分层诊断。
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Optional

WORLDS = ("physical", "story")
SPLITS = ("train", "dev", "test")
CONDITIONS = ("base", "C1", "C2", "C3")
GENRES = ("dialog", "record")


@dataclass(frozen=True)
class T2Spec:
    n_packages: int = 12
    n_members: int = 6
    n_relations: int = 8
    chain_len: int = 3                  # 每条陈述链的事件数
    n_chains: int = 6                   # 每题的链数（含设定链）
    n_speakers: int = 6
    train_pair_fraction: float = 0.4    # 两个世界都在 TRAIN 的对象对
    world_split_fraction: float = 0.2   # 一个世界在 TRAIN、另一个留出的对象对
    level_range: int = 80               # 包的参考水平取值范围
    offset_range: int = 12              # 成员偏差取值范围（±）
    n_pairs: Optional[int] = None       # 抽多少个对象对；None＝全部
    complex_fraction: float = 0.5       # base、C1、C2 里带链间覆盖的题的比例
    missing_packages: int = 2           # C1：base 里不出现的包（编号最大的几个）
    change_keys: int = 400              # C2、C3 各从 base 的（对象对, 世界）里抽多少个出新题
    seed: int = 20261102


PRESETS = {
    "small": T2Spec(),
    "main": T2Spec(n_packages=96, n_members=12, n_relations=12, chain_len=4, n_chains=6, n_speakers=8,
                   level_range=600, offset_range=24, n_pairs=60000, missing_packages=4, change_keys=30000),
}


def build_t2(spec: T2Spec = T2Spec()) -> dict:
    if spec.chain_len < 2 or spec.n_relations < spec.chain_len + 1 or spec.n_speakers < 4 or spec.n_chains < 6:
        raise ValueError("每条链至少 2 个事件、关系种类多于链长、至少 4 个说话人、每题至少 6 条链")
    rng = random.Random(spec.seed)
    objects = [(p, m) for p in range(spec.n_packages) for m in range(spec.n_members)]
    values = _distinct_values(spec, rng)
    missing = set(range(spec.n_packages - spec.missing_packages, spec.n_packages))
    total = len(objects) * (len(objects) - 1) // 2
    if spec.n_pairs is None or spec.n_pairs >= total:
        pairs = list(combinations(objects, 2))
    else:
        chosen = set()
        while len(chosen) < spec.n_pairs:
            i, j = rng.randrange(len(objects)), rng.randrange(len(objects))
            if i != j:
                chosen.add((min(i, j), max(i, j)))
        pairs = [(objects[i], objects[j]) for i, j in sorted(chosen)]
    rng.shuffle(pairs)
    n_train = int(len(pairs) * spec.train_pair_fraction)
    n_world = int(len(pairs) * spec.world_split_fraction)
    assignment, pair_kind = {}, {}
    for i, pair in enumerate(pairs):
        held = "dev" if i % 2 == 0 else "test"
        if i < n_train:
            pair_kind[pair] = "train"
            for w in WORLDS:
                assignment[(pair, w)] = "train"
        elif i < n_train + n_world:
            pair_kind[pair] = "world_new"
            seen = rng.choice(WORLDS)
            for w in WORLDS:
                assignment[(pair, w)] = "train" if w == seen else held
        else:
            pair_kind[pair] = "pair_new"
            for w in WORLDS:
                assignment[(pair, w)] = held

    def involves_missing(pair):
        return pair[0][0] in missing or pair[1][0] in missing

    base_pool = [o for o in objects if o[0] not in missing]
    keys = sorted(assignment)
    episodes = []
    for key in keys:
        pair, world = key
        cond = "C1" if involves_missing(pair) else "base"
        episodes.append(_episode(len(episodes), assignment[key], world, pair, pair_kind[pair], cond,
                                 objects if cond == "C1" else base_pool, values, spec, rng))
    base_keys = [k for k in keys if not involves_missing(k[0])]
    for cond in ("C2", "C3"):
        for key in sorted(rng.sample(base_keys, min(spec.change_keys, len(base_keys)))):
            pair, world = key
            episodes.append(_episode(len(episodes), assignment[key], world, pair, pair_kind[pair], cond, base_pool,
                                     values, spec, rng))
    rng.shuffle(episodes)
    return {"spec": asdict(spec), "objects": objects, "missing_packages": sorted(missing),
            "hidden_values": {f"{p},{m}": v for (p, m), v in values.items()}, "episodes": episodes}


def label_of(world: str, va: float, vb: float) -> int:
    """物理世界大的赢；故事世界（前提“小的赢”）小的赢。"""
    return int(va > vb) if world == "physical" else int(va < vb)


def theory_resolve(episode: dict) -> tuple[tuple, tuple, str]:
    """按出题规则（理论侧，模型看不到这条规则）找出 A、B 和当前世界。只给门禁、基线和诊断用。"""
    x, ra, y, rb = episode["query"]
    pick = (lambda xs: xs[-1]) if episode["genre"] == 0 else (lambda xs: xs[0])
    chains = episode["chains"]
    world = pick([c["world"] for c in chains if c["kind"] == "setting"])

    def find(speaker, rel):
        chain = pick([c for c in chains if c["kind"] == "say" and c["speaker"] == speaker
                      and any(e[0] == rel for e in c["events"])])
        return tuple([e for e in chain["events"] if e[0] == rel][-1][1:])     # 链内改口：以后一次为准
    return find(x, ra), find(y, rb), world


def exact_resolve(episode: dict) -> Optional[tuple[tuple, tuple, str]]:
    """CPU 侧只凭可见信息、不用任何学来的规则就能唯一确定的 A、B 和世界；不唯一就返回 None。
    KA 只用这种观察（上层的选择错误不当作下层的标签）。"""
    x, ra, y, rb = episode["query"]
    chains = episode["chains"]
    settings = [c["world"] for c in chains if c["kind"] == "setting"]

    def unique(speaker, rel):
        hits = [e for c in chains if c["kind"] == "say" and c["speaker"] == speaker for e in c["events"] if e[0] == rel]
        return tuple(hits[0][1:]) if len(hits) == 1 else None
    a, b = unique(x, ra), unique(y, rb)
    if len(settings) != 1 or a is None or b is None:
        return None
    return a, b, settings[0]


def _distinct_values(spec: T2Spec, rng: random.Random) -> dict:
    """同 T1：包的参考水平取小数，成员偏差取互不相同的非零整数；所有数值互不相同。"""
    for _ in range(1000):
        levels = [round(rng.uniform(0, spec.level_range), 6) for _ in range(spec.n_packages)]
        values = {}
        for p in range(spec.n_packages):
            offsets = [0] + rng.sample([d for d in range(-spec.offset_range, spec.offset_range + 1) if d != 0],
                                       spec.n_members - 1)
            for m, d in enumerate(offsets):
                values[(p, m)] = levels[p] + d
        if len(set(values.values())) == len(values):
            return values
    raise RuntimeError("找不到互不相同的数值，请放宽取值范围")


def _episode(idx, split, world, pair, kind, cond, pool, values, spec: T2Spec, rng: random.Random) -> dict:
    a, b = pair if rng.random() < 0.5 else (pair[1], pair[0])
    x, y = rng.sample(range(spec.n_speakers), 2)
    ra, rb = rng.sample(range(spec.n_relations), 2)
    genre = 1 if cond == "C3" else 0
    sup_x = sup_y = override = False
    if cond == "C3" or rng.random() < spec.complex_fraction:
        while not (sup_x or sup_y or override):
            sup_x, sup_y, override = (rng.random() < 0.5 for _ in range(3))
    dup_x = dup_y = False
    if cond == "C2":
        while not (dup_x or dup_y):
            dup_x, dup_y = rng.random() < 0.5, rng.random() < 0.5

    used = {a, b}

    def fresh():
        while True:
            o = pool[rng.randrange(len(pool))]
            if o not in used:
                used.add(o)
                return o

    def say(speaker, rel=None, obj=None, dup=False):
        """一条陈述链：可带一个指定事件 (rel, obj)；dup 时同一关系在它前面先出现一次（随后被改口）。"""
        n_other = spec.chain_len - (rel is not None) - dup
        others = [r for r in range(spec.n_relations) if r != rel]
        events = [[r, *fresh()] for r in rng.sample(others, n_other)]
        rng.shuffle(events)
        if rel is not None:
            target = [rel, *obj]
            if dup:
                i, j = sorted(rng.sample(range(len(events) + 2), 2))
                events.insert(i, [rel, *fresh()])
                events.insert(j, target)
            else:
                events.insert(rng.randrange(len(events) + 1), target)
        return {"kind": "say", "speaker": speaker, "events": events}

    chains = [say(x, ra, a, dup_x), say(y, rb, b, dup_y), {"kind": "setting", "world": world}]
    order = []                                  # (算数的链, 被覆盖的链)：体裁 0 时前者在后，体裁 1 时前者在前
    if sup_x:
        chains.append(say(x, ra, fresh()))
        order.append((0, len(chains) - 1))
    if sup_y:
        chains.append(say(y, rb, fresh()))
        order.append((1, len(chains) - 1))
    if override:
        chains.append({"kind": "setting", "world": WORLDS[1 - WORLDS.index(world)]})
        order.append((2, len(chains) - 1))
    fillers = [s for s in range(spec.n_speakers) if s not in (x, y)]
    while len(chains) < spec.n_chains:
        chains.append(say(rng.choice(fillers)))
    slots = list(range(len(chains)))
    rng.shuffle(slots)                          # slots[i]：第 i 条链放在第几位
    for keep, old in order:
        if (slots[keep] > slots[old]) != (genre == 0):
            slots[keep], slots[old] = slots[old], slots[keep]
    placed = [None] * len(chains)
    for i, s in enumerate(slots):
        placed[s] = chains[i]

    def event_at(chain, rel):
        return max(j for j, e in enumerate(chain["events"]) if e[0] == rel)
    hidden = {"A": a, "B": b, "world": world, "pair_kind": kind, "same_package": a[0] == b[0],
              "a_chain": slots[0], "b_chain": slots[1], "set_chain": slots[2],
              "a_event": event_at(chains[0], ra), "b_event": event_at(chains[1], rb),
              "sup_x": sup_x, "sup_y": sup_y, "override": override, "dup_x": dup_x, "dup_y": dup_y,
              "needs_ca": sup_x or sup_y or override, "needs_ea": dup_x or dup_y}
    return {"id": f"t2-{idx:06d}", "split": split, "condition": cond, "genre": genre, "chains": placed,
            "query": (x, ra, y, rb), "label": label_of(world, values[a], values[b]), "hidden": hidden}
