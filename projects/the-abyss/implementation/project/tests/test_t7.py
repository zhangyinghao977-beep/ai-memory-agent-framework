"""T7：向量变模糊时，题和比特不变；余弦基线不偷看。"""
from __future__ import annotations

from dataclasses import replace

import pytest
import torch

from empirical_core.t5.task import T5Spec, build_lattice, build_task
from empirical_core.t6.model import train_one6
from empirical_core.t7.baseline import cosine_choice_two, cosine_scores

SPEC = T5Spec(n_train=256, n_dev=512, n_test=512)
TASKS = ("anchor", "mutual")


@pytest.fixture(scope="module")
def tasks():
    return {t: build_task(t, SPEC) for t in TASKS}


def test_noise_changes_only_the_vectors(tasks):
    noisy = replace(SPEC, member_offset=2.0)
    a, b = build_lattice(SPEC), build_lattice(noisy)
    assert torch.equal(a["bit"], b["bit"])
    assert not torch.equal(a["vec"], b["vec"])
    for t in TASKS:
        other = build_task(t, noisy)
        for k in ("rel", "obj", "query", "target", "n_cand"):
            assert torch.equal(tasks[t]["train"][k], other["train"][k])
            assert torch.equal(tasks[t]["test_new"][k], other["test_new"][k])


def test_reference_member_keeps_its_vector():
    a = build_lattice(SPEC)["vec"].view(-1, SPEC.n_members, SPEC.k)
    b = build_lattice(replace(SPEC, member_offset=2.0))["vec"].view(-1, SPEC.n_members, SPEC.k)
    assert torch.equal(a[:, 0], b[:, 0])
    assert not torch.equal(a[:, 1], b[:, 1])


@pytest.mark.parametrize("task", TASKS)
def test_cosine_is_near_perfect_when_clean_and_falls_with_noise(task, tasks):
    accs = []
    for sigma in (0.2, 1.25, 3.0):
        spec = replace(SPEC, member_offset=sigma)
        accs.append(cosine_choice_two(task, tasks[task]["dev"], build_lattice(spec)["vec"], spec))
    assert accs[0] > 0.98
    assert accs[0] > accs[1] > accs[2] > 0.5


@pytest.mark.parametrize("task", TASKS)
def test_cosine_does_not_read_packages_or_answers(task, tasks):
    d = dict(tasks[task]["dev"])
    vec = build_lattice(SPEC)["vec"]
    before = cosine_scores(task, d, vec, SPEC)
    d["pkg"] = torch.zeros_like(d["pkg"])
    d["target"] = torch.zeros_like(d["target"])
    assert torch.equal(before, cosine_scores(task, d, vec, SPEC))


@pytest.mark.parametrize("task", TASKS)
def test_cosine_only_picks_legal_candidates(task, tasks):
    d = tasks[task]["dev"]
    pick = cosine_scores(task, d, build_lattice(SPEC)["vec"], SPEC).argmax(-1)
    assert (d["rel"].gather(1, pick.unsqueeze(1)).squeeze(1) == d["query"]).all()


def test_noisy_training_runs_and_keeps_vectors_fixed(tasks):
    spec = replace(SPEC, member_offset=1.25)
    lat = build_lattice(spec)
    before = lat["vec"].clone()
    m, c = train_one6(spec, lat, tasks["mutual"], "sim", "full", 1, steps=3, eval_every=3)
    assert len(c) == 1 and torch.equal(m.vec, before)
