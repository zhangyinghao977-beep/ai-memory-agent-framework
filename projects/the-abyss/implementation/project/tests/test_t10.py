"""T10：只有关系嵌入开始时的大小变了；scale=1 就是 T9。"""
from __future__ import annotations

from pathlib import Path

import pytest
import torch

from empirical_core.t5.task import T5Spec, build_lattice, build_task
from empirical_core.t9.model import Selector9, train_one9
from empirical_core.t10 import model as model10
from empirical_core.t10.model import make10, part_sizes, train_one10

SPEC = T5Spec(n_train=2048, n_dev=256, n_test=128)
R = SPEC.n_relations


def truth() -> torch.Tensor:
    t = torch.zeros(R, R, dtype=torch.bool)
    t[torch.arange(R - 1), torch.arange(R - 1)] = True
    return t


@pytest.fixture(scope="module")
def lat():
    return build_lattice(SPEC)


@pytest.fixture(scope="module", params=["anchor", "mutual"])
def data(request):
    return build_task(request.param, SPEC)


@pytest.mark.parametrize("kind", ["pair", "attn"])
@pytest.mark.parametrize("scale", [0.25, 0.0])
def test_only_the_relation_embedding_changes_at_start(lat, kind, scale):
    torch.manual_seed(3)
    old = Selector9(SPEC, lat["vec"], truth(), kind)
    new = make10(SPEC, lat["vec"], truth(), kind, 3, scale, True)
    a, b = dict(old.named_parameters()), dict(new.named_parameters())
    assert a.keys() == b.keys()
    assert all(torch.equal(a[k], b[k]) for k in a if k != "rel.weight")
    assert torch.equal(b["rel.weight"], a["rel.weight"] * scale)


@pytest.mark.parametrize("kind", ["pair", "attn"])
def test_scale_one_is_t9(lat, data, kind):
    a = train_one9(SPEC, lat["vec"], truth(), lat["bit"], data, kind, 1, steps=6, eval_every=3)
    b = train_one10(SPEC, lat["vec"], truth(), lat["bit"], data, kind, 1, 1.0, True, steps=6, eval_every=3)
    assert a[1] == b[1]
    assert all(torch.equal(x, y) for x, y in zip(a[0].state_dict().values(), b[0].state_dict().values()))


def test_off_stays_zero_and_the_rest_learns(lat, data):
    m, _ = train_one10(SPEC, lat["vec"], truth(), lat["bit"], data, "pair", 1, 0.0, False, steps=4, eval_every=2)
    start = make10(SPEC, lat["vec"], truth(), "pair", 1, 0.0, False)
    assert m.rel.weight.abs().sum() == 0
    assert not torch.equal(m.ptr.weight, start.ptr.weight)


def test_zero_start_can_still_grow(lat, data):
    m, _ = train_one10(SPEC, lat["vec"], truth(), lat["bit"], data, "pair", 1, 0.0, True, steps=4, eval_every=2)
    assert m.rel.weight.abs().sum() > 0


def test_sizes_at_start(lat, data):
    b = {k: v[:64] for k, v in data["train"].items()}
    assert part_sizes(make10(SPEC, lat["vec"], truth(), "pair", 1, 0.0, True), b, SPEC.k)["rel"] == 0
    big = part_sizes(make10(SPEC, lat["vec"], truth(), "pair", 1, 1.0, True), b, SPEC.k)["rel"]
    small = part_sizes(make10(SPEC, lat["vec"], truth(), "pair", 1, 0.25, True), b, SPEC.k)["rel"]
    assert small == pytest.approx(big / 4, rel=1e-4)


def test_model_does_not_read_the_anchor():
    assert "anchor_rel" not in Path(model10.__file__).read_text(encoding="utf-8").split('"""', 2)[2]
