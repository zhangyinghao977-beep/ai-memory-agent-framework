"""T1 的共用输入、对照模型、计时工具与架构登记（2026-10-28）。只做前向和结构检查，没有任何优化器步骤。"""
import torch

from empirical_core.integrity import check_integrity
from empirical_core.registry import UNKNOWN
from empirical_core.t1.controls import LinearPriorControl, MLPControl, TransformerControl, count_params, match_size
from empirical_core.t1.features import encode, flat_features, registered_offsets, token_features
from empirical_core.t1.register import STORY, package_id, register_t1
from empirical_core.t1.task import WORLDS, build_t1, resolve
from empirical_core.timing import SegmentTimer, environment, time_call
from empirical_core.valve import MemoryValve
from empirical_core.experience import ExperienceLog
from empirical_core.registry import PackageRegistry

torch.set_num_threads(2)
DATA = build_t1()
SPEC = DATA["spec"]
P, M, L = SPEC["n_packages"], SPEC["n_members"], SPEC["history_len"]


def test_features_carry_the_same_information_and_no_hidden_values():
    offsets = registered_offsets(DATA)
    a = encode(DATA, "test", offsets)
    b = encode(DATA, "test", None)
    n = sum(ep["split"] == "test" for ep in DATA["episodes"])
    assert a.rel_match.shape == (n, L, 2) and a.package.shape == (n, L) and a.labels.shape == (n,)
    assert torch.equal(a.rel_match, b.rel_match) and torch.equal(a.package, b.package)
    assert b.offset_known.sum() == 0 and a.offset_known.sum() == n * L         # T1-b 不给偏差，T1-a 全给
    assert all(offsets[(p, 0)] == 0 for p in range(P))                         # 参考成员偏差为 0：包的参考水平不在输入里
    assert torch.equal(a.premise, (a.world == WORLDS.index("story")).float())
    ep0 = next(ep for ep in DATA["episodes"] if ep["split"] == "test")
    ra, rb = ep0["query"]
    pick = a.rel_match[0].argmax(dim=0).tolist()
    assert [tuple(ep0["history"][j][1:]) for j in pick] == list(resolve(ep0))
    assert flat_features(a, P, M).shape == (n, L * (2 + P + M + 2) + 3)
    assert token_features(a, P, M).shape[:2] == (n, L + 1)


def test_controls_run_forward_and_report_parameter_matching():
    batch = encode(DATA, "dev", registered_offsets(DATA))
    mlp = MLPControl(P, M, L, hidden=4)
    tfm = TransformerControl(P, M, L, d_model=8)
    for model in (mlp, tfm, LinearPriorControl(P, M)):
        out = model(batch)
        assert out.shape == (len(batch.ids),) and torch.isfinite(out).all()
    tiny = match_size(lambda h: MLPControl(P, M, L, h), range(1, 65), target=52)
    assert tiny["size"] == 1 and not tiny["within_tolerance"]   # 目标太小时，最小的 MLP 也超过 ±10%，如实报告
    tenfold = match_size(lambda d: TransformerControl(P, M, L, d), range(2, 65), target=520)
    assert tenfold["params"] == count_params(TransformerControl(P, M, L, tenfold["size"]))


def test_linear_prior_can_express_the_optimum():
    """构造性检查（不是训练结果）：把隐藏数值直接填进 D′，它能在 TEST 上全对——说明这个对照族能表达最优解。"""
    model = LinearPriorControl(P, M)
    values = {tuple(map(int, k.split(","))): v for k, v in DATA["hidden_values"].items()}
    with torch.no_grad():
        for (p, m), v in values.items():
            model.value[p * M + m] = v
        model.direction.copy_(torch.tensor([1.0, -1.0]))
    batch = encode(DATA, "test")
    pred = (model(batch) > 0).float()
    assert torch.equal(pred, batch.labels)


def test_timing_tools_record_segments_and_environment():
    timer = SegmentTimer()
    for _ in range(4):
        with timer.segment("cpu_prep"):
            sum(range(1000))
        with timer.segment("neural"):
            torch.ones(8, 8) @ torch.ones(8, 8)
    s = timer.summary(warmup=1)
    assert set(s) == {"cpu_prep", "neural"} and s["neural"]["n"] == 3
    assert time_call(lambda: None, repeats=3)["n"] == 3
    env = environment()
    assert env["torch_threads"] >= 1 and "platform" in env


def test_register_t1_into_the_architecture(store):
    info = register_t1(store, DATA, variant="a", episode_limit=30)
    log = ExperienceLog(store)
    reg = PackageRegistry(store, log)
    valve = MemoryValve(store, log)
    offsets = registered_offsets(DATA)
    pv = reg.latest(package_id(3))
    assert pv.members[0].difference == {"kind": "self_reference"}
    assert pv.members[2].difference == {"kind": "registered_offset", "scale": "T1 数值", "value": offsets[(3, 2)]}
    assert all(m.value == UNKNOWN for m in pv.members)                        # 数值要学，不直接告诉模型
    assert reg.round_info(info["round_id"])["products"] == sorted(package_id(p) for p in range(P))
    for ep in DATA["episodes"][:30]:
        occ = info["occurrences"][ep["id"]]
        cache = info["caches"][ep["world"]]
        active = [p.content for p in valve.active_premises(cache, occ)]
        assert active == (["小的赢"] if ep["world"] == "story" else [])
    assert valve.worlds_of("package", package_id(0))[0] == {"physical"}
    assert STORY in valve.cache_worlds(info["caches"]["story"])
    assert check_integrity(store)["ok"]


def test_register_t1_b_keeps_offsets_unknown(store):
    register_t1(store, DATA, variant="b", episode_limit=0)
    reg = PackageRegistry(store, ExperienceLog(store))
    assert all(m.difference == UNKNOWN for m in reg.latest(package_id(0)).members[1:])
