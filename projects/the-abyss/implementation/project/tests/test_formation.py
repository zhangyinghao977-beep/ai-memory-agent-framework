"""组合轮次、成员的值、局部／全局与发布、包之间的概念关系（2026-10-28 新增：对照报告 B2、B3、B4、N6）。"""
import pytest

from _helpers import COMPUTATION, package, source
from empirical_core.experience import SourceType
from empirical_core.registry import UNKNOWN, MemberSpec
from empirical_core.valve import ItemKind

REGRESSION = {"status": "passed", "scope": "其他三个包的固定调用"}


def _obs(experiences, text):
    return experiences.record(chain_id="t", source_type=SourceType.OBSERVATION, content=text, origin="self")


# ---------- B4：成员的值与来源 ----------

def test_member_value_and_sources_are_kept_and_unknown_by_default(registry, experiences):
    tasted = _obs(experiences, "尝了梨 B：偏酸")
    a, b, c = registry.add_raw("苹果A"), registry.add_raw("梨B"), registry.add_raw("樱桃C")
    v = registry.register_package("sweet", "甜味", [
        MemberSpec(a, value={"sweetness_note": "甜"}),
        MemberSpec(b, value={"sweetness_note": "偏酸"}, sources=(tasted,)),
        MemberSpec(c),
    ], COMPUTATION, [source(experiences)], "甜味比较")
    assert v.members[1].value == {"sweetness_note": "偏酸"} and v.members[1].sources == (tasted,)
    assert v.members[2].value == UNKNOWN and v.members[2].sources == ()  # 没给出就是未知，不是 0
    v2 = registry.add_members("sweet", [MemberSpec(registry.add_raw("桃D"))], [source(experiences)], "追加")
    assert v2.members[1].value == {"sweetness_note": "偏酸"} and v2.members[1].sources == (tasted,)  # 新版本保留
    with pytest.raises(ValueError):
        registry.register_package("bad", "x", [MemberSpec(a), MemberSpec(b, sources=(9999,))], COMPUTATION, [], "来源不存在")


# ---------- B3：组合轮次 ----------

def test_round_limits_materials_and_layer(registry, experiences):
    a, b, c = registry.add_raw("a"), registry.add_raw("b"), registry.add_raw("c")
    r1 = registry.open_round(1, [a, b], "第一轮：原始素材", [source(experiences)])
    with pytest.raises(ValueError, match="没有进入第"):  # c 没进入本轮
        registry.register_package("p_ac", "x", [MemberSpec(a), MemberSpec(c)], COMPUTATION, [source(experiences)], "x",
                                  round_id=r1)
    with pytest.raises(ValueError, match="层级"):  # 计算登记的层级要和本轮一致
        registry.register_package("p_ab", "x", [MemberSpec(a), MemberSpec(b)], dict(COMPUTATION, layer=2),
                                  [source(experiences)], "x", round_id=r1)
    registry.register_package("p_ab", "ab", [MemberSpec(a), MemberSpec(b)], COMPUTATION, [source(experiences)], "x",
                              round_id=r1)
    registry.extend_round(r1, [c], "补进 c")
    registry.register_package("p_c", "c", [MemberSpec(c)], COMPUTATION, [source(experiences)], "x", round_id=r1)
    assert registry.close_round(r1) == ["p_ab", "p_c"]
    with pytest.raises(ValueError):
        registry.register_package("late", "x", [MemberSpec(a)], COMPUTATION, [source(experiences)], "x", round_id=r1)

    # 上一轮的产物成为下一轮的素材
    r2 = registry.open_round(2, [registry.package_material("p_ab"), registry.package_material("p_c")],
                             "第二轮：用上一轮的包", [source(experiences)])
    up = registry.register_package("p_up", "上层", [MemberSpec(registry.package_material("p_ab")),
                                                   MemberSpec(registry.package_material("p_c"))],
                                   dict(COMPUTATION, layer=2), [source(experiences)], "x", round_id=r2)
    assert up.reference == registry.package_material("p_ab")
    assert registry.round_info(r2)["layer"] == 2 and registry.round_info(r2)["products"] == ["p_up"]


