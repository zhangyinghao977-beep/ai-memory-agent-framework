"""T4：记忆登记、固定调用协议、资源池与资源保护、FSM 脚手架、单元存储、世界、存活循环、真杀进程的重启测试。
只在 small 档上跑很少的步数，检查程序与边界（契约），不是实验结果。"""
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import psutil
import pytest
import torch

from empirical_core.t2.features import encode, take
from empirical_core.t2.units import EAUnit, UnitStore, config_for
from empirical_core.t4 import fsm as F
from empirical_core.t4 import records as R
from empirical_core.t4.guided import GuidedEA, GuidedSpiral, ca_states
from empirical_core.t4.life import Life, LifeConf, encode_ids
from empirical_core.t4.records import CallProtocol, LongStore, QuickLog, recover
from empirical_core.t4.resources import Meter, Pool, Protector, ResourceInterrupt
from empirical_core.t4.units import LoggedUnitStore
from empirical_core.t4.world import WorldSpec, build_world, resolve_t4

torch.set_num_threads(2)
T4_RUNNER = (Path(__file__).resolve().parents[2] / "experiments" /
             "t4_survival_20261103" / "live_t4.py")
WS = WorldSpec(new_packages=1, new_package_day=2, new_genre_day=2, days=2, questions_per_day=48, probe_size=48)
WORLD = build_world(WS)
CFG = config_for(WORLD["spec"], "small")
SMALL = dict(epochs={"ka": 1, "ea": 1, "ca": 1}, sleep_rounds=1, cache_capacity=16, batch_per_call=16,
             learn_window=64, margin=-1.0, budgets={"ka": 1 << 26, "ea": 1 << 30, "ca": 1 << 30},
             pools={"awake": {"cpu_seconds": 1e6, "gpu_seconds": 1e6}, "sleep": {"cpu_seconds": 1e6, "gpu_seconds": 1e6}})


def _life(tmp_path, arm="survive", **kw):
    return Life(tmp_path / arm, WORLD, CFG, LifeConf(arm=arm, **{**SMALL, **kw}), device="cpu",
                proc=psutil.Process(), gpu_duty=None)


