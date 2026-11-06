"""T1 三档规模、模型 A 与可放大的对照模型（2026-10-28）。只做前向和一次反向检查，没有任何优化器步骤。"""
from dataclasses import asdict, replace

import torch

from empirical_core.t1 import baselines as bl
from empirical_core.t1.controls import EmbedMLPControl, EmbedTransformerControl, count_params, match_size
from empirical_core.t1.features import encode, registered_offsets
from empirical_core.t1.model_a import ModelA, config_for
from empirical_core.t1.task import PRESETS, build_t1

torch.set_num_threads(2)


def _reduced(size, n_pairs=3000):
    """大档题目用较少的对象对，测试才跑得快；对象数量、事件长度等保持原档设定。"""
    return build_t1(replace(PRESETS[size], n_pairs=n_pairs))


def test_large_task_keeps_its_shape_and_passes_the_gate():
    data = _reduced("large", n_pairs=20000)
    assert len(data["objects"]) == 256 * 16 and len(set(data["hidden_values"].values())) == 256 * 16
    assert all(len(ep["history"]) == 8 for ep in data["episodes"])
    report = bl.gate(data, "test", min_main=200)
    assert report.passed, report.details["strata_counts"]
    path = bl.score(data, "test", bl.path_reasoner(data))     # 4096 个对象，传递闭包也算得动
    assert 0 < sum(path.values()) <= len(path)


def test_gate_blocks_a_task_that_is_too_sparse():
    """4096 个对象只出 3000 对：多数对象在训练里几乎没出现，单部分规则判断不了，主要类别不够 200 题，门禁拦下。"""
    report = bl.gate(_reduced("large", n_pairs=3000), "test", min_main=200)
    assert not report.passed
    counts = report.details["strata_counts"]
    assert counts["new_undetermined"] > counts.get("new_conflict", 0)


def test_model_a_small_forward_and_backward_wiring():
    data = build_t1()
    cfg = config_for(data["spec"], "small")
    model = ModelA(cfg)
    batch = encode(data, "dev", registered_offsets(data))
    out = model(batch)
    assert out["logit"].shape == (len(batch.ids),)
    assert torch.allclose(out["select"].sum(-1), torch.ones(len(batch.ids), 2))
    assert torch.equal(model.offsets()[:, 0], torch.zeros(cfg.n_packages, cfg.k))   # 参考成员的偏差恒为 0
    loss = torch.nn.functional.binary_cross_entropy_with_logits(out["logit"], batch.labels)
    loss.backward()                                                                 # 只检查梯度能传到每个部分，不更新参数
    for name in ("member_offset", "registered_read.weight", "convert_w", "convert_b", "ea_none", "ea_ptr.weight"):
        assert dict(model.named_parameters())[name].grad is not None, name


def test_model_a_large_size_and_forward():
    data = _reduced("large", n_pairs=600)
    cfg = config_for(data["spec"], "large")
    with torch.device("meta"):
        n = count_params(ModelA(cfg))
    assert 9_000_000 <= n <= 11_000_000                     # 与历史 v19 的 1022 万参数同一量级
    model = ModelA(cfg)
    batch = encode(data, "test", registered_offsets(data), ids=[ep["id"] for ep in data["episodes"]
                                                                if ep["split"] == "test"][:16])
    with torch.no_grad():
        out = model(batch)
    assert out["logit"].shape == (16,) and torch.isfinite(out["logit"]).all()


def test_controls_match_model_a_at_every_size():
    for size, d, layers, heads in (("small", 4, 1, 1), ("medium", 64, 3, 4), ("large", 128, 6, 4)):
        spec = asdict(PRESETS[size])
        P, M, L = spec["n_packages"], spec["n_members"], spec["history_len"]
        with torch.device("meta"):
            target = count_params(ModelA(config_for(spec, size)))
        mlp = match_size(lambda h: EmbedMLPControl(P, M, L, d, h), range(1, 4097, 1 if size == "small" else 8), target)
        tfm = match_size(lambda dm: EmbedTransformerControl(P, M, L, dm, layers, heads), range(4, 1025, 4), target)
        assert mlp["within_tolerance"] and tfm["within_tolerance"], (size, mlp, tfm)


def test_scalable_controls_forward_on_small_task():
    data = build_t1()
    batch = encode(data, "dev", registered_offsets(data))
    P, M, L = 10, 6, 4
    for model in (EmbedMLPControl(P, M, L, 4, 26), EmbedTransformerControl(P, M, L, 8, 1, 1)):
        out = model(batch)
        assert out.shape == (len(batch.ids),) and torch.isfinite(out).all()
