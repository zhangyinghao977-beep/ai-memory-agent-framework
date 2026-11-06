"""决定因素重合与单部分捷径门禁、按类别报告（测试方案 v0.1 第三、四节）。

用历史 v19 的出题规则（答案＝两段历史强度之和 > 7）做反例：该 DEV 会被这道门禁拦下；
重新设计的留出集（新组合、而且两部分意见冲突）能通过。
"""
import random
from itertools import combinations

from empirical_core.evaluation.gates import Example, decisive_factor_audit, fit_part_rules, stratify
from empirical_core.evaluation.report import compare_to_baselines, stratified_metrics


def strength(i):
    return i % 6 + 1


def answer(a, b):
    return int(a + b > 7)


def v19_split(seed=19):
    """复刻历史 v19 expanded_corpus._fixed_pair_partition；来源审查记录：v19_r10_review_20261027。"""
    groups = {0: [], 1: []}
    for pair in combinations(range(12), 2):
        a, b = strength(pair[0]), strength(pair[1])
        if a * b != (7 - a) * (7 - b):
            groups[int(a * b > (7 - a) * (7 - b))].append(pair)
    rng = random.Random(seed)
    train, dev = [], []
    for k in (0, 1):
        rng.shuffle(groups[k])
        train += groups[k][:16]
        dev += groups[k][16:20]
    return train, dev


KEY = lambda x: tuple(sorted((x["a"], x["b"])))  # 决定答案的关键值：答案只看 a＋b，所以不分先后
PARTS = {"history_1": lambda x: x["a"], "history_2": lambda x: x["b"]}


def _examples(pairs, split):
    return [Example(f"{split}{i}", split, {"a": strength(p[0]), "b": strength(p[1])},
                    answer(strength(p[0]), strength(p[1]))) for i, p in enumerate(pairs)]


def test_gate_blocks_the_v19_dev_split():
    train, dev = v19_split()
    exs = _examples(train, "train") + _examples(dev, "dev")
    report = decisive_factor_audit(exs, KEY, PARTS)
    assert not report.passed
    d = report.details
    assert d["main_stratum_count"] == 0                        # 没有一道“新组合 × 冲突”的题
    # 6/8 的关键值训练里见过；两道新组合都是两部分意见一致的题。
    assert d["strata_counts"] == {"new_agree": 2, "seen_agree": 4, "seen_conflict": 2}
    assert d["part_rule_results"]["history_2"]["all"] == {"n": 8, "correct": 8}  # 只看第二段就满分


def test_gate_passes_a_split_with_new_conflicting_combinations():
    pairs = [(a, b) for a in range(1, 7) for b in range(1, 7) if a + b != 7]
    held = {(3, 5), (1, 4), (2, 6), (1, 5), (3, 6), (2, 4), (5, 3), (4, 1), (6, 2), (5, 1), (6, 3), (4, 2)}
    train = [Example(f"t{a}{b}", "train", {"a": a, "b": b}, answer(a, b)) for a, b in pairs if (a, b) not in held]
    test = [Example(f"e{a}{b}", "test", {"a": a, "b": b}, answer(a, b)) for a, b in sorted(held)]
    report = decisive_factor_audit(train + test, KEY, PARTS, min_main=12)
    assert report.passed, report.details["worst_part_rule_accuracy_on_main"]
    assert report.details["strata_counts"] == {"new_conflict": 12}
    assert report.details["worst_part_rule_accuracy_on_main"] == 0.5


def test_part_rules_are_pessimistic_on_unseen_values():
    train = [Example("t1", "train", {"a": 1, "b": 2}, 0), Example("t2", "train", {"a": 1, "b": 6}, 1)]
    rules = fit_part_rules(train, PARTS)
    assert rules["history_1"]({"a": 1, "b": 0}) is None  # 训练里 a=1 的答案一半一半：并列，不偷算
    assert rules["history_2"]({"a": 0, "b": 9}) is None  # 没见过的值
    strata = stratify(train + [Example("e", "test", {"a": 5, "b": 2}, 0)], KEY, PARTS)
    assert strata == {"e": "new_undetermined"}


def test_stratified_metrics_report_each_stratum_separately():
    strata = {"q1": "new_conflict", "q2": "new_conflict", "q3": "seen_agree", "q4": "seen_agree"}
    model = {"q1": True, "q2": False, "q3": True, "q4": True}
    base = {"only_history_2": {"q1": True, "q2": True, "q3": True, "q4": True}}
    metrics = stratified_metrics("DEV 正确率", model, base, strata, chance=0.5, ties={"q2": True})
    names = [m["name"] for m in metrics]
    assert names == ["DEV 正确率［new_conflict］", "DEV 正确率［seen_agree］"]
    hard = metrics[0]
    assert (hard["n"], hard["model"], hard["baselines"]["only_history_2"], hard["ties"]) == (2, 1, 2, 1)
    assert compare_to_baselines(hard)["verdict"].startswith("未超过")  # 难的那一类不如捷径规则，就不能说学会了
