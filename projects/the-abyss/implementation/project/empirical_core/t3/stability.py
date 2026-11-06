"""T3 的统一校验：看 EA/KA 相互修正是否稳定（图谱网站 2026-11-03 增补）。

网站登记：停止方向是“看 EA/KA 相互修正是否稳定，并进入容许范围”；具体量化、阈值和连续窗口尚未定；
本实验不以“可验证收益”或“修正完成”作为判据；固定次数只是硬上限，截断不是收敛。
每隔若干轮按包训练后做一次统一校验，比较不同校验频率的成本。

所以这里只做“候选观察”，不定阈值：
- 校验的对象（待进一步验证的工作解释）：
  - slot：EA↔KA 的结果。在一份固定的 TRAIN 探针上，EA 在每条候选链（有对得上查询关系的事件）上选出的表示；
  - ka：全部 KA 产品（材料）；
  - ea：EA 在每条候选链上选中的事件（筛子）；
  - answer：整个模型的二选一答案（含 CA，只作参照）。
- 变化量：这一次校验和上一次校验相比。slot、ka 用相对变化 ‖新 − 旧‖ / ‖旧‖；ea、answer 用改变了的比例。
- 来回摆动：slot 相邻两次变化方向的余弦（负数＝往回摆）；ea 选择“改了又改回去”的比例。
校验不看答案、不看隐藏真值、不写任何单元。
停在哪一轮由事后模拟给出（simulate_stop）：训练总是跑到硬上限，校验是只读的，所以按哪种节奏校验都不改变训练过程本身。
"""
from __future__ import annotations

import time
from typing import Optional

import torch

from ..t2.features import T2Batch, take, to_device

LAGS = (1, 2, 3, 4, 5)
MEASURES = ("slot", "ka", "ea", "answer")


@torch.no_grad()
def snapshot(sp, probe: T2Batch, chunk: int = 2048) -> dict:
    """一次统一校验要用的状态，全部放回 CPU。"""
    versions = sp.store.snapshot()
    ea, ca = sp._frozen("ea").to(sp.device), sp._frozen("ca").to(sp.device)
    ct = sp.ctable().to(sp.device)
    slot, arg, ans = [], [], []
    n = len(probe.ids)
    for s in range(0, n, chunk):
        b = to_device(take(probe, torch.arange(s, min(s + chunk, n))), sp.device)
        rep_a, _, sel_a = sp.ea_reps(ea, b, ct, "a")
        rep_b, _, sel_b = sp.ea_reps(ea, b, ct, "b")
        slot.append(torch.stack([rep_a, rep_b], 2).float().cpu())                  # [n, C, 2, k]
        arg.append(torch.stack([sel_a.argmax(-1), sel_b.argmax(-1)], -1).cpu())   # [n, C, 2]
        logit, _ = sp.combine(ca, ca.select(b), b, rep_a, rep_b)
        ans.append((logit > 0).cpu())
        sp.guard()
    if sp.store.snapshot() != versions:
        raise RuntimeError("统一校验改动了单元版本：校验必须只读")
    cand = torch.stack([probe.rel_a.sum(-1) > 0, probe.rel_b.sum(-1) > 0], -1).cpu()   # [N, C, 2] 候选链
    return {"ka": sp.ctable().clone().float(), "slot": torch.cat(slot), "ea_arg": torch.cat(arg),
            "answer": torch.cat(ans), "cand": cand}


def _rel(new: torch.Tensor, old: torch.Tensor) -> float:
    return float((new - old).norm() / old.norm().clamp_min(1e-12))


def measures(new: dict, old: dict) -> dict:
    """新、旧两次校验之间的变化量（不定阈值，只记数）。"""
    m = new["cand"]
    return {"slot": _rel(new["slot"][m], old["slot"][m]),
            "ka": _rel(new["ka"], old["ka"]),
            "ea": float((new["ea_arg"] != old["ea_arg"])[m].float().mean()),
            "answer": float((new["answer"] != old["answer"]).float().mean())}


