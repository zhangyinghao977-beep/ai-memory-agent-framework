"""关系评价的流转接口（名词解释 v0.14 第三节“损失／偏差／置信度”、第二节“尺子变化”、第五节 5 候选行契约）。

v0.14：损失、偏差、置信度、吻合度大多指同一件事——关系的吻合或偏离程度；差别只在流转时体现：
比较谁、用哪把尺子、数值朝哪个方向读、怎样交给下一步。

本模块不定义评价算法，只管流转时必须说清的东西：
- 每个评价都带尺子（scale）、方向（direction）和参考框架（frame，例如哪个包的哪个版本）。
- 没算出来就记未知（value=None），不写 0。
- 方向转换只按登记过的约定进行：尺子范围是 [0, 1] 时，可用“损失 = 1 − 吻合度”。其他情况没有登记的转换，直接拒绝。
- 不同尺子或不同参考框架的值不能直接相减、比较；要先有登记的转换（本模块不提供跨尺子转换）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ConversionError(ValueError):
    """没有登记的转换：不同尺子、不同参考或无界尺度上的方向转换。"""


class Direction(str, Enum):
    HIGHER_MATCHES_MORE = "higher_matches_more"    # 越大越吻合（吻合度／置信度的读法）
    HIGHER_DEVIATES_MORE = "higher_deviates_more"  # 越大越偏离（损失／偏差的读法）


@dataclass(frozen=True)
class Scale:
    name: str                     # 尺子：比较维度或评价接口的名字
    low: Optional[float] = None   # None 表示无下界
    high: Optional[float] = None  # None 表示无上界

    def __post_init__(self):
        if not self.name:
            raise ValueError("尺子必须有名字")
        if self.low is not None and self.high is not None and not self.low < self.high:
            raise ValueError("尺子范围必须满足 low < high")

    @property
    def unit_interval(self) -> bool:
        return self.low == 0 and self.high == 1

    def to_dict(self) -> dict:
        return {"name": self.name, "low": self.low, "high": self.high}


@dataclass(frozen=True)
class EvaluationSpec:
    """计算登记里的“输出解释”：这次计算的评价用哪把尺子、朝哪个方向读。"""
    scale: Scale
    direction: Direction

    def to_dict(self) -> dict:
        return {"scale": self.scale.to_dict(), "direction": self.direction.value}

    @staticmethod
    def from_dict(d: dict) -> "EvaluationSpec":
        if not isinstance(d, dict) or "scale" not in d or "direction" not in d:
            raise ValueError("评价登记必须写明 scale（尺子）与 direction（方向）")
        s = d["scale"]
        if not isinstance(s, dict) or "name" not in s:
            raise ValueError("scale 必须是带 name 的记录")
        return EvaluationSpec(Scale(s["name"], s.get("low"), s.get("high")), Direction(d["direction"]))


@dataclass(frozen=True)
class Evaluation:
    value: Optional[float]  # None＝未知（未计算或缺依据），不是 0
    spec: EvaluationSpec
    frame: str              # 参考框架，例如 "pkg:<包>@v<版本>"

    def __post_init__(self):
        if not self.frame:
            raise ValueError("评价必须写明参考框架")
        if self.value is None:
            return
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or math.isnan(self.value):
            raise ValueError("评价值必须是数，未知请用 None")
        s = self.spec.scale
        if (s.low is not None and self.value < s.low) or (s.high is not None and self.value > s.high):
            raise ValueError(f"评价值 {self.value} 超出尺子 {s.name} 的范围")

    @property
    def known(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict:
        return {"value": self.value, "known": self.known, "frame": self.frame, **self.spec.to_dict()}

    @staticmethod
    def from_dict(d: dict) -> "Evaluation":
        return Evaluation(d["value"], EvaluationSpec.from_dict(d), d["frame"])


def convert_direction(ev: Evaluation, target: Direction) -> Evaluation:
    """同一评价换一种读法。只在 [0, 1] 尺子上用“1 − 值”的登记约定；未知仍是未知。"""
    target = Direction(target)
    if ev.spec.direction is target:
        return ev
    if not ev.spec.scale.unit_interval:
        raise ConversionError(f"尺子 {ev.spec.scale.name} 不是 [0, 1]，没有登记的方向转换")
    value = None if ev.value is None else 1 - ev.value
    return Evaluation(value, EvaluationSpec(ev.spec.scale, target), ev.frame)


def check_same_ruler(a: Evaluation, b: Evaluation) -> None:
    """两个评价能否直接比较：尺子、方向与参考框架都要相同。"""
    if a.spec.scale != b.spec.scale:
        raise ConversionError(f"尺子不同（{a.spec.scale.name} 与 {b.spec.scale.name}），需要登记的转换")
    if a.frame != b.frame:
        raise ConversionError(f"参考框架不同（{a.frame} 与 {b.frame}），不能直接比较或相减")
    if a.spec.direction is not b.spec.direction:
        raise ConversionError("方向不同，先用 convert_direction 统一读法")


def difference(a: Evaluation, b: Evaluation) -> float:
    """同一把尺子、同一参考下两个已知评价的差。"""
    check_same_ruler(a, b)
    if not (a.known and b.known):
        raise ValueError("有评价未知，不能相减（未知不是 0）")
    return a.value - b.value
