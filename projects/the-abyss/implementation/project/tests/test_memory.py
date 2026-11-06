"""形成后的记忆（2026-10-27 新增，名词解释 v0.14：经验 → 拆解学习 → 记忆）。"""
import pytest

from _helpers import package, source
from empirical_core.experience import SourceType, Verification
from empirical_core.memory import MemoryOrigin

FORMATION = {"method_id": "manual_v0", "description": "人工整理；拆解学习算法待定"}


def test_memory_must_come_from_experience(memory, experiences):
    with pytest.raises(ValueError):
        memory.form(content="苹果 A 是甜的", from_experience_ids=[], formation=FORMATION, reason="没有来源")
    with pytest.raises(ValueError):
        memory.form(content="苹果 A 是甜的", from_experience_ids=[999], formation=FORMATION, reason="来源不存在")
    tasted = experiences.record(chain_id="taste", source_type=SourceType.OBSERVATION, content="尝了苹果 A：甜", origin="self")
    with pytest.raises(ValueError):
        memory.form(content="苹果 A 是甜的", from_experience_ids=[tasted], formation={"method_id": "x"}, reason="方法没写清")
    mid = memory.form(content="苹果 A 是甜的", from_experience_ids=[tasted], formation=FORMATION, reason="一次品尝")
    item = memory.get(mid)
    assert item.origin is MemoryOrigin.LEARNED and item.experience_sources == [tasted]


def test_recording_an_experience_does_not_create_memory(experiences, store):
    experiences.record(chain_id="c", source_type=SourceType.EXTERNAL_STATEMENT, content="原文", origin="doc")
    assert store.conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0] == 0


def test_imagination_needs_knowledge_and_is_not_an_experience(memory, experiences, registry, store):
    package(registry, experiences, "fruit", ["苹果", "梨", "樱桃"])
    with pytest.raises(ValueError):
        memory.imagine(content="一盘水果", from_packages=[], formation=FORMATION, reason="没有知识依据")
    n_experiences = store.conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]
    mid = memory.imagine(content="想象一盘洗好的苹果和梨", from_packages=[("fruit", 1)],
                         formation={"method_id": "imagine_manual", "description": "人工构造场景"}, reason="想象力")
    item = memory.get(mid)
    assert item.origin is MemoryOrigin.IMAGINATION and item.package_sources == [("fruit", 1)]
    # 想象形成的是记忆，不新增经验；核实证据只能是经验，所以想象无法被当作证据。
    assert store.conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0] == n_experiences


def test_imagination_cannot_use_cropped_package(memory, experiences, registry):
    package(registry, experiences, "old", ["a", "b"])
    registry.crop("old", "参照含义改变", {}, [source(experiences, "复核")])
    with pytest.raises(ValueError):
        memory.imagine(content="x", from_packages=[("old", 1)], formation=FORMATION, reason="已裁剪")


def test_revision_keeps_the_original_and_links_back(memory, experiences):
    """v0.17：修订在原基础上新建承接版本，保留原版；新的相似经历是新记忆，不是修订。"""
    tasted = experiences.record(chain_id="taste", source_type=SourceType.OBSERVATION, content="周一尝了苹果 A：甜", origin="self")
    m1 = memory.form(content="周一：苹果 A 是甜的", from_experience_ids=[tasted], formation=FORMATION, reason="一次品尝")
    fix = experiences.record(chain_id="taste", source_type=SourceType.OBSERVATION, content="看日历：其实是周二尝的", origin="self")
    with pytest.raises(ValueError):
        memory.revise(m1, content="周二：苹果 A 是甜的", basis_experience_ids=[], formation=FORMATION, reason="没有依据")
    with pytest.raises(ValueError):
        memory.revise(m1, content="周一：苹果 A 是甜的", basis_experience_ids=[fix], formation=FORMATION, reason="没变化")
    m2 = memory.revise(m1, content="周二：苹果 A 是甜的", basis_experience_ids=[fix], formation=FORMATION, reason="更正时间")
    assert memory.get(m1).content == "周一：苹果 A 是甜的"  # 原版不动
    assert memory.get(m2).revises == m1 and memory.lineage(m2) == [m2, m1] and memory.revisions_of(m1) == [m2]
    assert memory.get(m2).experience_sources == [tasted, fix]  # 继承原来源，加上修订依据

    again = experiences.record(chain_id="taste", source_type=SourceType.OBSERVATION, content="周五又尝了苹果 A：甜", origin="self")
    m3 = memory.form(content="周五：苹果 A 是甜的", from_experience_ids=[again], formation=FORMATION, reason="新一次经历")
    assert memory.get(m3).revises is None and memory.revisions_of(m1) == [m2]


def test_recall_is_a_new_experience_not_an_external_fact(memory, experiences):
    tasted = experiences.record(chain_id="taste", source_type=SourceType.OBSERVATION, content="尝了苹果 A：甜", origin="self")
    mid = memory.form(content="苹果 A 是甜的", from_experience_ids=[tasted], formation=FORMATION, reason="一次品尝")
    ev = memory.recall(mid, chain_id="today", origin="self")
    assert experiences.get(ev).source_type is SourceType.RECALL
    assert memory.recalled_memory(ev) == mid
    claim = experiences.record(chain_id="today", source_type=SourceType.CANDIDATE_INFERENCE, content="今天的苹果甜", origin="model")
    with pytest.raises(ValueError):
        experiences.verify(claim, Verification.SUPPORTED, [ev], "回忆不是当前外部事实")
