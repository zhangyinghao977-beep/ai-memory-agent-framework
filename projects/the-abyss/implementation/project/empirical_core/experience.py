"""经验／溯源记录（名词解释 v0.14 第一节、v0.8 来源边界、v0.9 逆向形成；架构图谱 0.3“经验”节点）。

v0.14：经验 → 拆解学习 → 记忆。本模块登记的是“经验”本身，即每一次发生或接收的出处、位置、时间与绑定。
它是溯源依据，不是形成后的记忆（形成后的记忆见 memory.py）。
2026-10-27 之前本模块叫 memory.py／EventMemory，按 v0.14 改名，因为“登记经历不等于形成记忆”。

要点：
- 一条记录是一次发生；相同内容共享存储，但不同发生不合并。
- 来源类型与核实状态分开：收到陈述 ≠ 已确认陈述中的事发生；推导候选被保存 ≠ 被验证。
- 工具层分开登记描述、计划和已执行结果；只有已执行结果和观察能当核实证据。
- 解释是另一条记录，用 INTERPRETS 链接到原记录。
- 只能链接到更早登记的记录，所以一次预测的输入不可能包含它之后的反馈。
- 可以引用知识包的某个版本（知识 → 经验：实践用了哪个包）。
- 回忆（RECALL）只能经 memory.py 登记，计算经历（COMPUTATION）只能经 calls.py 登记，保证它们带着各自的指向。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional, Sequence

from .store import Store, now_iso


class SourceType(str, Enum):
    EXTERNAL_STATEMENT = "EXTERNAL_STATEMENT"    # 收到的语料、对话、文档：只说明“有人这样说”
    OBSERVATION = "OBSERVATION"                  # 系统自身观察到的现象
    TOOL_DESCRIPTION = "TOOL_DESCRIPTION"        # 操作描述：说明怎么做，不是已发生的操作
    TOOL_PLAN = "TOOL_PLAN"                      # 尝试计划：预期结果不能冒充已发生结果
    TOOL_EXECUTION = "TOOL_EXECUTION"            # 工具层实际执行及其结果（知识 → 经验）
    CANDIDATE_INFERENCE = "CANDIDATE_INFERENCE"  # 模型推导出的候选
    COMPUTATION = "COMPUTATION"                  # why 的一次计算经历（calls.py）：输出只是候选
    RECALL = "RECALL"                            # 回忆／重演（记忆 → 经验）：发生回忆是当前事件，被回忆的内容不因此成为外部事实


# 核实事实的证据：只认观察和实际执行。
EVIDENCE_SOURCES = frozenset({SourceType.OBSERVATION, SourceType.TOOL_EXECUTION})
# 训练／修正的反馈：必须来自外部。外部陈述可以当教学反馈（例如用户告诉正确答案），但不能当核实事实的证据。
EXTERNAL_FEEDBACK_SOURCES = frozenset({SourceType.EXTERNAL_STATEMENT, SourceType.OBSERVATION, SourceType.TOOL_EXECUTION})
# 只能经专门接口登记的来源类型。
_SPECIAL_SOURCES = {SourceType.COMPUTATION: "calls.py 的 CallLog.record_call", SourceType.RECALL: "memory.py 的 MemoryLayer.recall"}


class Relation(str, Enum):
    INPUT = "input"                # 被当作本次计算的输入
    PART_OF = "part_of"            # 组成关系
    INTERPRETS = "interprets"      # 本记录是对目标记录的解释
    FEEDBACK_FOR = "feedback_for"  # 本记录是对目标计算或预测的反馈
    DERIVED_FROM = "derived_from"  # 其他派生关系


class PackageUse(str, Enum):
    APPLIED = "applied"  # 实践中运用了这个包的知识（知识 → 经验）
    INPUT = "input"      # 作为本次计算或组合的素材
    CALLED = "called"    # 调用了这个包登记的计算（calls.py）


class Verification(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"


@dataclass(frozen=True)
class Experience:
    experience_id: int
    chain_id: str
    source_type: SourceType
    content: str
    origin: str
    occurred_at: Optional[str]
    position: Optional[dict]
    binding: Optional[dict]
    recorded_at: Optional[str] = None  # 登记时间；与发生时间 occurred_at 分开（v0.15）


class ExperienceLog:
    def __init__(self, store: Store):
        self.store = store

    def record(
        self,
        *,
        chain_id: str,
        source_type: SourceType,
        content: str,
        origin: str,
        occurred_at: Optional[str] = None,
        position: Optional[dict] = None,
        binding: Optional[dict] = None,
        links: Iterable[tuple[int, Relation]] = (),
        package_refs: Iterable[tuple[str, int, PackageUse]] = (),
    ) -> int:
        """登记一次发生。链接目标必须是已登记的更早记录；引用的知识包版本必须存在。"""
        source_type = SourceType(source_type)
        if source_type in _SPECIAL_SOURCES:
            raise ValueError(f"{source_type.value} 只能经 {_SPECIAL_SOURCES[source_type]} 登记")
        return self._record(chain_id=chain_id, source_type=source_type, content=content, origin=origin,
                            occurred_at=occurred_at, position=position, binding=binding,
                            links=links, package_refs=package_refs)

    def _record(self, *, chain_id, source_type, content, origin, occurred_at=None, position=None,
                binding=None, links=(), package_refs=()) -> int:
        """供 memory.py 与 calls.py 在同一事务内调用；不检查专用来源类型。"""
        source_type = SourceType(source_type)
        links = [(int(t), Relation(r)) for t, r in links]
        package_refs = [(str(p), int(v), PackageUse(u)) for p, v, u in package_refs]
        with self.store.transaction() as c:
            for target, _ in links:
                if not self.exists(target):
                    raise ValueError(f"链接目标记录 {target} 不存在（只能链接到更早登记的记录）")
            for pid, ver, _ in package_refs:
                if c.execute("SELECT 1 FROM package_versions WHERE package_id = ? AND version = ?",
                             (pid, ver)).fetchone() is None:
                    raise ValueError(f"知识包版本 {pid}@{ver} 不存在")
            h = self.store.put_content(content)
            cur = c.execute(
                "INSERT INTO experiences(chain_id, source_type, content_hash, origin, occurred_at, recorded_at,"
                " position_json, binding_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (chain_id, source_type.value, h, origin, occurred_at, now_iso(), _dump(position), _dump(binding)),
            )
            experience_id = cur.lastrowid
            c.executemany(
                "INSERT INTO experience_links(experience_id, target_experience_id, relation) VALUES (?, ?, ?)",
                [(experience_id, t, r.value) for t, r in links],
            )
            c.executemany(
                "INSERT INTO experience_package_refs(experience_id, package_id, version, use) VALUES (?, ?, ?, ?)",
                [(experience_id, p, v, u.value) for p, v, u in package_refs],
            )
        return experience_id

    # ---------- 读取 ----------

    def get(self, experience_id: int) -> Experience:
        row = self.store.conn.execute(
            "SELECT e.experience_id, e.chain_id, e.source_type, c.content, e.origin, e.occurred_at,"
            " e.position_json, e.binding_json, e.recorded_at"
            " FROM experiences e JOIN contents c ON c.content_hash = e.content_hash WHERE e.experience_id = ?",
            (experience_id,),
        ).fetchone()
        if row is None:
            raise KeyError(experience_id)
        return _experience(row)

    def chain(self, chain_id: str) -> list[Experience]:
        rows = self.store.conn.execute(
            "SELECT e.experience_id, e.chain_id, e.source_type, c.content, e.origin, e.occurred_at,"
            " e.position_json, e.binding_json, e.recorded_at"
            " FROM experiences e JOIN contents c ON c.content_hash = e.content_hash"
            " WHERE e.chain_id = ? ORDER BY e.experience_id",
            (chain_id,),
        ).fetchall()
        return [_experience(r) for r in rows]

    def links_from(self, experience_id: int, relation: Optional[Relation] = None) -> list[tuple[int, Relation]]:
        sql = "SELECT target_experience_id, relation FROM experience_links WHERE experience_id = ?"
        args: list[Any] = [experience_id]
        if relation is not None:
            sql += " AND relation = ?"
            args.append(Relation(relation).value)
        return [(t, Relation(r)) for t, r in self.store.conn.execute(sql + " ORDER BY target_experience_id", args)]

    def links_to(self, experience_id: int, relation: Optional[Relation] = None) -> list[tuple[int, Relation]]:
        sql = "SELECT experience_id, relation FROM experience_links WHERE target_experience_id = ?"
        args: list[Any] = [experience_id]
        if relation is not None:
            sql += " AND relation = ?"
            args.append(Relation(relation).value)
        return [(e, Relation(r)) for e, r in self.store.conn.execute(sql + " ORDER BY experience_id", args)]

    def package_refs(self, experience_id: int) -> list[tuple[str, int, PackageUse]]:
        return [(p, v, PackageUse(u)) for p, v, u in self.store.conn.execute(
            "SELECT package_id, version, use FROM experience_package_refs WHERE experience_id = ?"
            " ORDER BY package_id, version, use", (experience_id,))]

    def experiences_using(self, package_id: str, version: Optional[int] = None) -> list[int]:
        sql = "SELECT DISTINCT experience_id FROM experience_package_refs WHERE package_id = ?"
        args: list[Any] = [package_id]
        if version is not None:
            sql += " AND version = ?"
            args.append(version)
        return [r[0] for r in self.store.conn.execute(sql + " ORDER BY experience_id", args)]

    def exists(self, experience_id: int) -> bool:
        return self.store.conn.execute(
            "SELECT 1 FROM experiences WHERE experience_id = ?", (experience_id,)).fetchone() is not None

    # ---------- 核实 ----------

    def verify(self, experience_id: int, status: Verification, evidence_ids: Sequence[int], note: str) -> None:
        """追加一条核实记录。证据必须是其他的、已登记的观察或实际执行记录。"""
        status = Verification(status)
        if status is not Verification.UNVERIFIED and not evidence_ids:
            raise ValueError("SUPPORTED／CONTRADICTED 必须给出证据记录")
        self.get(experience_id)
        for ev in evidence_ids:
            if ev == experience_id:
                raise ValueError("记录不能作为自己的证据")
            src = self.get(ev).source_type
            if src not in EVIDENCE_SOURCES:
                raise ValueError(f"记录 {ev} 的来源是 {src.value}，不能作为核实证据")
        with self.store.transaction() as c:
            c.execute(
                "INSERT INTO verifications(experience_id, status, evidence_json, note) VALUES (?, ?, ?, ?)",
                (experience_id, status.value, json.dumps(list(evidence_ids)), note),
            )

    def verification(self, experience_id: int) -> Verification:
        """当前核实状态＝最后一条核实记录；没有记录即 UNVERIFIED。"""
        row = self.store.conn.execute(
            "SELECT status FROM verifications WHERE experience_id = ? ORDER BY verification_id DESC LIMIT 1",
            (experience_id,),
        ).fetchone()
        return Verification(row[0]) if row else Verification.UNVERIFIED

    def verification_history(self, experience_id: int) -> list[dict]:
        rows = self.store.conn.execute(
            "SELECT status, evidence_json, note FROM verifications WHERE experience_id = ? ORDER BY verification_id",
            (experience_id,),
        ).fetchall()
        return [{"status": s, "evidence": json.loads(e), "note": n} for s, e, n in rows]

    def require_external_feedback(self, ids: Sequence[int], what: str) -> None:
        """修正（R1／R2／来源修正）的依据：必须存在、来自外部，且没有被核实为相反。"""
        if not ids:
            raise ValueError(f"{what} 必须给出外部反馈记录作为依据")
        for ev in ids:
            if not self.exists(ev):
                raise ValueError(f"依据记录 {ev} 不存在")
            src = self.get(ev).source_type
            if src not in EXTERNAL_FEEDBACK_SOURCES:
                raise ValueError(f"记录 {ev} 的来源是 {src.value}，不是外部反馈，不能作为 {what} 的依据")
            if self.verification(ev) is Verification.CONTRADICTED:
                raise ValueError(f"记录 {ev} 已被核实为相反，不能作为 {what} 的依据")


def _dump(obj: Optional[dict]) -> Optional[str]:
    return None if obj is None else json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _experience(row: tuple) -> Experience:
    experience_id, chain_id, src, content, origin, occurred_at, pos, bind, recorded_at = row
    return Experience(
        experience_id=experience_id,
        chain_id=chain_id,
        source_type=SourceType(src),
        content=content,
        origin=origin,
        occurred_at=occurred_at,
        position=None if pos is None else json.loads(pos),
        binding=None if bind is None else json.loads(bind),
        recorded_at=recorded_at,
    )
