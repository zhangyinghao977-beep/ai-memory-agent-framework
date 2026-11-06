"""T2：出题器、三层单元、螺旋训练、修复写范围与逐级加深（2026-11-02）。
只在 small 档上跑很少的步数，检查程序与边界，不是实验结果。"""
from dataclasses import replace

import pytest
import torch

from empirical_core.t2 import baselines as bl
from empirical_core.t2.evaluate import decide, layer_diagnostics, score
from empirical_core.t2.features import concat, encode
from empirical_core.t2.repair import LADDER, escalate, local_packages, resolve_scope
from empirical_core.t2.spiral import ChainSpiral, DirtyVersion, ResourcePending, ka_name
from empirical_core.t2.task import PRESETS, build_t2, exact_resolve, theory_resolve
from empirical_core.t2.units import CAUnit, EAUnit, UnitStore, config_for, ka_init, ka_product

torch.set_num_threads(2)
DATA = build_t2(replace(PRESETS["small"], seed=7))          # 不是正式实验的题
CFG = config_for(DATA["spec"], "small")
PARTS = {c: encode(DATA, "train", (c,)) for c in ("base", "C1", "C2", "C3")}
TRAIN = concat(*(PARTS[c][0] for c in ("base", "C1", "C2", "C3")))
OFFS, _o = {}, 0
for _c in ("base", "C1", "C2", "C3"):
    OFFS[_c] = torch.arange(_o, _o + len(PARTS[_c][0].ids))
    _o += len(PARTS[_c][0].ids)
DEV, DEV_DIAG = encode(DATA, "dev", ("base",))


def _sp(tmp_path, **kw):
    args = dict(seed=0, epochs_per_phase=1, batch_size=128, lr={"ka": 3e-3, "ea": 1e-3, "ca": 1e-3},
                budgets={"ka": 1 << 26, "ea": 1 << 30, "ca": 1 << 30})
    args.update(kw)
    return ChainSpiral(CFG, UnitStore(tmp_path / "units"), TRAIN, **args)


# ---------- 出题器 ----------
def test_rules_resolve_to_hidden_truth_and_exact_agrees():
    for ep in DATA["episodes"]:
        a, b, w = theory_resolve(ep)
        h = ep["hidden"]
        assert (a, b, w) == (h["A"], h["B"], h["world"])
        ex = exact_resolve(ep)
        assert ex is None or ex == (a, b, w)
        chains = ep["chains"]
        assert chains[h["a_chain"]]["events"][h["a_event"]][1:] == list(a)
        assert chains[h["set_chain"]]["world"] == w


def test_conditions_change_only_their_own_layer():
    missing = set(DATA["missing_packages"])
    for ep in DATA["episodes"]:
        h, c = ep["hidden"], ep["condition"]
        mentioned = {e[1] for ch in ep["chains"] if ch["kind"] == "say" for e in ch["events"]}
        if c in ("base", "C2", "C3"):
            assert not mentioned & missing                   # 遗漏的包在其他条件里连干扰项也不出现
        else:
            assert {h["A"][0], h["B"][0]} & missing
        assert (ep["genre"] == 1) == (c == "C3")
        assert h["needs_ea"] == (c == "C2")
        if c == "C3":
            assert h["needs_ca"]


def test_all_conditions_share_one_split_table():
    split = {}
    for ep in DATA["episodes"]:
        key = (tuple(sorted((tuple(ep["hidden"]["A"]), tuple(ep["hidden"]["B"])))), ep["hidden"]["world"])
        assert split.setdefault(key, ep["split"]) == ep["split"]


def test_encoding_exact_rows_and_diag_match_rules():
    b, dg = PARTS["base"]
    eps = {ep["id"]: ep for ep in DATA["episodes"]}
    for i in range(0, len(b.ids), 37):
        ep = eps[b.ids[i]]
        ex = exact_resolve(ep)
        assert bool(b.exact[i]) == (ex is not None)
        if ex is not None:
            assert tuple(b.ex_a[i].tolist()) == ex[0] and tuple(b.ex_b[i].tolist()) == ex[1]
        assert int(dg["a_chain"][i]) == ep["hidden"]["a_chain"]
        assert float(b.spk_x[i, ep["hidden"]["a_chain"]]) == 1.0
        assert float(b.rel_a[i, ep["hidden"]["a_chain"], ep["hidden"]["a_event"]]) == 1.0


