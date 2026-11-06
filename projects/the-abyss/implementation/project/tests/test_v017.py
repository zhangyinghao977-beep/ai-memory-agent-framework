"""名词解释 v0.15–v0.17 新增要求（2026-10-28）：记忆的适用范围／条件／绑定、引用方向、默认索引；时间与可见视图的可回溯。"""
import pytest

from _helpers import cache_with, package
from empirical_core.calls import CandidateInput, Decision
from empirical_core.experience import SourceType
from empirical_core.valve import PHYSICAL, ItemKind

FORMATION = {"method_id": "manual_v0", "description": "人工整理；拆解学习算法待定"}


def _obs(experiences, text):
    return experiences.record(chain_id="m", source_type=SourceType.OBSERVATION, content=text, origin="self")


def test_memory_scope_is_part_of_the_memory_and_changes_only_by_revision(memory, experiences, valve):
    """v0.17：记忆提供适用范围、条件与绑定；外部标注不能改写，要改就修订（新建承接版本）。"""
    valve.register_world("story", "龙的故事", "用户讲的故事", [_obs(experiences, "开始讲故事")])
    seen = _obs(experiences, "龙在故事里说话了")
    m1 = memory.form(content="龙会说话", from_experience_ids=[seen], formation=FORMATION, reason="故事里的经历",
                     worlds=["story"], conditions={"仅在": "讲这个故事时"})
    assert valve.worlds_of("memory", m1) == (frozenset({"story"}), False)
    with pytest.raises(ValueError, match="修订"):
        valve.tag_world("memory", m1, PHYSICAL, [seen], "想把它改成现实")

    m0 = memory.form(content="今天下雨", from_experience_ids=[_obs(experiences, "看到下雨")], formation=FORMATION,
                     reason="没说明世界")
    assert valve.worlds_of("memory", m0) == (frozenset({PHYSICAL}), True)  # 没说明：默认物理世界，并标明是默认

    fix = _obs(experiences, "用户说：这段其实是现实里发生的")
    m2 = memory.revise(m1, worlds=[PHYSICAL], basis_experience_ids=[fix], formation=FORMATION, reason="更正世界")
    assert memory.get(m1).worlds == ("story",) and memory.get(m2).worlds == (PHYSICAL,)
    assert memory.get(m2).content == "龙会说话" and memory.get(m2).conditions == {"仅在": "讲这个故事时"}
    assert memory.lineage(m2) == [m2, m1]


def test_memory_only_references_things_that_do_not_change(memory, experiences, registry):
    """v0.17 引用方向：“一旦记忆引用了外部的东西不就是被污染了嘛”。绑定只能指向不会变的对象。"""
    package(registry, experiences, "keys", ["家门钥匙", "车钥匙"])
    door, key = registry.add_raw("家里的门"), registry.add_raw("家门钥匙")
    used = _obs(experiences, "用这把钥匙开了家里的门")
    with pytest.raises(ValueError, match="最新版"):
        memory.form(content="这把钥匙开这扇门", from_experience_ids=[used], formation=FORMATION, reason="x",
                    bindings={"门": {"kind": "material", "id": door}, "知识": {"kind": "package", "id": "keys"}})
    m = memory.form(content="这把钥匙开这扇门", from_experience_ids=[used], formation=FORMATION, reason="具体绑定",
                    bindings={"门": {"kind": "material", "id": door}, "钥匙": {"kind": "material", "id": key},
                              "知识": {"kind": "package", "id": "keys", "version": 1}})
    assert memory.get(m).bindings["钥匙"]["id"] == key
    with pytest.raises(ValueError):
        memory.form(content="x", from_experience_ids=[used], formation=FORMATION, reason="x",
                    bindings={"门": {"kind": "material", "id": "raw:不存在"}})
    # 包后来有了新版本，记忆里的绑定不跟着变。
    registry.add_members("keys", [], [used], "新版本")
    assert memory.get(m).bindings["知识"]["version"] == 1


def test_default_index_by_time_and_by_use(memory, experiences):
    a = memory.form(content="A", from_experience_ids=[_obs(experiences, "a")], formation=FORMATION, reason="x")
    b = memory.form(content="B", from_experience_ids=[_obs(experiences, "b")], formation=FORMATION, reason="x")
    c = memory.form(content="C", from_experience_ids=[_obs(experiences, "c")], formation=FORMATION, reason="x")
    assert memory.index("time") == [a, b, c]
    for _ in range(2):
        memory.recall(c, chain_id="today", origin="self")
    memory.recall(b, chain_id="today", origin="self")
    assert memory.index("use") == [c, b, a]
    with pytest.raises(ValueError):
        memory.index("truth")


def test_record_time_is_kept_apart_from_occurrence_time(experiences, memory, registry):
    """v0.15：事件发生时间、登记时间与版本号不能互相冒充。"""
    ev = experiences.record(chain_id="t", source_type=SourceType.EXTERNAL_STATEMENT, content="上周的事",
                            origin="user", occurred_at="2026-10-20")
    got = experiences.get(ev)
    assert got.occurred_at == "2026-10-20" and got.recorded_at and got.recorded_at[:10] != "2026-10-20"
    unknown_time = experiences.record(chain_id="t", source_type=SourceType.EXTERNAL_STATEMENT, content="不知道何时", origin="u")
    assert experiences.get(unknown_time).occurred_at is None and experiences.get(unknown_time).recorded_at
    mid = memory.form(content="x", from_experience_ids=[ev], formation=FORMATION, reason="x")
    assert memory.get(mid).recorded_at
    pv = package(registry, experiences, "p", ["a", "b"])
    assert registry.store.conn.execute("SELECT recorded_at FROM package_versions WHERE package_id = 'p'").fetchone()[0]
    assert pv.version == 1  # 版本号只是序号，不是时间


def test_call_remembers_what_was_visible_at_that_time(registry, experiences, valve, calls):
    """v0.15：后来缓存里进进出出，不能改变当时调用看到的视图。"""
    a = package(registry, experiences, "a_pkg", ["甲", "乙"])
    package(registry, experiences, "b_pkg", ["丙", "丁"])
    cache = cache_with(valve, ("a_pkg", a.version))
    call = calls.record_call(cache_id=cache, chain_id="c", package_id="a_pkg", purpose="p", context={},
                             inputs={"context": "x"}, origin="model",
                             candidates=[CandidateInput(0, 0.7, Decision.SELECTED)])
    valve.enter(cache, ItemKind.PACKAGE, ("b_pkg", 1))
    valve.exit(cache, ItemKind.PACKAGE, ("a_pkg", 1), "这一段用完了")
    then = calls.visible_view(call)
    assert then["package"] == {"a_pkg@v1": None} and then["world"] == {PHYSICAL: None}
    assert valve.entered(cache, ItemKind.PACKAGE) == {"b_pkg@v1": None}  # 现在的视图已经不同
