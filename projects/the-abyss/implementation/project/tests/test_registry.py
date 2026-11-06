import pytest

from _helpers import COMPUTATION, cache_with, package, source
from empirical_core.calls import CandidateInput, Decision
from empirical_core.corrections import CorrectionKind
from empirical_core.experience import SourceType, Verification
from empirical_core.registry import SELF_REFERENCE, UNKNOWN, DependencyError, MemberSpec

SWEET = {"kind": "observed_offset", "scale": "甜味", "value_ref": "obs:1"}
REGRESSION_OK = {"status": "not_run", "scope": "测试中没有其他组合"}


def test_first_member_is_reference_and_unknown_is_not_zero(registry, experiences):
    v = package(registry, experiences, "p", ["猫", "狗", "兔"], [None, SWEET, None])
    assert v.reference == registry.add_raw("猫")
    assert v.members[0].difference == SELF_REFERENCE
    assert v.members[1].difference == SWEET
    assert v.members[2].difference == UNKNOWN


def test_reference_member_cannot_carry_a_difference(registry):
    m = registry.add_raw("猫")
    with pytest.raises(ValueError):
        registry.register_package("p", "p", [MemberSpec(m, SWEET)], COMPUTATION, [], "x")


def test_bare_zero_or_unscaled_difference_rejected(registry):
    a, b = registry.add_raw("a"), registry.add_raw("b")
    with pytest.raises(ValueError):
        registry.register_package("p", "p", [MemberSpec(a), MemberSpec(b, 0)], COMPUTATION, [], "x")
    with pytest.raises(ValueError):  # 差异必须说明是哪把尺子上的差异
        registry.register_package("p", "p", [MemberSpec(a), MemberSpec(b, {"kind": "offset"})], COMPUTATION, [], "x")


def test_computation_registration_required(registry):
    m = registry.add_raw("a")
    with pytest.raises(ValueError):
        registry.register_package("p", "p", [MemberSpec(m)], {"computation_id": "x"}, [], "x")


@pytest.mark.parametrize("field,bad", [
    ("layer", 0.5), ("layer", -1), ("layer", None),
    ("parameter_version", "v1"), ("parameter_version", {"kind": "weights"}),
    ("output_evaluation", {"scale": {"name": "s"}}),
])
def test_computation_needs_layer_parameter_version_and_scale(registry, field, bad):
    """A4：计算登记要有适用层级、参数版本，以及输出的尺子与方向。"""
    m = registry.add_raw("a")
    with pytest.raises(ValueError):
        registry.register_package("p", "p", [MemberSpec(m)], dict(COMPUTATION, **{field: bad}), [], "x")


def test_unknown_layer_is_allowed_but_not_zero(registry):
    m = registry.add_raw("a")
    v = registry.register_package("p", "p", [MemberSpec(m)], dict(COMPUTATION, layer=UNKNOWN), [], "x")
    assert v.computation["layer"] == UNKNOWN


def test_same_package_id_cannot_be_reused(registry, experiences):
    package(registry, experiences, "p", ["a"])
    with pytest.raises(ValueError):
        package(registry, experiences, "p", ["b"])


def test_add_members_appends_version_and_keeps_old(registry, experiences):
    package(registry, experiences, "p", ["猫", "狗"])
    v2 = registry.add_members("p", [MemberSpec(registry.add_raw("兔"))], [source(experiences, "新语料")], "追加")
    assert v2.version == 2 and v2.parent_version == 1
    assert len(v2.members) == 3 and v2.reference == registry.add_raw("猫")
    assert len(registry.version("p", 1).members) == 2


def test_material_reuse_across_packages(registry, experiences):
    package(registry, experiences, "eco", ["物种", "演化"])
    package(registry, experiences, "astro", ["轨道", "演化"])
    evo = registry.add_raw("演化")
    assert evo in [m.material_id for m in registry.latest("eco").members]
    assert evo in [m.material_id for m in registry.latest("astro").members]


