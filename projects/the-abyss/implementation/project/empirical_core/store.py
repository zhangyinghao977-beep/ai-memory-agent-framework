"""共享 SQLite 存储：知识库与记忆层用同一个库文件（名词解释：记忆层与知识库目前强绑定）。"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .schema import SCHEMA


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    """登记时间（UTC）。v0.15：登记时间、事件发生时间与版本号是三件事。"""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Store:
    """持有单一连接；嵌套的 `transaction()` 只在最外层提交一次（批量写入单事务提交）。"""

    def __init__(self, path: str, readonly: bool = False):
        self.path = path
        self.readonly = readonly
        if readonly:
            uri = f"file:{path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True)
        else:
            self.conn = sqlite3.connect(path)
            self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._depth = 0
        if not readonly:
            with self.transaction():
                self.conn.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self.readonly:
            raise PermissionError("只读存储不能写入")
        self._depth += 1
        try:
            yield self.conn
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.conn.rollback()
            raise
        self._depth -= 1
        if self._depth == 0:
            self.conn.commit()

    def put_content(self, text: str) -> str:
        """相同内容只存一份；不同发生由记忆层的事件区分。"""
        h = content_hash(text)
        with self.transaction() as c:
            c.execute("INSERT OR IGNORE INTO contents(content_hash, content) VALUES (?, ?)", (h, text))
        return h

    def get_content(self, h: str) -> str:
        row = self.conn.execute("SELECT content FROM contents WHERE content_hash = ?", (h,)).fetchone()
        if row is None:
            raise KeyError(h)
        return row[0]

    def backup(self, dest_path: str) -> None:
        """整库一致性备份（SQLite 在线备份）。只能在没有未提交事务时做，保证备份是某一时刻的完整状态。"""
        if self._depth != 0:
            raise RuntimeError("事务进行中，不能备份")
        dst = sqlite3.connect(dest_path)
        try:
            self.conn.backup(dst)
        finally:
            dst.close()

    def close(self) -> None:
        self.conn.close()
