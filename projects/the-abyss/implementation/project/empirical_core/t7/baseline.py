"""T7 的余弦基线：不训练，只看向量（2026-11-06）。

和 sim 看到的东西一样：参考向量、关系是否对得上、是不是锚。
- anchor：选和锚余弦最大的候选；
- mutual：选和某个非候选事件余弦最大的候选。
不用包的编号，也不用答案。
"""
from __future__ import annotations

import torch

from ..t5.task import T5Spec


def cosine_scores(task: str, d: dict, vec: torch.Tensor, spec: T5Spec) -> torch.Tensor:
    v = torch.nn.functional.normalize(vec[d["obj"]], dim=-1)
    c = v @ v.transpose(1, 2)
    cand = d["rel"] == d["query"].unsqueeze(1)
    who = d["rel"] == spec.anchor_rel if task == "anchor" else ~cand
    s = c.masked_fill(~who.unsqueeze(1), -9.0).max(-1).values
    return s.masked_fill(~cand, -99.0)


def cosine_choice_two(task: str, d: dict, vec: torch.Tensor, spec: T5Spec) -> float:
    right = cosine_scores(task, d, vec, spec).argmax(-1) == d["target"]
    return float(right[d["n_cand"] == 2].float().mean())
