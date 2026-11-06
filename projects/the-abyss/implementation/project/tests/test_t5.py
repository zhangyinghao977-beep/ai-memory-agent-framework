"""T5：题和选择器的检查。"""
from __future__ import annotations

import random
from dataclasses import replace

import pytest
import torch

from empirical_core.t5.model import BLOCK_KINDS, KINDS, Selector, evaluate, n_params, take, train_one
from empirical_core.t5.task import TASKS, T5Spec, baselines, build_lattice, build_task, make_question, rule_ref, signature

SPEC = T5Spec(n_train=256, n_dev=64, n_test=128)


@pytest.fixture(scope="module")
def lat():
    return build_lattice(SPEC)


@pytest.fixture(scope="module")
def tasks():
    return {t: build_task(t, SPEC) for t in TASKS}


@pytest.mark.parametrize("task", TASKS)
def test_rule_matches_target_and_candidates_legal(task, tasks):
    for split in ("train", "test_iid", "test_new"):
        for q in tasks[task]["raw"][split]:
            assert q["rel"][q["target"]] == q["query"]
            assert q["n_cand"] == sum(r == q["query"] for r in q["rel"])
            assert q["n_cand"] in (1, 2)
            assert rule_ref(task, q, SPEC) == q["target"]
            assert len(set(q["obj"])) == SPEC.chain_len


@pytest.mark.parametrize("task", TASKS)
def test_splits_do_not_share_questions_or_new_packages(task, tasks):
    raw = tasks[task]["raw"]
    seen = {signature(q) for q in raw["train"]}
    assert not seen & {signature(q) for q in raw["test_iid"]}
    train_pk = {p for q in raw["train"] for p in q["pkg"]}
    new_pk = {p for q in raw["test_new"] for p in q["pkg"]}
    assert not train_pk & new_pk


def test_mutual_wrong_candidate_has_no_support_and_decoys_exist(tasks):
    for q in tasks["mutual"]["raw"]["train"]:
        if q["n_cand"] != 2:
            continue
        cands = [i for i, r in enumerate(q["rel"]) if r == q["query"]]
        wrong = next(i for i in cands if i != q["target"])
        assert q["pkg"].count(q["pkg"][wrong]) == 1
        assert q["pkg"].count(q["pkg"][q["target"]]) == 2
        repeats = {p for p in q["pkg"] if q["pkg"].count(p) == 2}
        assert len(repeats) == 2


def test_anchor_wrong_candidate_has_a_decoy(tasks):
    for q in tasks["anchor"]["raw"]["train"]:
        if q["n_cand"] != 2:
            continue
        cands = [i for i, r in enumerate(q["rel"]) if r == q["query"]]
        wrong = next(i for i in cands if i != q["target"])
        assert q["pkg"].count(q["pkg"][wrong]) == 2
        assert q["pkg"][q["rel"].index(SPEC.anchor_rel)] == q["pkg"][q["target"]]


def test_position_gives_no_content_signal(tasks):
    for q in tasks["position"]["raw"]["train"]:
        if q["n_cand"] != 2:
            continue
        for i, r in enumerate(q["rel"]):
            if r == q["query"]:
                assert q["pkg"].count(q["pkg"][i]) == 2


def test_questions_are_deterministic():
    a, b = build_task("mutual", SPEC), build_task("mutual", SPEC)
    assert torch.equal(a["train"]["obj"], b["train"]["obj"])
    assert torch.equal(a["test_new"]["target"], b["test_new"]["target"])


def test_same_package_vectors_are_close(lat):
    v = torch.nn.functional.normalize(lat["vec"], dim=-1)
    M = SPEC.n_members
    same = (v[0] * v[1]).sum()
    assert same > 0.8
    assert torch.equal(lat["vec"][0], lat["vec"][0])
    assert (v[0] * v[M]).sum().abs() < same


def test_block_kinds_have_the_same_parameter_count(lat):
    counts = {n_params(Selector(SPEC, lat["vec"], k, True)) for k in BLOCK_KINDS}
    assert len(counts) == 1


def test_token_kind_does_not_pass_information_between_tokens(lat, tasks):
    m = Selector(SPEC, lat["vec"], "token", False).eval()
    b = take(tasks["mutual"]["train"], torch.arange(8))
    x = m.features(b)
    h1 = m.inp(x) + m.pos.weight
    x2 = x.clone()
    x2[:, 0] += 1.0
    h2 = m.inp(x2) + m.pos.weight
    for blk in m.blocks:
        h1, h2 = blk(h1), blk(h2)
    assert torch.equal(h1[:, 1:], h2[:, 1:])


@pytest.mark.parametrize("kind", KINDS)
def test_hard_lattice_only_chooses_legal_positions(kind, lat, tasks):
    d = tasks["mutual"]["test_iid"]
    m = Selector(SPEC, lat["vec"], kind, True).eval()
    with torch.no_grad():
        sel = m(take(d, torch.arange(len(d["target"]))))
    illegal = d["rel"] != d["query"].unsqueeze(1)
    assert sel[illegal].max() < 1e-6
    one = d["n_cand"] == 1
    assert (sel[one].argmax(-1) == d["target"][one]).all()


@pytest.mark.parametrize("kind", ("attn", "flat"))
@pytest.mark.parametrize("lattice", (True, False))
def test_training_runs_and_is_reproducible(kind, lattice, lat, tasks):
    a, ca = train_one(SPEC, lat, tasks["position"], kind, lattice, 3, steps=5, eval_every=5)
    b, cb = train_one(SPEC, lat, tasks["position"], kind, lattice, 3, steps=5, eval_every=5)
    assert ca == cb
    for p, q in zip(a.parameters(), b.parameters()):
        assert torch.equal(p, q)


def test_lattice_vectors_are_not_trained(lat, tasks):
    before = lat["vec"].clone()
    m, _ = train_one(SPEC, lat, tasks["position"], "attn", True, 1, steps=3, eval_every=3)
    assert torch.equal(m.vec, before)


def test_position_is_learned_without_any_attention_on_a_small_budget(lat):
    spec = replace(SPEC, n_train=2048)
    t = build_task("position", spec)
    m, _ = train_one(spec, lat, t, "token", True, 0, steps=400, eval_every=400)
    assert evaluate(m, t["test_iid"], lat["bit"])["choice_two"] > 0.9


def test_baselines_rule_is_exact_and_shortcuts_are_near_chance(tasks):
    for task in ("anchor", "mutual"):
        b = baselines(task, tasks[task], SPEC)["test_iid"]
        assert b["rule_ref"] == 1.0
        assert 0.3 < b["pick_last"] < 0.7


def test_single_question_has_one_candidate():
    rng = random.Random(0)
    for task in TASKS:
        q = make_question(task, list(range(48)), SPEC, rng, True)
        assert q["n_cand"] == 1
