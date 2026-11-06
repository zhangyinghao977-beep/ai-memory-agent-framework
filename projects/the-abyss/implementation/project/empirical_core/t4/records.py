"""T4 的记忆登记：快速登记、长期登记、固定调用协议、重启恢复。

借用红尘仙 0.4 的设计思想（只借思想，不算对红尘仙的验证）：
- 调用开始登记一份记忆；调用结束或中断时登记另一份关联记忆，再报告。严格先保存成功，再报告。
- 已存但没报告：保留“已存待报”，重启后对同一调用补报，不重新执行；保存失败不假称登记完成。
- 快速登记保存当前进度，面向意外重启后的恢复；长期登记整理成记录库，带索引和 description。
  两者各做各的，通过固定输入输出协作：输入是记录范围，输出是结果和位置，失败保留未完成。
- 已有带时间戳的记录保持稳定，新增记录带新时间戳。
- 缺项用符号的空状态查询发现。补全需要语义；这里没有语言逻辑，description 用符号模板生成，标为占位。
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Callable, Optional

_CRASH_SEEN: dict[str, int] = {}


def crashpoint(name: str) -> None:
    """重启测试用：环境变量 T4_CRASH_AT＝name、T4_CRASH_NTH＝n 时，第 n 次经过这里就硬退出进程
    （os._exit：不跑 finally、不刷缓冲，相当于突然断电）。正式运行不设这两个变量。"""
    if os.environ.get("T4_CRASH_AT") != name:
        return
    _CRASH_SEEN[name] = _CRASH_SEEN.get(name, 0) + 1
    if _CRASH_SEEN[name] >= int(os.environ.get("T4_CRASH_NTH", "1")):
        os._exit(86)


class QuickLog:
    """快速登记：只追加的 JSONL，每条写完就落盘（fsync）。重启时从这里恢复进度。
    最后一行如果只写了一半（断电），它从来没有保存成功：原样移到 .torn.jsonl 登记，再把文件截回完整的部分。
    中间某行坏了不是断电能造成的，直接报错，不自动修。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[dict] = []
        self.torn: Optional[str] = None
        if self.path.exists():
            raw = self.path.read_bytes()
            lines = raw.split(b"\n")
            keep = 0
            for i, line in enumerate(lines):
                if not line:
                    continue
                try:
                    self.records.append(json.loads(line.decode("utf-8")))
                    keep += len(line) + 1
                except (json.JSONDecodeError, UnicodeDecodeError):
                    if i != len(lines) - 1:
                        raise RuntimeError(f"{self.path} 第 {i + 1} 行损坏，不是断电留下的半行，拒绝自动修复")
                    self.torn = line.decode("utf-8", errors="replace")
            if self.torn is not None:
                with open(self.path.with_suffix(".torn.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"time": time.time(), "torn_tail": self.torn}, ensure_ascii=False) + "\n")
                with open(self.path, "r+b") as f:
                    f.truncate(keep)
        for i, rec in enumerate(self.records):
            if rec.get("seq") != i:
                raise RuntimeError(f"{self.path} 的序号不连续（第 {i} 条是 {rec.get('seq')}）")

    @property
    def seq(self) -> int:
        return len(self.records)

    def append(self, kind: str, **fields) -> dict:
        rec = {"seq": self.seq, "time": time.time(), "kind": kind, **fields}
        line = json.dumps(rec, ensure_ascii=False, default=str) + "\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        self.records.append(rec)
        return rec

    def of_kind(self, *kinds: str) -> list[dict]:
        return [r for r in self.records if r["kind"] in kinds]


class CallProtocol:
    """固定调用协议：开始登记 → 执行 → 结束（或中断）登记 → 保存成功 → 报告 → 登记已报告。
    report 是把结果交给上层（这里是存活循环里的“逻辑”）；它只在结束记录保存成功之后才发生。"""

    def __init__(self, log: QuickLog):
        self.log = log
        ids = [r["call"] for r in log.of_kind("call_start")]
        self.next_id = max(ids, default=-1) + 1

    def start(self, call_kind: str, **info) -> int:
        cid = self.next_id
        self.next_id += 1
        self.log.append("call_start", call=cid, call_kind=call_kind, **info)
        crashpoint("after_call_start")
        return cid

    def end(self, cid: int, status: str, **result) -> dict:
        rec = self.log.append("call_end", call=cid, status=status, **result)
        crashpoint("after_call_end")
        return rec

    def report(self, cid: int, end_rec: dict, reporter: Callable[[dict], None], late: bool = False) -> None:
        reporter(end_rec)
        self.log.append("report", call=cid, late=late)

    def run(self, call_kind: str, fn: Callable[[], dict], reporter: Callable[[dict], None], interrupt=(), **info):
        """执行一次调用。fn 抛出 interrupt 里的异常（资源保护打断）时，登记“中断”并报告，然后把异常继续抛出去。"""
        cid = self.start(call_kind, **info)
        try:
            result = fn()
        except interrupt as e:
            rec = self.end(cid, "interrupted", call_kind=call_kind, reason=str(e))
            self.report(cid, rec, reporter)
            raise
        rec = self.end(cid, "done", call_kind=call_kind, **result)
        self.report(cid, rec, reporter)
        return rec


def recover(log: QuickLog, reporter: Callable[[dict], None]) -> dict:
    """重启后的恢复（只按快速登记里已经保存成功的记录）：
    - 有开始、没结束：调用在执行中断电。登记一份“断电中断”的结束记录并报告；不重新执行。
    - 有结束、没报告：已存待报。对同一调用补报一次，不重新执行。"""
    starts = {r["call"]: r for r in log.of_kind("call_start")}
    ends = {r["call"]: r for r in log.of_kind("call_end")}
    reported = {r["call"] for r in log.of_kind("report")}
    proto = CallProtocol(log)
    lost, late = [], []
    for cid, st in sorted(starts.items()):
        if cid not in ends:
            rec = log.append("call_end", call=cid, status="lost_in_crash", call_kind=st["call_kind"])
            proto.report(cid, rec, reporter, late=True)
            lost.append(cid)
        elif cid not in reported:
            proto.report(cid, ends[cid], reporter, late=True)
            late.append(cid)
    rec = log.append("recovered", lost_calls=lost, late_reports=late, torn_tail=log.torn is not None)
    return {"lost_calls": lost, "late_reports": late, "torn_tail": log.torn, "record": rec}


class LongStore:
    """长期登记：SQLite 记录库，带索引和 description。由走神时的后台整理写入。
    固定输入输出：输入是快速登记的一段序号范围；输出是写入的条数和库的位置；
    整段在一个事务里提交，提交以前断电，游标不动，下次从同一处重做（失败保留未完成）。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS records (seq INTEGER PRIMARY KEY, time REAL, kind TEXT, call INTEGER,
                                                day INTEGER, payload TEXT);
            CREATE TABLE IF NOT EXISTS idx (seq INTEGER, key TEXT, value TEXT);
            CREATE TABLE IF NOT EXISTS descr (seq INTEGER PRIMARY KEY, text TEXT, source TEXT);
        """)
        self.conn.commit()

    def cursor(self) -> int:
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'cursor'").fetchone()
        return int(row[0]) if row else 0

    def consolidate(self, log: QuickLog, upto: Optional[int] = None, describe: bool = True) -> dict:
        start = self.cursor()
        stop = log.seq if upto is None else min(upto, log.seq)
        rows = log.records[start:stop]
        cur = self.conn.cursor()
        for r in rows:
            cur.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
                        (r["seq"], r["time"], r["kind"], r.get("call"), r.get("day"),
                         json.dumps(r, ensure_ascii=False, default=str)))
            for key in ("kind", "call", "day", "qid", "state"):
                if r.get(key) is not None:
                    cur.execute("INSERT INTO idx VALUES (?, ?, ?)", (r["seq"], key, str(r[key])))
            if describe:
                cur.execute("INSERT INTO descr VALUES (?, ?, ?)", (r["seq"], template_description(r), "template_placeholder"))
        cur.execute("INSERT OR REPLACE INTO meta VALUES ('cursor', ?)", (str(stop),))
        crashpoint("before_long_commit")
        self.conn.commit()
        return {"input": [start, stop], "output": {"rows": len(rows), "location": str(self.path)}, "status": "done"}

    def missing(self) -> dict:
        """空状态查询（纯符号）：哪些已保存的记录还没有 description、没有索引。缺项不妨碍记录本身已保存。"""
        no_descr = [s for (s,) in self.conn.execute(
            "SELECT seq FROM records WHERE seq NOT IN (SELECT seq FROM descr) ORDER BY seq")]
        no_idx = [s for (s,) in self.conn.execute(
            "SELECT seq FROM records WHERE seq NOT IN (SELECT seq FROM idx) ORDER BY seq")]
        return {"no_description": no_descr, "no_index": no_idx}

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    def close(self) -> None:
        self.conn.close()


def template_description(r: dict) -> str:
    """占位的 description：只按字段拼出来，不是语义理解。"""
    parts = [r["kind"]]
    for key in ("call", "day", "qid", "status", "state"):
        if r.get(key) is not None:
            parts.append(f"{key}={r[key]}")
    return " ".join(parts)
