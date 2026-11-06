"""事件链＝广义 AST（名词解释 v0.14 第五节 1、4.1、4.2；设计稿 v0.3 第二节）。

两层，相连但不混同：
- 结构层（ProcessStructures）：可复用的过程。节点有种类、slot（带角色／类型约束）和子节点；
  父节点用对应表把子节点的 slot 接到自己的 slot 上，接到同一个父 slot 的就是“同一个对象”，
  例如 顺序(洗(X), 吃(X))。节点被别处引用就是折叠使用，读子节点就是展开。只追加版本。
- 发生层（Occurrences）：每一次实际发生。指向一个结构节点版本，属于一个工作缓存（valve.py），
  由一条经验或记忆作依据——经验的来源类型说明它是计划、已执行、观察还是别人说的，计划不冒充已发生。
  槽位绑定有三种状态：已绑定、候选、缺口；不知道的不强行补。

3×3 互转在设计中是事件链流转过程的计算因子，不是节点上的固定标签，
而是每一步流转时实际发生的转换：在发生上记一条流转步（从哪个面到哪个面、输入、输出）。
各配对具体怎么算，文档写着“待定”，这里只记录、不代填。

节点种类是工作解释（可以再加）；折叠／展开的语义等价、AST 与 attention 的具体编码，都未实现。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

from .experience import EVIDENCE_SOURCES, ExperienceLog
from .store import Store
from .valve import ItemKind, MemoryValve


class NodeKind(str, Enum):
    OPERATION = "OPERATION"  # 操作（叶子）
    SEQUENCE = "SEQUENCE"    # 顺序
    BRANCH = "BRANCH"        # 分支：几种可能
    LOOP = "LOOP"            # 循环：一个重复的部分
    CONDITION = "CONDITION"  # 条件：条件满足后才做；必须写明条件


# 每种节点允许的子节点个数（最少, 最多；None 表示不限）。
CHILD_COUNTS = {
    NodeKind.OPERATION: (0, 0),
    NodeKind.SEQUENCE: (1, None),
    NodeKind.BRANCH: (2, None),
    NodeKind.LOOP: (1, 1),
    NodeKind.CONDITION: (1, 1),
}
REF_KINDS = ("material", "package", "experience", "memory", "literal")


class BindingState(str, Enum):
    BOUND = "BOUND"            # 已绑定一个对象
    CANDIDATES = "CANDIDATES"  # 保留多个候选
    GAP = "GAP"                # 缺口：未知，不强行补


class ConditionState(str, Enum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"


class Face(str, Enum):
    WHAT = "what"
    WHY = "why"
    HOW = "how"


@dataclass(frozen=True)
class ChildRef:
    node_id: str
    version: int
    slot_map: dict = field(default_factory=dict)  # 子节点 slot → 父节点 slot（接到同一个父 slot＝同一个对象）


@dataclass(frozen=True)
class Node:
    node_id: str
    version: int
    kind: NodeKind
    name: str
    slots: dict                # slot → 约束，例如 {"role": "对象", "ref_kinds": ["material"]}
    children: list[ChildRef]
    condition: Optional[str]


@dataclass(frozen=True)
class Binding:
    state: BindingState
    value: Any = None          # BOUND：一个引用；CANDIDATES：引用列表；GAP：None
    inherited: bool = False


def bound(ref: dict) -> Binding:
    return Binding(BindingState.BOUND, ref)


def candidates(*refs: dict) -> Binding:
    if len(refs) < 2:
        raise ValueError("候选至少两个；只有一个就是已绑定")
    return Binding(BindingState.CANDIDATES, list(refs))


def gap() -> Binding:
    return Binding(BindingState.GAP)


@dataclass(frozen=True)
class Occurrence:
    occurrence_id: int
    node_id: str
    version: int
    parent_occurrence_id: Optional[int]
    child_ord: Optional[int]
    cache_id: int
    experience_id: Optional[int]
    memory_id: Optional[int]


class ProcessStructures:
    """结构层：可复用的过程。"""

    def __init__(self, store: Store, experiences: ExperienceLog):
        self.store = store
        self.experiences = experiences

    def define(self, node_id: str, kind: NodeKind, name: str, *, slots: Optional[dict] = None,
               children: Sequence[ChildRef] = (), condition: Optional[str] = None,
               basis_ids: Sequence[int], reason: str) -> Node:
        """登记一个节点的新版本。子节点必须是已登记的版本，所以结构不会成环。"""
        kind = NodeKind(kind)
        slots = dict(slots or {})
        lo, hi = CHILD_COUNTS[kind]
        if len(children) < lo or (hi is not None and len(children) > hi):
            raise ValueError(f"{kind.value} 节点的子节点个数不对：{len(children)}")
        if kind is NodeKind.CONDITION and not condition:
            raise ValueError("条件节点必须写明条件")
        if kind is not NodeKind.CONDITION and condition:
            raise ValueError("只有条件节点写条件")
        for slot, constraint in slots.items():
            _check_constraint(slot, constraint)
        for ch in children:
            child = self.get(ch.node_id, ch.version)
            for child_slot, parent_slot in ch.slot_map.items():
                if child_slot not in child.slots:
                    raise ValueError(f"子节点 {ch.node_id} 没有 slot {child_slot}")
                if parent_slot not in slots:
                    raise ValueError(f"本节点没有 slot {parent_slot}")
        if not basis_ids:
            raise ValueError("登记结构要写明依据")
        for ev in basis_ids:
            if not self.experiences.exists(ev):
                raise ValueError(f"依据记录 {ev} 不存在")
        with self.store.transaction() as c:
            version = (c.execute("SELECT MAX(version) FROM ast_nodes WHERE node_id = ?", (node_id,)).fetchone()[0] or 0) + 1
            c.execute("INSERT INTO ast_nodes(node_id, version, kind, name, condition_text, basis_json, reason)"
                      " VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (node_id, version, kind.value, name, condition, json.dumps(list(basis_ids)), reason))
            c.executemany("INSERT INTO ast_slots(node_id, version, slot, constraint_json) VALUES (?, ?, ?, ?)",
                          [(node_id, version, s, _dumps(cons)) for s, cons in slots.items()])
            c.executemany("INSERT INTO ast_children(node_id, version, ord, child_id, child_version, slot_map_json)"
                          " VALUES (?, ?, ?, ?, ?, ?)",
                          [(node_id, version, i, ch.node_id, ch.version, _dumps(ch.slot_map)) for i, ch in enumerate(children)])
        return self.get(node_id, version)

    def get(self, node_id: str, version: Optional[int] = None) -> Node:
        c = self.store.conn
        if version is None:
            version = c.execute("SELECT MAX(version) FROM ast_nodes WHERE node_id = ?", (node_id,)).fetchone()[0]
        row = c.execute("SELECT kind, name, condition_text FROM ast_nodes WHERE node_id = ? AND version = ?",
                        (node_id, version)).fetchone()
        if row is None:
            raise KeyError((node_id, version))
        kind, name, condition = row
        slots = {s: json.loads(cons) for s, cons in c.execute(
            "SELECT slot, constraint_json FROM ast_slots WHERE node_id = ? AND version = ? ORDER BY slot", (node_id, version))}
        children = [ChildRef(cid, cver, json.loads(sm)) for cid, cver, sm in c.execute(
            "SELECT child_id, child_version, slot_map_json FROM ast_children WHERE node_id = ? AND version = ? ORDER BY ord",
            (node_id, version))]
        return Node(node_id, version, NodeKind(kind), name, slots, children, condition)

    def unfold(self, node_id: str, version: Optional[int] = None) -> dict:
        """展开：沿保留的组成关系读出整棵结构。"""
        n = self.get(node_id, version)
        return {"node": f"{n.node_id}@v{n.version}", "kind": n.kind.value, "name": n.name, "slots": n.slots,
                "condition": n.condition,
                "children": [dict(self.unfold(ch.node_id, ch.version), slot_map=ch.slot_map) for ch in n.children]}

    def used_in(self, node_id: str, version: int) -> list[tuple[str, int]]:
        """哪些结构把这个节点折叠引用为子节点（同一结构可被多处引用，不复制）。"""
        return [(p, v) for p, v in self.store.conn.execute(
            "SELECT DISTINCT node_id, version FROM ast_children WHERE child_id = ? AND child_version = ?"
            " ORDER BY node_id, version", (node_id, version))]


class Occurrences:
    """发生层：每一次实际发生。"""

    def __init__(self, store: Store, experiences: ExperienceLog, structures: ProcessStructures, valve: MemoryValve):
        self.store = store
        self.experiences = experiences
        self.structures = structures
        self.valve = valve

    def occur(self, node_id: str, version: Optional[int] = None, *, cache_id: int,
              experience_id: Optional[int] = None, memory_id: Optional[int] = None,
              parent_occurrence_id: Optional[int] = None, child_ord: Optional[int] = None,
              bindings: Optional[dict[str, Binding]] = None) -> int:
        node = self.structures.get(node_id, version)
        if self.valve.cache_status(cache_id) != "OPEN":
            raise ValueError(f"工作缓存 {cache_id} 已关闭")
        if (experience_id is None) == (memory_id is None):
            raise ValueError("每次发生必须正好有一个依据：一条经验，或一条记忆")
        if experience_id is not None and not self.experiences.exists(experience_id):
            raise ValueError(f"经验 {experience_id} 不存在")
        if memory_id is not None and self.store.conn.execute(
                "SELECT 1 FROM memory_items WHERE memory_id = ?", (memory_id,)).fetchone() is None:
            raise ValueError(f"记忆 {memory_id} 不存在")
        bindings = dict(bindings or {})
        unknown_slots = set(bindings) - set(node.slots)
        if unknown_slots:
            raise ValueError(f"节点 {node_id} 没有这些 slot：{sorted(unknown_slots)}")

        slot_map: dict = {}
        parent_bindings: dict[str, Binding] = {}
        if parent_occurrence_id is not None:
            parent = self.get(parent_occurrence_id)
            if parent.cache_id != cache_id:
                raise ValueError("子发生必须和父发生在同一个工作缓存里")
            pnode = self.structures.get(parent.node_id, parent.version)
            matches = [i for i, ch in enumerate(pnode.children) if (ch.node_id, ch.version) == (node.node_id, node.version)]
            if child_ord is None:
                if len(matches) != 1:
                    raise ValueError("请写明这是父结构里的第几个子节点" if matches else "这个节点不是父结构的子节点")
                child_ord = matches[0]
            elif child_ord not in matches:
                raise ValueError(f"父结构第 {child_ord} 个子节点不是 {node_id}@v{node.version}")
            slot_map = pnode.children[child_ord].slot_map
            parent_bindings = self.bindings(parent_occurrence_id)
        elif child_ord is not None:
            raise ValueError("没有父发生就不能写 child_ord")

        final: dict[str, Binding] = {}
        for slot in node.slots:
            given = bindings.get(slot)
            parent_slot = slot_map.get(slot)
            inherited = parent_bindings.get(parent_slot) if parent_slot else None
            if inherited is not None and inherited.state is BindingState.BOUND:
                if given is not None and given != bound(inherited.value):
                    raise ValueError(f"slot {slot} 与父结构的 {parent_slot} 是同一个对象，不能绑定成别的")
                final[slot] = Binding(BindingState.BOUND, inherited.value, inherited=True)
            elif given is not None:
                final[slot] = given
            elif inherited is not None:
                final[slot] = Binding(inherited.state, inherited.value, inherited=True)
            else:
                final[slot] = gap()
            self._check_binding(node, slot, final[slot], cache_id)
        if parent_occurrence_id is not None:
            self._check_same_object_among_siblings(parent_occurrence_id, slot_map, final)

        with self.store.transaction() as c:
            occ_id = c.execute(
                "INSERT INTO occurrences(node_id, version, parent_occurrence_id, child_ord, cache_id, experience_id, memory_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (node.node_id, node.version, parent_occurrence_id, child_ord, cache_id, experience_id, memory_id)).lastrowid
            c.executemany(
                "INSERT INTO occurrence_bindings(occurrence_id, slot, state, value_json, inherited) VALUES (?, ?, ?, ?, ?)",
                [(occ_id, s, b.state.value, _dumps(b.value), int(b.inherited)) for s, b in final.items()])
        return occ_id

    def get(self, occurrence_id: int) -> Occurrence:
        row = self.store.conn.execute(
            "SELECT node_id, version, parent_occurrence_id, child_ord, cache_id, experience_id, memory_id"
            " FROM occurrences WHERE occurrence_id = ?", (occurrence_id,)).fetchone()
        if row is None:
            raise KeyError(occurrence_id)
        return Occurrence(occurrence_id, *row)

    def bindings(self, occurrence_id: int) -> dict[str, Binding]:
        return {s: Binding(BindingState(st), json.loads(v), bool(inh)) for s, st, v, inh in self.store.conn.execute(
            "SELECT slot, state, value_json, inherited FROM occurrence_bindings WHERE occurrence_id = ? ORDER BY slot",
            (occurrence_id,))}

    def ancestors(self, occurrence_id: int) -> list[int]:
        out, cur = [], self.get(occurrence_id).parent_occurrence_id
        while cur is not None:
            out.append(cur)
            cur = self.get(cur).parent_occurrence_id
        return out

    # ---------- 条件 ----------

    def check_condition(self, occurrence_id: int, state: ConditionState, evidence_ids: Sequence[int], note: str) -> None:
        """记下条件状态。满足／不满足都要有观察或已执行的证据；高分（计算经历）不能当证据。"""
        occ = self.get(occurrence_id)
        node = self.structures.get(occ.node_id, occ.version)
        if node.kind is not NodeKind.CONDITION:
            raise ValueError("只有条件节点的发生才有条件状态")
        state = ConditionState(state)
        if state is not ConditionState.UNKNOWN:
            if not evidence_ids:
                raise ValueError("判断条件满足或不满足，必须给出证据")
            for ev in evidence_ids:
                if not self.experiences.exists(ev):
                    raise ValueError(f"证据 {ev} 不存在")
                src = self.experiences.get(ev).source_type
                if src not in EVIDENCE_SOURCES:
                    raise ValueError(f"记录 {ev} 的来源是 {src.value}，不能当条件的证据（高分不能绕过条件）")
        with self.store.transaction() as c:
            c.execute("INSERT INTO condition_checks(occurrence_id, state, evidence_json, note) VALUES (?, ?, ?, ?)",
                      (occurrence_id, state.value, json.dumps(list(evidence_ids)), note))

    def condition_state(self, occurrence_id: int) -> ConditionState:
        row = self.store.conn.execute(
            "SELECT state FROM condition_checks WHERE occurrence_id = ? ORDER BY check_id DESC LIMIT 1",
            (occurrence_id,)).fetchone()
        return ConditionState(row[0]) if row else ConditionState.UNKNOWN

    def governing_conditions(self, occurrence_id: int) -> list[tuple[int, ConditionState]]:
        """这次发生处在哪些条件之下（由近到远）。"""
        out = []
        for occ_id in [occurrence_id] + self.ancestors(occurrence_id):
            occ = self.get(occ_id)
            if self.structures.get(occ.node_id, occ.version).kind is NodeKind.CONDITION:
                out.append((occ_id, self.condition_state(occ_id)))
        return out

    # ---------- 流转（3×3 互转作为计算因子） ----------

    def record_flow(self, occurrence_id: int, from_face: Face, to_face: Face,
                    inputs: Sequence[dict], outputs: Sequence[dict], note: str) -> int:
        """记一步流转：从哪个面转到哪个面，输入和输出各是什么。输入、输出都要交代（连续性审查原则）。"""
        occ = self.get(occurrence_id)
        if not inputs or not outputs:
            raise ValueError("流转步必须交代输入和输出；输出未知请写 literal 未知，不要省略")
        for ref in list(inputs) + list(outputs):
            self._check_flow_ref(ref, occ.cache_id)
        with self.store.transaction() as c:
            return c.execute(
                "INSERT INTO flow_steps(occurrence_id, from_face, to_face, inputs_json, outputs_json, note)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (occurrence_id, Face(from_face).value, Face(to_face).value, _dumps(list(inputs)), _dumps(list(outputs)),
                 note)).lastrowid

    def flow(self, occurrence_id: int) -> list[dict]:
        return [{"step_id": s, "from": f, "to": t, "inputs": json.loads(i), "outputs": json.loads(o), "note": n}
                for s, f, t, i, o, n in self.store.conn.execute(
                    "SELECT step_id, from_face, to_face, inputs_json, outputs_json, note FROM flow_steps"
                    " WHERE occurrence_id = ? ORDER BY step_id", (occurrence_id,))]

    # ---------- 内部 ----------

    def _check_binding(self, node: Node, slot: str, b: Binding, cache_id: int) -> None:
        if b.state is BindingState.GAP:
            if b.value is not None:
                raise ValueError("缺口不能带值")
            return
        refs = [b.value] if b.state is BindingState.BOUND else list(b.value or [])
        if b.state is BindingState.CANDIDATES and len(refs) < 2:
            raise ValueError("候选至少两个")
        allowed = node.slots[slot].get("ref_kinds")
        for ref in refs:
            if allowed is not None and ref.get("kind") not in allowed:
                raise ValueError(f"slot {slot} 只接受 {allowed}，不接受 {ref.get('kind')}（类型约束）")
            self._check_ref(ref, cache_id)

    def _check_ref(self, ref: dict, cache_id: int) -> None:
        """引用必须存在；包、记忆、经验还必须已进入本轮工作缓存（只在准入范围内使用）。"""
        if not isinstance(ref, dict) or ref.get("kind") not in REF_KINDS:
            raise ValueError(f"引用必须是 {REF_KINDS} 之一：{ref}")
        kind, c = ref["kind"], self.store.conn
        if kind == "literal":
            if "value" not in ref:
                raise ValueError("literal 引用要有 value")
            return
        if kind == "material":
            if c.execute("SELECT 1 FROM materials WHERE material_id = ?", (ref.get("id"),)).fetchone() is None:
                raise ValueError(f"素材 {ref.get('id')} 不存在")
            return
        key = (ref.get("id"), ref.get("version")) if kind == "package" else ref.get("id")
        if not self.valve.is_entered(cache_id, ItemKind(kind), key):
            raise ValueError(f"{kind}:{key} 没有进入工作缓存 {cache_id}，不能在本轮使用")

    def _check_flow_ref(self, ref: dict, cache_id: int) -> None:
        c = self.store.conn
        kind = ref.get("kind") if isinstance(ref, dict) else None
        if kind == "call":
            row = c.execute("SELECT cache_id FROM calls WHERE call_id = ?", (ref.get("id"),)).fetchone()
            if row is None or row[0] != cache_id:
                raise ValueError(f"调用 {ref.get('id')} 不存在或不在本工作缓存")
        elif kind == "binding":
            row = c.execute("SELECT 1 FROM occurrence_bindings b JOIN occurrences o ON o.occurrence_id = b.occurrence_id"
                            " WHERE b.occurrence_id = ? AND b.slot = ? AND o.cache_id = ?",
                            (ref.get("occurrence_id"), ref.get("slot"), cache_id)).fetchone()
            if row is None:
                raise ValueError(f"绑定 {ref} 不存在或不在本工作缓存")
        else:
            self._check_ref(ref, cache_id)

    def _check_same_object_among_siblings(self, parent_occurrence_id: int, slot_map: dict, final: dict) -> None:
        """父 slot 还是缺口或候选时，各子发生接到同一个父 slot 的已绑定对象必须一致。"""
        parent = self.get(parent_occurrence_id)
        pnode = self.structures.get(parent.node_id, parent.version)
        for slot, parent_slot in slot_map.items():
            b = final.get(slot)
            if b is None or b.state is not BindingState.BOUND:
                continue
            for (sib_id, sib_ord) in self.store.conn.execute(
                    "SELECT occurrence_id, child_ord FROM occurrences WHERE parent_occurrence_id = ?",
                    (parent_occurrence_id,)).fetchall():
                sib_map = pnode.children[sib_ord].slot_map
                for sib_slot, sib_parent_slot in sib_map.items():
                    if sib_parent_slot != parent_slot:
                        continue
                    sb = self.bindings(sib_id).get(sib_slot)
                    if sb is not None and sb.state is BindingState.BOUND and sb.value != b.value:
                        raise ValueError(f"父结构的 {parent_slot} 是同一个对象：兄弟发生已绑定为 {sb.value}，"
                                         f"这里不能绑定为 {b.value}")


def _check_constraint(slot: str, constraint) -> None:
    if not isinstance(constraint, dict):
        raise ValueError(f"slot {slot} 的约束必须是记录（可以为空 {{}}）")
    kinds = constraint.get("ref_kinds")
    if kinds is not None and (not kinds or set(kinds) - set(REF_KINDS)):
        raise ValueError(f"slot {slot} 的 ref_kinds 必须是 {REF_KINDS} 的非空子集")


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
