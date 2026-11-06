"""T8 的经验：训练题的事件链，加上新包的无答案事件链（2026-11-06）。

答案和包的编号都不进入长向量的过程：长向量只收对象编号。
新包的事件链用同一个出题器生成，但目标被丢掉，不和 test_new 重复。
"""
from __future__ import annotations

import random

import torch

from ..t5.task import T5Spec, _pack, make_question, signature
from .grow import dilute, grow_new, grow_vectors, seen_objects


def new_package_questions(task: str, spec: T5Spec, n: int, tag: str, avoid: set) -> list:
    rng = random.Random(f"{spec.seed}-{task}-{tag}")
    pkgs = list(range(spec.n_train_packages, spec.n_train_packages + spec.n_new_packages))
    out = []
    while len(out) < n:
        q = make_question(task, pkgs, spec, rng, rng.random() < spec.single_fraction)
        if signature(q) not in avoid:
            out.append(q)
    return out


def grown_lattice(task: str, data: dict, spec: T5Spec, n_chains: int, fraction: float, n_life: int, dilute_seed: int = 7) -> torch.Tensor:
    """按一种经验条件长出全部对象的向量。"""
    avoid = {signature(q) for q in data["raw"]["test_new"]}
    life = _pack(new_package_questions(task, spec, n_life, "life", avoid))["obj"]
    chains = data["train"]["obj"][:n_chains]
    if fraction > 0:
        chains, life = dilute(chains, fraction, dilute_seed), dilute(life, fraction, dilute_seed + 1)
    vec = grow_vectors(chains, spec.n_objects, spec.k)
    return grow_new(vec, life, seen_objects(chains, spec.n_objects), spec.k)


def separation(vec: torch.Tensor, spec: T5Spec, pkgs: range) -> dict:
    v = vec.view(-1, spec.n_members, vec.shape[-1])[list(pkgs)]
    same = torch.stack([(v[:, a] * v[:, b]).sum(-1) for a in range(spec.n_members) for b in range(a + 1, spec.n_members)]).mean()
    other = (v[:-1, 0] * v[1:, 0]).sum(-1).abs().mean()
    return {"same_cos": float(same), "other_abs_cos": float(other)}