def test_gate_and_path_reasoner_run_on_each_condition():
    for c, train_c in (("base", ("base",)), ("C1", ("base", "C1")), ("C3", ("base", "C3"))):
        rep = bl.gate(DATA, "test", (c,), train_c, min_main=0)
        assert rep.details["main_stratum"] == "new_conflict"
        path = bl.path_reasoner(DATA, train_c)
        eps = [ep for ep in DATA["episodes"] if ep["split"] == "test" and ep["condition"] == c]
        answered = [path(ep) for ep in eps]
        assert all(p == ep["label"] for p, ep in zip(answered, eps) if p is not None)


# ---------- 单元 ----------
def test_identity_bias_makes_ea_and_ca_follow_cpu_identity():
    torch.manual_seed(0)
    b, dg = PARTS["base"]
    ea, ca = EAUnit(CFG), CAUnit(CFG)
    rows = torch.arange(len(b.ids))
    with torch.no_grad():
        sel_a = ea(b.rel_a[rows, dg["a_chain"]], b.ev_valid[rows, dg["a_chain"]])
        sel = ca.select(b)
    assert float(sel_a[rows, dg["a_event"]].mean()) > 0.9
    simple = ~(dg["needs_ca"].bool())
    assert float(sel[rows, 0, dg["a_chain"]][simple].mean()) > 0.9
    assert float(sel[rows, 2, dg["set_chain"]][simple].mean()) > 0.9


def test_ka_reference_member_is_zero_before_conversion():
    unit = ka_init(CFG, 3, seed=0)
    unit["W"], unit["b"] = torch.eye(CFG.k), torch.zeros(CFG.k)
    assert torch.equal(ka_product(unit)[0], torch.zeros(CFG.k))


def test_store_never_overwrites_versions_even_from_a_new_process(tmp_path):
    s1 = UnitStore(tmp_path)
    assert s1.write("ea", {"x": 1}) == 1 and s1.write("ea", {"x": 2}) == 2
    s2 = UnitStore(tmp_path)                                  # 续跑时的新进程
    s2.restore({"ea": 1})
    assert s2.read("ea") == {"x": 1}
    assert s2.write("ea", {"x": 3}) == 3
    assert UnitStore(tmp_path).latest == {} and (tmp_path / "ea" / "v00002.pt").exists()


# ---------- 螺旋训练与修复 ----------
def test_fit_writes_all_three_layers_and_keeps_versions(tmp_path):
    sp = _sp(tmp_path)
    rec = sp.fit("base", OFFS["base"], rounds=2, arrival_seed=1, curve=(DEV,))
    assert len(rec["curve"]) == 2
    layers = {b["layer"] for b in sp.bills}
    assert layers == {"KA", "EA", "CA"}
    assert all(b["projected"] == 0 for b in sp.bills if b["layer"] == "KA" and b["round"] == 1)
    assert any(b["projected"] > 0 for b in sp.bills if b["layer"] == "KA" and b["round"] == 2)
    assert sp.store.version("ea") == 2 and sp.store.version("ca") == 2
    missing = DATA["missing_packages"]
    assert all(sp.store.version(ka_name(p)) == 0 for p in missing)          # 遗漏的包在 base 里没有材料
    pred = sp.predict(DEV, DEV_DIAG)
    sc = score(pred, DEV.labels, DEV.ids)
    assert sc["overall"]["n"] == len(DEV.ids)
    diag = layer_diagnostics(pred, DEV.labels, DEV_DIAG)
    assert diag["ca_all"]["n"] == len(DEV.ids)


