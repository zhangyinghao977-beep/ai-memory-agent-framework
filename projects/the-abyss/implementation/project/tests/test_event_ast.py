"""事件链＝广义 AST：结构层与发生层（2026-10-27 新增，设计稿 v0.3 第二节；v0.14 4.2“拿起苹果 洗净 再吃”）。"""
import pytest

from _helpers import cache_with, package, source
from empirical_core.calls import CandidateInput, Decision
from empirical_core.event_ast import (
    BindingState, ChildRef, ConditionState, Face, NodeKind, bound, candidates, gap,
)
from empirical_core.experience import SourceType
from empirical_core.valve import ItemKind

OBJ = {"role": "对象", "ref_kinds": ["material"]}


def _apple_process(structures, experiences):
    """顺序(拿起(X), 洗(X), 条件[有可食用的依据] 吃(X))。"""
    b = [source(experiences, "过程说明")]
    for nid, name in (("pick", "拿起"), ("wash", "洗"), ("eat", "吃")):
        structures.define(nid, NodeKind.OPERATION, name, slots={"对象": OBJ}, basis_ids=b, reason="x")
    structures.define("eat_if_safe", NodeKind.CONDITION, "条件满足后吃", slots={"对象": OBJ},
                      condition="有可食用的依据", children=[ChildRef("eat", 1, {"对象": "对象"})], basis_ids=b, reason="x")
    return structures.define("apple_process", NodeKind.SEQUENCE, "拿起、洗净、再吃", slots={"X": OBJ},
                             children=[ChildRef("pick", 1, {"对象": "X"}), ChildRef("wash", 1, {"对象": "X"}),
                                       ChildRef("eat_if_safe", 1, {"对象": "X"})], basis_ids=b, reason="x")


def _exp(experiences, text, src=SourceType.TOOL_EXECUTION):
    return experiences.record(chain_id="apple", source_type=src, content=text, origin="self")


def test_node_kinds_have_child_rules(structures, experiences):
    b = [source(experiences)]
    structures.define("op", NodeKind.OPERATION, "操作", basis_ids=b, reason="x")
    with pytest.raises(ValueError):
        structures.define("bad", NodeKind.OPERATION, "x", children=[ChildRef("op", 1)], basis_ids=b, reason="x")
    with pytest.raises(ValueError):
        structures.define("bad", NodeKind.BRANCH, "x", children=[ChildRef("op", 1)], basis_ids=b, reason="x")
    with pytest.raises(ValueError):  # 条件节点必须写明条件
        structures.define("bad", NodeKind.CONDITION, "x", children=[ChildRef("op", 1)], basis_ids=b, reason="x")
    with pytest.raises(ValueError):  # 对应表里的 slot 必须存在
        structures.define("bad", NodeKind.SEQUENCE, "x", slots={"X": {}}, children=[ChildRef("op", 1, {"对象": "X"})],
                          basis_ids=b, reason="x")
    with pytest.raises(ValueError):
        structures.define("bad", NodeKind.OPERATION, "x", basis_ids=[], reason="没有依据")


def test_structure_unfolds_and_is_reused_without_copying(structures, experiences):
    _apple_process(structures, experiences)
    tree = structures.unfold("apple_process")
    assert [c["name"] for c in tree["children"]] == ["拿起", "洗", "条件满足后吃"]
    assert tree["children"][2]["children"][0]["name"] == "吃"
    structures.define("pear_process", NodeKind.SEQUENCE, "洗梨", slots={"Y": OBJ},
                      children=[ChildRef("wash", 1, {"对象": "Y"})], basis_ids=[source(experiences)], reason="复用洗")
    assert structures.used_in("wash", 1) == [("apple_process", 1), ("pear_process", 1)]


