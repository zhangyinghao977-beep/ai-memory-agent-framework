"""T9 的后来的经历：同一批包的新事件链，用来长新世界的规则，不和测试题重复（2026-11-06）。"""
from __future__ import annotations

import random

from ..t5.task import T5Spec, make_question, signature


def later_questions(task: str, spec: T5Spec, n: int, avoid: set) -> list:
    rng = random.Random(f"{spec.seed}-{task}-later")
    pkgs = list(range(spec.n_train_packages))
    out = []
    while len(out) < n:
        q = make_question(task, pkgs, spec, rng, rng.random() < spec.single_fraction)
        if signature(q) not in avoid:
            out.append(q)
    return out
