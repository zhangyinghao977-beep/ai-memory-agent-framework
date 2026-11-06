"""T3 的门禁、分层与简单基线：直接用 T2 的（只有 base 一个条件），另加“间接包”这一层。"""
from __future__ import annotations

import torch

from ..t2 import baselines as t2b

INDIRECT = ("none", "one", "both")


def gate(data: dict, split: str, min_main: int, max_shortcut_accuracy: float):
    return t2b.gate(data, split, ("base",), ("base",), min_main=min_main, max_shortcut_accuracy=max_shortcut_accuracy)


def majority(data: dict):
    return t2b.majority(data, ("base",))


def path_reasoner(data: dict):
    return t2b.path_reasoner(data, ("base",))


def strata(data: dict, split: str) -> dict:
    """T2 的分层（门禁类别、这一对见过与否、路径能否推出、需要哪一层、同包／跨包），加上 A、B 里有几个属于间接包。"""
    out = t2b.strata(data, split, ("base",), ("base",))
    for ep in data["episodes"]:
        if ep["split"] == split:
            out[ep["id"]]["indirect"] = INDIRECT[ep["hidden"]["indirect"]]
    return out


def indirect_exact_rows(train, indirect: list) -> int:
    """TRAIN 里 CPU 能精确对应、而且 A 或 B 属于间接包的题数。按出题规则应当是 0（门禁会查）。"""
    ind = torch.tensor(sorted(indirect))
    hit = torch.isin(train.ex_a[:, 0], ind) | torch.isin(train.ex_b[:, 0], ind)
    return int((train.exact & hit).sum())
