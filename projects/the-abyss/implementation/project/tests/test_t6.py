"""T6：拆开的晶格和不是 attention 的比较。"""
from __future__ import annotations

import pytest
import torch

from empirical_core.t5.model import evaluate, n_params, take, train_one
from empirical_core.t5.task import T5Spec, build_lattice, build_task
from empirical_core.t6.model import KINDS, PARTS, PairBlock, Selector6, train_one6

SPEC = T5Spec(n_train=256, n_dev=64, n_test=128)


@pytest.fixture(scope="module")
def lat():
    return build_lattice(SPEC)


@pytest.fixture(scope="module")
def tasks():
    return {t: build_task(t, SPEC) for t in ("anchor", "mutual")}


@pytest.mark.parametrize("kind", ("attn", "mean"))
@pytest.mark.parametrize("part,lattice", (("full", True), ("none", False)))
def test_full_and_none_walk_the_same_path_as_t5(kind, part, lattice, lat, tasks):
    a, ca = train_one(SPEC, lat, tasks["mutual"], kind, lattice, 3, steps=20, eval_every=10)
    b, cb = train_one6(SPEC, lat, tasks["mutual"], kind, part, 3, steps=20, eval_every=10)
    assert [c["dev_choice_two"] for c in ca] == [c["dev_choice_two"] for c in cb]
    for p, q in zip(a.parameters(), b.parameters()):
        assert torch.equal(p, q)


def test_parts_give_what_they_say(lat):
    def names(part):
        return {n.split(".")[0] for n, _ in Selector6(SPEC, lat["vec"], "attn", part).named_parameters()}

    assert not {"obj", "rel", "qry"} & names("full")
    assert "obj" not in names("vec") and {"rel", "qry"} <= names("vec")
    assert "obj" in names("rule") and not {"rel", "qry"} & names("rule")
    assert {"obj", "rel", "qry"} <= names("none")


@pytest.mark.parametrize("part", PARTS)
def test_mask_exists_only_when_the_rule_is_given(part, lat, tasks):
    d = tasks["mutual"]["test_iid"]
    m = Selector6(SPEC, lat["vec"], "attn", part).eval()
    with torch.no_grad():
        sel = m(take(d, torch.arange(len(d["target"]))))
    illegal = sel[d["rel"] != d["query"].unsqueeze(1)]
    if part in ("full", "rule"):
        assert illegal.max() < 1e-6
    else:
        assert illegal.max() > 1e-3


def test_vector_part_does_not_see_the_rule_flags(lat, tasks):
    m = Selector6(SPEC, lat["vec"], "attn", "vec")
    b = take(tasks["mutual"]["train"], torch.arange(4))
    assert m.features(b).shape[-1] == 3 * SPEC.k


def test_rule_part_does_not_see_the_reference_vectors(lat, tasks):
    b = take(tasks["mutual"]["train"], torch.arange(4))
    m = Selector6(SPEC, lat["vec"], "attn", "rule")
    x = m.features(b)
    m2 = Selector6(SPEC, lat["vec"] + 1.0, "attn", "rule")
    m2.load_state_dict({k: v for k, v in m.state_dict().items() if k != "vec"}, strict=False)
    assert torch.equal(x, m2.features(b))


@pytest.mark.parametrize("part", ("vec", "rule", "none"))
def test_sim_needs_the_whole_lattice(part, lat):
    with pytest.raises(ValueError):
        Selector6(SPEC, lat["vec"], "sim", part)


def test_sim_has_six_numbers(lat):
    assert n_params(Selector6(SPEC, lat["vec"], "sim", "full")) == 6


@pytest.mark.parametrize("task,w_q,w_a,c", (("mutual", -20.0, 0.0, 10.0), ("anchor", 0.0, 20.0, -10.0)))
def test_sim_can_represent_both_rules(task, w_q, w_a, c, lat, tasks):
    m = Selector6(SPEC, lat["vec"], "sim", "full")
    with torch.no_grad():
        m.t.fill_(60.0)
        m.b.fill_(0.92)
        m.a.fill_(20.0)
        m.gate.weight.copy_(torch.tensor([[w_q, w_a]]))
        m.gate.bias.fill_(c)
    for split in ("test_iid", "test_new"):
        assert evaluate(m, tasks[task][split], lat["bit"])["choice_two"] > 0.97


def test_pair_block_passes_information_between_tokens():
    torch.manual_seed(0)
    blk = PairBlock(8).eval()
    x = torch.randn(2, 4, 8)
    y = x.clone()
    y[:, 0] += 1.0
    assert not torch.allclose(blk(x)[:, 1:], blk(y)[:, 1:])


def test_pair_block_has_no_competition_between_partners():
    """加一个和自己无关的伙伴，不会把别的伙伴的权重压低：这里只查没有 softmax 的归一化。"""
    torch.manual_seed(0)
    blk = PairBlock(8).eval()
    x = torch.randn(1, 3, 8)
    q, k = blk.q(x), blk.k(x)
    m = blk.g(q.unsqueeze(2) * k.unsqueeze(1))
    assert torch.allclose(m[0, 0, 1], blk.g(q[0, 0] * k[0, 1]), atol=1e-6)


@pytest.mark.parametrize("kind", KINDS)
def test_training_runs_and_is_reproducible(kind, lat, tasks):
    a, ca = train_one6(SPEC, lat, tasks["anchor"], kind, "full", 3, steps=5, eval_every=5)
    b, cb = train_one6(SPEC, lat, tasks["anchor"], kind, "full", 3, steps=5, eval_every=5)
    assert ca == cb
    for p, q in zip(a.parameters(), b.parameters()):
        assert torch.equal(p, q)


@pytest.mark.parametrize("part", ("vec", "rule"))
def test_split_parts_train(part, lat, tasks):
    m, c = train_one6(SPEC, lat, tasks["mutual"], "attn", part, 1, steps=5, eval_every=5)
    assert len(c) == 1 and c[0]["train_loss"] > 0


def test_reference_vectors_are_not_trained(lat, tasks):
    before = lat["vec"].clone()
    m, _ = train_one6(SPEC, lat, tasks["anchor"], "sim", "full", 1, steps=3, eval_every=3)
    assert torch.equal(m.vec, before)
