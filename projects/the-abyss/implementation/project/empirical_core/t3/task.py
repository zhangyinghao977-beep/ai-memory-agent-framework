"""T3 出题器：T2 的 base 条件，另有链内改口和“间接包”（2026-11-03）。

依据（图谱网站 2026-11-03 增补；名词解释版本 v0.57）：
- KA 绑定 SLOT；EA↔KA 双向的结果是 SLOT；SLOT 在 EA↔CA 这一段作局部不变量，不是永久冻结。
- 训练停止方向：看 EA/KA 相互修正是否稳定并进入容许范围；量化、阈值、连续窗口待定；固定轮数只是硬上限。
- 筛子类比：EA 如筛子、KA 如材料；单向反复筛可能抹平差异，理想是双方互相适应。
- 比较循环训练中每隔若干轮统一校验的时间成本。

和 T2 base 的不同：
- 一部分题带链内改口（同一关系在目标链里出现两次，以后一次为准），比例 dup_fraction。EA 要学这条规则。
- 间接包（编号最大的 n_indirect 个包）：TRAIN 里凡是 A 或 B 属于间接包的题，那一边一定带链内改口。
  所以 CPU 不能精确对应这些包的成员（task.exact_resolve 返回 None），KA 只有经过 EA 的选择（筛子）才拿得到材料。
  DEV、TEST 里间接包和其他包一样出题。
题目结构、规则和划分同 T2（一张（无序对象对, 世界）划分表），所以可以直接用 T2 的编码、门禁和计分。
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Optional

from ..t2.task import WORLDS, _distinct_values, _episode


@dataclass(frozen=True)
class T3Spec:
    n_packages: int = 12
    n_members: int = 6
    n_relations: int = 8
    chain_len: int = 3
    n_chains: int = 6
    n_speakers: int = 6
    train_pair_fraction: float = 0.4
    world_split_fraction: float = 0.2
    level_range: int = 80
    offset_range: int = 12
    n_pairs: Optional[int] = None
    complex_fraction: float = 0.5       # 带链间覆盖的题的比例（同 T2）
    dup_fraction: float = 0.3           # 带链内改口的题的比例（间接包的 TRAIN 题另外强制）
    n_indirect: int = 2                 # 间接包：编号最大的几个
    seed: int = 20261103


PRESETS = {
    "small": T3Spec(),
    "main": T3Spec(n_packages=96, n_members=12, n_relations=12, chain_len=4, n_chains=6, n_speakers=8,
                   level_range=600, offset_range=24, n_pairs=60000, n_indirect=16),
}


def build_t3(spec: T3Spec = T3Spec()) -> dict:
    if spec.chain_len < 2 or spec.n_relations < spec.chain_len + 1 or spec.n_speakers < 4 or spec.n_chains < 6:
        raise ValueError("每条链至少 2 个事件、关系种类多于链长、至少 4 个说话人、每题至少 6 条链")
    if not 0 < spec.n_indirect < spec.n_packages:
        raise ValueError("间接包的个数要在 1 和包数之间")
    rng = random.Random(spec.seed)
    objects = [(p, m) for p in range(spec.n_packages) for m in range(spec.n_members)]
    values = _distinct_values(spec, rng)
    indirect = set(range(spec.n_packages - spec.n_indirect, spec.n_packages))
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
    for i, pair in enumerate(pairs):                    # 划分同 T2
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

    episodes = []
    for key in sorted(assignment):
        pair, world = key
        split = assignment[key]
        if split == "train" and (pair[0][0] in indirect or pair[1][0] in indirect):
            while True:                                 # 间接包那一边一定带链内改口：抽到满足为止
                ep = _episode(len(episodes), split, world, pair, pair_kind[pair], "C2", objects, values, spec, rng)
                h = ep["hidden"]
                if (h["A"][0] not in indirect or h["dup_x"]) and (h["B"][0] not in indirect or h["dup_y"]):
                    break
        else:
            cond = "C2" if rng.random() < spec.dup_fraction else "base"
            ep = _episode(len(episodes), split, world, pair, pair_kind[pair], cond, objects, values, spec, rng)
        ep["id"] = f"t3-{len(episodes):06d}"
        ep["condition"] = "base"
        ep["hidden"]["indirect"] = int(ep["hidden"]["A"][0] in indirect) + int(ep["hidden"]["B"][0] in indirect)
        episodes.append(ep)
    rng.shuffle(episodes)
    return {"spec": asdict(spec), "objects": objects, "indirect_packages": sorted(indirect),
            "hidden_values": {f"{p},{m}": v for (p, m), v in values.items()}, "episodes": episodes}
