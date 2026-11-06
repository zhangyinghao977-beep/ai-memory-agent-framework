"""学习材料库、记忆的遗忘与可达性、整库备份与完整性检查（2026-10-28 新增）。"""
import pytest

from _helpers import COMPUTATION, cache_with, package, source
from empirical_core.calls import CandidateInput, Decision
from empirical_core.event_ast import NodeKind, bound
from empirical_core.experience import SourceType
from empirical_core.integrity import check_integrity, table_counts
from empirical_core.learning_store import LearningMaterialStore
from empirical_core.store import Store

FORMATION = {"method_id": "manual_v0", "description": "人工整理；拆解学习算法待定"}
WEIGHTS = {"kind": "weights", "sha256": "ab" * 32}


def _obs(experiences, text):
    return experiences.record(chain_id="m", source_type=SourceType.OBSERVATION, content=text, origin="self")


# ---------- 学习材料库（v0.16） ----------

def test_learning_materials_are_references_and_training_is_a_separate_receipt(store, memory, experiences, registry):
    lm = LearningMaterialStore(store)
    said = experiences.record(chain_id="m", source_type=SourceType.EXTERNAL_STATEMENT, content="有人说苹果都是甜的", origin="chat")
    mid = memory.form(content="有人说苹果都是甜的", from_experience_ids=[said], formation=FORMATION, reason="x")
    item = lm.add("memory", mid, "学习“甜”的表述方式", "用户同意拿来学")
    assert lm.trainings_using(item) == []                       # 收录 ≠ 已训练
    assert experiences.verification(said).value == "UNVERIFIED"  # 收录 ≠ 证实
    with pytest.raises(ValueError):
        lm.add("memory", 999, "x", "x")
    with pytest.raises(ValueError):
        lm.record_training(computation_id="ka_stub", parameter_version={"kind": "none"}, item_ids=[item], purpose="x")
    tid = lm.record_training(computation_id="ka_stub", parameter_version=WEIGHTS, item_ids=[item], purpose="第一次训练")
    assert lm.trainings_using(item) == [tid] and lm.training(tid)["items"] == [item]

    # 参数版本可以一路回查到训练记录；对不上就拒绝。
    package(registry, experiences, "p", ["a", "b"])
    good = dict(COMPUTATION, parameter_version=dict(WEIGHTS, training_id=tid))
    registry.register_package("p2", "p2", [__import__("empirical_core.registry", fromlist=["MemberSpec"]).MemberSpec(
        registry.add_raw("c"))], good, [source(experiences)], "x")
    bad = dict(COMPUTATION, parameter_version={"kind": "weights", "sha256": "cd" * 32, "training_id": tid})
    with pytest.raises(ValueError, match="不一致"):
        registry.register_package("p3", "p3", [__import__("empirical_core.registry", fromlist=["MemberSpec"]).MemberSpec(
            registry.add_raw("d"))], bad, [source(experiences)], "x")


# ---------- 遗忘与可达性（v0.17：不可篡改不等于不可遗忘） ----------

def test_forgetting_changes_reachability_not_content(store, memory, experiences):
    lm = LearningMaterialStore(store)
    m = memory.form(content="旧住址是北岸路 3 号", from_experience_ids=[_obs(experiences, "搬家前")],
                    formation=FORMATION, reason="x")
    keep = memory.form(content="喜欢木版画", from_experience_ids=[_obs(experiences, "聊天")], formation=FORMATION, reason="x")
    ask = experiences.record(chain_id="m", source_type=SourceType.EXTERNAL_STATEMENT, content="请忘掉旧住址", origin="user")
    with pytest.raises(ValueError):
        memory.forget(m, [], "没有依据")
    memory.forget(m, [ask], "用户要求")
    assert not memory.reachable(m) and memory.index("time") == [keep]
    assert memory.index("time", include_forgotten=True) == [m, keep]
    assert memory.get(m).content == "旧住址是北岸路 3 号"   # 内容没被改写；引用仍能解析
    for action in (lambda: memory.recall(m, chain_id="x", origin="self"),
                   lambda: memory.revise(m, content="改", basis_experience_ids=[ask], formation=FORMATION, reason="x"),
                   lambda: lm.add("memory", m, "x", "x")):
        with pytest.raises(ValueError, match="遗忘"):
            action()
    memory.restore(m, [experiences.record(chain_id="m", source_type=SourceType.EXTERNAL_STATEMENT,
                                          content="还是记着吧", origin="user")], "用户改主意")
    assert memory.reachable(m) and memory.index("time") == [m, keep]


# ---------- 联合状态恢复（最小检查） ----------

def _build_state(store, experiences, registry, memory, valve, calls, structures, occurrences):
    pv = package(registry, experiences, "fruit", ["苹果A", "梨B"])
    cache = cache_with(valve, ("fruit", pv.version))
    calls.record_call(cache_id=cache, chain_id="c", package_id="fruit", purpose="p", context={},
                      inputs={"context": "x"}, origin="model", candidates=[CandidateInput(0, 0.8, Decision.SELECTED)])
    seen = _obs(experiences, "吃了苹果 A")
    memory.form(content="苹果 A 甜", from_experience_ids=[seen], formation=FORMATION, reason="x",
                bindings={"对象": {"kind": "material", "id": registry.add_raw("苹果A")}})
    structures.define("eat", NodeKind.OPERATION, "吃", slots={"对象": {"ref_kinds": ["material"]}},
                      basis_ids=[seen], reason="x")
    occurrences.occur("eat", cache_id=cache, experience_id=seen,
                      bindings={"对象": bound({"kind": "material", "id": registry.add_raw("苹果A")})})
    LearningMaterialStore(store).add("experience", seen, "学习", "x")


def test_backup_restores_a_consistent_joint_state(store, experiences, registry, memory, valve, calls, structures,
                                                  occurrences, tmp_path):
    _build_state(store, experiences, registry, memory, valve, calls, structures, occurrences)
    assert check_integrity(store)["ok"]
    dest = str(tmp_path / "backup.sqlite3")
    store.backup(dest)
    restored = Store(dest, readonly=True)
    try:
        report = check_integrity(restored)
        assert report["ok"], report["problems"]
        assert table_counts(restored) == table_counts(store)
        assert "不含神经网络权重" in report["boundary"]
    finally:
        restored.close()


def test_integrity_check_finds_broken_references(store, experiences, registry, memory, valve, calls, structures,
                                                 occurrences, tmp_path):
    _build_state(store, experiences, registry, memory, valve, calls, structures, occurrences)
    dest = str(tmp_path / "broken.sqlite3")
    store.backup(dest)
    broken = Store(dest)
    try:
        broken.conn.execute("PRAGMA foreign_keys = OFF")
        broken.conn.execute("UPDATE memory_items SET bindings_json = ?",
                            ('{"对象": {"kind": "material", "id": "raw:不存在"}}',))
        broken.conn.execute("UPDATE calls SET cache_log_mark = 999")
        broken.conn.execute("DELETE FROM experiences WHERE experience_id = (SELECT MAX(experience_id) FROM experiences)")
        broken.conn.commit()
        report = check_integrity(broken)
        assert not report["ok"]
        text = "\n".join(report["problems"])
        assert "记忆" in text and "可见视图" in text and "外键" in text
    finally:
        broken.close()