def test_repair_writes_only_its_scope_and_ka_local_keeps_old_predictions(tmp_path):
    sp = _sp(tmp_path)
    sp.fit("base", OFFS["base"], rounds=2, arrival_seed=1)
    snap = sp.store.snapshot()
    before = sp.predict(DEV)["logit"]
    local = local_packages(sp, OFFS["C1"])
    assert sorted(local) == DATA["missing_packages"]
    assert local_packages(sp, OFFS["C2"]) == []
    sp.repair("C1-KA_local", OFFS["C1"], OFFS["base"], ka_packages=local, ea=False, ca=False, rounds=1,
              replay_ratio=1.0)
    after = sp.store.snapshot()
    changed = {k for k in set(snap) | set(after) if snap.get(k) != after.get(k)}
    assert changed == {ka_name(p) for p in local}
    assert torch.equal(sp.predict(DEV)["logit"], before)     # 契约检查：旧条件的题不经过这些单元
    sp.store.restore(snap)
    sp.repair("C3-CA", OFFS["C3"], OFFS["base"], ka_packages=[], ea=False, ca=True, rounds=1, replay_ratio=1.0)
    assert {k for k, v in sp.store.snapshot().items() if snap.get(k) != v} == {"ca"}


def test_stale_ea_products_are_refused(tmp_path):
    sp = _sp(tmp_path)
    sp.fit("base", OFFS["base"][:300], rounds=1, arrival_seed=1)
    idx = OFFS["base"][:300]
    prod = sp.ea_products(idx)
    sp._ea_phase("x", 9, idx)                                 # EA 换了版本
    with pytest.raises(DirtyVersion):
        sp._ca_phase("x", 9, idx, prod)


def test_budget_too_small_stops_instead_of_trimming(tmp_path):
    sp = _sp(tmp_path, budgets={"ka": 1000, "ea": 1 << 30, "ca": 1 << 30})
    with pytest.raises(ResourcePending):
        sp.fit("base", OFFS["base"], rounds=1, arrival_seed=1)


def test_escalation_rolls_back_failed_steps_and_records_them(tmp_path):
    sp = _sp(tmp_path)
    sp.fit("base", OFFS["base"], rounds=1, arrival_seed=1)
    snap = sp.store.snapshot()
    calls = []

    def check():                                              # 假的检查：只有写到 EA 的那一级算够用
        calls.append(sp.store.snapshot())
        ok = sp.store.version("ea") != snap["ea"] and sp.store.version("ca") == snap["ca"]
        return {"new_dev": 0.9 if ok else 0.5, "old_dev": 0.9}
    res = escalate(sp, snap, "C2-esc", OFFS["C2"], OFFS["base"], rounds=1, replay_ratio=1.0, check=check,
                   target=0.9, margin=0.02)
    assert [t["layers"] for t in res["trace"]] == [list(x) for x in LADDER[:3]]
    assert res["trace"][0]["skipped"] and res["status"] == "enough" and res["adopted"].endswith("/EA")
    assert sp.store.version("ca") == snap["ca"] and sp.store.version("ea") != snap["ea"]
    assert calls[0]["ca"] != snap["ca"] and calls[1]["ca"] == snap["ca"]      # 第二级从基线出发：CA 已回退


def test_unknown_rule_uses_none_probability():
    pred = {"logit": torch.tensor([3.0, 0.1, -3.0]), "none": torch.tensor([[0.0, 0.0], [0.0, 0.0], [0.0, 0.8]])}
    d = decide(pred)
    assert d["forced"].tolist() == [1, 1, 0] and d["unknown"].tolist() == [False, True, True]


def test_scope_resolution():
    sp = ChainSpiral.__new__(ChainSpiral)
    sp.cfg, sp.train, sp.store = CFG, TRAIN, UnitStore("unused")
    sc = resolve_scope(("CA", "EA", "KA_all"), sp, OFFS["C2"])
    assert sc["ka_packages"] == list(range(CFG.n_packages)) and sc["ea"] and sc["ca"]
