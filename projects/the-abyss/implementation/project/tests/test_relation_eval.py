"""关系评价的流转（2026-10-27 新增：名词解释 v0.14 第三节与苹果／梨／樱桃案例；对照报告 N8、A5）。"""
import pytest

from empirical_core.relation_eval import (
    ConversionError, Direction, Evaluation, EvaluationSpec, Scale, check_same_ruler, convert_direction, difference,
)

SWEET = EvaluationSpec(Scale("甜味包吻合度", 0.0, 1.0), Direction.HIGHER_MATCHES_MORE)
RED = EvaluationSpec(Scale("颜色包吻合度", 0.0, 1.0), Direction.HIGHER_MATCHES_MORE)


def test_match_converts_to_loss_only_on_unit_scale():
    a = Evaluation(0.8, SWEET, "pkg:sweet@v1")
    loss = convert_direction(a, Direction.HIGHER_DEVIATES_MORE)
    assert loss.value == pytest.approx(0.2) and loss.spec.direction is Direction.HIGHER_DEVIATES_MORE
    assert convert_direction(loss, Direction.HIGHER_MATCHES_MORE).value == pytest.approx(0.8)
    unbounded = Evaluation(-3.0, EvaluationSpec(Scale("负平方距离", None, 0.0), Direction.HIGHER_MATCHES_MORE), "pkg:t@v1")
    with pytest.raises(ConversionError):
        convert_direction(unbounded, Direction.HIGHER_DEVIATES_MORE)


def test_unknown_stays_unknown_and_is_not_zero():
    u = Evaluation(None, SWEET, "pkg:sweet@v1")
    assert not u.known
    assert convert_direction(u, Direction.HIGHER_DEVIATES_MORE).value is None
    with pytest.raises(ValueError):
        difference(u, Evaluation(0.5, SWEET, "pkg:sweet@v1"))


def test_different_rulers_cannot_be_subtracted():
    """v0.14 案例：不能拿颜色的 0.9 减去甜味的 0.8，称“跨包损失为 0.1”。"""
    sweet = Evaluation(0.8, SWEET, "pkg:sweet@v1")
    red = Evaluation(0.9, RED, "pkg:color@v1")
    with pytest.raises(ConversionError):
        difference(red, sweet)
    with pytest.raises(ConversionError):  # 同一把尺子名，但参考框架不同，也不能直接比
        check_same_ruler(Evaluation(0.8, SWEET, "pkg:sweet@v1"), Evaluation(0.7, SWEET, "pkg:sweet@v2"))
    assert difference(Evaluation(0.8, SWEET, "pkg:sweet@v1"), Evaluation(0.5, SWEET, "pkg:sweet@v1")) == pytest.approx(0.3)


def test_values_must_fit_the_ruler():
    with pytest.raises(ValueError):
        Evaluation(1.2, SWEET, "pkg:sweet@v1")
    with pytest.raises(ValueError):
        Evaluation(float("nan"), SWEET, "pkg:sweet@v1")
    with pytest.raises(ValueError):
        Evaluation(0.5, SWEET, "")
    with pytest.raises(ValueError):
        EvaluationSpec.from_dict({"scale": {"name": "x"}})


def test_round_trip():
    a = Evaluation(0.25, SWEET, "pkg:sweet@v3")
    assert Evaluation.from_dict(a.to_dict()) == a
