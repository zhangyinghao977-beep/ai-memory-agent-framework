"""T3：间接包出题、EA↔KA 单向／双向修正、统一校验（2026-11-03）。
只在 small 档上跑很少的步数，检查程序与边界，不是实验结果。"""
from dataclasses import replace

import torch

from empirical_core.t2.features import encode
from empirical_core.t2.spiral import ChainSpiral, ka_name
from empirical_core.t2.task import exact_resolve, label_of, theory_resolve
from empirical_core.t2.units import UnitStore, config_for
from empirical_core.t3 import baselines as bl
from empirical_core.t3.spiral import MutualSpiral
from empirical_core.t3.stability import Checker, ka_differences, measures, oscillation, simulate_stop, snapshot
from empirical_core.t3.task import PRESETS, build_t3

torch.set_num_threads(2)
DATA = build_t3(replace(PRESETS["small"], seed=11))         # 不是正式实验的题
CFG = config_for(DATA["spec"], "small")
TRAIN, _ = encode(DATA, "train")
DEV, DEV_DIAG = encode(DATA, "dev")
IND = DATA["indirect_packages"]
VALUES = {tuple(map(int, k.split(","))): v for k, v in DATA["hidden_values"].items()}
ARGS = dict(seed=0, epochs_per_phase=1, batch_size=128, lr={"ka": 3e-3, "ea": 1e-3, "ca": 1e-3},
            budgets={"ka": 1 << 26, "ea": 1 << 30, "ca": 1 << 30})


def _sp(tmp_path, two_way, name="units"):
    return MutualSpiral(CFG, UnitStore(tmp_path / name), TRAIN, two_way=two_way, **ARGS)


# ---------- 出题器 ----------
def test_rules_and_labels_match_hidden_truth():
    for ep in DATA["episodes"]:
        h = ep["hidden"]
        assert theory_resolve(ep) == (h["A"], h["B"], h["world"])
        assert ep["label"] == label_of(h["world"], VALUES[h["A"]], VALUES[h["B"]])
        assert ep["condition"] == "base" and ep["genre"] == 0
        assert h["indirect"] == (h["A"][0] in IND) + (h["B"][0] in IND)


def test_indirect_packages_have_no_exact_train_material_but_appear_elsewhere():
    assert bl.indirect_exact_rows(TRAIN, IND) == 0
    train_ind = [ep for ep in DATA["episodes"] if ep["split"] == "train" and ep["hidden"]["indirect"]]
    assert train_ind and all(exact_resolve(ep) is None for ep in train_ind)
    for ep in train_ind:                                    # 间接包那一边一定带链内改口
        h = ep["hidden"]
        assert (h["A"][0] not in IND or h["dup_x"]) and (h["B"][0] not in IND or h["dup_y"])
    held = [ep for ep in DATA["episodes"] if ep["split"] != "train" and ep["hidden"]["indirect"]]
    assert any(exact_resolve(ep) is not None for ep in held)   # 留出集里间接包照常出题
    assert any(ep["hidden"]["needs_ea"] for ep in DATA["episodes"] if not ep["hidden"]["indirect"])


def test_one_split_table_and_strata_have_indirect():
    split = {}
    for ep in DATA["episodes"]:
        key = (tuple(sorted((tuple(ep["hidden"]["A"]), tuple(ep["hidden"]["B"])))), ep["hidden"]["world"])
        assert split.setdefault(key, ep["split"]) == ep["split"]
    st = bl.strata(DATA, "dev")
    assert {v["indirect"] for v in st.values()} <= {"none", "one", "both"}
    assert len(st) == len(DEV.ids)


# ---------- 单向／双向 ----------
def test_one_way_is_t2_and_never_trains_indirect_ka(tmp_path):
    a = _sp(tmp_path, False, "a")
    t2 = ChainSpiral(CFG, UnitStore(tmp_path / "b"), TRAIN, **ARGS)
    idx = torch.arange(len(TRAIN.ids))
    for r in (1, 2):
        a.run_round("t", r, idx, list(range(CFG.n_packages)), True, True)
        t2.run_round("t", r, idx, list(range(CFG.n_packages)), True, True)
    assert a.store.snapshot() == t2.store.snapshot()
    assert torch.equal(a.ctable(), t2.ctable())
    assert all(a.store.version(ka_name(p)) == 0 for p in IND)      # 契约：单向时间接包没有材料，从不写


