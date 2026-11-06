"""分段计时工具（测试方案 v0.1 第四节“计时规则”；名词解释 v0.15 优化检查清单第 6 项）。

- 分段记录：例如“CPU 准备”“神经计算”“保存”各自计时，不混成一个总数。
- 每段至少重复几次，去掉预热，报告中位数和全部原始数值；同时记下硬件、线程数和软件版本。
- 只负责计时，不判断快慢是否合理（v0.15：慢不能单独证明架构错误，“保存历史”也不能证明慢得合理）。
"""
from __future__ import annotations

import os
import platform
import statistics
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Callable


class SegmentTimer:
    def __init__(self):
        self.samples: dict[str, list[float]] = defaultdict(list)

    @contextmanager
    def segment(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.samples[name].append(time.perf_counter() - start)

    def summary(self, warmup: int = 0) -> dict:
        """每段：去掉前 warmup 次后的中位数、次数、原始数值（秒）。"""
        out = {}
        for name, xs in self.samples.items():
            kept = xs[warmup:]
            if not kept:
                raise ValueError(f"段 {name} 去掉预热后没有样本")
            out[name] = {"median_s": statistics.median(kept), "n": len(kept), "raw_s": kept}
        return out


def time_call(fn: Callable[[], object], repeats: int = 5, warmup: int = 1) -> dict:
    """重复调用 fn，去掉预热，报告中位数（秒）。"""
    if repeats < 1:
        raise ValueError("至少重复一次")
    timer = SegmentTimer()
    for _ in range(warmup + repeats):
        with timer.segment("call"):
            fn()
    return timer.summary(warmup)["call"]


def environment() -> dict:
    """计时时的环境：硬件、线程数、软件版本。"""
    info = {"platform": platform.platform(), "processor": platform.processor(), "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "omp_threads": os.environ.get("OMP_NUM_THREADS"), "mkl_threads": os.environ.get("MKL_NUM_THREADS")}
    try:
        import torch
        info.update({"torch": torch.__version__, "torch_threads": torch.get_num_threads(),
                     "cuda_available": torch.cuda.is_available()})
    except ImportError:
        info["torch"] = None
    return info
