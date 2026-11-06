"""T1 的对照模型（测试方案 v0.1 第二节；被测模型 A 设计稿第四节）。这里只有模型定义，没有训练代码。

- B：MLP，输入是所有事件特征拼成的一行（features.flat_features）。
- C：小 Transformer，每个事件一个 token，再加一个“世界＋前提” token（features.token_features）。
- D′：带同样先验的线性模型：每个对象一个数值；用 CPU 的关系匹配直接取出 A、B（不学选择），
  比较两者，再乘以每个世界各自一个方向系数。没有知识包、没有存异，也不用已登记的偏差。
参数量对齐：match_size 在给定的结构里找最接近目标参数量的大小，并报告实际数字（做不到 ±10% 时如实报告）。
"""
from __future__ import annotations

from typing import Callable

import torch
import torch.nn as nn

from .features import T1Batch, flat_features, token_features


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


class MLPControl(nn.Module):
    def __init__(self, n_packages: int, n_members: int, history_len: int, hidden: int):
        super().__init__()
        self.n_packages, self.n_members = n_packages, n_members
        in_dim = history_len * (2 + n_packages + n_members + 2) + 2 + 1
        self.net = nn.Sequential(nn.Linear(in_dim, hidden), nn.ReLU(), nn.Linear(hidden, 1))

    def forward(self, batch: T1Batch) -> torch.Tensor:
        return self.net(flat_features(batch, self.n_packages, self.n_members)).squeeze(-1)  # A 赢的 logit


class TransformerControl(nn.Module):
    def __init__(self, n_packages: int, n_members: int, history_len: int, d_model: int, n_heads: int = 1):
        super().__init__()
        self.n_packages, self.n_members = n_packages, n_members
        token_dim = 2 + n_packages + n_members + 2 + history_len + 2 + 1
        self.inp = nn.Linear(token_dim, d_model)
        self.attn = nn.MultiheadAttention(d_model, n_heads, batch_first=True)
        self.norm1, self.norm2 = nn.LayerNorm(d_model), nn.LayerNorm(d_model)
        self.ffn = nn.Sequential(nn.Linear(d_model, 2 * d_model), nn.ReLU(), nn.Linear(2 * d_model, d_model))
        self.out = nn.Linear(d_model, 1)

    def forward(self, batch: T1Batch) -> torch.Tensor:
        x = self.inp(token_features(batch, self.n_packages, self.n_members))
        x = self.norm1(x + self.attn(x, x, x, need_weights=False)[0])
        x = self.norm2(x + self.ffn(x))
        return self.out(x.mean(dim=1)).squeeze(-1)


class LinearPriorControl(nn.Module):
    """D′：每个对象一个数值，按世界的方向比较。A、B 用 CPU 的关系匹配硬选出（与 A 模型拿到的身份判断相同）。"""

    def __init__(self, n_packages: int, n_members: int):
        super().__init__()
        self.n_members = n_members
        self.value = nn.Parameter(torch.zeros(n_packages * n_members))
        self.direction = nn.Parameter(torch.ones(2))  # 每个世界一个方向系数，可学

    def forward(self, batch: T1Batch) -> torch.Tensor:
        obj = batch.package * self.n_members + batch.member                       # [B, L]
        pick_a = batch.rel_match[..., 0].argmax(dim=1)
        pick_b = batch.rel_match[..., 1].argmax(dim=1)
        rows = torch.arange(obj.shape[0])
        diff = self.value[obj[rows, pick_a]] - self.value[obj[rows, pick_b]]
        return self.direction[batch.world] * diff


class _EventEncoder(nn.Module):
    """对照组共用的事件编码：对象编号的嵌入（与模型 A 一样知道“是哪一个对象”）＋关系匹配＋已登记偏差＋事件位置。"""

    def __init__(self, n_packages: int, n_members: int, history_len: int, d: int):
        super().__init__()
        self.n_members = n_members
        self.obj = nn.Embedding(n_packages * n_members, d)
        self.feat = nn.Linear(4, d)                  # 关系匹配 2 个＋偏差＋偏差是否已知
        self.pos = nn.Embedding(history_len, d)

    def forward(self, batch: T1Batch) -> torch.Tensor:
        feats = torch.cat([batch.rel_match, batch.offset.unsqueeze(-1), batch.offset_known.unsqueeze(-1)], dim=-1)
        return self.obj(batch.package * self.n_members + batch.member) + self.feat(feats) + self.pos(batch.position)


class EmbedMLPControl(nn.Module):
    """B（可放大）：事件编码拼成一行，再加世界和前提，经过若干层 MLP。"""

    def __init__(self, n_packages: int, n_members: int, history_len: int, d: int, hidden: int, depth: int = 2):
        super().__init__()
        self.enc = _EventEncoder(n_packages, n_members, history_len, d)
        layers, width = [], history_len * d + 2 + 1
        for _ in range(depth):
            layers += [nn.Linear(width, hidden), nn.GELU()]
            width = hidden
        self.net = nn.Sequential(*layers, nn.Linear(width, 1))

    def forward(self, batch: T1Batch) -> torch.Tensor:
        x = self.enc(batch).flatten(1)
        world = torch.nn.functional.one_hot(batch.world, 2).float()
        return self.net(torch.cat([x, world, batch.premise.unsqueeze(-1)], dim=-1)).squeeze(-1)


class EmbedTransformerControl(nn.Module):
    """C（可放大）：每个事件一个 token，另加“世界＋前提” token；标准 Transformer 编码后取平均。"""

    def __init__(self, n_packages: int, n_members: int, history_len: int, d_model: int, n_layers: int = 2,
                 n_heads: int = 4):
        super().__init__()
        self.enc = _EventEncoder(n_packages, n_members, history_len, d_model)
        self.world = nn.Embedding(2, d_model)
        self.premise = nn.Linear(1, d_model, bias=False)
        layer = nn.TransformerEncoderLayer(d_model, n_heads, 4 * d_model, dropout=0.0, batch_first=True)
        self.body = nn.TransformerEncoder(layer, n_layers, enable_nested_tensor=False)
        self.out = nn.Linear(d_model, 1)

    def forward(self, batch: T1Batch) -> torch.Tensor:
        world_tok = (self.world(batch.world) + self.premise(batch.premise.unsqueeze(-1))).unsqueeze(1)
        x = self.body(torch.cat([self.enc(batch), world_tok], dim=1))
        return self.out(x.mean(dim=1)).squeeze(-1)


def match_size(build: Callable[[int], nn.Module], sizes, target: int, tol: float = 0.10) -> dict:
    """在候选大小里选参数量最接近 target 的一个；返回实际参数量，以及是否落在 ±tol 以内。
    在 meta 设备上建模型，只数参数、不分配内存，千万级参数也很快。"""
    def n_params(s):
        with torch.device("meta"):
            return count_params(build(s))
    best = min(((abs(n_params(s) - target), s) for s in sizes), key=lambda t: (t[0], t[1]))
    size = best[1]
    n = n_params(size)
    return {"size": size, "params": n, "target": target, "within_tolerance": abs(n - target) <= tol * target}
