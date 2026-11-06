"""T6 的选择器：把晶格拆开，再加两种不是 attention 的比较（2026-11-05）。

T5 里晶格是整个给或整个拿走的。这里拆成两部分：
- 参考向量（知识参考系）：对象的固定向量。不给时，对象用从头学的嵌入。
- 规则（合法转移）：关系是否对得上、是不是锚、不合法的位置不能选。不给时，关系和查询用从头学的嵌入，什么位置都能选。

part：
- full：两部分都给（等于 T5 的有晶格）；
- vec：只给参考向量；
- rule：只给规则；
- none：都不给（等于 T5 的没有晶格）。

kind：
- attn、mean：和 T5 一样；
- pair：每一对 token 先相乘，再过同一个小 MLP，然后加起来。没有 softmax，token 之间不竞争；
- sim：比较由晶格给：固定参考向量的余弦。只学 6 个数：相似到多少算一样、谁算数、分数放大多少。
  这个结构是人按题目写的，不是通用的做法。

本实验比较 attention 与其他候选比较机制，不预设哪种机制更优。
"""
from __future__ import annotations

import torch
import torch.nn as nn

from ..t5.model import Block, answer_prob, evaluate, labels, n_params, take  # noqa: F401
from ..t5.task import T5Spec

PARTS = ("full", "vec", "rule", "none")
KINDS = ("attn", "mean", "pair", "sim")


class PairBlock(nn.Module):
    def __init__(self, d: int):
        super().__init__()
        self.q, self.k = nn.Linear(d, d), nn.Linear(d, d)
        self.g = nn.Sequential(nn.Linear(d, d), nn.ReLU(), nn.Linear(d, d))
        self.out = nn.Linear(d, d)
        self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.ff = nn.Sequential(nn.Linear(d, 2 * d), nn.ReLU(), nn.Linear(2 * d, d))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        T = x.shape[1]
        m = self.g(self.q(x).unsqueeze(2) * self.k(x).unsqueeze(1))
        off = 1.0 - torch.eye(T, dtype=x.dtype, device=x.device)
        m = (m * off[None, :, :, None]).sum(2) / (T - 1)
        x = self.n1(x + self.out(m))
        return self.n2(x + self.ff(x))


class Selector6(nn.Module):
    def __init__(self, spec: T5Spec, vec: torch.Tensor, kind: str, part: str, d: int = 32, layers: int = 2, heads: int = 4):
        super().__init__()
        if kind not in KINDS or part not in PARTS:
            raise ValueError((kind, part))
        if kind == "sim" and part != "full":
            raise ValueError("sim 的比较来自参考向量和规则，只有 full 能用")
        self.spec, self.kind, self.part = spec, kind, part
        self.give_vec, self.give_rule = part in ("full", "vec"), part in ("full", "rule")
        self.register_buffer("vec", vec)
        if kind == "sim":
            self.t = nn.Parameter(torch.tensor(4.0))
            self.b = nn.Parameter(torch.tensor(0.5))
            self.a = nn.Parameter(torch.tensor(1.0))
            self.gate = nn.Linear(2, 1)
            return
        L, k = spec.chain_len, spec.k
        if not self.give_vec:
            self.obj = nn.Embedding(spec.n_objects, k)
        if not self.give_rule:
            self.rel = nn.Embedding(spec.n_relations, k)
            self.qry = nn.Embedding(spec.n_relations, k)
        self.inp = nn.Linear((2 if self.give_rule else 2 * k) + k, d)
        self.pos = nn.Embedding(L, d)
        self.blocks = nn.ModuleList(PairBlock(d) if kind == "pair" else Block(d, heads, kind) for _ in range(layers))
        self.ptr = nn.Linear(d, 1)

    def flags(self, b: dict) -> torch.Tensor:
        is_q = (b["rel"] == b["query"].unsqueeze(1)).float()
        is_a = (b["rel"] == self.spec.anchor_rel).float()
        return torch.stack([is_q, is_a], dim=-1)

    def features(self, b: dict) -> torch.Tensor:
        if self.give_rule:
            rule = self.flags(b)
        else:
            q = self.qry(b["query"]).unsqueeze(1).expand(-1, b["rel"].shape[1], -1)
            rule = torch.cat([self.rel(b["rel"]), q], dim=-1)
        return torch.cat([rule, self.vec[b["obj"]] if self.give_vec else self.obj(b["obj"])], dim=-1)

    def sim_scores(self, b: dict) -> torch.Tensor:
        v = nn.functional.normalize(self.vec[b["obj"]], dim=-1)
        same = torch.sigmoid(self.t * (v @ v.transpose(1, 2) - self.b))
        who = torch.sigmoid(self.gate(self.flags(b))).squeeze(-1)
        T = v.shape[1]
        off = 1.0 - torch.eye(T, dtype=v.dtype, device=v.device)
        return self.a * (same * off * who.unsqueeze(1)).sum(-1)

    def forward(self, b: dict) -> torch.Tensor:
        """选择概率 [N, L]。"""
        if self.kind == "sim":
            s = self.sim_scores(b)
        else:
            h = self.inp(self.features(b)) + self.pos.weight
            for blk in self.blocks:
                h = blk(h)
            s = self.ptr(h).squeeze(-1)
        if self.give_rule:
            s = s.masked_fill(b["rel"] != b["query"].unsqueeze(1), -1e4)
        return torch.softmax(s, dim=-1)


def train_one6(spec: T5Spec, lat: dict, data: dict, kind: str, part: str, seed: int, *, steps: int, batch: int = 128,
               lr: float = 1e-3, eval_every: int = 1000, clip: float = 1.0, log=None) -> tuple:
    """和 T5 的 train_one 同一个循环。full、none 用同一个种子时，前面的步数和 T5 走的是同一条路。"""
    torch.manual_seed(seed)
    m = Selector6(spec, lat["vec"], kind, part)
    opt = torch.optim.Adam(m.parameters(), lr=lr)
    g = torch.Generator().manual_seed(seed + 7)
    tr, bit = data["train"], lat["bit"]
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
        nn.utils.clip_grad_norm_(m.parameters(), clip)
        opt.step()
        total, count = total + float(loss.detach()), count + 1
        if step % eval_every == 0 or step == steps:
            ev = evaluate(m, data["dev"], bit)
            curve.append({"step": step, "dev_choice_two": ev["choice_two"], "train_loss": total / count})
            total, count = 0.0, 0
            if log:
                log(step, ev)
    return m, curve
