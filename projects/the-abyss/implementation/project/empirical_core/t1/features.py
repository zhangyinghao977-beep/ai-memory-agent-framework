"""T1 的输入编码：所有模型（被测模型 A 与对照 B、C、D′）拿到完全相同的信息（测试方案 v0.1 第二节）。

每个事件：
- 关系是否等于查询的 r_A、r_B（CPU 的身份判断，两个 0／1）；
- 包编号、成员位置、事件在历史里的位置；
- T1-a：这个成员已登记的存异结果（相对本包参考的偏差）及“是否已知”；T1-b：偏差一律未知（0，且“已知”为 0）。
每道题：世界；“小的赢”这条前提此刻是否适用（由记忆边界阀判断，T1 里等于“是否在故事世界”）。
隐藏数值、A／B 是谁、答案以外的生成信息都不进入输入。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import torch

from .task import WORLDS


@dataclass
class T1Batch:
    ids: list
    rel_match: torch.Tensor     # [B, L, 2]
    package: torch.Tensor       # [B, L] long
    member: torch.Tensor        # [B, L] long
    position: torch.Tensor      # [B, L] long
    offset: torch.Tensor        # [B, L]
    offset_known: torch.Tensor  # [B, L]
    world: torch.Tensor         # [B] long：0 物理，1 故事
    premise: torch.Tensor       # [B]：前提“小的赢”是否适用
    labels: torch.Tensor        # [B] float


def registered_offsets(data: dict) -> dict:
    """T1-a 的已登记知识：每个成员相对本包参考（首成员）的偏差。不含包的参考水平。"""
    values = {tuple(map(int, k.split(","))): v for k, v in data["hidden_values"].items()}
    return {(p, m): round(v - values[(p, 0)], 6) for (p, m), v in values.items()}


def encode(data: dict, split: str, offsets: Optional[dict] = None, ids: Optional[list] = None) -> T1Batch:
    eps = [ep for ep in data["episodes"] if ep["split"] == split and (ids is None or ep["id"] in set(ids))]
    if not eps:
        raise ValueError(f"划分 {split} 里没有题")
    L = data["spec"]["history_len"]
    B = len(eps)
    rel_match = torch.zeros(B, L, 2)
    package = torch.zeros(B, L, dtype=torch.long)
    member = torch.zeros(B, L, dtype=torch.long)
    offset = torch.zeros(B, L)
    known = torch.zeros(B, L)
    world = torch.zeros(B, dtype=torch.long)
    labels = torch.zeros(B)
    for b, ep in enumerate(eps):
        ra, rb = ep["query"]
        for j, (rel, p, m) in enumerate(ep["history"]):
            rel_match[b, j, 0] = float(rel == ra)
            rel_match[b, j, 1] = float(rel == rb)
            package[b, j], member[b, j] = p, m
            if offsets is not None:
                offset[b, j], known[b, j] = offsets[(p, m)], 1.0
        world[b] = WORLDS.index(ep["world"])
        labels[b] = float(ep["label"])
    position = torch.arange(L).expand(B, L).clone()
    premise = (world == WORLDS.index("story")).float()
    return T1Batch([ep["id"] for ep in eps], rel_match, package, member, position, offset, known, world, premise, labels)


def flat_features(batch: T1Batch, n_packages: int, n_members: int) -> torch.Tensor:
    """给 MLP（对照 B）：把所有事件特征和世界、前提拼成一行。"""
    B, L = batch.package.shape
    per_event = torch.cat([
        batch.rel_match,
        torch.nn.functional.one_hot(batch.package, n_packages).float(),
        torch.nn.functional.one_hot(batch.member, n_members).float(),
        batch.offset.unsqueeze(-1),
        batch.offset_known.unsqueeze(-1),
    ], dim=-1)
    world = torch.nn.functional.one_hot(batch.world, len(WORLDS)).float()
    return torch.cat([per_event.reshape(B, -1), world, batch.premise.unsqueeze(-1)], dim=-1)


def token_features(batch: T1Batch, n_packages: int, n_members: int) -> torch.Tensor:
    """给小 Transformer（对照 C）：每个事件一个 token，再加一个“世界＋前提” token。形状 [B, L+1, F]。"""
    B, L = batch.package.shape
    pos = torch.nn.functional.one_hot(batch.position, L).float()
    ev = torch.cat([
        batch.rel_match,
        torch.nn.functional.one_hot(batch.package, n_packages).float(),
        torch.nn.functional.one_hot(batch.member, n_members).float(),
        batch.offset.unsqueeze(-1), batch.offset_known.unsqueeze(-1), pos,
        torch.zeros(B, L, len(WORLDS) + 1),
    ], dim=-1)
    world_tok = torch.zeros(B, 1, ev.shape[-1])
    world_tok[:, 0, -(len(WORLDS) + 1):-1] = torch.nn.functional.one_hot(batch.world, len(WORLDS)).float()
    world_tok[:, 0, -1] = batch.premise
    return torch.cat([ev, world_tok], dim=1)
