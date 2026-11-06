"""T2 的输入编码。模型只拿到可见信息；hidden 里的东西另放在 diag 里，只给分层诊断用，不进入模型。

每条链（共 C 条）：是不是陈述链、是不是设定链、设定说的是不是故事世界、说话人是否等于 x、是否等于 y（CPU 的身份判断）。
每个事件（每条陈述链 L 个）：包、成员、是否有效（设定链没有事件）、关系是否等于 r_A、是否等于 r_B。
每道题：体裁。链和事件的位置由下标给出。
另外，CPU 侧只凭可见信息能唯一确定 A、B 和世界的题（task.exact_resolve），记下 exact 及其结果，作为 KA 的材料。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import torch

from .task import WORLDS, exact_resolve

FIELDS = ("chain_say", "chain_set", "set_story", "spk_x", "spk_y", "genre", "ev_pkg", "ev_mem", "ev_valid",
          "rel_a", "rel_b", "labels", "exact", "ex_a", "ex_b", "ex_story")
DIAG = ("a_chain", "b_chain", "set_chain", "a_event", "b_event", "needs_ca", "needs_ea", "same_package")


@dataclass
class T2Batch:
    ids: list
    chain_say: torch.Tensor     # [B, C]
    chain_set: torch.Tensor     # [B, C]
    set_story: torch.Tensor     # [B, C]
    spk_x: torch.Tensor         # [B, C]
    spk_y: torch.Tensor         # [B, C]
    genre: torch.Tensor         # [B] long
    ev_pkg: torch.Tensor        # [B, C, L] long
    ev_mem: torch.Tensor        # [B, C, L] long
    ev_valid: torch.Tensor      # [B, C, L]
    rel_a: torch.Tensor         # [B, C, L]
    rel_b: torch.Tensor         # [B, C, L]
    labels: torch.Tensor        # [B]
    exact: torch.Tensor         # [B] bool
    ex_a: torch.Tensor          # [B, 2] long：（包, 成员）；exact 为假时是 0
    ex_b: torch.Tensor          # [B, 2] long
    ex_story: torch.Tensor      # [B]：唯一的设定是不是故事世界


def encode(data: dict, split: str, conditions=("base",), ids: Optional[list] = None) -> tuple[T2Batch, dict]:
    """返回 (输入, 诊断)。诊断里是 hidden 的选择真值，模型看不到。"""
    keep = set(ids) if ids is not None else None
    eps = [ep for ep in data["episodes"] if ep["split"] == split and ep["condition"] in conditions
           and (keep is None or ep["id"] in keep)]
    if not eps:
        raise ValueError(f"划分 {split}、条件 {conditions} 里没有题")
    spec = data["spec"]
    B, C, L = len(eps), spec["n_chains"], spec["chain_len"]
    t = {f: torch.zeros(B, C) for f in ("chain_say", "chain_set", "set_story", "spk_x", "spk_y")}
    ev_pkg = torch.zeros(B, C, L, dtype=torch.long)
    ev_mem = torch.zeros(B, C, L, dtype=torch.long)
    ev = {f: torch.zeros(B, C, L) for f in ("ev_valid", "rel_a", "rel_b")}
    genre = torch.zeros(B, dtype=torch.long)
    labels = torch.zeros(B)
    exact = torch.zeros(B, dtype=torch.bool)
    ex_a = torch.zeros(B, 2, dtype=torch.long)
    ex_b = torch.zeros(B, 2, dtype=torch.long)
    ex_story = torch.zeros(B)
    diag = {f: torch.zeros(B, dtype=torch.long) for f in DIAG}
    for i, ep in enumerate(eps):
        x, ra, y, rb = ep["query"]
        for c, chain in enumerate(ep["chains"]):
            if chain["kind"] == "setting":
                t["chain_set"][i, c] = 1.0
                t["set_story"][i, c] = float(chain["world"] == "story")
                continue
            t["chain_say"][i, c] = 1.0
            t["spk_x"][i, c] = float(chain["speaker"] == x)
            t["spk_y"][i, c] = float(chain["speaker"] == y)
            for j, (rel, p, m) in enumerate(chain["events"]):
                ev_pkg[i, c, j], ev_mem[i, c, j] = p, m
                ev["ev_valid"][i, c, j] = 1.0
                ev["rel_a"][i, c, j] = float(rel == ra)
                ev["rel_b"][i, c, j] = float(rel == rb)
        genre[i] = ep["genre"]
        labels[i] = float(ep["label"])
        res = exact_resolve(ep)
        if res is not None:
            exact[i] = True
            ex_a[i], ex_b[i] = torch.tensor(res[0]), torch.tensor(res[1])
            ex_story[i] = float(res[2] == "story")
        h = ep["hidden"]
        for f in DIAG:
            diag[f][i] = int(h[f])
    batch = T2Batch([ep["id"] for ep in eps], t["chain_say"], t["chain_set"], t["set_story"], t["spk_x"], t["spk_y"],
                    genre, ev_pkg, ev_mem, ev["ev_valid"], ev["rel_a"], ev["rel_b"], labels, exact, ex_a, ex_b,
                    ex_story)
    return batch, diag


def take(batch: T2Batch, idx: torch.Tensor) -> T2Batch:
    idx_dev = idx.to(batch.labels.device)
    return T2Batch([batch.ids[i] for i in idx.tolist()], *(getattr(batch, f)[idx_dev] for f in FIELDS))


def to_device(batch: Optional[T2Batch], device) -> Optional[T2Batch]:
    if batch is None or device is None:
        return batch
    return T2Batch(batch.ids, *(getattr(batch, f).to(device) for f in FIELDS))


def concat(*batches: T2Batch) -> T2Batch:
    return T2Batch(sum((b.ids for b in batches), []), *(torch.cat([getattr(b, f) for b in batches]) for f in FIELDS))


def world_index(name: str) -> int:
    return WORLDS.index(name)
