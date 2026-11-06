"""联合状态恢复的最小检查（名词解释 v0.15“三种能力分别记证据”中的“联合状态恢复”）。

恢复边界（要写清楚）：这里的“联合状态”指同一个 SQLite 库里的经验、记忆、知识包、阀门、事件链 AST、
计算经历、修正记录与学习材料库。神经网络权重、外部工具与环境的历史状态**不在**这个边界里。
本模块只检查一份库（例如备份恢复后的库）里的引用是否彼此相容：
- SQLite 自身完整性与外键；
- 写在 JSON 里、外键管不到的引用（记忆绑定、成员来源、绑定引用、依据列表等）是否都能解析；
- 计算调用记下的可见视图位置是否仍然存在。
它不证明“任意时间点都能恢复”，也不是确定性重放。
"""
from __future__ import annotations

import json

from .store import Store

_REF_TABLES = {"experience": ("experiences", "experience_id"), "memory": ("memory_items", "memory_id"),
               "material": ("materials", "material_id"), "call": ("calls", "call_id")}


def table_counts(store: Store) -> dict[str, int]:
    names = [r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {n: store.conn.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0] for n in names}


def check_integrity(store: Store) -> dict:
    c = store.conn
    problems: list[str] = []
    ic = c.execute("PRAGMA integrity_check").fetchone()[0]
    if ic != "ok":
        problems.append(f"SQLite 完整性检查：{ic}")
    for row in c.execute("PRAGMA foreign_key_check").fetchall():
        problems.append(f"外键不成立：表 {row[0]} 第 {row[1]} 行 → {row[2]}")

    def exists(kind: str, ident) -> bool:
        if kind == "package":
            return False
        table, key = _REF_TABLES[kind]
        return c.execute(f"SELECT 1 FROM {table} WHERE {key} = ?", (ident,)).fetchone() is not None

    def package_version_exists(pid, ver) -> bool:
        return c.execute("SELECT 1 FROM package_versions WHERE package_id = ? AND version = ?", (pid, ver)).fetchone() is not None

    def check_ref(ref: dict, where: str) -> None:
        kind = ref.get("kind")
        if kind == "literal":
            return
        if kind == "package":
            if not package_version_exists(ref.get("id"), ref.get("version")):
                problems.append(f"{where}：包版本 {ref.get('id')}@{ref.get('version')} 不存在")
        elif kind in _REF_TABLES:
            if not exists(kind, ref.get("id")):
                problems.append(f"{where}：{kind}:{ref.get('id')} 不存在")
        else:
            problems.append(f"{where}：无法识别的引用 {ref}")

    def check_ids(ids, kind: str, where: str) -> None:
        for i in ids:
            if not exists(kind, i):
                problems.append(f"{where}：{kind}:{i} 不存在")

    for mid, bindings, revises in c.execute("SELECT memory_id, bindings_json, revises_memory_id FROM memory_items"):
        if bindings:
            for name, ref in json.loads(bindings).items():
                check_ref(ref, f"记忆 {mid} 的绑定 {name}")
        if revises is not None and not revises < mid:
            problems.append(f"记忆 {mid} 承接的版本 {revises} 不在它之前")
    for pid, ver, pos, src in c.execute("SELECT package_id, version, position, sources_json FROM version_members"):
        check_ids(json.loads(src), "experience", f"包 {pid}@{ver} 成员 {pos} 的来源")
    for pid, ver, basis in c.execute("SELECT package_id, version, basis_json FROM package_versions"):
        check_ids(json.loads(basis), "experience", f"包 {pid}@{ver} 的依据")
    for occ, slot, state, value in c.execute("SELECT occurrence_id, slot, state, value_json FROM occurrence_bindings"):
        refs = [] if state == "GAP" else ([json.loads(value)] if state == "BOUND" else json.loads(value))
        for ref in refs:
            check_ref(ref, f"发生 {occ} 的绑定 {slot}")
    for call_id, cache_id, mark in c.execute("SELECT call_id, cache_id, cache_log_mark FROM calls"):
        top = c.execute("SELECT MAX(log_id) FROM cache_log WHERE cache_id = ?", (cache_id,)).fetchone()[0] or 0
        if not 0 <= mark <= top:
            problems.append(f"调用 {call_id} 记下的可见视图位置 {mark} 不存在")
    for item, kind, sid in c.execute("SELECT item_id, source_kind, source_id FROM learning_items"):
        if not exists(kind, sid):
            problems.append(f"学习材料 {item} 的来源 {kind}:{sid} 不存在")
    for tag, kind, ref in c.execute("SELECT tag_id, target_kind, target_ref FROM world_tags"):
        ok = (c.execute("SELECT 1 FROM packages WHERE package_id = ?", (ref,)).fetchone() is not None
              if kind == "package" else exists(kind, int(ref)))
        if not ok:
            problems.append(f"世界标注 {tag} 指向的 {kind}:{ref} 不存在")
    return {"ok": not problems, "problems": problems,
            "boundary": "单个 SQLite 库内的联合状态；不含神经网络权重、外部工具与环境状态"}