# ---------- B2：局部／全局，候选／可发布 ----------

def test_local_package_stays_in_its_cache_until_promoted(registry, experiences, valve):
    home = valve.open_cache("今天整理水果")
    a, b = registry.add_raw("苹果A"), registry.add_raw("梨B")
    registry.register_package("today_fruit", "今天的水果", [MemberSpec(a), MemberSpec(b)], COMPUTATION,
                              [source(experiences)], "工作侧挂靠", work_cache_id=home)
    assert registry.standing("today_fruit") == ("LOCAL", home)
    valve.enter(home, ItemKind.PACKAGE, ("today_fruit", 1))
    other = valve.open_cache("别的任务")
    with pytest.raises(ValueError, match="局部包"):  # 局部成功不直接推广
        valve.enter(other, ItemKind.PACKAGE, ("today_fruit", 1))

    with pytest.raises(ValueError):  # 推广要写明回归检查
        registry.promote("today_fruit", [source(experiences)], "推广", {"status": "maybe"})
    with pytest.raises(ValueError):
        registry.promote("today_fruit", [source(experiences)], "推广", {"status": "failed", "scope": "别的包"})
    registry.promote("today_fruit", [source(experiences, "三次使用都没问题")], "整合到更广范围", REGRESSION)
    assert registry.standing("today_fruit") == ("GLOBAL", None)
    valve.enter(other, ItemKind.PACKAGE, ("today_fruit", 1))


def test_registered_is_not_published(registry, experiences, valve):
    home = valve.open_cache("工作")
    package(registry, experiences, "learned", ["a", "b"])  # 不在工作缓存里登记：学习侧产物，全局
    a = registry.add_raw("x")
    registry.register_package("local_one", "x", [MemberSpec(a)], COMPUTATION, [source(experiences)], "x",
                              work_cache_id=home)
    assert registry.publication("learned") == "CANDIDATE"   # 登记 ≠ 发布
    guess = experiences.record(chain_id="t", source_type=SourceType.CANDIDATE_INFERENCE, content="我觉得对", origin="model")
    with pytest.raises(ValueError):  # 发布要观察或实际执行的证据
        registry.publish("learned", [guess], "模型觉得对")
    with pytest.raises(ValueError):  # 局部包要先推广
        registry.publish("local_one", [_obs(experiences, "看过了")], "x")
    registry.publish("learned", [_obs(experiences, "核对了三次，结果一致")], "核实后发布")
    assert registry.publication("learned") == "PUBLISHED"
    with pytest.raises(ValueError):
        registry.publish("learned", [_obs(experiences, "又看了")], "重复发布")


# ---------- N6：包之间的概念关系 ----------

def test_concept_relations_are_graph_references_separate_from_members(registry, experiences):
    package(registry, experiences, "sweet", ["苹果A", "梨B"])
    package(registry, experiences, "red", ["苹果A", "樱桃C"])
    basis = [source(experiences, "讨论记录")]
    r1 = registry.relate("sweet", 1, "red", 1, "常一起比较", basis, "甜且红")
    r2 = registry.relate("red", 1, "sweet", 1, "常一起比较", basis, "反方向")  # 允许成环
    assert {r["relation_id"] for r in registry.relations("sweet")} == {r1, r2}
    assert registry.dependents("sweet") == []  # 概念关系不是成员关系
    assert len(registry.latest("sweet").members) == 2
    with pytest.raises(ValueError):
        registry.relate("sweet", 1, "red", 9, "x", basis, "版本不存在")
    registry.retract_relation(r2, [source(experiences, "反方向不成立")], "撤回")
    assert [r["relation_id"] for r in registry.relations("sweet")] == [r1]
    assert len(registry.relations("sweet", include_retracted=True)) == 2  # 原记录保留
    with pytest.raises(ValueError):
        registry.retract_relation(r2, basis, "再撤一次")
