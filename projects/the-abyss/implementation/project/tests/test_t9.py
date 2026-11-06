"""T9：长规则只看关系和查询，不靠编号相等；模型不知道谁是锚；换表不用重新训练。"""
from __future__ import annotations

from pathlib import Path

import pytest
import torch

from empirical_core.t5.task import T5Spec, build_lattice, build_task
from empirical_core.t9 import model as model9
from empirical_core.t9 import rule as rule9
from empirical_core.t9.model import Selector9, train_one9
from empirical_core.t9.rule import cosine_choice_two9, legal_table, relation_lift, shift_map, shuffle_relations, window_table

SPEC = T5Spec(n_train=2048, n_dev=256, n_test=128)
R = SPEC.n_relations


def truth() -> torch.Tensor:
    t = torch.zeros(R, R, dtype=torch.bool)
    t[torch.arange(R - 1), torch.arange(R - 1)] = True
    return t


@pytest.fixture(scope="module", params=["anchor", "mutual"])
def task(request):
    return request.param, build_task(request.param, SPEC)


def test_lift_counts_what_is_more_common_than_usual():
    rel = torch.tensor([[0, 1], [0, 2], [1, 2], [1, 2]])
    query = torch.tensor([0, 0, 1, 1])
    lift = relation_lift(rel, query, 4)
    assert lift[0, 0] > 1 and lift[1, 0] == 0 and lift[3].sum() == 0


def test_table_is_right_with_enough_chains(task):
    _, d = task
    assert torch.equal(legal_table(d["train"]["rel"], d["train"]["query"], R), truth())


def test_table_does_not_use_equal_numbers(task):
    """换掉查询的编号，表的行跟着换；靠“编号相等”的规则做不到。"""
    _, d = task
    perm = torch.tensor([3, 5, 0, 6, 1, 2, 4, 7])
    t = legal_table(d["train"]["rel"], perm[d["train"]["query"]], R)
    assert torch.equal(t[perm], truth())


def test_query_never_seen_has_no_legal_relation():
    t = legal_table(torch.tensor([[0, 1, 2, 3]] * 8), torch.zeros(8, dtype=torch.long), 6)
    assert t[1:].sum() == 0


def test_relation_never_seen_is_not_legal(task):
    name, d = task
    t = legal_table(d["train"]["rel"], d["train"]["query"], R)
    assert t[:, R - 1].sum() == 0
    assert name == "anchor" or int((d["train"]["rel"] == R - 1).sum()) == 0


def test_shuffling_removes_the_rule_and_keeps_the_counts(task):
    _, d = task
    rel = d["train"]["rel"]
    s = shuffle_relations(rel, 3)
    assert torch.equal(s.flatten().sort().values, rel.flatten().sort().values)
    assert not torch.equal(legal_table(s, d["train"]["query"], R), truth())


def test_shift_moves_every_ordinary_relation_and_keeps_the_anchor():
    p = shift_map(R - 1, R, 9)
    assert sorted(p.tolist()) == list(range(R))
    assert (p[: R - 1] != torch.arange(R - 1)).all() and p[R - 1] == R - 1


def test_window_forgets_the_old_world(task):
    _, d = task
    rel, query = d["train"]["rel"], d["train"]["query"]
    p = shift_map(R - 1, R, 9)
    old, new = (rel[:1024], query[:1024]), (p[rel[1024:]], query[1024:])
    new_truth = torch.zeros(R, R, dtype=torch.bool)
    new_truth[torch.arange(R - 1), p[: R - 1]] = True
    assert torch.equal(window_table(old, new, 0, 1024, R), truth())
    assert torch.equal(window_table(old, new, 1024, 1024, R), new_truth)


def test_model_does_not_read_the_anchor():
    assert "anchor_rel" not in Path(model9.__file__).read_text(encoding="utf-8").split('"""', 2)[2]
    assert "anchor_rel" not in Path(rule9.__file__).read_text(encoding="utf-8").split('"""', 2)[2]


@pytest.mark.parametrize("kind", ["sim", "pair", "attn"])
def test_illegal_positions_cannot_be_chosen(task, kind):
    _, d = task
    lat = build_lattice(SPEC)
    m = Selector9(SPEC, lat["vec"], truth(), kind)
    b = {k: d["dev"][k][:32] for k in ("rel", "obj", "query", "target", "n_cand")}
    p = m(b)
    assert torch.allclose(p.sum(-1), torch.ones(32), atol=1e-5)
    assert p[b["rel"] != b["query"].unsqueeze(1)].abs().max() < 1e-6


def test_swapping_the_table_needs_no_training(task):
    _, d = task
    lat = build_lattice(SPEC)
    m = Selector9(SPEC, lat["vec"], truth(), "sim")
    before = {k: v.clone() for k, v in m.named_parameters()}
    m.legal = torch.zeros(R, R, dtype=torch.bool)
    b = {k: d["dev"][k][:8] for k in ("rel", "obj", "query", "target", "n_cand")}
    assert torch.allclose(m(b), torch.full((8, SPEC.chain_len), 1.0 / SPEC.chain_len))
    assert all(torch.equal(before[k], v) for k, v in m.named_parameters())


def test_sim_has_twelve_numbers():
    assert sum(p.numel() for p in Selector9(SPEC, build_lattice(SPEC)["vec"], truth(), "sim").parameters()) == 12


def test_cosine_with_table_does_not_know_the_anchor():
    d = build_task("anchor", SPEC)
    vec = build_lattice(SPEC)["vec"]
    assert cosine_choice_two9(d["dev"], vec, truth()) < 0.7


def test_training_is_deterministic(task):
    _, d = task
    lat = build_lattice(SPEC)
    a = train_one9(SPEC, lat["vec"], truth(), lat["bit"], d, "pair", 1, steps=4, eval_every=2)
    b = train_one9(SPEC, lat["vec"], truth(), lat["bit"], d, "pair", 1, steps=4, eval_every=2)
    assert a[1] == b[1]
    assert all(torch.equal(x, y) for x, y in zip(a[0].state_dict().values(), b[0].state_dict().values()))
