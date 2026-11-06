"""T2 的作答规则、计分和分层诊断。

- 作答规则同 T1，事先固定（名词解释 v0.28：断点先说“我不知道”）：
  - 强制二选一：logit > 0 选“A 赢”；
  - “不知道”：|p − 0.5| < UNKNOWN_MARGIN，或者 A、B 任一边“没有合适的链或事件”的概率 > NONE_LIMIT。
- 分层诊断（只用于报告，隐藏真值不进入模型）：
  - CA 选链：A 所在的链、B 所在的链、当前有效的设定，argmax 是否选对；
  - EA 选事件：在真正的那条链上，argmax 是否选中真正的那个事件；
  - KA＋比较：CA、EA 都选对的题里，答案对不对。
"""
from __future__ import annotations

from typing import Optional

import torch

UNKNOWN_MARGIN = 0.1
NONE_LIMIT = 0.5


def decide(pred: dict) -> dict:
    p = torch.sigmoid(pred["logit"])
    unknown = (p - 0.5).abs() < UNKNOWN_MARGIN
    if pred.get("none") is not None:
        unknown = unknown | (pred["none"].max(dim=1).values > NONE_LIMIT)
    return {"forced": (pred["logit"] > 0).long(), "unknown": unknown}


def score(pred: dict, labels: torch.Tensor, ids: list, strata: Optional[dict] = None) -> dict:
    d = decide(pred)
    correct = (d["forced"] == labels.long()).tolist()
    answered = (~d["unknown"]).tolist()

    def tally(idx):
        return {"n": len(idx), "forced_correct": sum(correct[i] for i in idx),
                "answered": sum(answered[i] for i in idx),
                "answered_correct": sum(correct[i] and answered[i] for i in idx)}
    out = {"overall": tally(list(range(len(ids))))}
    if strata:
        groups: dict = {}
        for i, qid in enumerate(ids):
            for dim, value in strata[qid].items():
                groups.setdefault(dim, {}).setdefault(value, []).append(i)
        out["strata"] = {dim: {v: tally(idx) for v, idx in sorted(vals.items())} for dim, vals in groups.items()}
    return out


def layer_diagnostics(pred: dict, labels: torch.Tensor, diag: dict) -> dict:
    """各层选得对不对。每项给 {n, correct}；“需要 CA”“需要 EA”的题另算一份。"""
    ca = pred["ca_arg"]
    ea = pred["ea_arg"]
    ok = {"ca_a": ca[:, 0] == diag["a_chain"], "ca_b": ca[:, 1] == diag["b_chain"], "ca_set": ca[:, 2] == diag["set_chain"],
          "ea_a": ea[:, 0] == diag["a_event"], "ea_b": ea[:, 1] == diag["b_event"]}
    ca_all = ok["ca_a"] & ok["ca_b"] & ok["ca_set"]
    ea_all = ok["ea_a"] & ok["ea_b"]
    answer = (pred["logit"] > 0).long() == labels.long()
    needs_ca, needs_ea = diag["needs_ca"].bool(), diag["needs_ea"].bool()

    def c(mask, sel=None):
        sel = torch.ones_like(mask) if sel is None else sel
        return {"n": int(sel.sum()), "correct": int((mask & sel).sum())}
    return {"ca_all": c(ca_all), "ca_all_needs_ca": c(ca_all, needs_ca),
            "ea_all": c(ea_all), "ea_all_needs_ea": c(ea_all, needs_ea),
            "answer_given_selection_right": c(answer, ca_all & ea_all),
            **{k: c(v) for k, v in ok.items()}}