def test_record_differences_writes_back_storage_of_difference(registry, experiences):
    """N7：偏差登记在存异结果里，参考不变。"""
    package(registry, experiences, "sweet", ["苹果A", "梨B", "樱桃C"])
    basis = experiences.record(chain_id="taste", source_type=SourceType.OBSERVATION, content="品尝记录", origin="self")
    with pytest.raises(ValueError):
        registry.record_differences("sweet", {0: SWEET}, [basis], "参考不能改")
    with pytest.raises(ValueError):
        registry.record_differences("sweet", {1: SWEET}, [], "没有依据")
    v2 = registry.record_differences("sweet", {1: SWEET}, [basis], "甜味差异")
    assert v2.change == "differences_recorded" and v2.reference == registry.version("sweet", 1).reference
    assert v2.members[1].difference == SWEET and v2.members[2].difference == UNKNOWN
    assert registry.version("sweet", 1).members[1].difference == UNKNOWN


def _call_and_feedback(registry, calls, experiences, pid, source_type=SourceType.TOOL_EXECUTION):
    cid = cache_with(calls.valve, (pid, registry.latest(pid).version))
    call = calls.record_call(chain_id="r2", cache_id=cid, package_id=pid, purpose="选实证", context={"q": "哪个是实证"},
                             inputs={"context": "q"}, origin="model",
                             candidates=[CandidateInput(0, 0.2), CandidateInput(2, 0.7, Decision.SELECTED)])
    fb = calls.feedback(call, source_type=source_type, content="实际反馈：正确答案是实证", origin="tool")
    return call, fb


def test_r2_needs_external_feedback_for_a_call_of_current_version(registry, experiences, calls, corrections):
    package(registry, experiences, "p", ["严谨", "求实", "实证"])
    new_comp = dict(COMPUTATION, training_basis="feedback events", parameter_version={"kind": "weights", "sha256": "ab" * 32})

    with pytest.raises(ValueError):
        registry.update_computation("p", new_comp, [], "没有依据", REGRESSION_OK)
    guess = experiences.record(chain_id="r2", source_type=SourceType.CANDIDATE_INFERENCE, content="我猜应该选实证", origin="model")
    with pytest.raises(ValueError):
        registry.update_computation("p", new_comp, [guess], "自生成依据", REGRESSION_OK)
    loose = experiences.record(chain_id="r2", source_type=SourceType.TOOL_EXECUTION, content="不对应任何调用", origin="tool")
    with pytest.raises(ValueError):  # A3：反馈必须对应一次调用
        registry.update_computation("p", new_comp, [loose], "没有对应调用", REGRESSION_OK)

    _, fb = _call_and_feedback(registry, calls, experiences, "p")
    with pytest.raises(ValueError):  # B6：必须写明回归检查
        registry.update_computation("p", new_comp, [fb], "局部训练", {"status": "maybe"})
    with pytest.raises(ValueError):
        registry.update_computation("p", new_comp, [fb], "局部训练", {"status": "failed", "scope": "其他包"})
    v2 = registry.update_computation("p", new_comp, [fb], "局部训练", REGRESSION_OK)
    assert v2.change == "computation_updated" and v2.basis_event_ids == [fb]
    assert v2.regression == REGRESSION_OK
    assert v2.reference == registry.version("p", 1).reference
    assert registry.version("p", 1).computation == COMPUTATION

    # 反馈对应的是 v1，包已经到 v2：不直接更新。
    with pytest.raises(ValueError):
        registry.update_computation("p", new_comp, [fb], "旧版本反馈", REGRESSION_OK)

    r2 = [c for c in corrections.all() if c.kind is CorrectionKind.R2_PACKAGE_EVALUATION]
    assert len(r2) == 1 and r2[0].target == {"package_id": "p", "from_version": 1, "to_version": 2}