# ---------- 快速登记与固定调用协议 ----------
def test_quicklog_keeps_records_and_moves_torn_tail(tmp_path):
    log = QuickLog(tmp_path / "q.jsonl")
    log.append("a", x=1)
    log.append("b", x=2)
    with open(tmp_path / "q.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "kind": "half')                       # 断电时只写了一半
    again = QuickLog(tmp_path / "q.jsonl")
    assert [r["kind"] for r in again.records] == ["a", "b"] and again.torn is not None
    assert (tmp_path / "q.torn.jsonl").exists()
    again.append("c")
    assert [r["seq"] for r in QuickLog(tmp_path / "q.jsonl").records] == [0, 1, 2]


def test_quicklog_refuses_corruption_in_the_middle(tmp_path):
    (tmp_path / "q.jsonl").write_text('{"seq": 0, "kind": "a"}\nnot json\n{"seq": 2, "kind": "c"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError):
        QuickLog(tmp_path / "q.jsonl")


def test_protocol_saves_before_report_and_recovery_never_reexecutes(tmp_path):
    log = QuickLog(tmp_path / "q.jsonl")
    proto = CallProtocol(log)
    seen = []
    proto.run("answer", lambda: {"v": 1}, seen.append)
    kinds = [r["kind"] for r in log.records]
    assert kinds == ["call_start", "call_end", "report"] and seen[0]["status"] == "done"
    a = proto.start("answer")                                  # 断电：开始了、没结束
    b = proto.start("answer")
    proto.end(b, "done", call_kind="answer", v=2)              # 断电：结束了、没报告
    calls = []
    out = recover(QuickLog(tmp_path / "q.jsonl"), calls.append)
    assert out["lost_calls"] == [a] and out["late_reports"] == [b]
    assert [c["status"] for c in calls] == ["lost_in_crash", "done"]


def test_interrupt_is_registered_and_reported(tmp_path):
    log = QuickLog(tmp_path / "q.jsonl")

    def boom():
        raise ResourceInterrupt("满了")
    with pytest.raises(ResourceInterrupt):
        CallProtocol(log).run("answer", boom, lambda r: None, interrupt=(ResourceInterrupt,))
    assert [r["kind"] for r in log.records] == ["call_start", "call_end", "report"]
    assert log.records[1]["status"] == "interrupted"


def test_long_store_commits_whole_range_or_nothing(tmp_path, monkeypatch):
    log = QuickLog(tmp_path / "q.jsonl")
    for i in range(5):
        log.append("x", call=i)

    def crash(name):
        if name == "before_long_commit":
            raise KeyboardInterrupt
    monkeypatch.setattr(R, "crashpoint", crash)
    first = LongStore(tmp_path / "l.sqlite")
    with pytest.raises(KeyboardInterrupt):
        first.consolidate(log)
    first.close()                                               # 进程死掉时连接也没了：没提交的事务作废
    monkeypatch.setattr(R, "crashpoint", lambda name: None)
    ls = LongStore(tmp_path / "l.sqlite")
    assert ls.cursor() == 0 and ls.count() == 0                 # 提交以前断电：什么都没写，游标不动
    res = ls.consolidate(log)
    assert res["input"] == [0, 5] and ls.count() == 5 and ls.missing() == {"no_description": [], "no_index": []}
    log.append("y")
    assert ls.consolidate(log)["input"] == [5, 6]


# ---------- 资源池与资源保护 ----------
class _FakeProc:
    def __init__(self):
        self.t, self.rss = 0.0, 1

    def cpu_times(self):
        return type("T", (), {"user": self.t, "system": 0.0})()

    def memory_info(self):
        return type("M", (), {"rss": self.rss})()


def test_pool_charges_real_readings_and_never_resets_on_restart(tmp_path):
    log = QuickLog(tmp_path / "q.jsonl")
    proc = _FakeProc()
    meter = Meter(proc, False)
    pool = Pool("sleep", {"cpu_seconds": 10.0, "gpu_seconds": 0}, log, cycle=1)
    pool.open(meter)
    proc.t = 4.0
    pool.close(meter)
    again = Pool("sleep", {"cpu_seconds": 10.0, "gpu_seconds": 0}, QuickLog(tmp_path / "q.jsonl"), cycle=1)
    assert again.used["cpu_seconds"] == 4.0 and abs(again.frac_used() - 0.4) < 1e-9
    assert Pool("sleep", {"cpu_seconds": 10.0}, log, cycle=2).used["cpu_seconds"] == 0.0     # 新的一天是新的一份


def test_protector_trips_early_and_leaves_reserve(tmp_path):
    proc = _FakeProc()
    meter = Meter(proc, False)
    pool = Pool("awake", {"cpu_seconds": 10.0}, QuickLog(tmp_path / "q.jsonl"), cycle=1)
    pr = Protector(meter, trigger=0.8, max_rss_bytes=100)
    pr.active = pool
    pool.open(meter)
    proc.t = 7.0
    pr.check()
    proc.t = 8.5
    with pytest.raises(ResourceInterrupt):
        pr.check()
    assert pool.frac_used() < 1.0                               # 触发时还留着余量
    with pytest.raises(ValueError):
        Protector(meter, trigger=1.0, max_rss_bytes=100)


# ---------- FSM 脚手架 ----------
def test_fsm_choices_follow_continuous_inputs():
    p = F.FSMParams()
    assert F.decide(F.Observation(5, 0.1, 1.0, 1.0, 10), p)[0] == "awake"
    assert F.decide(F.Observation(0, 0.1, 1.0, 1.0, 10), p)[0] == "sleep"
    assert F.decide(F.Observation(0, 0.0, 1.0, 1.0, 10), p)[0] == "wander"
    assert F.decide(F.Observation(5, 0.1, 0.0, 1.0, 10), p)[0] == "sleep"      # 清醒池用完了
    assert F.decide(F.Observation(5, 0.1, 0.0, 0.0, 10), p)[0] == "wander"
    assert F.decide(F.Observation(3, 0.9, 1.0, 1.0, 300), p)[0] == "sleep"     # 积压很多又累了：先睡
    rec = F.record(F.Observation(0, 0.0, 1.0, 1.0, 0), p, "awake")
    assert rec["params"] == F.asdict(p) and rec["drives"]["awake"] is None


# ---------- 单元存储 ----------
def test_logged_store_atomic_adopt_rollback_and_candidates(tmp_path):
    log = QuickLog(tmp_path / "q.jsonl")
    st = LoggedUnitStore(tmp_path / "u", log)
    st.write("ea", {"w": 1})
    st.adopt("start")
    st.write("ea", {"w": 2})
    st.rollback()
    assert st.version("ea") == 1
    assert st.leftovers()["unadopted_versions"] == ["ea/v00002.pt"]
    st.write("ea", {"w": 3})
    st.adopt("sleep")
    assert st.version("ea") == 3 and st.superseded() == ["ea/v00001.pt", "ea/v00002.pt"]
    again = LoggedUnitStore(tmp_path / "u", QuickLog(tmp_path / "q.jsonl"))
    assert again.version("ea") == 3 and not list((tmp_path / "u").rglob("*.tmp"))


# ---------- 世界 ----------
def test_world_keeps_probes_apart_from_days():
    eps = WORLD["episodes"]
    key = lambda e: (tuple(sorted((tuple(e["hidden"]["A"]), tuple(e["hidden"]["B"])))), e["hidden"]["world"])
    days = [e for e in eps if e["split"].startswith("day")]
    probe_old = {key(e) for e in eps if e["split"] == "probe_old"}
    probe_new = {key(e)[0] for e in eps if e["split"] == "probe_new_package"}
    assert not probe_old & {key(e) for e in days}
    assert not probe_new & {key(e)[0] for e in days}
    new = set(WORLD["new_packages"])
    for e in days:
        pk = {ev[1] for ch in e["chains"] if ch["kind"] == "say" for ev in ch["events"]}
        if e["day"] < WS.new_package_day:
            assert not pk & new
        assert (e["genre"] == 1) == e["change"].startswith("new_genre")
        assert not e["change"].startswith("new_genre") or e["day"] >= WS.new_genre_day
    assert len(days) == WS.days * WS.questions_per_day


def test_every_episode_follows_the_t4_rule_and_record_dup_keeps_the_earlier_event():
    dups = 0
    for e in WORLD["episodes"]:
        h = e["hidden"]
        assert resolve_t4(e) == (tuple(h["A"]), tuple(h["B"]), h["world"])
        assert e["chains"][h["a_chain"]]["events"][h["a_event"]][1:] == list(h["A"])
        assert e["chains"][h["b_chain"]]["events"][h["b_event"]][1:] == list(h["B"])
        if e["change"] == "new_genre_dup":
            dups += 1
            _, ra, _, rb = e["query"]
            assert h["needs_ea"]
            for side, rel, flag in (("a", ra, h["dup_x"]), ("b", rb, h["dup_y"])):
                hits = [i for i, ev in enumerate(e["chains"][h[f"{side}_chain"]]["events"]) if ev[0] == rel]
                assert len(hits) == (2 if flag else 1) and hits[0] == h[f"{side}_event"]
    assert dups >= WS.probe_size


# ---------- CA 指引 EA ----------
def _pair(tmp_path, train):
    args = dict(two_way=True, seed=0, epochs_per_phase=1, batch_size=128, lr={"ka": 3e-3, "ea": 1e-3, "ca": 1e-3},
                budgets={"ka": 1 << 26, "ea": 1 << 30, "ca": 1 << 30})
    store = UnitStore(tmp_path / "u")
    return GuidedSpiral(CFG, store, train, guided=False, **args), GuidedSpiral(CFG, store, train, guided=True, **args)


def test_guided_ea_starts_exactly_like_the_blind_ea(tmp_path):
    b, diag = encode(WORLD, "probe_old")
    blind, guided = _pair(tmp_path, b)
    blind.run_round("t", 1, torch.arange(len(b.ids)), list(range(CFG.n_packages)), True, True)
    x, y = blind.predict(b, diag), guided.predict(b, diag)
    assert torch.equal(x["logit"], y["logit"]) and torch.equal(x["ea_arg"], y["ea_arg"])
    guided.store.write("ea", {"model": EAUnit(CFG).state_dict(), "opt": {"from": "t3"}})        # T3 存下来的 EA 没有 guide
    module, opt = guided._load_module("ea")
    assert isinstance(module, GuidedEA) and opt is None        # 旧版的优化器状态对不上新参数，重新开始
    assert float(module.guide.weight.abs().sum()) == 0.0


def test_trying_candidates_picks_the_event_that_makes_the_answer_right(tmp_path):
    """用一个假的比较头：答案只看 A 的第 0 维是不是正数。链上两个候选，只有一个让答案对。"""
    b, _ = encode(WORLD, "probe_old")
    _, guided = _pair(tmp_path, b)
    sub = take(b, torch.arange(1))
    C, L, k = CFG.n_chains, CFG.chain_len, CFG.k
    sub.rel_a = torch.zeros(1, C, L)
    sub.rel_a[0, 2, 0] = sub.rel_a[0, 2, 1] = 1.0              # 第 2 条链上有两个候选
    sub.rel_b = torch.zeros(1, C, L)
    sub.rel_b[0, 3, 0] = 1.0                                   # B 只有一个候选，不该产生目标
    sub.ev_pkg = torch.zeros(1, C, L, dtype=torch.long)
    sub.ev_mem = torch.zeros(1, C, L, dtype=torch.long)
    sub.ev_mem[0, 2, 1] = 1
    ct = torch.zeros(CFG.n_packages, CFG.n_members, k)
    ct[0, 0, 0], ct[0, 1, 0] = -1.0, 1.0                       # 位置 0 的答案是 0，位置 1 的答案是 1
    sub.labels = torch.ones(1)                                 # 反馈说答案是 1

    class FakeCA:
        @staticmethod
        def compare_logit(c_a, c_b, premise):
            return c_a[:, 0]
    sel = torch.zeros(1, 3, C + 1)
    sel[0, 0, 2] = sel[0, 1, 3] = sel[0, 2, 0] = 1.0
    out = guided.try_candidates(FakeCA, sub, ct, torch.zeros(1, C, k), torch.zeros(1, C, k), sel)
    chain, target, use = out["a"]
    assert int(chain[0]) == 2 and int(target[0]) == 1 and bool(use[0])
    assert not bool(out["b"][2][0])
    sub.labels = torch.zeros(1)                                # 反馈反过来，目标也反过来
    assert int(guided.try_candidates(FakeCA, sub, ct, torch.zeros(1, C, k), torch.zeros(1, C, k), sel)["a"][1][0]) == 0


def test_sieve_handles_a_batch_with_nothing_to_sieve(tmp_path):
    b, _ = encode(WORLD, "probe_old")
    _, guided = _pair(tmp_path, b)
    sv = guided.sieve(torch.arange(0))
    assert sv["w_a"].shape == (0, CFG.n_chains, CFG.chain_len) and len(sv["owner_a"]) == 0


def test_only_the_guided_ea_can_learn_a_rule_that_depends_on_genre(tmp_path):
    """契约检查：对话以后一次为准，档案以前一次为准。EA 看不到体裁时学不了，收到 CA 的状态才学得了。"""
    b, _ = encode(WORLD, "probe_old")
    _, guided = _pair(tmp_path, b)
    n, L = 256, CFG.chain_len
    rel = torch.zeros(n, L)
    rel[:, 0] = rel[:, 1] = 1.0
    valid = torch.ones(n, L)
    sub = take(b, torch.arange(n) % len(b.ids))
    sub.genre = torch.arange(n) % 2
    g = ca_states(guided._frozen("ca"), sub).detach()[:, 0]
    want = 1 - sub.genre                                        # 体裁 0 选第 1 个（后一次），体裁 1 选第 0 个
    res = {}
    for name, net, args in (("blind", EAUnit(CFG), (rel, valid)), ("guided", GuidedEA(CFG), (rel, valid, g))):
        opt = torch.optim.Adam(net.parameters(), lr=0.01)
        for _ in range(150):
            loss = torch.nn.functional.nll_loss(net(*args).clamp_min(1e-9).log(), want)
            opt.zero_grad()
            loss.backward()
            opt.step()
        res[name] = float((net(*args).argmax(-1) == want).float().mean())
    assert res["blind"] <= 0.55 and res["guided"] >= 0.95, res


def test_experience_labels_come_from_feedback_and_match_truth(tmp_path):
    life = _life(tmp_path)
    life.seed_units(None, None)
    b, _ = life._day_batch(1)
    qids = b.ids[:16]
    life.awake(1, qids, Pool("awake", SMALL["pools"]["awake"], life.log, 1))
    exp = life._experience(qids)
    assert exp.labels.tolist() == [float(life.episodes[q]["label"]) for q in qids]


# ---------- 存活循环 ----------
@pytest.mark.parametrize("arm", ["frozen", "survive", "survive_blind", "full_repair"])
def test_life_runs_two_days(tmp_path, arm):
    life = _life(tmp_path, arm)
    life.seed_units(None, None)
    days = life.live(2)
    assert [m["day"] for m in days] == [1, 2] and all(m["unanswered"] == 0 for m in days)
    states = {r["state"] for r in life.log.of_kind("fsm")}
    if arm == "frozen":
        assert "sleep" not in states and not life.log.of_kind("unit_write")
    else:
        assert "sleep" in states and life.log.of_kind("sleep_end")
    assert life.long.missing() == {"no_description": [], "no_index": []}
    once = [q for r in life.log.of_kind("call_end") if r["status"] == "done" for q in r["qids"]]
    assert len(once) == len(set(once)) == 2 * WS.questions_per_day


def test_local_scope_means_packages_met_after_birth(tmp_path):
    life = _life(tmp_path)
    life.seed_units(None, None)
    new = WORLD["new_packages"][0]
    day2 = [e["id"] for e in WORLD["episodes"] if e["split"] == "day2" and e["change"] == "new_package"]
    b, _ = encode_ids(WORLD, day2)
    sp = life.spiral(b)
    life.store.write(f"ka{new:04d}", {"params": {}, "opt": {}})   # 清醒小修碰过一次，也还算局部
    assert life._scope(("KA_local",), sp, torch.arange(len(day2)))["ka_packages"] == [new]
    old = [e["id"] for e in WORLD["episodes"] if e["split"] == "day1"]
    b, _ = encode_ids(WORLD, old)
    assert life._scope(("KA_local",), life.spiral(b), torch.arange(len(old)))["ka_packages"] == []


def test_self_check_groups_use_only_what_is_visible(tmp_path):
    life = _life(tmp_path)
    new = WORLD["new_packages"][0]
    day2 = [e for e in WORLD["episodes"] if e["split"] == "day2"]
    fresh = next(e for e in day2 if e["change"] == "new_package" and new in (e["hidden"]["A"][0], e["hidden"]["B"][0]))
    genre = next(e for e in day2 if e["change"] == "new_genre_dup")
    old = next(e for e in WORLD["episodes"] if e["split"] == "day1")
    assert life._group(fresh["id"]) == "genre0+new_package"
    assert life._group(genre["id"]) == "genre1"
    assert life._group(old["id"]) == "genre0"


def test_self_check_is_fixed_by_question_id_and_never_trained(tmp_path):
    life = _life(tmp_path)
    life.seed_units(None, None)
    life.live(1)
    rec = life.log.of_kind("sleep_start")[0]
    assert rec["learn"] > 0 and rec["check"] > 0 and rec["old_check"] == len(life.past_check) > 0
    lived = list(life.feedback())
    assert 0 < sum(map(life._is_check, lived)) < len(lived)
    assert all(life._is_check(q) == (int(q.split("-")[1]) % life.conf.self_check_every == 0) for q in lived)


@pytest.mark.parametrize("scores,status,adopted,repairs", [
    ([(0.95, 0.95)], "already_enough", None, 0),                # 一开始就够用：不修
    # 这里材料里没有出生以后才遇到的包，所以梯子有 4 级：CA、EA、CA+EA、全部
    ([(0.5, 0.9)] + [(0.5, 0.9)] * 4, "nothing_kept", None, 4),  # 哪一级都没变好：什么都不留
    ([(0.5, 0.9)] + [(0.9, 0.5)] * 4, "nothing_kept", None, 4),  # 新题好了但旧本领坏了：也不留
    ([(0.5, 0.9), (0.6, 0.9), (0.7, 0.9), (0.6, 0.9), (0.6, 0.9)], "improved_kept", "EA", 4),   # 留变好最多的一级
    ([(0.5, 0.9), (0.6, 0.9), (0.89, 0.9)], "enough", "EA", 2),  # 够用就停，后面几级不再试
])
def test_ladder_only_keeps_a_step_that_really_helps(tmp_path, scores, status, adopted, repairs):
    life = _life(tmp_path, margin=0.02)
    life.seed_units(None, None)
    b, _ = life._day_batch(1)
    sp = life.spiral(b)
    calls = []

    def fake_repair(tag, new, old, **kw):
        calls.append(tag)
        life.store.write("ca", {"step": len(calls)})
    sp.repair = fake_repair
    it = iter(scores)

    def check():
        new, old = next(it)
        return {"new": new, "old": old}
    base = dict(life.store.adopted)
    res = life._ladder(sp, 1, torch.arange(8), torch.arange(0), check)
    assert res["status"] == status and res["adopted"] == adopted and len(calls) == repairs
    if adopted is None:
        assert life.store.snapshot() == base                    # 回到上次采用的版本


def test_awake_fix_only_writes_never_trained_ka(tmp_path):
    life = _life(tmp_path)
    life.seed_units(None, None)
    life.live(2)
    fixes = life.log.of_kind("adopt")
    fix = [r for r in fixes if r["reason"] == "awake_fix"]
    assert fix and set(fix[0]["ka_packages"]) <= set(range(CFG.n_packages))


# ---------- 可选进程集成：只让本测试创建的子进程模拟断电 ----------
def _test_cpu_affinity():
    """Use at most one CPU from this process's allowed set when affinity is supported."""
    try:
        return sorted(psutil.Process().cpu_affinity())[:1]
    except (AttributeError, NotImplementedError, psutil.Error):
        return []


def _conf(tmp_path):
    conf = {"world": {k: v for k, v in WS.__dict__.items()}, "model_size": "small", "arm": "survive", "seed": 0,
            "days": 2, "life": {k: v for k, v in SMALL.items()}, "fsm": {}, "start": None, "evaluate": False,
            "resources": {"device": "cpu", "threads": 1, "cpu_affinity": _test_cpu_affinity()}}
    p = tmp_path / "conf.json"
    p.write_text(json.dumps(conf), encoding="utf-8")
    return p


def _run(conf, out, crash=None, nth=1):
    if not T4_RUNNER.is_file():
        pytest.skip("Optional process integration requires experiments/t4_survival_20261103/live_t4.py")
    env = dict(os.environ)
    env.pop("T4_CRASH_AT", None)
    env.pop("T4_CRASH_NTH", None)
    env.update({"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    if crash:
        env.update({"T4_CRASH_AT": crash, "T4_CRASH_NTH": str(nth)})
    return subprocess.run([sys.executable, "-B", str(T4_RUNNER), str(conf), str(out)], env=env,
                          cwd=out.parent, capture_output=True, text=True, timeout=900)


@pytest.mark.process_integration
@pytest.mark.parametrize("point,nth", [("after_call_start", 2), ("inside_answer", 3), ("after_call_end", 2),
                                       ("sleep_before_adopt", 1), ("unit_tmp_written", 1), ("before_long_commit", 1)])
def test_hard_kill_then_restart(tmp_path, point, nth):
    conf, out = _conf(tmp_path), tmp_path / "life"
    first = _run(conf, out, point, nth)
    assert first.returncode == 86, first.stderr[-2000:]
    before = (out / "quick.jsonl").read_text(encoding="utf-8").splitlines()
    second = _run(conf, out)
    assert second.returncode == 0, second.stderr[-2000:]
    after = (out / "quick.jsonl").read_text(encoding="utf-8").splitlines()
    assert after[:len(before)] == before                        # 断电以前保存成功的记录一条不少、一字不改
    recs = [json.loads(x) for x in after]
    done = [q for r in recs if r["kind"] == "call_end" and r["status"] == "done" for q in r["qids"]]
    assert len(done) == len(set(done)) == 2 * WS.questions_per_day      # 每道题恰好答完一次：不丢、不重复执行
    summ = [r for r in recs if r["kind"] == "recovery_summary"][-1]     # 重启那一次的恢复
    if point in ("after_call_start", "inside_answer"):
        assert summ["lost_calls"]
    if point == "after_call_end":
        assert summ["late_reports"] and not summ["lost_calls"]
    if point == "sleep_before_adopt":
        assert any(r["kind"] == "sleep_interrupted" and "断电" in r["reason"] for r in recs)
        assert summ["leftovers"]["unadopted_versions"]
    if point == "unit_tmp_written":
        assert summ["leftovers"]["tmp_files"]
    used = {}
    for r in recs:                                              # 每份池子的累计消耗只增不减：重启没有重置预算
        if r["kind"] == "pool":
            k = (r["pool"], r["cycle"])
            assert all(r["used"][x] >= used.get(k, {}).get(x, 0.0) - 1e-9 for x in r["used"])
            used[k] = r["used"]
    ls = LongStore(out / "long.sqlite")
    assert ls.count() == ls.cursor() and ls.missing() == {"no_description": [], "no_index": []}
