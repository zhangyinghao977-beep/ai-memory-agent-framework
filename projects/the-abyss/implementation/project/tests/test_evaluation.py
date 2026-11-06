import json

import pytest

from empirical_core.evaluation.baselines import (
    evaluate_ranker, lexical_ranker, majority_ranker, ngram_nn_ranker, pessimistic_rank,
)
from empirical_core.evaluation.gates import Example, input_collision_audit, shared_substrings, text_overlap_audit
from empirical_core.evaluation.plan import PlanError, freeze_plan, verify_plan
from empirical_core.evaluation.report import (
    ABOVE_CLEAR, ABOVE_OVERLAP, NOT_ABOVE, compare_to_baselines, render_report, wilson_interval,
)

PLAN = {
    "name": "toy",
    "task": "受控任务",
    "data": {"train": "sha-a", "dev": "sha-b"},
    "seed": 7,
    "metrics": [{"name": "top1", "compare_to": ["lexical", "majority"]}],
    "baselines": [{"name": "lexical"}, {"name": "majority"}],
    "ablations": [],
}


# ---------- 计划 ----------

def test_plan_requires_baselines_per_metric():
    bad = dict(PLAN, metrics=[{"name": "top1"}])
    with pytest.raises(PlanError):
        freeze_plan(bad, [], "unused")
    bad = dict(PLAN, metrics=[{"name": "top1", "compare_to": ["nn"]}])
    with pytest.raises(PlanError):
        freeze_plan(bad, [], "unused")
    with pytest.raises(PlanError):
        freeze_plan(dict(PLAN, baselines=[]), [], "unused")


def test_frozen_plan_detects_source_change_and_refuses_overwrite(tmp_path):
    src = tmp_path / "model.py"
    src.write_text("x = 1\n", encoding="utf-8")
    out = tmp_path / "PLAN.json"
    frozen = freeze_plan(PLAN, [str(src)], str(out))
    assert verify_plan(str(out))["identity"] == frozen["identity"]
    with pytest.raises(PlanError):
        freeze_plan(PLAN, [str(src)], str(out))
    src.write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(PlanError):
        verify_plan(str(out))


def test_frozen_plan_detects_edited_plan(tmp_path):
    out = tmp_path / "PLAN.json"
    freeze_plan(PLAN, [], str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    data["plan"]["seed"] = 8
    out.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlanError):
        verify_plan(str(out))


# ---------- 门禁 ----------

def test_input_collision_flags_conflicts_and_leaks():
    ex = [
        Example("t1", "train", {"ctx": [1, 2]}, "A"),
        Example("t2", "train", {"ctx": [1, 2]}, "B"),   # 同输入、不同答案
        Example("t3", "train", {"ctx": [3]}, "A"),
        Example("d1", "dev", {"ctx": [3]}, "A"),        # 训练与评测输入完全相同
        Example("d2", "dev", {"ctx": [4]}, "B"),
    ]
    rep = input_collision_audit(ex)
    assert not rep.passed
    assert rep.details["train_label_conflicts"][0]["example_ids"] == ["t1", "t2"]
    assert rep.details["train_eval_overlap"][0]["other_ids"] == ["dev:d1"]

    dist = input_collision_audit(ex[:3] + ex[4:], allow_label_distribution=True)
    assert dist.passed and dist.details["train_label_conflicts"]


def test_text_overlap_catches_paraphrase_that_5gram_misses():
    train = [("t1", "航道暗礁密布且雷达突然失灵，货轮在狂风中寸步难行", "crisis"),
             ("t2", "孩子们笑着追逐彩蝶", "joy")]
    evals = [("e1", "狂风撕碎了船帆，暗礁四伏的黑夜里指南针也失灵", "crisis")]
    rep = text_overlap_audit(train, evals, review_shared_len=2)
    assert rep.passed  # 没有完全相同，5-gram 也不高
    item = rep.details["items"][0]
    assert item["nearest_label_matches"]
    assert {"暗礁", "狂风", "失灵"} <= set(item["shared_with_same_label"])
    assert rep.details["needs_review"] == ["e1"]


def test_text_overlap_fails_on_exact_copy():
    rep = text_overlap_audit([("t", "完全一样的句子", "a")], [("e", "完全一样的句子", "a")])
    assert not rep.passed and rep.details["exact_matches"] == 1


def test_shared_substrings_are_maximal():
    assert shared_substrings("技术壁垒终于洞开", "冲破最后一道技术壁垒后") == ["技术壁垒"]


# ---------- 基线 ----------

def test_lexical_ranker_and_pessimistic_ties():
    rank = lexical_ranker({"轨道": ["astro"], "演化": ["astro", "eco"], "物种": ["eco"]})
    assert rank("物种在演化") == [("eco", 2), ("astro", 1)]
    # 只有“演化”时两包同分：悲观并列下都不算 top1
    tie = rank("演化")
    assert pessimistic_rank(tie, "eco") == 2 and pessimistic_rank(tie, "astro") == 2
    res = evaluate_ranker([("物种在演化", "eco"), ("演化", "eco"), ("无关", "eco")], rank)
    assert res == {"n": 3, "top1": 1, "top3": 2}


def test_ngram_nn_and_majority():
    nn = ngram_nn_ranker([("暗礁狂风", "crisis"), ("笑声彩蝶", "joy")])
    assert nn("狂风暗礁")[0][0] == "crisis"
    maj = majority_ranker(["a", "a", "b"])
    assert maj("任何输入") == [("a", 2), ("b", 1)]


# ---------- 报告 ----------

def test_wilson_matches_known_values():
    lo, hi = wilson_interval(5, 12)
    assert round(lo, 3) == 0.193 and round(hi, 3) == 0.680


def test_compare_verdicts():
    assert compare_to_baselines({"name": "m", "n": 12, "model": 5, "baselines": {"nn": 8}})["verdict"] == NOT_ABOVE
    assert compare_to_baselines({"name": "m", "n": 12, "model": 9, "baselines": {"nn": 8}})["verdict"] == ABOVE_OVERLAP
    assert compare_to_baselines({"name": "m", "n": 200, "model": 180, "baselines": {"nn": 80}})["verdict"] == ABOVE_CLEAR


def test_report_conclusion_follows_results_not_fixed_text():
    receipt = {
        "plan_identity": "abc",
        "run_status": "completed",
        "gates": [{"name": "input_collision", "passed": True}],
        "contract_checks": [{"name": "首成员零偏差", "passed": True, "note": "按构造成立"}],
        "metrics": [{"name": "top1", "n": 12, "model": 5, "baselines": {"lexical": 8}}],
        "limitations": ["样本只有 12 题"],
    }
    text = render_report(receipt, "测试")
    assert "不能说“学会了”" in text
    assert "契约检查（按构造成立，不计入实验结果）" in text

    receipt["gates"][0]["passed"] = False
    assert "门禁未全部通过" in render_report(receipt, "测试")
