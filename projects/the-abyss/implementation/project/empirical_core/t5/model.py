"""T5 的选择器：同一个结构，只换 token 之间怎么交流；再加两个不用 attention 的 MLP（2026-11-05）。

kind：
- attn：自注意力，权重看内容；
- mean：权重固定为平均。token 之间能交流，但不会挑；
- token：每个位置只看自己。token 之间不交流；
- flat：把整条链摊平进 MLP，参数量和上面相近；
- flat_big：同上，隐藏层大很多，给不用 attention 的做法一个宽松的机会。

lattice：
- True：拿到晶格：对象的参考向量（固定）、关系是否对得上、是不是锚；不合法的位置不能选（硬晶格）。
- False：没有晶格：对象、关系、查询都是从头学的嵌入，什么位置都能选。结构要系统自己长出来。

选择的结果只用来查 KA 给的比特，得到答案；损失只看整个答案对不对。
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn

from .task import T5Spec

KINDS = ("attn", "mean", "token", "flat", "flat_big")
BLOCK_KINDS = ("attn", "mean", "token")


class Block(nn.Module):
    def __init__(self, d: int, heads: int, kind: str):
        super().__init__()
        self.h, self.kind = heads, kind
        self.qkv = nn.Linear(d, 3 * d)
        self.out = nn.Linear(d, d)
        self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.ff = nn.Sequential(nn.Linear(d, 2 * d), nn.ReLU(), nn.Linear(2 * d, d))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T, D = x.shape
        q, k, v = (t.view(B, T, self.h, D // self.h).transpose(1, 2) for t in self.qkv(x).chunk(3, dim=-1))
        if self.kind == "attn":
            w = torch.softmax(q @ k.transpose(-1, -2) / math.sqrt(D // self.h), dim=-1)
        elif self.kind == "mean":
            w = torch.full((T, T), 1.0 / T, dtype=x.dtype, device=x.device)
        else:
            w = torch.eye(T, dtype=x.dtype, device=x.device)
        x = self.n1(x + self.out((w @ v).transpose(1, 2).reshape(B, T, D)))
        return self.n2(x + self.ff(x))


class Selector(nn.Module):
    def __init__(self, spec: T5Spec, vec: torch.Tensor, kind: str, lattice: bool, d: int = 32, layers: int = 2, heads: int = 4,
                 flat_hidden: int = 64, flat_big_hidden: int = 512):
        super().__init__()
        if kind not in KINDS:
            raise ValueError(kind)
        self.spec, self.kind, self.lattice = spec, kind, lattice
        self.register_buffer("vec", vec)
        L, k = spec.chain_len, spec.k
        if lattice:
            feat = 2 + k
        else:
            self.obj = nn.Embedding(spec.n_objects, k)
            self.rel = nn.Embedding(spec.n_relations, k)
            self.qry = nn.Embedding(spec.n_relations, k)
            feat = 3 * k
        if kind in BLOCK_KINDS:
            self.inp = nn.Linear(feat, d)
            self.pos = nn.Embedding(L, d)
            self.blocks = nn.ModuleList(Block(d, heads, kind) for _ in range(layers))
            self.ptr = nn.Linear(d, 1)
        else:
            h = flat_hidden if kind == "flat" else flat_big_hidden
            self.mlp = nn.Sequential(nn.Linear(L * feat, h), nn.ReLU(), nn.Linear(h, h), nn.ReLU(), nn.Linear(h, L))

    def features(self, b: dict) -> torch.Tensor:
        if self.lattice:
            is_q = (b["rel"] == b["query"].unsqueeze(1)).float()
            is_a = (b["rel"] == self.spec.anchor_rel).float()
            return torch.cat([is_q.unsqueeze(-1), is_a.unsqueeze(-1), self.vec[b["obj"]]], dim=-1)
        q = self.qry(b["query"]).unsqueeze(1).expand(-1, b["rel"].shape[1], -1)
        return torch.cat([self.rel(b["rel"]), q, self.obj(b["obj"])], dim=-1)

    def forward(self, b: dict) -> torch.Tensor:
        """选择概率 [N, L]。"""
        x = self.features(b)
        if self.kind in BLOCK_KINDS:
            h = self.inp(x) + self.pos.weight
            for blk in self.blocks:
                h = blk(h)
            s = self.ptr(h).squeeze(-1)
        else:
            s = self.mlp(x.flatten(1))
        if self.lattice:
            s = s.masked_fill(b["rel"] != b["query"].unsqueeze(1), -1e4)
        return torch.softmax(s, dim=-1)


def n_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())


def take(data: dict, idx: torch.Tensor) -> dict:
    return {k: data[k][idx] for k in ("rel", "obj", "query", "target", "n_cand")}


def answer_prob(sel: torch.Tensor, b: dict, bit: torch.Tensor) -> torch.Tensor:
    return (sel * bit[b["obj"]]).sum(-1)


def labels(b: dict, bit: torch.Tensor) -> torch.Tensor:
    return bit[b["obj"].gather(1, b["target"].unsqueeze(1)).squeeze(1)]


@torch.no_grad()
def evaluate(m: Selector, data: dict, bit: torch.Tensor, chunk: int = 2048) -> dict:
    m.eval()
    n = len(data["target"])
    pick, prob = [], []
    for s in range(0, n, chunk):
        b = take(data, torch.arange(s, min(s + chunk, n)))
        sel = m(b)
        pick.append(sel.argmax(-1))
        prob.append(answer_prob(sel, b, bit))
    pick, prob = torch.cat(pick), torch.cat(prob)
    m.train()
    right = pick == data["target"]
    y = labels(data, bit)
    two, one = data["n_cand"] == 2, data["n_cand"] == 1
    return {"choice_two": float(right[two].float().mean()), "choice_one": float(right[one].float().mean()),
            "answer_all": float(((prob > 0.5).float() == y).float().mean()),
            "n_two": int(two.sum()), "n_one": int(one.sum()), "right_two": int(right[two].sum()), "right_one": int(right[one].sum())}


def train_one(spec: T5Spec, lat: dict, data: dict, kind: str, lattice: bool, seed: int, *, steps: int, batch: int = 128,
              lr: float = 1e-3, eval_every: int = 1000, clip: float = 1.0, log=None) -> tuple:
    torch.manual_seed(seed)
    m = Selector(spec, lat["vec"], kind, lattice)
    opt = torch.optim.Adam(m.parameters(), lr=lr)
    g = torch.Generator().manual_seed(seed + 7)
    tr, bit = data["train"], lat["bit"]
    n = len(tr["target"])
    curve = []
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
        if step % eval_every == 0 or step == steps:
            ev = evaluate(m, data["dev"], bit)
            curve.append({"step": step, "dev_choice_two": ev["choice_two"]})
            if log:
                log(step, ev)
    return m, curve
