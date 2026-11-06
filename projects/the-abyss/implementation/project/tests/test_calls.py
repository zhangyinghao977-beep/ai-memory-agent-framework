"""计算经历与修正记录（2026-10-27 新增：对照报告 B1、N8、N5）。"""
import pytest

from _helpers import cache_with, package, source
from empirical_core.calls import CandidateInput, Decision, NoAnswerReason
from empirical_core.corrections import CorrectionKind
from empirical_core.experience import PackageUse, Relation, SourceType
from empirical_core.registry import UNKNOWN
from empirical_core.relation_eval import Direction

SWEET_B = {"kind": "observed_offset", "scale": "甜味", "value_ref": "obs:B"}


def _sweet_package(registry, experiences):
    package(registry, experiences, "sweet", ["苹果A", "梨B", "樱桃C"])
    basis = experiences.record(chain_id="taste", source_type=SourceType.OBSERVATION, content="品尝", origin="self")
    return registry.record_differences("sweet", {1: SWEET_B}, [basis], "甜味存异")


def test_call_rows_follow_the_candidate_row_contract(registry, experiences, calls):
    """N8：每行＝包引用＋成员＋该包参考系下的存异差异（从知识库读出）＋带尺子与方向的评价。"""
    pv = _sweet_package(registry, experiences)
    cache = cache_with(calls.valve, ("sweet", pv.version))
    cid = calls.record_call(cache_id=cache, chain_id="q", package_id="sweet", purpose="我要甜的", context={"query": "我要甜的"},
                            inputs={"context": "我要甜的"}, origin="model",
                            candidates=[CandidateInput(0, 0.8, Decision.SELECTED), CandidateInput(1, 0.6, Decision.REJECTED),
                                        CandidateInput(2, None)])
    call = calls.get(cid)
    assert call.version == pv.version == 2
    a, b, c = call.rows
    assert (a.package_id, a.version, a.material_id) == ("sweet", 2, registry.add_raw("苹果A"))
    assert a.difference == {"kind": "self_reference"} and b.difference == SWEET_B and c.difference == UNKNOWN
    assert a.evaluation.frame == "pkg:sweet@v2" and a.evaluation.spec.direction is Direction.HIGHER_MATCHES_MORE
    assert a.evaluation.spec.scale.name == "ka_stub_match"
    assert c.evaluation.value is None and not c.evaluation.known  # 未知不是 0
    assert b.decision is Decision.REJECTED  # 本次未采用，不等于不成立
    ev = call.experience_id
    assert experiences.get(ev).source_type is SourceType.COMPUTATION
    assert experiences.package_refs(ev) == [("sweet", 2, PackageUse.CALLED)]


def test_call_inputs_must_match_registration(registry, experiences, calls):
    pv = _sweet_package(registry, experiences)
    cache = cache_with(calls.valve, ("sweet", pv.version))
    base = dict(cache_id=cache, chain_id="q", package_id="sweet", purpose="p", context={}, origin="model",
                candidates=[CandidateInput(0, 0.5)])
    with pytest.raises(ValueError):
        calls.record_call(inputs={}, **base)                                # 缺登记的输入
    with pytest.raises(ValueError):
        calls.record_call(inputs={"context": "x", "secret": 1}, **base)     # 未登记的输入
    with pytest.raises(ValueError):
        calls.record_call(inputs={"context": None}, **base)                 # 未知要写 UNKNOWN
    calls.record_call(inputs={"context": UNKNOWN}, **base)


def test_call_values_must_fit_the_registered_scale(registry, experiences, calls):
    pv = _sweet_package(registry, experiences)
    cache = cache_with(calls.valve, ("sweet", pv.version))
    with pytest.raises(ValueError):
        calls.record_call(cache_id=cache, chain_id="q", package_id="sweet", purpose="p", context={}, inputs={"context": "x"},
                          origin="model", candidates=[CandidateInput(0, 1.7)])
    with pytest.raises(ValueError):
        calls.record_call(cache_id=cache, chain_id="q", package_id="sweet", purpose="p", context={}, inputs={"context": "x"},
                          origin="model", candidates=[CandidateInput(5, 0.1)])


