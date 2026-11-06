"""被测模型 A：T1 上的 EA／KA（被测模型 A 设计稿 v0.2 第三节）。这里只有模型定义，没有训练代码。

- EA（事件链 attention）：事件做成 token（关系匹配＋事件位置），经过多层 self-attention；
  两个指针头在“各事件＋没有合适事件”上选出 A 和 B，每个事件的选择概率都保留。
  EA 只看身份判断（关系是否对得上），不看对象本身——查包与身份判断由 CPU 侧提供，不让 attention 去猜。
  identity_bias > 0 时，CPU 的身份判断作为固定偏置直接加在选择分数上（结构约束），EA 仍可学着改动它。
  2026-11-01 的开发检查发现：只把身份判断当输入特征（identity_bias=0）时，EA 在 medium 开发题上学不会选事件（DEV 约 50%）。
- KA（知识 attention，每包一份）：成员在本包参考系里的表示＝可学习的向量偏差，参考成员固定为 0（存异）；
  T1-a 再加上已登记偏差的读数（一个可学习的线性读入）。
- 尺子转换：每包一个可学习的线性转换（矩阵＋偏置），把本包表示换到共同空间；不同包的表示不直接相减。
- 比较：在共同空间里对 A、B 做比较（MLP），前提是否适用作为一个输入，由学习决定它怎样影响比较。
输出“A 赢”的 logit，以及 EA 的选择概率和“没有合适事件”的概率。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
import torch.nn as nn

from .features import T1Batch


@dataclass(frozen=True)
class ModelAConfig:
    n_packages: int
    n_members: int
    history_len: int
    k: int = 4              # 包内参考系的表示维数
    d_event: int = 8        # EA 的事件表示维数
    n_layers: int = 1       # EA 层数
    n_heads: int = 1
    d_compare: int = 8      # 比较 MLP 的宽度
    identity_bias: float = 0.0   # CPU 侧身份判断（关系对得上查询）加在 EA 选择分数上的固定偏置；0＝只作输入特征


# 三档规模；题目规模取自 task.PRESETS。参数量以 count_params 实测为准。
SIZE_PRESETS = {
    "small": dict(k=4, d_event=8, n_layers=1, n_heads=1, d_compare=8),
    "medium": dict(k=48, d_event=128, n_layers=3, n_heads=4, d_compare=256),
    "large": dict(k=128, d_event=256, n_layers=6, n_heads=8, d_compare=512),
    "xl": dict(k=160, d_event=320, n_layers=8, n_heads=8, d_compare=640),        # 约 2500 万参数
}


def config_for(task_spec: dict, size: str, **overrides) -> ModelAConfig:
    return ModelAConfig(task_spec["n_packages"], task_spec["n_members"], task_spec["history_len"],
                        **{**SIZE_PRESETS[size], **overrides})


class ModelA(nn.Module):
    def __init__(self, cfg: ModelAConfig):
        super().__init__()
        self.cfg = cfg
        P, M, L, k = cfg.n_packages, cfg.n_members, cfg.history_len, cfg.k
        # KA：非参考成员的偏差向量；参考成员的偏差不是参数，固定为 0。
        self.member_offset = nn.Parameter(torch.randn(P, M - 1, k) * 0.02)
        self.registered_read = nn.Linear(1, k, bias=False)      # T1-a：已登记偏差的读数
        # 尺子转换：每包一个线性转换，初始化为恒等。
        self.convert_w = nn.Parameter(torch.eye(k).repeat(P, 1, 1) + torch.randn(P, k, k) * 0.01)
        self.convert_b = nn.Parameter(torch.zeros(P, k))
        # EA
        self.ea_in = nn.Linear(2, cfg.d_event)
        self.ea_pos = nn.Embedding(L, cfg.d_event)
        layer = nn.TransformerEncoderLayer(cfg.d_event, cfg.n_heads, 4 * cfg.d_event, dropout=0.0, batch_first=True)
        self.ea = nn.TransformerEncoder(layer, cfg.n_layers, enable_nested_tensor=False)
        self.ea_ptr = nn.Linear(cfg.d_event, 2)                 # 每个事件：作为 A、作为 B 的分数
        self.ea_none = nn.Parameter(torch.zeros(2))             # “没有合适事件”的分数
        # 比较：输入 [c_A, c_B, c_A − c_B, 前提是否适用]
        self.compare = nn.Sequential(nn.Linear(3 * k + 1, cfg.d_compare), nn.GELU(),
                                     nn.Linear(cfg.d_compare, cfg.d_compare), nn.GELU(),
                                     nn.Linear(cfg.d_compare, 1))

    def offsets(self) -> torch.Tensor:
        """[P, M, k]，第 0 个成员（参考）恒为 0。"""
        ref = torch.zeros(self.cfg.n_packages, 1, self.cfg.k, dtype=self.member_offset.dtype,
                          device=self.member_offset.device)
        return torch.cat([ref, self.member_offset], dim=1)

    def forward(self, batch: T1Batch) -> dict:
        # KA：本包参考系里的表示
        r = self.offsets()[batch.package, batch.member]                                     # [B, L, k]
        r = r + self.registered_read(batch.offset.unsqueeze(-1)) * batch.offset_known.unsqueeze(-1)
        # 尺子转换到共同空间
        c = torch.einsum("blk,blkj->blj", r, self.convert_w[batch.package]) + self.convert_b[batch.package]
        # EA：选出 A、B
        h = self.ea(self.ea_in(batch.rel_match) + self.ea_pos(batch.position))
        scores = self.ea_ptr(h).transpose(1, 2)                                             # [B, 2, L]
        scores = scores + self.cfg.identity_bias * batch.rel_match.transpose(1, 2)          # 结构约束：CPU 的身份判断
        none = self.ea_none.view(1, 2, 1).expand(scores.shape[0], 2, 1)
        select = torch.softmax(torch.cat([scores, none], dim=-1), dim=-1)                   # [B, 2, L+1]
        c_a = torch.einsum("bl,blk->bk", select[:, 0, :-1], c)
        c_b = torch.einsum("bl,blk->bk", select[:, 1, :-1], c)
        logit = self.compare(torch.cat([c_a, c_b, c_a - c_b, batch.premise.unsqueeze(-1)], dim=-1)).squeeze(-1)
        return {"logit": logit, "select": select, "none": select[:, :, -1]}

    def describe(self) -> dict:
        return {"config": asdict(self.cfg), "params": sum(p.numel() for p in self.parameters())}
