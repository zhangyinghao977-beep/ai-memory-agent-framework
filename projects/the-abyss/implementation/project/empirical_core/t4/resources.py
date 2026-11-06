"""T4 的资源：真实资源计量、清醒池／睡眠池、资源保护（2026-11-03）。

额度使用真实计算资源：
- CPU：本进程的 CPU 时间（psutil 的 user＋system，所有线程合计）；
- 显卡：忙碌时间（每步等显卡算完再计时，同 T1–T3 的限流器）；
- 另外查看进程内存和显存峰值。
经验主义 v0.55 设计：清醒和睡眠各自一份资源池。一次循环（这里是一天）里各轮共用一份池子，不每轮刷新；
累计消耗写进快速登记，重启后接着算，不重置。
资源保护（借用红尘仙 0.4 的思想）：优先级最高，用到触发比例就提前打断，留出余量来保存和报告。
"""
from __future__ import annotations

import time
from typing import Optional

from .records import QuickLog

RESOURCES = ("cpu_seconds", "gpu_seconds")


class ResourceInterrupt(RuntimeError):
    """资源保护打断当前活动：调用方先保存进度、登记中断，再报告。"""


class Meter:
    """真实资源读数。gpu_seconds 由限流器在每步等显卡算完时累加。"""

    def __init__(self, proc, use_gpu: bool):
        self.proc, self.use_gpu = proc, use_gpu
        self.gpu_busy = 0.0

    def cpu_seconds(self) -> float:
        t = self.proc.cpu_times()
        return t.user + t.system

    def reading(self) -> dict:
        return {"cpu_seconds": self.cpu_seconds(), "gpu_seconds": self.gpu_busy}

    def memory(self) -> dict:
        out = {"rss_bytes": self.proc.memory_info().rss}
        if self.use_gpu:
            import torch
            out["gpu_max_allocated_bytes"] = torch.cuda.max_memory_allocated()
        return out


class Pool:
    """一份资源池：每种资源一个额度；消耗按真实读数的增量记账。
    persist() 把累计消耗写进快速登记；恢复时取同一池子、同一循环最后一次登记的累计值。"""

    def __init__(self, name: str, budget: dict, log: QuickLog, cycle: int):
        self.name, self.budget, self.log, self.cycle = name, dict(budget), log, cycle
        self.used = {k: 0.0 for k in RESOURCES}
        for r in log.of_kind("pool"):
            if r["pool"] == name and r["cycle"] == cycle:
                self.used = dict(r["used"])
        self._mark: Optional[dict] = None

    def open(self, meter: Meter) -> None:
        self._mark = meter.reading()

    def charge(self, meter: Meter) -> None:
        """把上次 open／charge 以来的真实消耗记到这份池子。"""
        if self._mark is None:
            return
        now = meter.reading()
        for k in RESOURCES:
            self.used[k] += max(0.0, now[k] - self._mark[k])
        self._mark = now

    def close(self, meter: Meter) -> None:
        self.charge(meter)
        self._mark = None
        self.persist()

    def frac_used(self) -> float:
        return max(self.used[k] / self.budget[k] for k in RESOURCES if self.budget.get(k))

    def left(self) -> float:
        return max(0.0, 1.0 - self.frac_used())

    def persist(self) -> dict:
        return self.log.append("pool", pool=self.name, cycle=self.cycle, used=self.used, budget=self.budget)


class Protector:
    """资源保护：优先级最高，不替上层选结论，只负责在用到触发比例时打断。
    触发比例小于 1，剩下的部分就是留给保存和报告的余量。也看整个进程的内存上限。"""

    def __init__(self, meter: Meter, trigger: float, max_rss_bytes: int):
        if not 0 < trigger < 1:
            raise ValueError("触发比例要在 0 和 1 之间，留出保存和报告的余量")
        self.meter, self.trigger, self.max_rss = meter, trigger, max_rss_bytes
        self.active: Optional[Pool] = None
        self.trips: list[dict] = []

    def check(self) -> None:
        if self.active is not None:
            self.active.charge(self.meter)
            if self.active.frac_used() >= self.trigger:
                self._trip(f"{self.active.name} 池用到 {self.active.frac_used():.1%}，达到触发比例 {self.trigger:.0%}")
        rss = self.meter.proc.memory_info().rss
        if rss > self.max_rss:
            self._trip(f"进程内存 {rss} 字节超过上限 {self.max_rss}")

    def _trip(self, why: str) -> None:
        self.trips.append({"time": time.time(), "why": why})
        raise ResourceInterrupt(why)


class Throttle:
    """训练循环每一步都会调用（同 T1–T3 的 Guard）：用显卡时等这一步算完，记下忙了多久，再歇 1/占空比 − 1 倍；
    忙碌时间累加进 Meter.gpu_busy。随后交给资源保护检查。"""

    def __init__(self, meter: Meter, protector: Protector, gpu_duty: Optional[float]):
        self.meter, self.protector, self.gpu_duty = meter, protector, gpu_duty
        self.mark = time.perf_counter()
        self.slept = 0.0
        self.gpu_phase = True           # KA 在 CPU 上算时设为 False：不把 CPU 的时间算成显卡忙碌（CPU 时间另由进程读数计）

    def __call__(self) -> None:
        if self.gpu_duty and not self.gpu_phase:
            self.mark = time.perf_counter()
        elif self.gpu_duty:
            import torch
            torch.cuda.synchronize()
            busy = time.perf_counter() - self.mark
            self.meter.gpu_busy += busy
            pause = busy * (1 / self.gpu_duty - 1)
            time.sleep(pause)
            self.slept += pause
            self.mark = time.perf_counter()
        self.protector.check()