def oscillation(s2: dict, s1: dict, s0: dict) -> dict:
    """三次相邻校验（s0 → s1 → s2）：slot 两次变化方向的余弦；ea 选择改了又改回去的比例。"""
    m = s2["cand"]
    d1 = (s1["slot"][m] - s0["slot"][m]).flatten()
    d2 = (s2["slot"][m] - s1["slot"][m]).flatten()
    cos = float(d1 @ d2 / (d1.norm() * d2.norm()).clamp_min(1e-12))
    back = (s2["ea_arg"] == s0["ea_arg"]) & (s1["ea_arg"] != s0["ea_arg"])
    return {"slot_cos": cos, "ea_back": float(back[m].float().mean())}


class Checker:
    """每轮训练结束做一次校验并计时；保留最近几次的状态，算出和 1–5 轮以前相比的变化量。
    这样一次训练就能事后模拟“每 1、3、4、5 轮校验一次”。"""

    def __init__(self, sp, probe: T2Batch, chunk: int = 2048):
        self.sp, self.probe, self.chunk = sp, probe, chunk
        self.history: dict[int, dict] = {}
        self.records: list[dict] = []

    def _clock(self) -> tuple:
        return time.perf_counter(), getattr(self.sp.guard, "slept", 0.0)

    def __call__(self, r: int) -> dict:
        """第 r 轮（0＝训练前）的校验。计算秒数不含限流歇的时间；一次真正的校验只需要和上一次比一次，
        所以“一次校验的成本”＝取状态的时间＋算一次变化量的时间。"""
        t0, s0 = self._clock()
        snap = snapshot(self.sp, self.probe, self.chunk)
        t1, s1 = self._clock()
        rec = {"round": r, "lag": {}, "snapshot_seconds": (t1 - t0) - (s1 - s0)}
        for k in LAGS:
            if r - k in self.history:
                a, sa = self._clock()
                rec["lag"][k] = measures(snap, self.history[r - k])
                b, sb = self._clock()
                rec.setdefault("measure_seconds", (b - a) - (sb - sa))
        if r - 1 in self.history and r - 2 in self.history:
            rec["oscillation"] = oscillation(snap, self.history[r - 1], self.history[r - 2])
        self.history[r] = snap
        for old in [x for x in self.history if x < r - max(LAGS)]:
            del self.history[old]
        self.records.append(rec)
        return rec


def simulate_stop(records: list[dict], measure: str, cadence: int, tol: float, window: int, cap: int) -> Optional[int]:
    """每 cadence 轮校验一次（第 cadence、2·cadence…轮），和上一次校验相比；
    变化量连续 window 次低于 tol，就在这一轮停。到硬上限也没停，返回 None（截断，不是收敛）。"""
    by_round = {rec["round"]: rec for rec in records}
    run = 0
    for r in range(cadence, cap + 1, cadence):
        lag = by_round.get(r, {}).get("lag", {}).get(cadence)
        if lag is None:
            return None
        run = run + 1 if lag[measure] < tol else 0
        if run >= window:
            return r
    return None


@torch.no_grad()
def ka_differences(sp, hidden_values: dict, indirect: list) -> dict:
    """包内差异有没有保住（隐藏真值，只用于报告）：
    - order：用 CA 的比较头（物理世界）比较同一个包里每两个成员，谁大判断对的比例；
    - spread：同一个包里成员产品两两之间的平均距离（差异被抹平时会变小）。
    间接包和其他包分开算。"""
    ct = sp.ctable()
    compare = sp._frozen("ca").compare
    P, M = ct.shape[0], ct.shape[1]
    i, j = torch.triu_indices(M, M, offset=1)
    out = {}
    groups = {"indirect": sorted(indirect), "direct": [p for p in range(P) if p not in set(indirect)]}
    for name, pkgs in groups.items():
        right = total = 0
        spread = []
        for p in pkgs:
            ca_, cb_ = ct[p, i], ct[p, j]
            logit = compare(torch.cat([ca_, cb_, ca_ - cb_, torch.zeros(len(i), 1)], -1)).squeeze(-1)
            truth = torch.tensor([hidden_values[f"{p},{a}"] > hidden_values[f"{p},{b}"] for a, b in zip(i.tolist(), j.tolist())])
            right += int(((logit > 0) == truth).sum())
            total += len(i)
            spread.append(float((ca_ - cb_).norm(dim=-1).mean()))
        out[name] = {"order_correct": right, "order_n": total, "spread": sum(spread) / len(spread)}
    return out