def test_no_answer_keeps_its_reason(registry, experiences, calls):
    pv = _sweet_package(registry, experiences)
    cache = cache_with(calls.valve, ("sweet", pv.version))
    with pytest.raises(ValueError):
        calls.record_call(cache_id=cache, chain_id="q", package_id="sweet", purpose="p", context={}, inputs={"context": "x"},
                          origin="model", candidates=[CandidateInput(0, 0.9, Decision.SELECTED)],
                          no_answer=(NoAnswerReason.MISSING_CONDITION, "缺清洁证据"))
    with pytest.raises(ValueError):  # 被选中的候选评价不能是未知
        calls.record_call(cache_id=cache, chain_id="q", package_id="sweet", purpose="p", context={}, inputs={"context": "x"},
                          origin="model", candidates=[CandidateInput(0, None, Decision.SELECTED)])
    cid = calls.record_call(cache_id=cache, chain_id="q", package_id="sweet", purpose="甜且红", context={}, inputs={"context": "x"},
                            origin="model", candidates=[CandidateInput(1, None)],
                            no_answer=(NoAnswerReason.MISSING_EVIDENCE, "梨 B 的颜色依据缺失"))
    assert calls.get(cid).no_answer == {"reason": "MISSING_EVIDENCE", "note": "梨 B 的颜色依据缺失"}


def test_cropped_package_cannot_be_called(registry, experiences, calls):
    package(registry, experiences, "old", ["a", "b"])
    cache = cache_with(calls.valve, ("old", 1))
    registry.crop("old", "参照改变", {}, [source(experiences, "复核")])
    with pytest.raises(ValueError):
        calls.record_call(cache_id=cache, chain_id="q", package_id="old", purpose="p", context={}, inputs={"context": "x"},
                          origin="model", candidates=[CandidateInput(0, 0.1)])


def test_feedback_is_external_and_points_back_to_the_call(registry, experiences, calls):
    pv = _sweet_package(registry, experiences)
    cache = cache_with(calls.valve, ("sweet", pv.version))
    cid = calls.record_call(cache_id=cache, chain_id="q", package_id="sweet", purpose="p", context={}, inputs={"context": "x"},
                            origin="model", candidates=[CandidateInput(0, 0.9, Decision.SELECTED)])
    with pytest.raises(ValueError):
        calls.feedback(cid, source_type=SourceType.CANDIDATE_INFERENCE, content="我觉得对", origin="model")
    fb = calls.feedback(cid, source_type=SourceType.EXTERNAL_STATEMENT, content="用户：选对了", origin="user")
    assert calls.calls_answered_by(fb) == [cid]
    assert experiences.links_from(fb) == [(calls.get(cid).experience_id, Relation.FEEDBACK_FOR)]
    assert fb > calls.get(cid).experience_id  # 反馈晚于调用，不会混进当时的入参


def test_r1_and_source_corrections_are_recorded_not_overwritten(registry, experiences, calls, corrections):
    """N5：入参／绑定修正（R1）与来源记录修正，有目标、依据和修订内容；原记录不变。"""
    pv = _sweet_package(registry, experiences)
    cache = cache_with(calls.valve, ("sweet", pv.version))
    cid = calls.record_call(cache_id=cache, chain_id="q", package_id="sweet", purpose="p", context={}, inputs={"context": "苹果"},
                            origin="model", candidates=[CandidateInput(0, 0.9, Decision.SELECTED)])
    fb = calls.feedback(cid, source_type=SourceType.EXTERNAL_STATEMENT, content="用户：问的是梨", origin="user")
    with pytest.raises(ValueError):
        corrections.correct_input_binding(cid, {"weights": 1}, [fb], "不属于 R1 的字段")
    guess = experiences.record(chain_id="q", source_type=SourceType.CANDIDATE_INFERENCE, content="可能问的是梨", origin="model")
    with pytest.raises(ValueError):
        corrections.correct_input_binding(cid, {"inputs": {"context": "梨"}}, [guess], "自生成依据")
    r1 = corrections.correct_input_binding(cid, {"inputs": {"context": "梨"}}, [fb], "绑定错了对象")
    got = corrections.for_target(CorrectionKind.R1_INPUT_BINDING, {"call_id": cid})
    assert [c.correction_id for c in got] == [r1] and got[0].revision == {"inputs": {"context": "梨"}}
    assert calls.get(cid).inputs == {"context": "苹果"}  # 原调用记录不变

    doc = experiences.record(chain_id="d", source_type=SourceType.EXTERNAL_STATEMENT, content="原文", origin="doc:a")
    seen = experiences.record(chain_id="d", source_type=SourceType.OBSERVATION, content="查到原文出自 doc:b", origin="self")
    with pytest.raises(ValueError):
        corrections.correct_source_record(doc, {"origin": "doc:b"}, [doc], "自己证明自己")
    corrections.correct_source_record(doc, {"origin": "doc:b"}, [seen], "出处记错")
    assert experiences.get(doc).origin == "doc:a"
    assert corrections.for_target(CorrectionKind.SOURCE_RECORD, {"experience_id": doc})[0].revision == {"origin": "doc:b"}
