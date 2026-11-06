"""形成后的记忆（名词解释 v0.17 第一节、4.3、“记忆的具体依据、引用边界与灰度更新”；v0.9 逆向形成）。

经验 → 拆解学习 → 记忆。记忆是经验经拆解学习后形成的内容与关系，不是原始记录（原始记录见 experience.py）。
“拆解学习”的算法尚未确定（反合一 AU 只是 NOT_RUN 的候选），这里只规定接口和不变量，不代填算法：

- 学习形成的记忆：必须写明来自哪些经验，以及用了什么形成方法。方法要登记，可以如实写“人工整理”或“待定”。
- 知识 → 记忆（想象力）：必须写明依据哪些知识包版本；标明想象来源。它不是经验，所以永远不能当核实证据或训练反馈。
- 记忆 → 经验（回忆／重演）：回忆这件事登记为一条新经验，指向被回忆的记忆；被回忆的内容不因此成为当前外部事实。
- v0.17 记忆提供具体素材，以及适用范围、来源、条件与绑定；已有记忆不允许篡改：
  - 适用范围（世界）、条件、绑定都在形成时写进记忆本身；要改，只能修订。
  - 引用方向：记忆可以被外部引用，但记忆本身只引用**不会变**的东西（素材、包的某个版本、经验、其他记忆），
    不引用会随外部解释漂移的东西（例如“某个包的最新版”），以免来源指向变化。
  - 灰度更新：同一份记忆要修正时间、版本或内容时，在原基础上新建有承接关系的版本（revise），保留原版与修订来路；
    新一次相似经历是新记忆（form），不是旧记忆的修订。
  - 默认索引：按时间排序和使用排序。index() 是工作解释：时间＝登记先后，使用＝被回忆的次数；
    事件时间与登记时间怎样合并、“默认最新适用版本”怎样选，文档写着仍待细化，这里不替调用方选版本。
- 学习材料库（v0.16：why 层为 attention／映射函数学习提供材料的载体）不是记忆，见 learning_store.py。
- 不可篡改不等于不可遗忘：forget／restore 只记可达性变化，不改写、不删除记忆内容。
  被遗忘的记忆不出现在默认索引里，不能被回忆、修订或收进学习材料库；但已有引用仍能解析（墓碑）。
  这只是本库里的逻辑遗忘，不代表备份或磁盘残留已经删除；保留期限与真正删除的政策，文档没有制定。

尚未实现：事件链 AST 怎样组织形成后的记忆。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

from .experience import ExperienceLog, SourceType
from .store import Store, now_iso

REQUIRED_FORMATION_KEYS = ("method_id", "description")
PHYSICAL = "physical"
# 记忆的绑定只能指向不会变的对象（v0.17 引用方向）。
STABLE_REF_KINDS = ("material", "package", "experience", "memory", "literal")
_KEEP = object()


class MemoryOrigin(str, Enum):
    LEARNED = "LEARNED"          # 经验经拆解学习形成
    IMAGINATION = "IMAGINATION"  # 知识 → 记忆（想象力）：构造的场景，不是已发生的经历


@dataclass(frozen=True)
class MemoryItem:
    memory_id: int
    origin: MemoryOrigin
    content: str
    formation: dict
    reason: str
    experience_sources: list[int]
    package_sources: list[tuple[str, int]]
    memory_sources: list[int]
    revises: Optional[int] = None          # 承接的上一版本；None 表示原版
    worlds: tuple = ()                     # 适用世界；空＝没说明（阀门按默认物理世界处理）
    conditions: Optional[dict] = None
    bindings: Optional[dict] = None
    recorded_at: Optional[str] = None


class MemoryLayer:
    def __init__(self, store: Store, experiences: ExperienceLog):
        self.store = store
        self.experiences = experiences

    def form(self, *, content: str, from_experience_ids: Sequence[int], formation: dict, reason: str,
             worlds: Sequence[str] = (), conditions: Optional[dict] = None, bindings: Optional[dict] = None) -> int:
        """经验经拆解学习形成一条记忆。没有来源经验就不能形成。"""
        if not from_experience_ids:
            raise ValueError("学习形成的记忆必须写明来自哪些经验（经验先拆解学习，再形成记忆）")
        for ev in from_experience_ids:
            if not self.experiences.exists(ev):
                raise ValueError(f"来源经验 {ev} 不存在")
        _check_formation(formation)
        self._check_scope(worlds, conditions, bindings)
        with self.store.transaction() as c:
            memory_id = self._insert(c, MemoryOrigin.LEARNED, content, formation, reason, None, worlds, conditions, bindings)
            c.executemany("INSERT INTO memory_experience_sources(memory_id, experience_id) VALUES (?, ?)",
                          [(memory_id, int(ev)) for ev in dict.fromkeys(from_experience_ids)])
        return memory_id

    def imagine(
        self,
        *,
        content: str,
        from_packages: Sequence[tuple[str, int]],
        formation: dict,
        reason: str,
        from_memory_ids: Sequence[int] = (),
        worlds: Sequence[str] = (),
        conditions: Optional[dict] = None,
        bindings: Optional[dict] = None,
    ) -> int:
        """知识 → 记忆（想象力）：由知识包组合构造场景，标明想象来源。"""
        if not from_packages:
            raise ValueError("想象必须写明依据哪些知识包版本（知识 → 记忆）")
        _check_formation(formation)
        c0 = self.store.conn
        for pid, ver in from_packages:
            row = c0.execute("SELECT p.status FROM package_versions v JOIN packages p ON p.package_id = v.package_id"
                             " WHERE v.package_id = ? AND v.version = ?", (pid, ver)).fetchone()
            if row is None:
                raise ValueError(f"知识包版本 {pid}@{ver} 不存在")
            if row[0] != "ACTIVE":
                raise ValueError(f"知识包 {pid} 已裁剪，不能再被组合")
        for mid in from_memory_ids:
            self.get(mid)
        self._check_scope(worlds, conditions, bindings)
        with self.store.transaction() as c:
            memory_id = self._insert(c, MemoryOrigin.IMAGINATION, content, formation, reason, None, worlds, conditions,
                                     bindings)
            c.executemany("INSERT INTO memory_package_sources(memory_id, package_id, version) VALUES (?, ?, ?)",
                          [(memory_id, p, int(v)) for p, v in dict.fromkeys(map(tuple, from_packages))])
            c.executemany("INSERT INTO memory_memory_sources(memory_id, source_memory_id) VALUES (?, ?)",
                          [(memory_id, int(m)) for m in dict.fromkeys(from_memory_ids)])
        return memory_id

    def revise(self, memory_id: int, *, basis_experience_ids: Sequence[int], formation: dict, reason: str,
               content: Any = _KEEP, worlds: Any = _KEEP, conditions: Any = _KEEP, bindings: Any = _KEEP) -> int:
        """修订：新建承接原版的新版本，原版保留不动。依据是促成修订的经验（例如更正时间的观察）。

        没给出的部分沿用原版；新版本继承原版的来源（经验、知识包、记忆），再加上本次修订的依据。
        """
        old = self.get(memory_id)
        self._require_reachable(memory_id, "修订")
        if not basis_experience_ids:
            raise ValueError("修订记忆要写明依据（哪条经验促成了修订）")
        for ev in basis_experience_ids:
            if not self.experiences.exists(ev):
                raise ValueError(f"依据经验 {ev} 不存在")
        new_content = old.content if content is _KEEP else content
        new_worlds = tuple(old.worlds) if worlds is _KEEP else tuple(worlds)
        new_conditions = old.conditions if conditions is _KEEP else conditions
        new_bindings = old.bindings if bindings is _KEEP else bindings
        if (new_content, new_worlds, new_conditions, new_bindings) == (old.content, tuple(old.worlds), old.conditions,
                                                                       old.bindings):
            raise ValueError("没有任何变化，不需要修订")
        _check_formation(formation)
        self._check_scope(new_worlds, new_conditions, new_bindings)
        exps = list(dict.fromkeys(list(old.experience_sources) + [int(e) for e in basis_experience_ids]))
        with self.store.transaction() as c:
            new_id = self._insert(c, old.origin, new_content, formation, reason, memory_id, new_worlds, new_conditions,
                                  new_bindings)
            c.executemany("INSERT INTO memory_experience_sources(memory_id, experience_id) VALUES (?, ?)",
                          [(new_id, ev) for ev in exps])
            c.executemany("INSERT INTO memory_package_sources(memory_id, package_id, version) VALUES (?, ?, ?)",
                          [(new_id, p, v) for p, v in old.package_sources])
            c.executemany("INSERT INTO memory_memory_sources(memory_id, source_memory_id) VALUES (?, ?)",
                          [(new_id, m) for m in old.memory_sources])
        return new_id

    def lineage(self, memory_id: int) -> list[int]:
        """从这一版本一直追溯到原版：[当前, 上一版, ..., 原版]。"""
        out, cur = [], memory_id
        while cur is not None:
            out.append(cur)
            cur = self.get(cur).revises
        return out

    def revisions_of(self, memory_id: int) -> list[int]:
        """直接承接这一版本的修订（可能有多个；用哪个版本的策略尚未定稿）。"""
        return [r[0] for r in self.store.conn.execute(
            "SELECT memory_id FROM memory_items WHERE revises_memory_id = ? ORDER BY memory_id", (memory_id,))]

    def index(self, order: str = "time", include_forgotten: bool = False) -> list[int]:
        """默认索引（工作解释）：time＝按登记先后；use＝按被回忆次数从多到少，次数相同再按登记先后。

        排序只用来找到和使用记忆，不代表真假，也不代表哪个版本“默认适用”。被遗忘的记忆默认不列出。
        """
        if order == "time":
            sql = "SELECT memory_id FROM memory_items ORDER BY memory_id"
        elif order == "use":
            sql = ("SELECT m.memory_id FROM memory_items m LEFT JOIN recalls r ON r.memory_id = m.memory_id"
                   " GROUP BY m.memory_id ORDER BY COUNT(r.experience_id) DESC, m.memory_id")
        else:
            raise ValueError("order 只能是 time 或 use")
        ids = [r[0] for r in self.store.conn.execute(sql)]
        return ids if include_forgotten else [i for i in ids if self.reachable(i)]

    # ---------- 遗忘与可达性（v0.17：不可篡改不等于不可遗忘） ----------

    def forget(self, memory_id: int, basis_ids: Sequence[int], reason: str) -> None:
        """让这条记忆不可达。不改写、不删除内容；已有引用仍能解析。"""
        self.get(memory_id)
        self._require_reachable(memory_id, "遗忘")
        self._reachability(memory_id, "FORGET", basis_ids, reason)

    def restore(self, memory_id: int, basis_ids: Sequence[int], reason: str) -> None:
        if self.reachable(memory_id):
            raise ValueError(f"记忆 {memory_id} 本来就可达")
        self._reachability(memory_id, "RESTORE", basis_ids, reason)

    def reachable(self, memory_id: int) -> bool:
        row = self.store.conn.execute(
            "SELECT action FROM memory_reachability WHERE memory_id = ? ORDER BY event_id DESC LIMIT 1",
            (memory_id,)).fetchone()
        return row is None or row[0] == "RESTORE"

    def _reachability(self, memory_id: int, action: str, basis_ids: Sequence[int], reason: str) -> None:
        if not basis_ids:
            raise ValueError("遗忘或恢复要写明依据（例如用户的要求）")
        for ev in basis_ids:
            if not self.experiences.exists(ev):
                raise ValueError(f"依据经验 {ev} 不存在")
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory_reachability(memory_id, action, basis_json, reason, recorded_at)"
                      " VALUES (?, ?, ?, ?, ?)", (memory_id, action, json.dumps(list(basis_ids)), reason, now_iso()))

    def _require_reachable(self, memory_id: int, what: str) -> None:
        if not self.reachable(memory_id):
            raise ValueError(f"记忆 {memory_id} 已被遗忘（不可达），不能{what}；需要时先 restore")

    def recall(self, memory_id: int, *, chain_id: str, origin: str, occurred_at: Optional[str] = None,
               position: Optional[dict] = None, binding: Optional[dict] = None) -> int:
        """记忆 → 经验：登记“发生了一次回忆”这条新经验，返回经验编号。"""
        item = self.get(memory_id)
        self._require_reachable(memory_id, "回忆")
        with self.store.transaction() as c:
            ev = self.experiences._record(chain_id=chain_id, source_type=SourceType.RECALL, content=item.content,
                                          origin=origin, occurred_at=occurred_at, position=position, binding=binding)
            c.execute("INSERT INTO recalls(experience_id, memory_id) VALUES (?, ?)", (ev, memory_id))
        return ev

    def recalled_memory(self, experience_id: int) -> Optional[int]:
        row = self.store.conn.execute("SELECT memory_id FROM recalls WHERE experience_id = ?", (experience_id,)).fetchone()
        return None if row is None else row[0]

    def get(self, memory_id: int) -> MemoryItem:
        c = self.store.conn
        row = c.execute(
            "SELECT m.origin_kind, ct.content, m.formation_json, m.reason, m.revises_memory_id, m.worlds_json,"
            " m.conditions_json, m.bindings_json, m.recorded_at FROM memory_items m"
            " JOIN contents ct ON ct.content_hash = m.content_hash WHERE m.memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            raise KeyError(memory_id)
        origin, content, formation, reason, revises, worlds, conditions, bindings, recorded_at = row
        exps = [r[0] for r in c.execute(
            "SELECT experience_id FROM memory_experience_sources WHERE memory_id = ? ORDER BY experience_id", (memory_id,))]
        pkgs = [(p, v) for p, v in c.execute(
            "SELECT package_id, version FROM memory_package_sources WHERE memory_id = ? ORDER BY package_id, version",
            (memory_id,))]
        mems = [r[0] for r in c.execute(
            "SELECT source_memory_id FROM memory_memory_sources WHERE memory_id = ? ORDER BY source_memory_id", (memory_id,))]
        return MemoryItem(memory_id, MemoryOrigin(origin), content, json.loads(formation), reason, exps, pkgs, mems,
                          revises, tuple(json.loads(worlds)), _load(conditions), _load(bindings), recorded_at)

    def _insert(self, c, origin: MemoryOrigin, content: str, formation: dict, reason: str, revises: Optional[int],
                worlds: Sequence[str], conditions: Optional[dict], bindings: Optional[dict]) -> int:
        h = self.store.put_content(content)
        cur = c.execute(
            "INSERT INTO memory_items(origin_kind, content_hash, formation_json, reason, revises_memory_id, worlds_json,"
            " conditions_json, bindings_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (origin.value, h, _dumps(formation), reason, revises, json.dumps(list(dict.fromkeys(worlds)), ensure_ascii=False),
             None if conditions is None else _dumps(conditions), None if bindings is None else _dumps(bindings), now_iso()))
        return cur.lastrowid

    def _check_scope(self, worlds: Sequence[str], conditions: Optional[dict], bindings: Optional[dict]) -> None:
        c = self.store.conn
        for w in worlds:
            if c.execute("SELECT 1 FROM worlds WHERE world_id = ?", (w,)).fetchone() is None:
                raise ValueError(f"世界 {w} 不存在")
        if conditions is not None and not isinstance(conditions, dict):
            raise ValueError("条件必须是记录")
        if bindings is None:
            return
        if not isinstance(bindings, dict):
            raise ValueError("绑定必须是 {名字: 引用} 的记录")
        for name, ref in bindings.items():
            kind = ref.get("kind") if isinstance(ref, dict) else None
            if kind not in STABLE_REF_KINDS:
                raise ValueError(f"绑定 {name} 只能指向 {STABLE_REF_KINDS}：{ref}")
            if kind == "literal":
                if "value" not in ref:
                    raise ValueError(f"绑定 {name} 的 literal 要有 value")
            elif kind == "package":
                if ref.get("version") is None:
                    raise ValueError(f"绑定 {name} 指向包时必须写明版本；“最新版”会随外部变化，记忆不能引用它")
                if c.execute("SELECT 1 FROM package_versions WHERE package_id = ? AND version = ?",
                             (ref.get("id"), ref["version"])).fetchone() is None:
                    raise ValueError(f"绑定 {name} 指向的包版本不存在")
            elif kind == "material":
                if c.execute("SELECT 1 FROM materials WHERE material_id = ?", (ref.get("id"),)).fetchone() is None:
                    raise ValueError(f"绑定 {name} 指向的素材不存在")
            elif kind == "experience":
                if not self.experiences.exists(ref.get("id")):
                    raise ValueError(f"绑定 {name} 指向的经验不存在")
            elif c.execute("SELECT 1 FROM memory_items WHERE memory_id = ?", (ref.get("id"),)).fetchone() is None:
                raise ValueError(f"绑定 {name} 指向的记忆不存在")


def _check_formation(formation: dict) -> None:
    missing = [k for k in REQUIRED_FORMATION_KEYS if k not in formation]
    if missing:
        raise ValueError(f"形成方法登记缺少字段：{missing}（算法未定时如实写明，不要省略）")


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _load(s: Optional[str]):
    return None if s is None else json.loads(s)
