"""why 的计算经历：一次包内计算调用的记录（名词解释 v0.14 4.1、4.3；图 v0.3 R；KA 图 ③④⑤）。

登记一次调用：需求、上下文、哪个包和版本、登记的计算、实际入参、候选行、选择／拒绝、未知与结果。
它是溯源依据（经验的一种，来源类型 COMPUTATION），不是记忆；要成为记忆，还要经过拆解学习（memory.py）。
v0.16／v0.17 把 why 用来学习映射的语料载体更名为“学习材料库”：计算经历可以成为它的来源，
但“拿来训练”不等于“保存为可追溯记忆”。学习材料库本身尚未实现。
事后反馈另记一条外部经验，用 FEEDBACK_FOR 指向这次调用；R2 只能依据这样的反馈（registry.update_computation）。

与计算登记和记忆边界阀相连（v0.14 连续性审查原则）：
- 每次调用必须写明在哪个工作缓存（valve.py）里运行；调用的包版本必须已进入这个缓存
  （attention 只在给定范围内计算，不自己裁定世界边界）。也可以写明它服务于事件链的哪一次发生。
- 入参必须正好是登记的那些输入；未知要写 {"kind": "unknown"}，不能省略。
- 候选行契约（v0.14 第五节 5）：每行＝包引用＋成员身份＋该包参考系下的存异差异＋当前评价。
  差异不由调用方填写，而是从知识库该版本的存异结果读出；评价的尺子与方向用登记的 output_evaluation。
- 没有答案时写明原因：缺依据、缺条件、无合适候选、资源停止（停止只表示本轮结束，不表示搜索完备）。
- 未被采用的候选记为 REJECTED（本次未采用）或 UNDECIDED，不等于不成立。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional, Sequence

from .experience import EXTERNAL_FEEDBACK_SOURCES, ExperienceLog, PackageUse, Relation, SourceType
from .registry import UNKNOWN, PackageRegistry, frame_name
from .relation_eval import Evaluation, EvaluationSpec
from .store import Store
from .valve import ItemKind, MemoryValve


class Decision(str, Enum):
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"      # 本次未采用，不等于不成立
    UNDECIDED = "UNDECIDED"


class NoAnswerReason(str, Enum):
    MISSING_EVIDENCE = "MISSING_EVIDENCE"            # 缺依据
    MISSING_CONDITION = "MISSING_CONDITION"          # 缺条件（入参或上下文不足）
    NO_SUITABLE_CANDIDATE = "NO_SUITABLE_CANDIDATE"  # 无合适候选
    RESOURCE_STOP = "RESOURCE_STOP"                  # 资源停止：本轮结束，不表示搜索完备或知识收敛


@dataclass(frozen=True)
class CandidateInput:
    position: int              # 本包成员的位置
    value: Optional[float]     # 当前评价；None＝未知，不是 0
    decision: Decision = Decision.UNDECIDED


@dataclass(frozen=True)
class CandidateRow:
    row: int
    package_id: str
    version: int
    position: int
    material_id: str
    difference: dict           # 来自知识库该版本的存异结果
    evaluation: Evaluation
    decision: Decision


@dataclass(frozen=True)
class Call:
    call_id: int
    experience_id: int
    cache_id: int
    occurrence_id: Optional[int]
    package_id: str
    version: int
    computation_id: str
    purpose: str
    context: Any
    inputs: dict
    rows: list[CandidateRow]
    no_answer: Optional[dict]


class CallLog:
    def __init__(self, store: Store, experiences: ExperienceLog, registry: PackageRegistry, valve: MemoryValve):
        self.store = store
        self.experiences = experiences
        self.registry = registry
        self.valve = valve

    def record_call(
        self,
        *,
        chain_id: str,
        cache_id: int,
        package_id: str,
        purpose: str,
        context: Any,
        inputs: dict,
        candidates: Sequence[CandidateInput],
        origin: str,
        version: Optional[int] = None,
        occurrence_id: Optional[int] = None,
        no_answer: Optional[tuple[NoAnswerReason, str]] = None,
        occurred_at: Optional[str] = None,
        links: Iterable[tuple[int, Relation]] = (),
    ) -> int:
        """登记一次包内计算调用，返回调用编号。"""
        if self.registry.status(package_id) != "ACTIVE":
            raise ValueError(f"包 {package_id} 已裁剪，不能再调用")
        pv = self.registry.latest(package_id) if version is None else self.registry.version(package_id, version)
        if self.valve.cache_status(cache_id) != "OPEN":
            raise ValueError(f"工作缓存 {cache_id} 已关闭")
        if not self.valve.is_entered(cache_id, ItemKind.PACKAGE, (package_id, pv.version)):
            raise ValueError(f"{pv.frame} 没有进入工作缓存 {cache_id}，不能在本轮调用")
        if occurrence_id is not None:
            row = self.store.conn.execute("SELECT cache_id FROM occurrences WHERE occurrence_id = ?",
                                          (occurrence_id,)).fetchone()
            if row is None or row[0] != cache_id:
                raise ValueError(f"发生 {occurrence_id} 不存在或不在工作缓存 {cache_id}")
        comp = pv.computation
        _check_inputs(comp, inputs)
        spec = EvaluationSpec.from_dict(comp["output_evaluation"])

        positions = [int(c.position) for c in candidates]
        if len(positions) != len(set(positions)):
            raise ValueError("同一成员在一次调用里只能有一行候选")
        rows = []
        for i, cand in enumerate(candidates):
            if not 0 <= cand.position < len(pv.members):
                raise ValueError(f"成员位置 {cand.position} 不在 {package_id}@v{pv.version} 中")
            m = pv.members[cand.position]
            rows.append(CandidateRow(i, package_id, pv.version, m.position, m.material_id, m.difference,
                                     Evaluation(cand.value, spec, pv.frame), Decision(cand.decision)))
        selected = [r for r in rows if r.decision is Decision.SELECTED]
        no_answer_rec = None
        if no_answer is not None:
            reason, note = no_answer
            no_answer_rec = {"reason": NoAnswerReason(reason).value, "note": note}
            if selected:
                raise ValueError("写了“没有答案”，就不能同时有被选中的候选")
        if selected and any(not r.evaluation.known for r in selected):
            raise ValueError("被选中的候选必须有已知评价；评价未知时请写明没有答案的原因")

        summary = {"package": pv.frame, "computation_id": comp["computation_id"], "purpose": purpose,
                   "cache_id": cache_id, "occurrence_id": occurrence_id,
                   "context": context, "inputs": inputs, "rows": [_row_dict(r) for r in rows],
                   "no_answer": no_answer_rec}
        with self.store.transaction() as c:
            mark = self.valve.log_mark(cache_id)
            ev = self.experiences._record(
                chain_id=chain_id, source_type=SourceType.COMPUTATION, content=_dumps(summary), origin=origin,
                occurred_at=occurred_at, links=links, package_refs=[(package_id, pv.version, PackageUse.CALLED)])
            cur = c.execute(
                "INSERT INTO calls(experience_id, cache_id, cache_log_mark, occurrence_id, package_id, version,"
                " computation_id, purpose, context_json, inputs_json, no_answer_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ev, cache_id, mark, occurrence_id, package_id, pv.version, comp["computation_id"], purpose,
                 _dumps(context), _dumps(inputs), None if no_answer_rec is None else _dumps(no_answer_rec)),
            )
            call_id = cur.lastrowid
            c.executemany(
                "INSERT INTO call_candidates(call_id, row, position, material_id, difference_json, evaluation_json,"
                " decision) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(call_id, r.row, r.position, r.material_id, _dumps(r.difference), _dumps(r.evaluation.to_dict()),
                  r.decision.value) for r in rows],
            )
        return call_id

    def feedback(self, call_id: int, *, source_type: SourceType, content: str, origin: str,
                 chain_id: Optional[str] = None, occurred_at: Optional[str] = None) -> int:
        """登记对某次调用的事后反馈（外部经验），返回经验编号。反馈不会混进当时的入参。"""
        source_type = SourceType(source_type)
        if source_type not in EXTERNAL_FEEDBACK_SOURCES:
            raise ValueError(f"{source_type.value} 不是外部反馈")
        call = self.get(call_id)
        chain = chain_id or self.experiences.get(call.experience_id).chain_id
        return self.experiences.record(chain_id=chain, source_type=source_type, content=content, origin=origin,
                                       occurred_at=occurred_at, links=[(call.experience_id, Relation.FEEDBACK_FOR)])

    def get(self, call_id: int) -> Call:
        c = self.store.conn
        row = c.execute(
            "SELECT experience_id, cache_id, occurrence_id, package_id, version, computation_id, purpose, context_json,"
            " inputs_json, no_answer_json FROM calls WHERE call_id = ?", (call_id,)).fetchone()
        if row is None:
            raise KeyError(call_id)
        ev, cache_id, occurrence_id, pid, ver, comp_id, purpose, ctx, inputs, no_answer = row
        rows = [
            CandidateRow(r, pid, ver, pos, mat, json.loads(diff), Evaluation.from_dict(json.loads(evj)), Decision(dec))
            for r, pos, mat, diff, evj, dec in c.execute(
                "SELECT row, position, material_id, difference_json, evaluation_json, decision FROM call_candidates"
                " WHERE call_id = ? ORDER BY row", (call_id,))
        ]
        return Call(call_id, ev, cache_id, occurrence_id, pid, ver, comp_id, purpose, json.loads(ctx),
                    json.loads(inputs), rows, None if no_answer is None else json.loads(no_answer))

    def visible_view(self, call_id: int) -> dict:
        """重建调用当时工作缓存的可见视图（v0.15 时间上的可回溯）：当时进入了哪些世界、包、记忆、经验。

        之后缓存里再进入或退出的东西，不会改变这里的结果。
        """
        row = self.store.conn.execute("SELECT cache_id, cache_log_mark FROM calls WHERE call_id = ?", (call_id,)).fetchone()
        if row is None:
            raise KeyError(call_id)
        cache_id, mark = row
        return {kind.value: self.valve.entered(cache_id, kind, as_of=mark) for kind in ItemKind}

    def call_of_experience(self, experience_id: int) -> Optional[int]:
        row = self.store.conn.execute("SELECT call_id FROM calls WHERE experience_id = ?", (experience_id,)).fetchone()
        return None if row is None else row[0]

    def calls_answered_by(self, experience_id: int) -> list[int]:
        """这条经验作为反馈所对应的调用编号。"""
        return [r[0] for r in self.store.conn.execute(
            "SELECT c.call_id FROM experience_links l JOIN calls c ON c.experience_id = l.target_experience_id"
            " WHERE l.experience_id = ? AND l.relation = ? ORDER BY c.call_id",
            (experience_id, Relation.FEEDBACK_FOR.value))]


def _check_inputs(computation: dict, inputs: dict) -> None:
    registered = [item["name"] for item in computation["inputs"]]
    if not isinstance(inputs, dict):
        raise ValueError("入参必须是 {输入名: 值} 的记录")
    missing = [n for n in registered if n not in inputs]
    extra = [n for n in inputs if n not in registered]
    if missing:
        raise ValueError(f"缺少登记的输入：{missing}（未知请写 {UNKNOWN}，不要省略）")
    if extra:
        raise ValueError(f"有未登记的输入：{extra}（相同可见入参不能让内部凭空识别未传入的差异）")
    for name, value in inputs.items():
        if value is None:
            raise ValueError(f"输入 {name} 是 null；未知请写 {UNKNOWN}")


def _row_dict(r: CandidateRow) -> dict:
    return {"row": r.row, "package": frame_name(r.package_id, r.version), "position": r.position,
            "material_id": r.material_id, "difference": r.difference, "evaluation": r.evaluation.to_dict(),
            "decision": r.decision.value}


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
