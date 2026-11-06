"""T1 的整体训练、预测与计分（冻结计划见 experiments/t1_run_20261101/PLAN.json）。

- 整体训练（A-joint 与对照 B、C、D′）：同一批 TRAIN 题、同样的批大小与 epoch 数；Adam，学习率按模型族事先固定；
  不早停、不按 DEV 成绩挑检查点、不调参。DEV 只在一个固定子集上画学习曲线。
- 作答规则（事先固定，名词解释 v0.28：断点先说“我不知道”）：
  - 强制二选一：logit > 0 选“A 赢”，照常计分，所有模型可比；
  - 另给“不知道”：|p − 0.5| < UNKNOWN_MARGIN；模型 A 另外在 EA 对 A 或 B 的“没有合适事件”概率 > NONE_LIMIT 时也说“不知道”。
  “不知道”不算对也不算错，单独报告作答率和作答题的正确率。
"""
from __future__ import annotations

import math
from typing import Callable, Optional

import torch
import torch.nn as nn

from ..timing import SegmentTimer
from .features import T1Batch

FIELDS = ("rel_match", "package", "member", "position", "offset", "offset_known", "world", "premise", "labels")
UNKNOWN_MARGIN = 0.1
NONE_LIMIT = 0.5


def take(batch: T1Batch, idx: torch.Tensor) -> T1Batch:
    idx_dev = idx.to(batch.labels.device)
    return T1Batch([batch.ids[i] for i in idx.tolist()], *(getattr(batch, f)[idx_dev] for f in FIELDS))


def to_device(batch: Optional[T1Batch], device) -> Optional[T1Batch]:
    if batch is None or device is None:
        return batch
    return T1Batch(batch.ids, *(getattr(batch, f).to(device) for f in FIELDS))


def logits_of(out) -> torch.Tensor:
    return out["logit"] if isinstance(out, dict) else out


@torch.no_grad()
def predict(model: nn.Module, batch: T1Batch, chunk: int = 256,
            after_chunk: Optional[Callable[[], None]] = None) -> dict:
    """逐块前向：每道题的 logit；模型 A 另给 EA 的“没有合适事件”概率 [n, 2]。结果都放回 CPU。
    模型在哪个设备上，输入就送到哪个设备；after_chunk 每块之后调用一次（用来限流）。"""
    was_training = model.training
    model.eval()
    device = next(model.parameters()).device
    logits, none = [], []
    n = len(batch.ids)
    for s in range(0, n, chunk):
        out = model(to_device(take(batch, torch.arange(s, min(s + chunk, n))), device))
        logits.append(logits_of(out).float().cpu())
        if isinstance(out, dict) and "none" in out:
            none.append(out["none"].float().cpu())
        if after_chunk:
            after_chunk()
    model.train(was_training)
    return {"logit": torch.cat(logits), "none": torch.cat(none) if none else None}


def decide(pred: dict) -> dict:
    logit = pred["logit"]
    p = torch.sigmoid(logit)
    unknown = (p - 0.5).abs() < UNKNOWN_MARGIN
    if pred.get("none") is not None:
        unknown = unknown | (pred["none"].max(dim=1).values > NONE_LIMIT)
    return {"forced": (logit > 0).long(), "unknown": unknown}


def score(pred: dict, batch: T1Batch, strata: Optional[dict] = None) -> dict:
    """总体与分层计数：n、强制二选一答对数、作答数、作答答对数。strata：{题号: {维度: 类别}}（baselines.strata）。"""
    d = decide(pred)
    labels = batch.labels.long()
    correct = (d["forced"] == labels).tolist()
    answered = (~d["unknown"]).tolist()

    def tally(idx):
        return {"n": len(idx), "forced_correct": sum(correct[i] for i in idx),
                "answered": sum(answered[i] for i in idx),
                "answered_correct": sum(correct[i] and answered[i] for i in idx)}

    out = {"overall": tally(list(range(len(batch.ids))))}
    if strata:
        groups: dict = {}
        for i, qid in enumerate(batch.ids):
            for dim, value in strata[qid].items():
                groups.setdefault(dim, {}).setdefault(value, []).append(i)
        out["strata"] = {dim: {v: tally(idx) for v, idx in sorted(vals.items())} for dim, vals in groups.items()}
    return out


def curve_accuracy(model: nn.Module, batch: Optional[T1Batch],
                   after_chunk: Optional[Callable[[], None]] = None) -> Optional[float]:
    if batch is None:
        return None
    pred = predict(model, batch, after_chunk=after_chunk)
    return float(((pred["logit"] > 0).long() == batch.labels.long().cpu()).float().mean())


def train_joint(model: nn.Module, train: T1Batch, *, epochs: int, batch_size: int, lr: float, seed: int,
                curve_batch: Optional[T1Batch] = None, curve_points: int = 10, clip: float = 1.0,
                guard: Optional[Callable[[], None]] = None, timer: Optional[SegmentTimer] = None,
                device=None) -> dict:
    """整体训练：一个总损失，对全部参数反向传播。返回训练记录（不含参数）。
    device 给定时（例如 "cuda"），模型和训练题都搬到该设备上；guard 每步调用一次（时间、内存与显卡限流）。"""
    timer = timer or SegmentTimer()
    if device is not None:
        model.to(device)
        train = to_device(train, device)
    gen = torch.Generator().manual_seed(seed)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    n = len(train.ids)
    total = epochs * math.ceil(n / batch_size)
    eval_at = {round(total * i / curve_points) for i in range(1, curve_points + 1)}
    losses, curve, step = [], [], 0
    model.train()
    for _ in range(epochs):
        perm = torch.randperm(n, generator=gen)
        for s in range(0, n, batch_size):
            with timer.segment("batch_prep"):
                b = take(train, perm[s:s + batch_size])
            with timer.segment("neural"):
                loss = nn.functional.binary_cross_entropy_with_logits(logits_of(model(b)), b.labels)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), clip)
                opt.step()
            losses.append(float(loss.detach()))
            step += 1
            if step in eval_at:
                curve.append({"step": step, "dev_subset_accuracy": curve_accuracy(model, curve_batch, guard)})
            if guard:
                guard()
    if not all(math.isfinite(x) for x in losses):
        raise FloatingPointError("训练损失出现非有限值")
    return {"updates": step, "examples_seen": epochs * n, "loss_first": _mean(losses[:20]),
            "loss_last": _mean(losses[-20:]), "loss_trace": losses[:: max(1, len(losses) // 200)], "curve": curve,
            "timing": timer.summary(warmup=min(5, len(losses) - 1) if len(losses) > 1 else 0)}


def _mean(xs):
    return sum(xs) / len(xs) if xs else None
