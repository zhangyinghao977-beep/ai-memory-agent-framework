"""学习材料库（名词解释 v0.16、v0.17：why 层为 attention／映射函数学习提供材料的载体，偏训练语料）。

- 学习材料库**不是记忆**。条目只是指向某条记忆、经验或计算经历的引用（它们本身都不会被改写），
  记录“拿它来学什么”。方向是单向的：记忆可以被抽象成学习材料，学习材料不能反过来改动记忆。
- 收录不等于证实：条目没有“真假”字段；材料里的陈述是否成立，仍看经验的核实记录。
- 提供材料不等于训练已经发生：只有登记了一次训练记录（record_training），才说明哪些材料被用来产生了哪个参数版本。
  这样“参数版本 ← 训练记录 ← 学习材料 ← 记忆／经验”可以一路回查（v0.15 形成依据的可回溯）。
- 已被遗忘（不可达）的记忆不能再收进来。
具体怎样提取、编码、调用与反馈，名词解释写着仍需落实，这里不代填。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from .store import Store, now_iso

SOURCE_KINDS = ("memory", "experience", "call")


@dataclass(frozen=True)
class LearningItem:
    item_id: int
    source_kind: str
    source_id: int
    purpose: str
    reason: str


class LearningMaterialStore:
    def __init__(self, store: Store):
        self.store = store

    def add(self, source_kind: str, source_id: int, purpose: str, reason: str) -> int:
        """收录一条学习材料（只存引用，不复制、不改动来源）。"""
        if source_kind not in SOURCE_KINDS:
            raise ValueError(f"学习材料只能来自 {SOURCE_KINDS}")
        if not purpose:
            raise ValueError("要写明拿它来学什么")
        c = self.store.conn
        table, key = {"memory": ("memory_items", "memory_id"), "experience": ("experiences", "experience_id"),
                      "call": ("calls", "call_id")}[source_kind]
        if c.execute(f"SELECT 1 FROM {table} WHERE {key} = ?", (source_id,)).fetchone() is None:
            raise ValueError(f"{source_kind}:{source_id} 不存在")
        if source_kind == "memory" and not _memory_reachable(c, source_id):
            raise ValueError(f"记忆 {source_id} 已被遗忘（不可达），不能再收进学习材料库")
        with self.store.transaction() as c:
            return c.execute("INSERT INTO learning_items(source_kind, source_id, purpose, reason, recorded_at)"
                             " VALUES (?, ?, ?, ?, ?)", (source_kind, source_id, purpose, reason, now_iso())).lastrowid

    def get(self, item_id: int) -> LearningItem:
        row = self.store.conn.execute("SELECT source_kind, source_id, purpose, reason FROM learning_items WHERE item_id = ?",
                                      (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return LearningItem(item_id, *row)

    def record_training(self, *, computation_id: str, parameter_version: dict, item_ids: Sequence[int],
                        purpose: str) -> int:
        """登记一次训练：用了哪些学习材料，产生了哪个参数版本。训练本身在别处进行，这里只记收据。"""
        if not item_ids:
            raise ValueError("训练记录要写明用了哪些学习材料")
        if not isinstance(parameter_version, dict) or parameter_version.get("kind") != "weights" \
                or not parameter_version.get("sha256"):
            raise ValueError("训练记录的参数版本必须是 {'kind': 'weights', 'sha256': ...}")
        for i in item_ids:
            self.get(i)
        with self.store.transaction() as c:
            tid = c.execute("INSERT INTO training_runs(computation_id, parameter_version_json, purpose, recorded_at)"
                            " VALUES (?, ?, ?, ?)",
                            (computation_id, json.dumps(parameter_version, sort_keys=True), purpose, now_iso())).lastrowid
            c.executemany("INSERT INTO training_run_items(training_id, item_id) VALUES (?, ?)",
                          [(tid, int(i)) for i in dict.fromkeys(item_ids)])
        return tid

    def training(self, training_id: int) -> dict:
        row = self.store.conn.execute(
            "SELECT computation_id, parameter_version_json, purpose FROM training_runs WHERE training_id = ?",
            (training_id,)).fetchone()
        if row is None:
            raise KeyError(training_id)
        items = [r[0] for r in self.store.conn.execute(
            "SELECT item_id FROM training_run_items WHERE training_id = ? ORDER BY item_id", (training_id,))]
        return {"training_id": training_id, "computation_id": row[0], "parameter_version": json.loads(row[1]),
                "purpose": row[2], "items": items}

    def trainings_using(self, item_id: int) -> list[int]:
        """这条材料被哪些训练用过；没有就说明它还只是被收录，没有被用来训练。"""
        return [r[0] for r in self.store.conn.execute(
            "SELECT training_id FROM training_run_items WHERE item_id = ? ORDER BY training_id", (item_id,))]


def _memory_reachable(c, memory_id: int) -> bool:
    row = c.execute("SELECT action FROM memory_reachability WHERE memory_id = ? ORDER BY event_id DESC LIMIT 1",
                    (memory_id,)).fetchone()
    return row is None or row[0] == "RESTORE"
