"""局部修正 R 的统一记录（名词解释 v0.14 第十三节“R 修正返回”；架构图谱 0.3“偏差与修正 R”节点）。

图谱：“修正箭头不是装饰：需要记录目标、依据与修订内容。”v0.14 要求按错误归属分别接回：

| 种类 | 修正对象 | 入口 |
|---|---|---|
| R1_INPUT_BINDING | 外部入参／绑定（S、EA）：由事件链侧修正传入的区别 | 本模块 correct_input_binding |
| R2_PACKAGE_EVALUATION | 包内评价（KA） | registry.update_computation |
| R3_REFERENCE_STRUCTURE | 参考／结构（P、K）：裁剪重组 | registry.crop |
| SOURCE_RECORD | 来源记录（经验／溯源） | 本模块 correct_source_record |

所有修正只追加记录，不改动原记录；原记录与修正记录都可回查。
记忆准入（记忆边界阀）与 FSM 映射的修正尚未实现，因为阀门与 FSM 本身还没有接口（对照报告 N2、第四组）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .experience import ExperienceLog
from .store import Store

R1_REVISION_KEYS = frozenset({"inputs", "context", "package_choice", "binding"})
SOURCE_REVISION_KEYS = frozenset({"origin", "occurred_at", "position", "binding", "source_type"})


class CorrectionKind(str, Enum):
    R1_INPUT_BINDING = "R1_INPUT_BINDING"
    R2_PACKAGE_EVALUATION = "R2_PACKAGE_EVALUATION"
    R3_REFERENCE_STRUCTURE = "R3_REFERENCE_STRUCTURE"
    SOURCE_RECORD = "SOURCE_RECORD"


@dataclass(frozen=True)
class Correction:
    correction_id: int
    kind: CorrectionKind
    target: dict
    basis: list[int]
    revision: dict
    reason: str


def insert_correction(c, kind: CorrectionKind, target: dict, basis: Sequence[int], revision: dict, reason: str) -> int:
    """在调用方的事务里写一条修正记录（registry 的 R2／R3 也用它）。"""
    cur = c.execute(
        "INSERT INTO corrections(kind, target_json, basis_json, revision_json, reason) VALUES (?, ?, ?, ?, ?)",
        (CorrectionKind(kind).value, _dumps(target), json.dumps([int(b) for b in basis]), _dumps(revision), reason),
    )
    return cur.lastrowid


class Corrections:
    def __init__(self, store: Store, experiences: ExperienceLog):
        self.store = store
        self.experiences = experiences

    def correct_input_binding(self, call_id: int, revision: dict, basis_ids: Sequence[int], reason: str) -> int:
        """R1：固定包与计算版本，修正某次调用的入参、上下文、选包或绑定。不改包，也不改原调用记录。"""
        if self.store.conn.execute("SELECT 1 FROM calls WHERE call_id = ?", (call_id,)).fetchone() is None:
            raise ValueError(f"调用 {call_id} 不存在")
        _check_revision(revision, R1_REVISION_KEYS)
        self.experiences.require_external_feedback(basis_ids, "R1 入参／绑定修正")
        with self.store.transaction() as c:
            return insert_correction(c, CorrectionKind.R1_INPUT_BINDING, {"call_id": call_id}, basis_ids, revision, reason)

    def correct_source_record(self, experience_id: int, revision: dict, basis_ids: Sequence[int], reason: str) -> int:
        """来源记录修正：原记录保留，修正内容另记。"""
        if not self.experiences.exists(experience_id):
            raise ValueError(f"经验记录 {experience_id} 不存在")
        _check_revision(revision, SOURCE_REVISION_KEYS)
        if experience_id in basis_ids:
            raise ValueError("记录不能作为修正自己的依据")
        self.experiences.require_external_feedback(basis_ids, "来源记录修正")
        with self.store.transaction() as c:
            return insert_correction(c, CorrectionKind.SOURCE_RECORD, {"experience_id": experience_id},
                                     basis_ids, revision, reason)

    def for_target(self, kind: CorrectionKind, target: dict) -> list[Correction]:
        rows = self.store.conn.execute(
            "SELECT correction_id, kind, target_json, basis_json, revision_json, reason FROM corrections"
            " WHERE kind = ? AND target_json = ? ORDER BY correction_id",
            (CorrectionKind(kind).value, _dumps(target)),
        ).fetchall()
        return [_correction(r) for r in rows]

    def all(self) -> list[Correction]:
        rows = self.store.conn.execute(
            "SELECT correction_id, kind, target_json, basis_json, revision_json, reason FROM corrections"
            " ORDER BY correction_id").fetchall()
        return [_correction(r) for r in rows]


def _check_revision(revision: dict, allowed: frozenset) -> None:
    if not isinstance(revision, dict) or not revision:
        raise ValueError("修订内容不能为空")
    extra = set(revision) - allowed
    if extra:
        raise ValueError(f"修订内容含有不属于这类修正的字段：{sorted(extra)}；允许：{sorted(allowed)}")


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _correction(row: tuple) -> Correction:
    cid, kind, target, basis, revision, reason = row
    return Correction(cid, CorrectionKind(kind), json.loads(target), json.loads(basis), json.loads(revision), reason)