def test_two_way_sieve_feeds_indirect_ka_from_previous_round(tmp_path):
    sp = _sp(tmp_path, True)
    idx = torch.arange(len(TRAIN.ids))
    sp.run_round("t", 1, idx, list(range(CFG.n_packages)), True, True)
    assert all(sp.store.version(ka_name(p)) == 0 for p in IND)     # 第一轮还没有筛子
    ea_v, ca_v = sp.store.version("ea"), sp.store.version("ca")
    sp.run_round("t", 2, idx, list(range(CFG.n_packages)), True, True)
    sieve = [b for b in sp.bills if b["layer"] == "SIEVE"]
    assert len(sieve) == 1 and sieve[0]["read"] == {"ea": ea_v, "ca": ca_v}
    ka2 = [b for b in sp.bills if b["layer"] == "KA" and b["round"] == 2]
    assert sum(b["sieved"] for b in ka2) > 0
    assert all(b["read"]["sieve"] == {"ea": ea_v, "ca": ca_v} for b in ka2)
    assert any(sp.store.version(ka_name(p)) > 0 for p in IND)


def test_sieve_weights_are_ca_times_ea_and_owner_is_argmax(tmp_path):
    sp = _sp(tmp_path, True)
    idx = torch.arange(len(TRAIN.ids))
    sp.run_round("t", 1, idx, list(range(CFG.n_packages)), True, True)
    rows = idx[~TRAIN.exact][:50]
    sv = sp.sieve(rows)
    assert sv["w_a"].shape == (50, CFG.n_chains, CFG.chain_len)
    assert float(sv["w_a"].sum(dim=(1, 2)).max()) <= 1 + 1e-5
    flat = sv["w_b"].reshape(50, -1).argmax(-1)
    pkg = TRAIN.ev_pkg[rows].reshape(50, -1)
    assert torch.equal(sv["owner_b"], pkg[torch.arange(50), flat])


# ---------- 统一校验 ----------
def test_checker_is_read_only_and_self_change_is_zero(tmp_path):
    sp = _sp(tmp_path, True)
    probe = DEV                                             # 测试里随便拿一份输入当探针
    s0 = snapshot(sp, probe)
    assert measures(s0, s0) == {"slot": 0.0, "ka": 0.0, "ea": 0.0, "answer": 0.0}
    chk = Checker(sp, probe)
    chk(0)
    before = sp.store.snapshot()
    chk(0)
    assert sp.store.snapshot() == before
    idx = torch.arange(len(TRAIN.ids))
    for r in (1, 2, 3):
        sp.run_round("t", r, idx, list(range(CFG.n_packages)), True, True)
        rec = chk(r)
    assert set(rec["lag"]) == {1, 2, 3} and "oscillation" in rec
    assert rec["lag"][1]["slot"] > 0 and rec["snapshot_seconds"] >= 0


def test_oscillation_sign():
    cand = torch.ones(1, 1, 2, dtype=torch.bool)
    s = [{"slot": torch.full((1, 1, 2, 3), float(v)), "ea_arg": torch.full((1, 1, 2), a), "cand": cand}
         for v, a in ((0, 0), (1, 1), (0, 0))]
    o = oscillation(s[2], s[1], s[0])
    assert o["slot_cos"] < -0.99 and o["ea_back"] == 1.0


def test_simulate_stop_uses_cadence_and_window():
    recs = [{"round": r, "lag": {k: {"slot": v} for k in (1, 2, 3)}}
            for r, v in enumerate([1.0, 0.5, 0.2, 0.05, 0.04, 0.2, 0.03, 0.02, 0.01])]
    assert simulate_stop(recs, "slot", 1, 0.1, 1, 8) == 3
    assert simulate_stop(recs, "slot", 1, 0.1, 2, 8) == 4
    assert simulate_stop(recs, "slot", 3, 0.1, 1, 8) == 3
    assert simulate_stop(recs, "slot", 3, 0.04, 1, 8) == 6
    assert simulate_stop(recs, "slot", 2, 0.01, 1, 8) is None       # 到上限也没停：截断


def test_ka_differences_counts(tmp_path):
    sp = _sp(tmp_path, True)
    d = ka_differences(sp, DATA["hidden_values"], IND)
    M = CFG.n_members
    assert d["indirect"]["order_n"] == len(IND) * M * (M - 1) // 2
    assert d["direct"]["order_n"] == (CFG.n_packages - len(IND)) * M * (M - 1) // 2
