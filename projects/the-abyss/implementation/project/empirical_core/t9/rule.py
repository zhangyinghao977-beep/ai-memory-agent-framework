"""T9：从事件链里长出规则（2026-11-06）。

T8 只长了参考向量，规则还是人给的：`rel == query` 判断关系对不对得上，`anchor_rel` 指出谁是锚。
图谱 11-05：“初始 SLOT 与参考系提供组合、比较及合法转移的起点”，“不据此预设……永久冻结”。
所以这里问：合法转移能不能从事件链里长出来，世界变了以后能不能修订。

工作解释（不是构造里的定义）：
某个查询的链里，总是比平常多出来的关系，算作和这个查询对得上。做法是查询 × 关系的计数，
算提升度（比平常多几倍）。每个查询取最高值和中位数的中点，高过中点的算合法。从没出现过的关系不参加。
只读关系和查询的编号。不读包的编号，不读答案，不比较两个编号是否相等，不知道谁是锚。

开发检查发现：第一版用“最大的间隔”切开。从没出现过的关系提升度是 0，最大的间隔落在最底下，
所有关系都算合法，互相支持题全错。所以换成中点。这个改动是看了 dev 才做的。
"""
from __future__ import annotations

import torch


def relation_lift(rel: torch.Tensor, query: torch.Tensor, n_rel: int) -> torch.Tensor:
    """rel：[N, L]，query：[N]。返回 [n_rel, n_rel]：查询 q 的链里，关系 r 比平常多几倍。没见过的是 0。"""
    c = torch.zeros(n_rel, n_rel, dtype=torch.float64)
    c.index_put_((query.unsqueeze(1).expand_as(rel), rel), torch.ones(rel.shape, dtype=torch.float64), accumulate=True)
    expected = c.sum(1, keepdim=True) * c.sum(0, keepdim=True) / c.sum().clamp(min=1.0)
    return torch.where(expected > 0, c / expected.clamp(min=1e-12), torch.zeros_like(c))


def legal_table(rel: torch.Tensor, query: torch.Tensor, n_rel: int) -> torch.Tensor:
    """返回 [n_rel, n_rel] 的布尔表：legal[q, r]。没见过的查询，整行都是 False。"""
    lift = relation_lift(rel, query, n_rel)
    seen = lift.sum(0) > 0
    out = torch.zeros(n_rel, n_rel, dtype=torch.bool)
    if not seen.any():
        return out
    part = lift[:, seen]
    line = (part.max(1, keepdim=True).values + part.median(1, keepdim=True).values) / 2
    out[:, seen] = (part > line) & (part.sum(1, keepdim=True) > 0)
    return out


def shuffle_relations(rel: torch.Tensor, seed: int) -> torch.Tensor:
    """把关系打乱到所有链：每种关系出现的次数不变，查询和关系的联系没有了。"""
    g = torch.Generator().manual_seed(seed)
    flat = rel.flatten()
    return flat[torch.randperm(len(flat), generator=g)].view(rel.shape)


def shift_map(n_ordinary: int, n_rel: int, seed: int) -> torch.Tensor:
    """世界变化：普通关系换一种对应，每个都换到别的编号；其余关系（锚）不变。返回 [n_rel]。"""
    g = torch.Generator().manual_seed(seed)
    while True:
        p = torch.randperm(n_ordinary, generator=g)
        if (p != torch.arange(n_ordinary)).all():
            return torch.cat([p, torch.arange(n_ordinary, n_rel)])


def window_table(old: tuple, new: tuple, m: int, window: int, n_rel: int) -> torch.Tensor:
    """只记得最近 window 条链：window − m 条旧的，m 条新的。不知道世界什么时候变的。"""
    rel = torch.cat([old[0][len(old[0]) - (window - m):], new[0][:m]])
    query = torch.cat([old[1][len(old[1]) - (window - m):], new[1][:m]])
    return legal_table(rel, query, n_rel)


def cosine_choice_two9(d: dict, vec: torch.Tensor, legal: torch.Tensor) -> float:
    """不训练的基线：合法的候选里，选和某个非候选事件余弦最大的。不知道谁是锚。"""
    v = torch.nn.functional.normalize(vec[d["obj"]], dim=-1)
    cand = legal[d["query"].unsqueeze(1), d["rel"]]
    s = (v @ v.transpose(1, 2)).masked_fill(cand.unsqueeze(1), -9.0).max(-1).values
    right = s.masked_fill(~cand, -99.0).argmax(-1) == d["target"]
    return float(right[d["n_cand"] == 2].float().mean())