def test_same_object_is_inherited_and_enforced(structures, occurrences, experiences, registry, valve):
    _apple_process(structures, experiences)
    apple_a, pear_b = registry.add_raw("苹果A"), registry.add_raw("梨B")
    A, B = {"kind": "material", "id": apple_a}, {"kind": "material", "id": pear_b}
    cache = valve.open_cache("吃苹果")
    plan = _exp(experiences, "打算拿起、洗净、再吃苹果 A", SourceType.TOOL_PLAN)
    root = occurrences.occur("apple_process", cache_id=cache, experience_id=plan, bindings={"X": bound(A)})

    wash = occurrences.occur("wash", cache_id=cache, parent_occurrence_id=root,
                             experience_id=_exp(experiences, "冲洗了苹果 A"))
    assert occurrences.bindings(wash)["对象"].value == A and occurrences.bindings(wash)["对象"].inherited
    with pytest.raises(ValueError, match="同一个对象"):  # 洗的是 A，吃的就不能是 B
        occurrences.occur("eat_if_safe", cache_id=cache, parent_occurrence_id=root,
                          experience_id=_exp(experiences, "x"), bindings={"对象": bound(B)})
    cond = occurrences.occur("eat_if_safe", cache_id=cache, parent_occurrence_id=root,
                             experience_id=_exp(experiences, "准备吃"))
    eat = occurrences.occur("eat", cache_id=cache, parent_occurrence_id=cond,
                            experience_id=_exp(experiences, "吃了", SourceType.TOOL_PLAN))
    assert occurrences.bindings(eat)["对象"].value == A  # 隔两层仍是同一个对象
    with pytest.raises(ValueError):  # 不是父结构里的子节点
        occurrences.occur("pick", cache_id=cache, parent_occurrence_id=cond, experience_id=_exp(experiences, "x"))
    assert experiences.get(occurrences.get(root).experience_id).source_type is SourceType.TOOL_PLAN  # 计划不冒充已发生


def test_unknown_binding_stays_a_gap_or_candidates(structures, occurrences, experiences, registry, valve):
    _apple_process(structures, experiences)
    A = {"kind": "material", "id": registry.add_raw("苹果A")}
    B = {"kind": "material", "id": registry.add_raw("梨B")}
    cache = valve.open_cache("吃水果")
    root = occurrences.occur("apple_process", cache_id=cache, experience_id=_exp(experiences, "要吃一个水果"))
    assert occurrences.bindings(root)["X"].state is BindingState.GAP  # 不强行补成 A
    pick = occurrences.occur("pick", cache_id=cache, parent_occurrence_id=root,
                             experience_id=_exp(experiences, "拿起一个"), bindings={"对象": candidates(A, B)})
    assert occurrences.bindings(pick)["对象"].state is BindingState.CANDIDATES
    occurrences.occur("wash", cache_id=cache, parent_occurrence_id=root,
                      experience_id=_exp(experiences, "洗了苹果 A"), bindings={"对象": bound(A)})
    with pytest.raises(ValueError, match="同一个对象"):  # 父 slot 还是缺口时，兄弟之间也必须是同一个对象
        occurrences.occur("eat_if_safe", cache_id=cache, parent_occurrence_id=root,
                          experience_id=_exp(experiences, "x"), bindings={"对象": bound(B)})
    with pytest.raises(ValueError, match="类型约束"):  # 类型约束：对象只能是素材
        occurrences.occur("pick", cache_id=cache, experience_id=_exp(experiences, "x"),
                          bindings={"对象": bound({"kind": "literal", "value": "某个东西"})})
    with pytest.raises(ValueError):
        candidates(A)


def test_second_use_does_not_reuse_first_result(structures, occurrences, experiences, registry, valve):
    _apple_process(structures, experiences)
    A = {"kind": "material", "id": registry.add_raw("苹果A")}
    cache = valve.open_cache("两次")
    occurrences.occur("wash", cache_id=cache, experience_id=_exp(experiences, "洗苹果 A"), bindings={"对象": bound(A)})
    second = occurrences.occur("wash", cache_id=cache, experience_id=_exp(experiences, "又洗了一次"))
    assert occurrences.bindings(second)["对象"] == gap()


