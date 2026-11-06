"""记忆边界阀：世界、前提与工作缓存（名词解释 v0.14 4.3；架构图谱 0.3“记忆阀门／局部工作缓存／全局记忆”；设计稿 v0.3 第三节）。

- 世界：内置“物理世界”。没有标世界的经验、记忆、知识包默认属于物理世界，并标明“这是默认的”
  这是未指定世界时的默认归属，不等于事实已经证实。
- 前提：登记时就写明适用范围（整个世界、某个工作缓存、事件链某个节点、某一次发生、某段时间）。
  范围到了就自然不适用；中途要改才记撤销。
  明确登记要有外部依据，直接生效；系统提出的只是候选，用外部依据确认后才生效。
- 工作缓存：每轮计算开一个，记下进入了哪些世界和素材，以及读取优先级。素材必须属于缓存里的某个世界，
  跨世界使用要写明“显式比较”的理由。退出只记录，不删除。
- 激活、优先级、真值分开：本模块只管前两项；真值看 experience.py 的核实记录。
- 撤销前提、退出世界或素材时，受影响的计算调用标记为“需要重查”，不自动重算。
自动准入规则、撤销规则与资源预算，文档写着“待定”，这里不代填。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Union

from .experience import ExperienceLog
from .store import Store

PHYSICAL = "physical"
TAG_KINDS = ("experience", "package")  # 记忆的世界写在记忆本身里，不另外标注


class ItemKind(str, Enum):
    WORLD = "world"
    PACKAGE = "package"        # 包的某个版本：ref ＝ (包, 版本)
    MEMORY = "memory"
    EXPERIENCE = "experience"


class PremiseStatus(str, Enum):
    ACTIVE = "ACTIVE"          # 生效（仍要看适用范围）
    CANDIDATE = "CANDIDATE"    # 系统提出，待确认
    REVOKED = "REVOKED"


class ScopeKind(str, Enum):
    WORLD = "world"            # 整个世界：这个世界进入缓存时都适用
    CACHE = "cache"            # 某个工作缓存
    NODE = "node"              # 事件链某个节点：它每次发生时，下面的部分都适用（像变量作用域）
    OCCURRENCE = "occurrence"  # 某一次发生及其下面的部分
    TIME = "time"              # 某段时间 [from, until)；until 可为空


@dataclass(frozen=True)
class Premise:
    premise_id: int
    world_id: str
    content: str
    scope: dict
    proposed_by: str
    status: PremiseStatus
    basis: list[int]


Ref = Union[str, int, tuple]


class MemoryValve:
    def __init__(self, store: Store, experiences: ExperienceLog):
        self.store = store
        self.experiences = experiences

    # ---------- 世界 ----------

    def register_world(self, world_id: str, name: str, description: str, basis_ids: Sequence[int]) -> None:
        if not basis_ids:
            raise ValueError("登记世界要写明依据")
        self._check_exist(basis_ids)
        if self._world_exists(world_id):
            raise ValueError(f"世界 {world_id} 已存在")
        with self.store.transaction() as c:
            c.execute("INSERT INTO worlds(world_id, name, description, basis_json) VALUES (?, ?, ?, ?)",
                      (world_id, name, description, json.dumps(list(basis_ids))))

    def tag_world(self, kind: str, ref: Ref, world_id: str, basis_ids: Sequence[int], reason: str) -> None:
        self._tag(kind, ref, world_id, "ADD", basis_ids, reason)

    def untag_world(self, kind: str, ref: Ref, world_id: str, basis_ids: Sequence[int], reason: str) -> None:
        if world_id not in self._explicit_worlds(kind, ref):
            raise ValueError(f"{kind}:{ref} 没有明确标为 {world_id}")
        self._tag(kind, ref, world_id, "REMOVE", basis_ids, reason)

    def worlds_of(self, kind: str, ref: Ref) -> tuple[frozenset, bool]:
        """返回（所属世界, 是否默认）。没有明确标注时默认物理世界。

        记忆的世界在形成时写进记忆本身（v0.17：适用范围是记忆的一部分，不被外部标注改写）。
        """
        if kind == "memory":
            row = self.store.conn.execute("SELECT worlds_json FROM memory_items WHERE memory_id = ?", (int(ref),)).fetchone()
            if row is None:
                raise ValueError(f"memory:{ref} 不存在")
            explicit = set(json.loads(row[0]))
        else:
            explicit = self._explicit_worlds(kind, ref)
        return (frozenset(explicit), False) if explicit else (frozenset({PHYSICAL}), True)

    # ---------- 前提 ----------

    def declare_premise(self, world_id: str, content: str, scope: dict, basis_ids: Sequence[int]) -> int:
        """明确登记：依据必须是外部记录（用户的话、任务设置等），登记后直接生效。"""
        self.experiences.require_external_feedback(basis_ids, "明确登记前提")
        return self._insert_premise(world_id, content, scope, "DECLARED", basis_ids)

    def propose_premise(self, world_id: str, content: str, scope: dict, basis_ids: Sequence[int]) -> int:
        """系统提出：只是候选，confirm_premise 之后才生效。"""
        if not basis_ids:
            raise ValueError("系统提出前提也要写明依据")
        self._check_exist(basis_ids)
        return self._insert_premise(world_id, content, scope, "SYSTEM", basis_ids)

    def confirm_premise(self, premise_id: int, basis_ids: Sequence[int], reason: str) -> None:
        p = self.premise(premise_id)
        if p.status is not PremiseStatus.CANDIDATE:
            raise ValueError(f"前提 {premise_id} 的状态是 {p.status.value}，不需要确认")
        self.experiences.require_external_feedback(basis_ids, "确认前提")
        self._premise_event(premise_id, "CONFIRM", basis_ids, reason)

    def revoke_premise(self, premise_id: int, basis_ids: Sequence[int], reason: str) -> None:
        """中途改变时的明确撤销。范围自然结束不需要撤销。"""
        p = self.premise(premise_id)
        if p.status is PremiseStatus.REVOKED:
            raise ValueError(f"前提 {premise_id} 已撤销")
        self.experiences.require_external_feedback(basis_ids, "撤销前提")
        with self.store.transaction():
            self._premise_event(premise_id, "REVOKE", basis_ids, reason)
            if p.scope["kind"] == ScopeKind.CACHE.value:
                caches = [p.scope["cache_id"]]
            else:
                caches = self._caches_that_entered(ItemKind.WORLD, p.world_id)
            for cache_id in caches:
                self._flag_calls(cache_id, None, {"premise_revoked": premise_id, "reason": reason})

    def premise(self, premise_id: int) -> Premise:
        row = self.store.conn.execute(
            "SELECT p.world_id, c.content, p.scope_json, p.proposed_by, p.basis_json FROM premises p"
            " JOIN contents c ON c.content_hash = p.content_hash WHERE p.premise_id = ?", (premise_id,)).fetchone()
        if row is None:
            raise KeyError(premise_id)
        world_id, content, scope, proposed_by, basis = row
        actions = [a for (a,) in self.store.conn.execute(
            "SELECT action FROM premise_events WHERE premise_id = ? ORDER BY premise_event_id", (premise_id,))]
        if "REVOKE" in actions:
            status = PremiseStatus.REVOKED
        elif proposed_by == "DECLARED" or "CONFIRM" in actions:
            status = PremiseStatus.ACTIVE
        else:
            status = PremiseStatus.CANDIDATE
        return Premise(premise_id, world_id, content, json.loads(scope), proposed_by, status, json.loads(basis))

    def active_premises(self, cache_id: int, occurrence_id: Optional[int] = None, at: Optional[str] = None) -> list[Premise]:
        """此刻适用的前提：世界已进入本缓存、状态生效，且适用范围覆盖当前位置。"""
        worlds = self.cache_worlds(cache_id)
        chain_occ, chain_nodes = [], []
        if occurrence_id is not None:
            row = self.store.conn.execute("SELECT cache_id FROM occurrences WHERE occurrence_id = ?",
                                          (occurrence_id,)).fetchone()
            if row is None:
                raise ValueError(f"发生 {occurrence_id} 不存在")
            if row[0] != cache_id:
                raise ValueError(f"发生 {occurrence_id} 不属于工作缓存 {cache_id}")
            chain_occ, chain_nodes = self._occurrence_chain(occurrence_id)
        out = []
        for (pid,) in self.store.conn.execute("SELECT premise_id FROM premises ORDER BY premise_id").fetchall():
            p = self.premise(pid)
            if p.world_id in worlds and p.status is PremiseStatus.ACTIVE and \
                    _covers(p.scope, cache_id, chain_occ, chain_nodes, at):
                out.append(p)
        return out

    # ---------- 工作缓存 ----------

    def open_cache(self, purpose: str, worlds: Sequence[str] = (PHYSICAL,), reason: str = "开始本轮计算") -> int:
        if not worlds:
            raise ValueError("工作缓存至少要进入一个世界")
        for w in worlds:
            if not self._world_exists(w):
                raise ValueError(f"世界 {w} 不存在")
        with self.store.transaction() as c:
            cache_id = c.execute("INSERT INTO work_caches(purpose) VALUES (?)", (purpose,)).lastrowid
            for w in dict.fromkeys(worlds):
                self._log(c, cache_id, "ENTER", ItemKind.WORLD, w, None, False, reason)
        return cache_id

    def enter(self, cache_id: int, kind: ItemKind, ref: Ref, *, priority: Optional[int] = None,
              cross_world_reason: Optional[str] = None, reason: str = "") -> None:
        """把世界或素材放进本轮。素材不属于本轮任何世界时，必须写明显式比较的理由。"""
        kind = ItemKind(kind)
        self._require_open(cache_id)
        key = self._cache_ref(kind, ref)
        if key in self.entered(cache_id, kind):
            raise ValueError(f"{kind.value}:{key} 已在工作缓存 {cache_id} 中")
        cross = False
        if kind is ItemKind.WORLD:
            if not self._world_exists(key):
                raise ValueError(f"世界 {key} 不存在")
        else:
            if kind is ItemKind.PACKAGE:
                home = self.store.conn.execute(
                    "SELECT p.home_cache_id, EXISTS(SELECT 1 FROM package_events e WHERE e.package_id = p.package_id"
                    " AND e.action = 'PROMOTE') FROM packages p WHERE p.package_id = ?", (ref[0],)).fetchone()
                if home and home[0] is not None and not home[1] and home[0] != cache_id:
                    raise ValueError(f"包 {ref[0]} 是工作缓存 {home[0]} 的局部包，推广到全局后才能在别处使用")
            tag_kind, tag_ref = (("package", ref[0]) if kind is ItemKind.PACKAGE else (kind.value, ref))
            item_worlds, _ = self.worlds_of(tag_kind, tag_ref)
            if not item_worlds & self.cache_worlds(cache_id):
                if not cross_world_reason:
                    raise ValueError(f"{kind.value}:{key} 属于 {sorted(item_worlds)}，不在本轮世界里；"
                                     "跨世界使用请写明显式比较的理由")
                cross = True
        with self.store.transaction() as c:
            self._log(c, cache_id, "ENTER", kind, key, priority, cross, cross_world_reason or reason)

    def exit(self, cache_id: int, kind: ItemKind, ref: Ref, reason: str) -> None:
        """退出本轮：只记录，不删除全局内容；受影响的调用标记重查。"""
        kind = ItemKind(kind)
        self._require_open(cache_id)
        key = self._cache_ref(kind, ref)
        if key not in self.entered(cache_id, kind):
            raise ValueError(f"{kind.value}:{key} 不在工作缓存 {cache_id} 中")
        # 退出包：只标记用过这个包版本的调用；退出世界、记忆或经验：调用的入参里可能用过，保守地全部标记。
        package = (str(ref[0]), int(ref[1])) if kind is ItemKind.PACKAGE else None
        with self.store.transaction() as c:
            self._log(c, cache_id, "EXIT", kind, key, None, False, reason)
            self._flag_calls(cache_id, package, {"exited": f"{kind.value}:{key}", "reason": reason})

    def close_cache(self, cache_id: int) -> None:
        self._require_open(cache_id)
        with self.store.transaction() as c:
            c.execute("UPDATE work_caches SET status = 'CLOSED' WHERE cache_id = ?", (cache_id,))

    def log_mark(self, cache_id: int) -> int:
        """缓存记录目前到哪一条（没有记录时为 0）。计算调用用它记住当时的可见视图（v0.15）。"""
        row = self.store.conn.execute("SELECT MAX(log_id) FROM cache_log WHERE cache_id = ?", (cache_id,)).fetchone()
        return row[0] or 0

    def entered(self, cache_id: int, kind: ItemKind, as_of: Optional[int] = None) -> dict[str, Optional[int]]:
        """在缓存里的某类条目：{ref: 优先级}。as_of 给出时，只看到那一条记录为止（当时的可见视图）。"""
        kind = ItemKind(kind)
        current: dict[str, Optional[int]] = {}
        sql = "SELECT action, item_ref, priority FROM cache_log WHERE cache_id = ? AND item_kind = ?"
        args: list = [cache_id, kind.value]
        if as_of is not None:
            sql += " AND log_id <= ?"
            args.append(as_of)
        for action, ref, priority in self.store.conn.execute(sql + " ORDER BY log_id", args):
            if action == "ENTER":
                current[ref] = priority
            else:
                current.pop(ref, None)
        return current

    def is_entered(self, cache_id: int, kind: ItemKind, ref: Ref) -> bool:
        kind = ItemKind(kind)
        return self._cache_ref(kind, ref) in self.entered(cache_id, kind)

    def cache_worlds(self, cache_id: int) -> set[str]:
        if not self._cache_exists(cache_id):
            raise ValueError(f"工作缓存 {cache_id} 不存在")
        return set(self.entered(cache_id, ItemKind.WORLD))

    def cache_status(self, cache_id: int) -> str:
        row = self.store.conn.execute("SELECT status FROM work_caches WHERE cache_id = ?", (cache_id,)).fetchone()
        if row is None:
            raise ValueError(f"工作缓存 {cache_id} 不存在")
        return row[0]

    # ---------- 重查 ----------

    def pending_rechecks(self, cache_id: Optional[int] = None) -> list[dict]:
        sql = ("SELECT r.recheck_id, r.call_id, r.trigger_json FROM rechecks r JOIN calls c ON c.call_id = r.call_id"
               " WHERE r.status = 'OPEN'")
        args: list = []
        if cache_id is not None:
            sql += " AND c.cache_id = ?"
            args.append(cache_id)
        return [{"recheck_id": r, "call_id": cid, "trigger": json.loads(t)}
                for r, cid, t in self.store.conn.execute(sql + " ORDER BY r.recheck_id", args)]

    def resolve_recheck(self, recheck_id: int, resolution: str) -> None:
        if not resolution:
            raise ValueError("要写明重查的结论")
        with self.store.transaction() as c:
            n = c.execute("UPDATE rechecks SET status = 'DONE', resolution = ? WHERE recheck_id = ? AND status = 'OPEN'",
                          (resolution, recheck_id)).rowcount
            if n != 1:
                raise ValueError(f"重查 {recheck_id} 不存在或已处理")

    # ---------- 内部 ----------

    def _insert_premise(self, world_id, content, scope, proposed_by, basis_ids) -> int:
        if not self._world_exists(world_id):
            raise ValueError(f"世界 {world_id} 不存在")
        self._check_scope(scope)
        with self.store.transaction() as c:
            h = self.store.put_content(content)
            return c.execute(
                "INSERT INTO premises(world_id, content_hash, scope_json, proposed_by, basis_json) VALUES (?, ?, ?, ?, ?)",
                (world_id, h, _dumps(scope), proposed_by, json.dumps(list(basis_ids)))).lastrowid

    def _premise_event(self, premise_id, action, basis_ids, reason) -> None:
        with self.store.transaction() as c:
            c.execute("INSERT INTO premise_events(premise_id, action, basis_json, reason) VALUES (?, ?, ?, ?)",
                      (premise_id, action, json.dumps(list(basis_ids)), reason))

    def _check_scope(self, scope: dict) -> None:
        """适用范围必须在登记时写明（事先选定），不能省略。"""
        if not isinstance(scope, dict) or "kind" not in scope:
            raise ValueError("前提必须写明适用范围 scope（事先选定）")
        kind = ScopeKind(scope["kind"])
        c = self.store.conn
        if kind is ScopeKind.CACHE:
            if not self._cache_exists(scope.get("cache_id")):
                raise ValueError("适用范围里的工作缓存不存在")
        elif kind is ScopeKind.NODE:
            sql, args = "SELECT 1 FROM ast_nodes WHERE node_id = ?", [scope.get("node_id")]
            if scope.get("version") is not None:
                sql += " AND version = ?"
                args.append(scope["version"])
            if c.execute(sql, args).fetchone() is None:
                raise ValueError("适用范围里的事件链节点不存在")
        elif kind is ScopeKind.OCCURRENCE:
            if c.execute("SELECT 1 FROM occurrences WHERE occurrence_id = ?",
                         (scope.get("occurrence_id"),)).fetchone() is None:
                raise ValueError("适用范围里的发生不存在")
        elif kind is ScopeKind.TIME:
            if not scope.get("from"):
                raise ValueError("时间范围要写明 from")
            if scope.get("until") is not None and not scope["from"] < scope["until"]:
                raise ValueError("时间范围要满足 from < until")

    def _occurrence_chain(self, occurrence_id: int) -> tuple[list[int], list[tuple[str, int]]]:
        occ, nodes = [], []
        cur = occurrence_id
        while cur is not None:
            node_id, version, parent = self.store.conn.execute(
                "SELECT node_id, version, parent_occurrence_id FROM occurrences WHERE occurrence_id = ?", (cur,)).fetchone()
            occ.append(cur)
            nodes.append((node_id, version))
            cur = parent
        return occ, nodes

    def _tag(self, kind, ref, world_id, action, basis_ids, reason) -> None:
        if kind == "memory":
            raise ValueError("记忆的适用世界在形成时确定，外部标注不能改写；要改请修订记忆（新建承接版本）")
        if kind not in TAG_KINDS:
            raise ValueError(f"只能给 {TAG_KINDS} 标世界")
        if not self._world_exists(world_id):
            raise ValueError(f"世界 {world_id} 不存在")
        if not basis_ids:
            raise ValueError("标注世界要写明依据")
        self._check_exist(basis_ids)
        self._check_target(kind, ref)
        with self.store.transaction() as c:
            c.execute("INSERT INTO world_tags(target_kind, target_ref, world_id, action, basis_json, reason)"
                      " VALUES (?, ?, ?, ?, ?, ?)", (kind, str(ref), world_id, action, json.dumps(list(basis_ids)), reason))

    def _explicit_worlds(self, kind, ref) -> set[str]:
        worlds: set[str] = set()
        for world_id, action in self.store.conn.execute(
                "SELECT world_id, action FROM world_tags WHERE target_kind = ? AND target_ref = ? ORDER BY tag_id",
                (kind, str(ref))):
            (worlds.add if action == "ADD" else worlds.discard)(world_id)
        return worlds

    def _check_target(self, kind, ref) -> None:
        c = self.store.conn
        if kind == "package":
            ok = c.execute("SELECT 1 FROM packages WHERE package_id = ?", (str(ref),)).fetchone()
        elif kind == "memory":
            ok = c.execute("SELECT 1 FROM memory_items WHERE memory_id = ?", (int(ref),)).fetchone()
        else:
            ok = c.execute("SELECT 1 FROM experiences WHERE experience_id = ?", (int(ref),)).fetchone()
        if ok is None:
            raise ValueError(f"{kind}:{ref} 不存在")

    def _cache_ref(self, kind: ItemKind, ref: Ref) -> str:
        if kind is ItemKind.WORLD:
            return str(ref)
        if kind is ItemKind.PACKAGE:
            pid, ver = ref
            if self.store.conn.execute("SELECT 1 FROM package_versions WHERE package_id = ? AND version = ?",
                                       (pid, ver)).fetchone() is None:
                raise ValueError(f"知识包版本 {pid}@{ver} 不存在")
            return f"{pid}@v{int(ver)}"
        self._check_target(kind.value, ref)
        return str(int(ref))

    def _log(self, c, cache_id, action, kind, ref, priority, cross, reason) -> None:
        c.execute("INSERT INTO cache_log(cache_id, action, item_kind, item_ref, priority, cross_world, reason)"
                  " VALUES (?, ?, ?, ?, ?, ?, ?)", (cache_id, action, ItemKind(kind).value, ref, priority, int(cross), reason))

    def _flag_calls(self, cache_id: int, package: Optional[tuple[str, int]], trigger: dict) -> None:
        sql, args = "SELECT call_id FROM calls WHERE cache_id = ?", [cache_id]
        if package is not None:
            sql += " AND package_id = ? AND version = ?"
            args += list(package)
        with self.store.transaction() as c:
            c.executemany("INSERT INTO rechecks(call_id, trigger_json) VALUES (?, ?)",
                          [(cid, _dumps(trigger)) for (cid,) in c.execute(sql, args).fetchall()])

    def _caches_that_entered(self, kind: ItemKind, ref: str) -> list[int]:
        return [r[0] for r in self.store.conn.execute(
            "SELECT DISTINCT cache_id FROM cache_log WHERE action = 'ENTER' AND item_kind = ? AND item_ref = ?"
            " ORDER BY cache_id", (ItemKind(kind).value, ref))]

    def _require_open(self, cache_id: int) -> None:
        if self.cache_status(cache_id) != "OPEN":
            raise ValueError(f"工作缓存 {cache_id} 已关闭")

    def _cache_exists(self, cache_id) -> bool:
        return self.store.conn.execute("SELECT 1 FROM work_caches WHERE cache_id = ?", (cache_id,)).fetchone() is not None

    def _world_exists(self, world_id) -> bool:
        return self.store.conn.execute("SELECT 1 FROM worlds WHERE world_id = ?", (world_id,)).fetchone() is not None

    def _check_exist(self, ids: Sequence[int]) -> None:
        for ev in ids:
            if not self.experiences.exists(ev):
                raise ValueError(f"依据记录 {ev} 不存在")


def _covers(scope: dict, cache_id: int, chain_occ: list[int], chain_nodes: list[tuple[str, int]],
            at: Optional[str]) -> bool:
    kind = ScopeKind(scope["kind"])
    if kind is ScopeKind.WORLD:
        return True
    if kind is ScopeKind.CACHE:
        return scope["cache_id"] == cache_id
    if kind is ScopeKind.NODE:
        return any(n == scope["node_id"] and (scope.get("version") is None or v == scope["version"])
                   for n, v in chain_nodes)
    if kind is ScopeKind.OCCURRENCE:
        return scope["occurrence_id"] in chain_occ
    # TIME：没有给出当前时间，就不能说它适用。
    return at is not None and scope["from"] <= at and (scope.get("until") is None or at < scope["until"])


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
