"""T1 受控组合任务：出题器、门禁、分层与简单基线（设计稿 T1_DESIGN.md）。不训练任何模型。"""
import json
from collections import Counter

import pytest

from empirical_core.t1 import baselines as bl
from empirical_core.t1.task import T1Spec, build_t1, label_of, resolve, visible

DATA = build_t1()


def _values(data):
    return {tuple(map(int, k.split(","))): v for k, v in data["hidden_values"].items()}


def test_same_seed_gives_the_same_task():
    assert json.dumps(build_t1(), sort_keys=True) == json.dumps(DATA, sort_keys=True)
    assert build_t1(T1Spec(seed=1))["episodes"] != DATA["episodes"]


def test_episodes_are_well_formed_and_labels_follow_the_world():
    values = _values(DATA)
    assert len(set(values.values())) == len(values)          # 没有平局
    for ep in DATA["episodes"]:
        rels = [r for r, _, _ in ep["history"]]
        assert len(rels) == len(set(rels)) == 4
        a, b = resolve(ep)                                    # 只用可见信息就能找到 A、B
        assert (a, b) == (tuple(ep["hidden"]["A"]), tuple(ep["hidden"]["B"]))
        assert ep["label"] == label_of(ep["world"], values[a], values[b])
        assert "hidden" not in visible(ep) and "label" not in visible(ep)


def test_splits_share_no_decisive_key_and_labels_are_balanced():
    keys = {s: {bl.KEY(ex.inputs) for ex in bl.examples(DATA, (s,))} for s in ("train", "dev", "test")}
    assert not keys["train"] & keys["dev"] and not keys["train"] & keys["test"] and not keys["dev"] & keys["test"]
    for split in ("train", "dev", "test"):
        labels = Counter(ep["label"] for ep in DATA["episodes"] if ep["split"] == split)
        assert 0.45 <= labels[1] / sum(labels.values()) <= 0.55


@pytest.mark.parametrize("split", ["dev", "test"])
def test_gate_passes_with_enough_new_conflicting_items(split):
    report = bl.gate(DATA, split, min_main=200)
    assert report.passed
    assert report.details["main_stratum_count"] >= 200
    assert report.details["worst_part_rule_accuracy_on_main"] <= 0.6   # 只看一部分，在冲突题上接近瞎猜


def test_world_new_items_flip_the_other_world():
    """换世界对：TRAIN 里见过同一对东西的另一个世界；两个世界的答案（按同一方向看）相反。"""
    values = _values(DATA)
    for ep in DATA["episodes"]:
        if ep["hidden"]["pair_kind"] == "world_new" and ep["split"] != "train":
            a, b = resolve(ep)
            other = "physical" if ep["world"] == "story" else "story"
            assert label_of(other, values[a], values[b]) == 1 - ep["label"]


def test_baselines_on_test():
    split = "test"
    st = bl.strata(DATA, split)
    n = len(st)
    maj = sum(bl.score(DATA, split, bl.majority(DATA)).values())
    path = bl.score(DATA, split, bl.path_reasoner(DATA))
    implied = [i for i, t in st.items() if t["path"] == "path_implied"]
    assert 0.4 <= maj / n <= 0.6
    assert all(path[i] for i in implied)                          # 路径推得出来时从不出错
    assert not any(path[i] for i, t in st.items() if t["path"] == "path_not_implied")  # 推不出来算错（悲观）
    assert Counter(t["pair"] for t in st.values())["pair_new"] > 0
    main = [i for i, t in st.items() if t["gate"] == "new_conflict"]
    for name, rule in bl.part_rules(DATA).items():
        hits = bl.score(DATA, split, rule)
        assert sum(hits[i] for i in main) / len(main) <= 0.6, name