def test_condition_needs_evidence_not_high_scores(structures, occurrences, experiences, registry, valve, calls):
    _apple_process(structures, experiences)
    pv = package(registry, experiences, "edible", ["可食用", "不可食用"])
    cache = cache_with(valve, ("edible", pv.version))
    A = {"kind": "material", "id": registry.add_raw("苹果A")}
    root = occurrences.occur("apple_process", cache_id=cache, experience_id=_exp(experiences, "吃苹果"),
                             bindings={"X": bound(A)})
    cond = occurrences.occur("eat_if_safe", cache_id=cache, parent_occurrence_id=root, experience_id=_exp(experiences, "要吃"))
    eat = occurrences.occur("eat", cache_id=cache, parent_occurrence_id=cond, experience_id=_exp(experiences, "吃"))
    assert occurrences.governing_conditions(eat) == [(cond, ConditionState.UNKNOWN)]

    call = calls.record_call(cache_id=cache, occurrence_id=cond, chain_id="apple", package_id="edible", purpose="能吃吗",
                             context={}, inputs={"context": "苹果A"}, origin="model",
                             candidates=[CandidateInput(0, 0.99, Decision.SELECTED)])
    with pytest.raises(ValueError, match="高分不能绕过条件"):  # 0.99 的高分不是证据
        occurrences.check_condition(cond, ConditionState.SATISFIED, [calls.get(call).experience_id], "分数很高")
    with pytest.raises(ValueError):
        occurrences.check_condition(cond, ConditionState.SATISFIED, [], "没有证据")
    with pytest.raises(ValueError):  # 只有条件节点才有条件状态
        occurrences.check_condition(eat, ConditionState.UNKNOWN, [], "x")
    seen = _exp(experiences, "看到苹果 A 已洗净、没有坏", SourceType.OBSERVATION)
    occurrences.check_condition(cond, ConditionState.SATISFIED, [seen], "观察")
    assert occurrences.governing_conditions(eat) == [(cond, ConditionState.SATISFIED)]


def test_flow_steps_record_face_conversion_with_inputs_and_outputs(structures, occurrences, experiences, registry,
                                                                   valve, calls):
    """3×3 互转是流转中的计算因子：每一步记下从哪个面到哪个面、输入和输出。"""
    _apple_process(structures, experiences)
    pv = package(registry, experiences, "edible", ["可食用", "不可食用"])
    cache = cache_with(valve, ("edible", pv.version))
    A = {"kind": "material", "id": registry.add_raw("苹果A")}
    root = occurrences.occur("apple_process", cache_id=cache, experience_id=_exp(experiences, "吃苹果"),
                             bindings={"X": bound(A)})
    call = calls.record_call(cache_id=cache, occurrence_id=root, chain_id="apple", package_id="edible", purpose="能吃吗",
                             context={}, inputs={"context": "苹果A"}, origin="model",
                             candidates=[CandidateInput(0, 0.8, Decision.SELECTED)])
    step = occurrences.record_flow(root, Face.WHAT, Face.WHY,
                                   inputs=[{"kind": "package", "id": "edible", "version": pv.version},
                                           {"kind": "binding", "occurrence_id": root, "slot": "X"}],
                                   outputs=[{"kind": "call", "id": call}], note="知识进入关系计算")
    assert occurrences.flow(root)[0]["step_id"] == step and occurrences.flow(root)[0]["from"] == "what"

    with pytest.raises(ValueError):  # 输出必须交代
        occurrences.record_flow(root, Face.WHY, Face.HOW, inputs=[{"kind": "call", "id": call}], outputs=[], note="x")
    package(registry, experiences, "fruit", ["苹果", "梨"])
    with pytest.raises(ValueError, match="没有进入工作缓存"):  # 不在本缓存的包不能当输入
        occurrences.record_flow(root, Face.WHAT, Face.WHY, inputs=[{"kind": "package", "id": "fruit", "version": 1}],
                                outputs=[{"kind": "call", "id": call}], note="x")
    other = valve.open_cache("别的缓存")
    stray = occurrences.occur("wash", cache_id=other, experience_id=_exp(experiences, "x"))
    with pytest.raises(ValueError, match="不在本工作缓存"):  # 调用属于另一个缓存
        occurrences.record_flow(stray, Face.WHY, Face.HOW, inputs=[{"kind": "call", "id": call}],
                                outputs=[{"kind": "literal", "value": {"kind": "unknown"}}], note="x")


def test_bindings_only_use_materials_entered_in_the_cache(structures, occurrences, experiences, registry, valve):
    b = [source(experiences)]
    structures.define("use_pkg", NodeKind.OPERATION, "用知识", slots={"知识": {"ref_kinds": ["package"]}},
                      basis_ids=b, reason="x")
    pv = package(registry, experiences, "k", ["a", "b"])
    cache = valve.open_cache("未准入")
    ref = {"kind": "package", "id": "k", "version": pv.version}
    with pytest.raises(ValueError, match="没有进入工作缓存"):
        occurrences.occur("use_pkg", cache_id=cache, experience_id=_exp(experiences, "x"), bindings={"知识": bound(ref)})
    valve.enter(cache, ItemKind.PACKAGE, ("k", pv.version))
    occ = occurrences.occur("use_pkg", cache_id=cache, experience_id=_exp(experiences, "y"), bindings={"知识": bound(ref)})
    assert occurrences.bindings(occ)["知识"].value == ref