def test_r2_rejects_recall_and_contradicted_feedback(registry, experiences, calls, memory):
    """A2：回忆不是外部反馈；已被核实为相反的反馈也不能用。"""
    package(registry, experiences, "p", ["严谨", "求实", "实证"])
    call, fb = _call_and_feedback(registry, calls, experiences, "p")
    tasted = experiences.record(chain_id="m", source_type=SourceType.OBSERVATION, content="以前的经历", origin="self")
    mid = memory.form(content="以前学过", from_experience_ids=[tasted],
                      formation={"method_id": "manual", "description": "人工"}, reason="x")
    recall = memory.recall(mid, chain_id="r2", origin="self")
    with pytest.raises(ValueError):
        registry.update_computation("p", COMPUTATION, [recall], "回忆当反馈", REGRESSION_OK)

    recheck = experiences.record(chain_id="r2", source_type=SourceType.TOOL_EXECUTION, content="复测：反馈记错了", origin="tool")
    experiences.verify(fb, Verification.CONTRADICTED, [recheck], "复测不符")
    with pytest.raises(ValueError):
        registry.update_computation("p", COMPUTATION, [fb], "被推翻的反馈", REGRESSION_OK)


def test_r3_crop_requires_basis_and_handling_dependents(registry, experiences, corrections):
    package(registry, experiences, "leaf", ["a", "b"])
    parent_member = registry.package_material("leaf")
    registry.register_package("parent", "parent", [MemberSpec(registry.add_raw("root")), MemberSpec(parent_member)],
                              COMPUTATION, [source(experiences)], "上层组合")
    assert registry.dependents("leaf") == ["parent"]
    review = source(experiences, "复核：参照含义改变")

    with pytest.raises(ValueError):
        registry.crop("leaf", "参照含义改变", {"parent": "待重组"}, [])
    with pytest.raises(DependencyError) as err:
        registry.crop("leaf", "参照含义改变", {}, [review])
    assert err.value.unhandled == ["parent"]

    registry.crop("leaf", "参照含义改变", {"parent": "待重组"}, [review])
    assert registry.status("leaf") == "CROPPED"
    assert registry.dangling_references() == [("parent", "leaf")]
    assert registry.latest("leaf").version == 1  # 历史保留
    r3 = [c for c in corrections.all() if c.kind is CorrectionKind.R3_REFERENCE_STRUCTURE]
    assert len(r3) == 1 and r3[0].basis == [review]

    with pytest.raises(ValueError):
        registry.add_members("leaf", [MemberSpec(registry.add_raw("c"))], [], "已裁剪")
    with pytest.raises(ValueError):
        registry.register_package("other", "other", [MemberSpec(registry.add_raw("x")), MemberSpec(parent_member)],
                                  COMPUTATION, [], "引用已裁剪包")

    new = registry.register_package("leaf_v2", "leaf_v2", [MemberSpec(registry.add_raw("b")), MemberSpec(registry.add_raw("a"))],
                                    COMPUTATION, [source(experiences)], "新参考重组", reorganized_from=["leaf"])
    assert new.reference == registry.add_raw("b")


def test_reorganize_requires_cropped_source(registry, experiences):
    package(registry, experiences, "leaf", ["a"])
    with pytest.raises(ValueError):
        registry.register_package("leaf2", "leaf2", [MemberSpec(registry.add_raw("b"))], COMPUTATION, [], "x",
                                  reorganized_from=["leaf"])


def test_package_cannot_contain_itself(registry, experiences):
    package(registry, experiences, "a", ["x"])
    registry.register_package("b", "b", [MemberSpec(registry.add_raw("y")), MemberSpec(registry.package_material("a"))],
                              COMPUTATION, [], "b 包含 a")
    with pytest.raises(ValueError):
        registry.add_members("a", [MemberSpec(registry.package_material("b"))], [], "会形成环")


def test_unknown_basis_event_rejected(registry):
    m = registry.add_raw("a")
    with pytest.raises(ValueError):
        registry.register_package("p", "p", [MemberSpec(m)], COMPUTATION, [12345], "x")
