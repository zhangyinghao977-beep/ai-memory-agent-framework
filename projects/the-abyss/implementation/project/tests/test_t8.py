"""T8：长向量只看事件链，不偷看包的编号和答案；新经历不动旧向量。"""
from __future__ import annotations

import pytest
import torch

from empirical_core.t5.task import T5Spec, build_lattice, build_task, signature
from empirical_core.t6.model import train_one6
from empirical_core.t7.baseline import cosine_choice_two
from empirical_core.t8.experience import grown_lattice, new_package_questions, separation
from empirical_core.t8.grow import cooccurrence, dilute, grow_new, grow_vectors, ppmi, seen_objects

SPEC = T5Spec(n_train=4096, n_dev=256, n_test=128)


@pytest.fixture(scope="module")
def mutual():
    return build_task("mutual", SPEC)


def test_cooccurrence_counts_pairs_in_a_chain_once():
    c = cooccurrence(torch.tensor([[0, 1, 2], [0, 1, 3]]), 5)
    assert c[0, 1] == 2 and c[1, 0] == 2 and c[0, 2] == 1 and c[2, 3] == 0
    assert c[4].sum() == 0 and torch.diag(c).sum() == 0


def test_ppmi_is_not_negative_and_empty_is_zero():
    assert (ppmi(cooccurrence(torch.randint(0, 20, (50, 5)), 20)) >= 0).all()
    assert ppmi(torch.zeros(4, 4, dtype=torch.float64)).sum() == 0


def test_vectors_are_unit_and_unseen_objects_are_zero():
    v = grow_vectors(torch.randint(0, 20, (200, 5)), 24, 8)
    norms = v.norm(dim=-1)
    assert torch.allclose(norms[:20], torch.ones(20), atol=1e-4)
    assert norms[20:].sum() == 0


def test_quality_does_not_come_from_object_numbering(mutual):
    """对象编号里藏着包（编号除以成员数）。把编号打乱后再长，同包还是要靠近。"""
    g = torch.Generator().manual_seed(1)
    perm = torch.randperm(SPEC.n_objects, generator=g)
    vec = grow_vectors(perm[mutual["train"]["obj"]], SPEC.n_objects, SPEC.k)
    back = vec[perm]
    s = separation(back, SPEC, range(SPEC.n_train_packages))
    assert s["same_cos"] > 0.7 and s["same_cos"] > 2 * s["other_abs_cos"]


def test_grown_vectors_answer_old_packages(mutual):
    vec = grow_vectors(mutual["train"]["obj"], SPEC.n_objects, SPEC.k)
    assert cosine_choice_two("mutual", mutual["dev"], vec, SPEC) > 0.95


def test_new_experience_leaves_old_vectors_alone(mutual):
    old = grow_vectors(mutual["train"]["obj"], SPEC.n_objects, SPEC.k)
    seen = seen_objects(mutual["train"]["obj"], SPEC.n_objects)
    life = torch.tensor([q["obj"] for q in new_package_questions("mutual", SPEC, 512, "life", set())])
    out = grow_new(old, life, seen, SPEC.k)
    assert torch.equal(out[seen], old[seen])
    assert out[~seen].norm(dim=-1).min() > 0.5
    assert old[~seen].abs().sum() == 0


def test_dilute_keeps_object_counts_and_removes_the_signal(mutual):
    chains = mutual["train"]["obj"]
    assert torch.equal(dilute(chains, 0.0, 1), chains)
    full = dilute(chains, 1.0, 1)
    assert torch.equal(full.flatten().sort().values, chains.flatten().sort().values)
    s = separation(grow_vectors(full, SPEC.n_objects, SPEC.k), SPEC, range(SPEC.n_train_packages))
    assert s["same_cos"] < 0.5


def test_life_chains_use_only_new_packages_and_avoid_the_test(mutual):
    avoid = {signature(q) for q in mutual["raw"]["test_new"]}
    qs = new_package_questions("mutual", SPEC, 256, "life", avoid)
    assert all(p >= SPEC.n_train_packages for q in qs for p in q["pkg"])
    assert not avoid & {signature(q) for q in qs}


def test_grown_lattice_runs_with_training(mutual):
    vec = grown_lattice("mutual", mutual, SPEC, 1024, 0.5, 256)
    assert vec.shape == (SPEC.n_objects, SPEC.k)
    lat = {"vec": vec, "bit": build_lattice(SPEC)["bit"]}
    m, c = train_one6(SPEC, lat, mutual, "sim", "full", 1, steps=3, eval_every=3)
    assert len(c) == 1 and torch.equal(m.vec, vec)
