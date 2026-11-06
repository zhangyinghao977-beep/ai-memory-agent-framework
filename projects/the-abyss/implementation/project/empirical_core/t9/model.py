"""T9 的选择器：谁合法看长出来的表，谁算数靠答案反馈（2026-11-06）。

和 T8 的 full 比，拿掉了两样人给的东西：
- `rel == query`：换成查规则表 legal[查询, 关系]；
- `anchor_rel`：这里不读。模型不知道谁是锚，只看到每个事件的关系编号，靠整个答案的反馈学谁算数。

kind：
- sim：固定余弦比较。学 12 个数：t、b、a，每种关系的权重 8 个，是不是候选的权重 1 个。结构还是人写的；
- pair、attn：和 T6 一样，输入里的“是不是锚”换成从头学的关系嵌入。

表是外面的东西，不是权重：换一张表，不用重新训练。
"""
from __future__ import annotations

import torch
import torch.nn as nn

from ..t5.model import Block, answer_prob, evaluate, labels, take
from ..t5.task import T5Spec
from ..t6.model import PairBlock

KINDS = ("attn", "pair", "sim")


class Selector9(nn.Module):
    def __init__(self, spec: T5Spec, vec: torch.Tensor, legal: torch.Tensor, kind: str, d: int = 32, layers: int = 2, heads: int = 4):
        super().__init__()
        if kind not in KINDS:
            raise ValueError(kind)
        self.kind = kind
        self.register_buffer("vec", vec)
        self.register_buffer("legal", legal)
        if kind == "sim":
            self.t = nn.Parameter(torch.tensor(4.0))
            self.b = nn.Parameter(torch.tensor(0.5))
            self.a = nn.Parameter(torch.tensor(1.0))
            self.w = nn.Parameter(torch.zeros(spec.n_relations))
            self.c = nn.Parameter(torch.tensor(0.0))
            return
        k = spec.k
        self.rel = nn.Embedding(spec.n_relations, k)
        self.inp = nn.Linear(1 + 2 * k, d)
        self.pos = nn.Embedding(spec.chain_len, d)
        self.blocks = nn.ModuleList(PairBlock(d) if kind == "pair" else Block(d, heads, kind) for _ in range(layers))
        self.ptr = nn.Linear(d, 1)

    def cand(self, b: dict) -> torch.Tensor:
        return self.legal[b["query"].unsqueeze(1), b["rel"]]

    def scores(self, b: dict, cand: torch.Tensor) -> torch.Tensor:
        if self.kind == "sim":
            v = nn.functional.normalize(self.vec[b["obj"]], dim=-1)
            same = torch.sigmoid(self.t * (v @ v.transpose(1, 2) - self.b))
            who = torch.sigmoid(self.w[b["rel"]] + self.c * cand.float())
            T = v.shape[1]
            off = 1.0 - torch.eye(T, dtype=v.dtype, device=v.device)
            return self.a * (same * off * who.unsqueeze(1)).sum(-1)
        x = torch.cat([cand.float().unsqueeze(-1), self.rel(b["rel"]), self.vec[b["obj"]]], dim=-1)
        h = self.inp(x) + self.pos.weight
        for blk in self.blocks:
            h = blk(h)
        return self.ptr(h).squeeze(-1)

    def forward(self, b: dict) -> torch.Tensor:
        """选择概率 [N, L]。"""
        cand = self.cand(b)
        return torch.softmax(self.scores(b, cand).masked_fill(~cand, -1e4), dim=-1)


def train_one9(spec: T5Spec, vec: torch.Tensor, legal: torch.Tensor, bit: torch.Tensor, data: dict, kind: str, seed: int, *, steps: int,
               batch: int = 128, lr: float = 1e-3, eval_every: int = 1000, clip: float = 1.0) -> tuple:
    """和 T6 的 train_one6 同一个循环。"""
    torch.manual_seed(seed)
    m = Selector9(spec, vec, legal, kind)
    opt = torch.optim.Adam(m.parameters(), lr=lr)
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
        nn.utils.clip_grad_norm_(m.parameters(), clip)
        opt.step()
        total, count = total + float(loss.detach()), count + 1
        if step % eval_every == 0 or step == steps:
            ev = evaluate(m, data["dev"], bit)
            curve.append({"step": step, "dev_choice_two": ev["choice_two"], "train_loss": total / count})
            total, count = 0.0, 0
    return m, curve
