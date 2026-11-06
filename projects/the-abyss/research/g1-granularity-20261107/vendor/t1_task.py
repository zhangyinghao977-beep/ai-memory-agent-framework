"""T1 出题器（设计稿 T1_DESIGN.md 第一、三节）。

在某个世界里，比较事件链中两件被提到的东西哪一个“更大”：
- 对象＝（包, 成员位置）。隐藏数值＝包的参考水平＋成员相对参考的偏差（首成员偏差为 0）；所有数值互不相同。
- 每题 4 个历史事件（关系, 包, 位置）：关系 r_A、r_B 各一个，另两个是干扰。查询给出 (r_A, r_B)。
- 物理世界：大的赢；故事世界有前提“小的赢”。答案 1＝A 赢。
- 划分按关键值（无序对象对, 世界）：
  - 训练对：两个世界都在 TRAIN；
  - 换世界对：一个世界在 TRAIN，另一个在 DEV 或 TEST（“见过这一对，没见过这个世界”）；
  - 留出对：两个世界都不在 TRAIN，整对放进 DEV 或 TEST（“这一对从没比较过”）。
模型可见的只有：世界、历史事件、查询关系。数值和 A／B 是谁只在 hidden 里，用于评分和审计。
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Optional

WORLDS = ("physical", "story")
SPLITS = ("train", "dev", "test")


@dataclass(frozen=True)
class T1Spec:
    n_packages: int = 10
    n_members: int = 6
    n_relations: int = 6
    history_len: int = 4
    train_pair_fraction: float = 0.4    # 两个世界都在 TRAIN 的对象对
    world_split_fraction: float = 0.2   # 一个世界在 TRAIN、另一个留出的对象对
    level_range: int = 60               # 包的参考水平取值范围
    offset_range: int = 12              # 成员偏差取值范围（±）
    seed: int = 20261028
    n_pairs: Optional[int] = None       # 抽多少个对象对出题；None＝全部（对象多时必须抽样）


# 三档规模（被测模型 A 设计稿 v0.2 第二节）。small 即默认设定。
PRESETS = {
    "small": T1Spec(),
    "medium": T1Spec(n_packages=64, n_members=12, n_relations=12, history_len=6, level_range=400, offset_range=24,
                     n_pairs=40000),
    "large": T1Spec(n_packages=256, n_members=16, n_relations=16, history_len=8, level_range=1600, offset_range=40,
                    n_pairs=150000),
    # xl 规模：对象数是 large 的 2 倍，出题量是 4 倍。
    "xl": T1Spec(n_packages=512, n_members=16, n_relations=16, history_len=8, level_range=3200, offset_range=40,
                 n_pairs=600000),
}


def build_t1(spec: T1Spec = T1Spec()) -> dict:
    if spec.history_len < 2 or spec.n_relations < spec.history_len:
        raise ValueError("关系种类要不少于每题事件数，且每题至少两个事件")
    rng = random.Random(spec.seed)
    objects = [(p, m) for p in range(spec.n_packages) for m in range(spec.n_members)]
    values = _distinct_values(spec, rng)

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
    assignment = {}                       # (无序对, 世界) -> 划分
    pair_kind = {}                        # 无序对 -> train / world_new / pair_new
    for i, pair in enumerate(pairs):
        if i < n_train:
            pair_kind[pair] = "train"
            for w in WORLDS:
                assignment[(pair, w)] = "train"
        elif i < n_train + n_world:
            pair_kind[pair] = "world_new"
            seen_world = rng.choice(WORLDS)
            held = "dev" if i % 2 == 0 else "test"
            for w in WORLDS:
                assignment[(pair, w)] = "train" if w == seen_world else held
        else:
            pair_kind[pair] = "pair_new"
            held = "dev" if i % 2 == 0 else "test"
            for w in WORLDS:
                assignment[(pair, w)] = held

    episodes = []
    for (pair, world), split in sorted(assignment.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        a, b = pair if rng.random() < 0.5 else (pair[1], pair[0])
        episodes.append(_episode(len(episodes), split, world, a, b, objects, values, pair_kind[pair], spec, rng))
    rng.shuffle(episodes)
    return {"spec": asdict(spec), "objects": objects, "hidden_values": {f"{p},{m}": v for (p, m), v in values.items()},
            "episodes": episodes}


def label_of(world: str, va: int, vb: int) -> int:
    """物理世界大的赢；故事世界（前提“小的赢”）小的赢。"""
    return int(va > vb) if world == "physical" else int(va < vb)


def resolve(episode: dict) -> tuple[tuple, tuple]:
    """只用可见信息找出 A、B：查询的两个关系各对应历史里唯一的那个事件（CPU 侧的关系对应）。"""
    ra, rb = episode["query"]
    found = {}
    for rel, p, m in episode["history"]:
        if rel in (ra, rb):
            if rel in found:
                raise ValueError(f"题 {episode['id']} 的关系 {rel} 出现了不止一次")
            found[rel] = (p, m)
    return found[ra], found[rb]


def visible(episode: dict) -> dict:
    """模型可见的输入：世界、历史事件、查询关系。"""
    return {"world": episode["world"], "history": [list(e) for e in episode["history"]], "query": list(episode["query"])}


def _distinct_values(spec: T1Spec, rng: random.Random) -> dict:
    """包的参考水平取小数（各包的范围互相重叠，跨包比较不能只看包），成员偏差取互不相同的非零整数。"""
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


def _episode(idx, split, world, a, b, objects, values, kind, spec: T1Spec, rng: random.Random) -> dict:
    rels = rng.sample(range(spec.n_relations), spec.history_len)
    ra, rb, others = rels[0], rels[1], rels[2:]
    distractors = []
    while len(distractors) < len(others):     # 干扰对象：不是 A、B，也互不重复
        o = objects[rng.randrange(len(objects))]
        if o not in (a, b) and o not in distractors:
            distractors.append(o)
    history = [(ra, *a), (rb, *b)] + [(r, *o) for r, o in zip(others, distractors)]
    rng.shuffle(history)
    return {"id": f"t1-{idx:05d}", "split": split, "world": world, "history": history, "query": (ra, rb),
            "label": label_of(world, values[a], values[b]),
            "hidden": {"A": a, "B": b, "pair_kind": kind, "same_package": a[0] == b[0]}}
