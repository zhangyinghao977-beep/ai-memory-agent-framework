"""经验／溯源记录（原 test_memory.py，2026-10-27 按 v0.14 改名并补充）。"""
import pytest

from _helpers import package
from empirical_core.experience import PackageUse, Relation, SourceType, Verification
from empirical_core.store import Store


def test_same_content_shared_but_occurrences_kept_apart(experiences, store):
    a = experiences.record(chain_id="c1", source_type=SourceType.EXTERNAL_STATEMENT, content="水在零度结冰", origin="doc:a")
    b = experiences.record(chain_id="c2", source_type=SourceType.EXTERNAL_STATEMENT, content="水在零度结冰", origin="doc:b")
    assert a != b
    assert experiences.get(a).origin == "doc:a" and experiences.get(b).origin == "doc:b"
    assert store.conn.execute("SELECT COUNT(*) FROM contents").fetchone()[0] == 1


def test_statement_is_not_verified_by_default(experiences):
    ev = experiences.record(chain_id="c", source_type=SourceType.EXTERNAL_STATEMENT, content="某人说下雨了", origin="chat")
    assert experiences.verification(ev) is Verification.UNVERIFIED


def test_only_observation_or_execution_can_be_evidence(experiences):
    claim = experiences.record(chain_id="c", source_type=SourceType.CANDIDATE_INFERENCE, content="明天会下雨", origin="model")
    other_claim = experiences.record(chain_id="c", source_type=SourceType.EXTERNAL_STATEMENT, content="天气预报说会下雨", origin="tv")
    for bad in (other_claim,):
        with pytest.raises(ValueError):
            experiences.verify(claim, Verification.SUPPORTED, [bad], "不是证据")
    with pytest.raises(ValueError):
        experiences.verify(claim, Verification.SUPPORTED, [claim], "自证")
    with pytest.raises(ValueError):
        experiences.verify(claim, Verification.SUPPORTED, [], "没有证据")

    seen = experiences.record(chain_id="c", source_type=SourceType.OBSERVATION, content="观察到地面湿了", origin="sensor")
    experiences.verify(claim, Verification.SUPPORTED, [seen], "观察支持")
    assert experiences.verification(claim) is Verification.SUPPORTED


def test_tool_description_and_plan_are_not_evidence(experiences):
    """v0.14：区分操作描述、尝试计划和实际执行；“计划清洗”不等于“已经洗净”。"""
    claim = experiences.record(chain_id="apple", source_type=SourceType.CANDIDATE_INFERENCE, content="苹果 A 已洗净", origin="model")
    desc = experiences.record(chain_id="apple", source_type=SourceType.TOOL_DESCRIPTION, content="清洗：用水冲洗", origin="manual")
    plan = experiences.record(chain_id="apple", source_type=SourceType.TOOL_PLAN, content="计划清洗苹果 A", origin="planner")
    for bad in (desc, plan):
        with pytest.raises(ValueError):
            experiences.verify(claim, Verification.SUPPORTED, [bad], "计划或描述不是证据")
    done = experiences.record(chain_id="apple", source_type=SourceType.TOOL_EXECUTION, content="已冲洗苹果 A 30 秒",
                              origin="tool", links=[(plan, Relation.DERIVED_FROM)])
    experiences.verify(claim, Verification.SUPPORTED, [done], "实际执行")
    assert experiences.verification(claim) is Verification.SUPPORTED


def test_recall_and_computation_need_their_own_entry(experiences):
    with pytest.raises(ValueError):
        experiences.record(chain_id="c", source_type=SourceType.RECALL, content="想起来了", origin="self")
    with pytest.raises(ValueError):
        experiences.record(chain_id="c", source_type=SourceType.COMPUTATION, content="算了一次", origin="model")


def test_verification_history_is_append_only(experiences):
    claim = experiences.record(chain_id="c", source_type=SourceType.CANDIDATE_INFERENCE, content="x=3", origin="model")
    run1 = experiences.record(chain_id="c", source_type=SourceType.TOOL_EXECUTION, content="运行得到 x=3", origin="tool")
    run2 = experiences.record(chain_id="c", source_type=SourceType.TOOL_EXECUTION, content="复测得到 x=4", origin="tool")
    experiences.verify(claim, Verification.SUPPORTED, [run1], "第一次")
    experiences.verify(claim, Verification.CONTRADICTED, [run2], "复测不符")
    assert experiences.verification(claim) is Verification.CONTRADICTED
    assert [h["status"] for h in experiences.verification_history(claim)] == ["SUPPORTED", "CONTRADICTED"]


def test_links_only_point_to_existing_earlier_records(experiences):
    raw = experiences.record(chain_id="c", source_type=SourceType.EXTERNAL_STATEMENT, content="原文", origin="doc")
    interp = experiences.record(
        chain_id="c", source_type=SourceType.CANDIDATE_INFERENCE, content="解释", origin="model",
        links=[(raw, Relation.INTERPRETS)],
    )
    assert experiences.links_from(interp) == [(raw, Relation.INTERPRETS)]
    assert experiences.links_to(raw, Relation.INTERPRETS) == [(interp, Relation.INTERPRETS)]
    with pytest.raises(ValueError):
        experiences.record(chain_id="c", source_type=SourceType.CANDIDATE_INFERENCE, content="引用未来", origin="model",
                           links=[(interp + 100, Relation.INPUT)])


def test_practice_can_reference_the_package_version_it_applied(experiences, registry):
    """A1：知识 → 经验。实践记录能指向用到的知识包版本。"""
    package(registry, experiences, "wash", ["清洗", "冲洗", "擦拭"])
    ev = experiences.record(chain_id="apple", source_type=SourceType.TOOL_EXECUTION, content="按清洗包冲洗了苹果 A",
                            origin="tool", package_refs=[("wash", 1, PackageUse.APPLIED)])
    assert experiences.package_refs(ev) == [("wash", 1, PackageUse.APPLIED)]
    assert experiences.experiences_using("wash") == [ev]
    with pytest.raises(ValueError):
        experiences.record(chain_id="apple", source_type=SourceType.TOOL_EXECUTION, content="x", origin="tool",
                           package_refs=[("wash", 9, PackageUse.APPLIED)])


def test_failed_record_leaves_nothing_behind(experiences, store):
    before = store.conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]
    with pytest.raises(ValueError):
        experiences.record(chain_id="c", source_type=SourceType.OBSERVATION, content="x", origin="o",
                           links=[(999, Relation.INPUT)])
    assert store.conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0] == before


def test_batch_commits_once_and_readonly_store_cannot_write(experiences, store):
    with store.transaction():
        for i in range(5):
            experiences.record(chain_id="batch", source_type=SourceType.OBSERVATION, content=f"obs {i}", origin="s")
    assert len(experiences.chain("batch")) == 5

    ro = Store(store.path, readonly=True)
    try:
        with pytest.raises(PermissionError):
            with ro.transaction():
                pass
        assert ro.conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0] == 5
    finally:
        ro.close()
