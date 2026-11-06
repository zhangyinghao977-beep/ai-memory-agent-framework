"""T10 的训练：和 T9 同一个模型、同一个循环，只改关系嵌入开始时的大小（2026-11-06）。

T9 的事后检查发现：互相支持题里没有锚，候选也和 T8 一样，但成对比较和 attention 掉了很多。
变的是 T9 加的 16 维关系嵌入，开始时它在第一层里比参考向量大 4 倍。

先用同一个种子造好 T9 的模型，再把 `rel.weight` 乘上 scale。这一步不用随机数，
所以别的初始权重和批次顺序都和 T9 一样。
- learn=True：关系嵌入继续靠答案的反馈学；
- learn=False：关系嵌入不学（只和 scale=0 一起用，等于没有这部分输入）。
"""
from __future__ import annotations

import torch
import torch.nn as nn

from ..t5.model import answer_prob, evaluate, labels, take
from ..t5.task import T5Spec
from ..t9.model import Selector9


def make10(spec: T5Spec, vec: torch.Tensor, legal: torch.Tensor, kind: str, seed: int, scale: float, learn: bool) -> Selector9:
    torch.manual_seed(seed)
    m = Selector9(spec, vec, legal, kind)
    with torch.no_grad():
        m.rel.weight.mul_(scale)
    m.rel.weight.requires_grad_(learn)
    return m


def part_sizes(m: Selector9, b: dict, k: int) -> dict:
    """第一层里，来自关系嵌入和来自参考向量的部分各有多大（每个位置的均方根）。"""
    W = m.inp.weight.detach()
    rel = m.rel(b["rel"]).detach() @ W[:, 1:1 + k].T
    vec = m.vec[b["obj"]] @ W[:, 1 + k:].T
    return {"rel": float(rel.pow(2).sum(-1).mean().sqrt()), "vec": float(vec.pow(2).sum(-1).mean().sqrt())}


def train_one10(spec: T5Spec, vec: torch.Tensor, legal: torch.Tensor, bit: torch.Tensor, data: dict, kind: str, seed: int, scale: float, learn: bool, *,
                steps: int, batch: int = 128, lr: float = 1e-3, eval_every: int = 1000, clip: float = 1.0) -> tuple:
    """和 T9 的 train_one9 同一个循环。scale=1、learn=True 时和 T9 逐位相同。"""
    m = make10(spec, vec, legal, kind, seed, scale, learn)
    opt = torch.optim.Adam([p for p in m.parameters() if p.requires_grad], lr=lr)
    g = torch.Generator().manual_seed(seed + 7)
    tr = data["train"]
    n = len(tr["target"])
    curve, total, count = [], 0.0, 0
    for step in range(1, steps + 1):
        b = take(tr, torch.randint(0, n, (batch,), generator=g))
        p = answer_prob(m(b), b, bit).clamp(1e-5, 1 - 1e-5)
        loss = nn.functional.binary_cross_entropy(p, labels(b, bit))
        if not torch.isfinite(loss):
            raise FloatingPointError(f"{kind} 第 {step} 步损失不是有限数")
        opt.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_([q for q in m.parameters() if q.requires_grad], clip)
        opt.step()
        total, count = total + float(loss.detach()), count + 1
        if step % eval_every == 0 or step == steps:
            ev = evaluate(m, data["dev"], bit)
            curve.append({"step": step, "dev_choice_two": ev["choice_two"], "train_loss": total / count})
            total, count = 0.0, 0
    return m, curve
