"""T1 训练、计分与螺旋式分层训练（2026-11-01）。只在 small 档的少量题上跑很少的步数，检查程序与边界，不是实验结果。"""
from dataclasses import replace

import pytest
import torch

from empirical_core.t1.features import encode
from empirical_core.t1.model_a import ModelA, config_for
from empirical_core.t1.spiral import DirtyVersion, ResourcePending, SpiralA, arrival_rounds, resolved_pairs
from empirical_core.t1.task import PRESETS, build_t1, resolve
from empirical_core.t1.train import decide, predict, score, train_joint

torch.set_num_threads(2)
DATA = build_t1(replace(PRESETS["small"], seed=3))      # 不是正式实验的题
TRAIN, DEV = encode(DATA, "train"), encode(DATA, "dev")
CFG = config_for(DATA["spec"], "small")


def _spiral(tmp_path, **kw):
    args = dict(seed=0, rounds=2, epochs_per_phase=1, batch_size=128, lr=1e-3, arrival_seed=5,
                l0_budget_bytes=64 << 20, l1_budget_bytes=1 << 30)
    args.update(kw)
    return SpiralA(CFG, tmp_path, **args)


def test_joint_training_runs_and_reports():
    torch.manual_seed(0)
    model = ModelA(CFG)
    rec = train_joint(model, TRAIN, epochs=2, batch_size=256, lr=1e-3, seed=0, curve_batch=DEV, curve_points=2)
    assert rec["updates"] == 2 * -(-len(TRAIN.ids) // 256) and len(rec["curve"]) == 2
    sc = score(predict(model, DEV), DEV)
    assert sc["overall"]["n"] == len(DEV.ids) and sc["overall"]["answered"] <= sc["overall"]["n"]


def test_unknown_rule_is_fixed_and_counts_separately():
    pred = {"logit": torch.tensor([3.0, 0.1, -3.0, -3.0]), "none": torch.tensor([[0.0, 0.0]] * 3 + [[0.9, 0.0]])}
    d = decide(pred)
    assert d["forced"].tolist() == [1, 1, 0, 0]
    assert d["unknown"].tolist() == [False, True, False, True]   # p≈0.52 太接近一半；EA 说找不到合适事件


def test_identity_bias_makes_ea_follow_the_cpu_identity_judgement():
    torch.manual_seed(0)
    plain, biased = ModelA(CFG), ModelA(config_for(DATA["spec"], "small", identity_bias=6.0))
    biased.load_state_dict(plain.state_dict())                     # 同样的参数，只差结构约束
    ia = DEV.rel_match[..., 0].argmax(1)
    with torch.no_grad():
        sel_plain, sel_biased = plain(DEV)["select"], biased(DEV)["select"]
    rows = torch.arange(len(DEV.ids))
    assert float(sel_biased[rows, 0, ia].mean()) > 0.9 > float(sel_plain[rows, 0, ia].mean())


def test_resolved_pairs_use_only_visible_relations():
    m = resolved_pairs(TRAIN)
    for i, ep in enumerate([ep for ep in DATA["episodes"] if ep["split"] == "train"][:50]):
        a, b = resolve(ep)
        assert (int(m["a_pkg"][i]), int(m["a_mem"][i])) == a and (int(m["b_pkg"][i]), int(m["b_mem"][i])) == b


def test_arrival_rounds_cover_everything_once():
    arr = arrival_rounds(1000, 8, seed=1)
    assert arr.min() == 1 and arr.max() == 8 and torch.bincount(arr)[1:].tolist() == [125] * 8


def test_spiral_writes_only_local_scope_and_keeps_versions(tmp_path):
    sp = _spiral(tmp_path)
    rec = sp.fit(TRAIN, DEV)
    assert len(rec["curve"]) == 2 and sp.l0_version == [2] * CFG.n_packages
    l0 = [b for b in sp.bills if b["layer"] == "L0"]
    assert all(b["write_scope"] == [f"o[{b['node']}]", f"u[{b['node']}]", f"pi[{b['node']}]"] for b in l0)
    assert all(b["projected"] == 0 for b in l0 if b["round"] == 1)           # 第一轮上层还没有产品
    assert any(b["projected"] > 0 for b in l0 if b["round"] == 2)            # 第二轮借上层产品做投影材料
    assert all((tmp_path / "L0" / f"r{r:02d}" / "p0000.pt").exists() for r in (1, 2))   # 旧版本保留
    assert (tmp_path / "L1" / "r01.pt").exists() and (tmp_path / "L1" / "r02.pt").exists()
    model = sp.assemble()
    assert torch.equal(model.offsets()[:, 0], torch.zeros(CFG.n_packages, CFG.k))
    for p in range(CFG.n_packages):                                           # 上层读的是下层本轮产品
        assert torch.equal(model.offsets()[p], sp.node_product(p))


def test_l0_phase_changes_only_its_own_node(tmp_path):
    sp = _spiral(tmp_path)
    sp.fit(TRAIN)
    before = [sp.node_product(p) for p in range(CFG.n_packages)]
    mats = resolved_pairs(TRAIN)
    sp._l0_phase(3, 4, mats, torch.ones(len(TRAIN.ids), dtype=torch.bool))
    after = [sp.node_product(p) for p in range(CFG.n_packages)]
    assert not torch.equal(before[4], after[4])
    assert all(torch.equal(before[p], after[p]) for p in range(CFG.n_packages) if p != 4)
    with pytest.raises(DirtyVersion):                                         # 下层换版、上层没重建：拒绝
        sp.assemble()


def test_replay_keeps_each_round_bounded_and_includes_all_new_arrivals(tmp_path):
    sp = _spiral(tmp_path, rounds=6, replay_ratio=1.0)
    arrival = arrival_rounds(600, 6, seed=2)
    seen_new = torch.zeros(600, dtype=torch.bool)
    for r in range(1, 7):
        chosen = sp.round_materials(arrival, r)
        assert torch.equal(chosen & (arrival == r), arrival == r)            # 本轮新到的全部要学
        assert not (chosen & (arrival > r)).any()                            # 不会读到还没到达的
        assert int(chosen.sum()) == 100 + min(100, (r - 1) * 100)           # 新 100 条＋至多同样多的旧题
        assert torch.equal(chosen, sp.round_materials(arrival, r))           # 同一种子同一轮，抽样固定
        seen_new |= arrival == r
    assert bool(seen_new.all())
    rec = sp.fit(TRAIN)
    assert len(rec["curve"]) == 6 and sp.l0_version == [6] * CFG.n_packages


def test_spiral_stops_instead_of_trimming_when_budget_is_too_small(tmp_path):
    sp = _spiral(tmp_path, l0_budget_bytes=1000)
    with pytest.raises(ResourcePending):
        sp.fit(TRAIN)
