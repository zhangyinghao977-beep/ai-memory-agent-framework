"""T2 的修复写范围与逐级加深（2026-11-02）。

写范围（只允许写哪些单元）：
- CA、EA：一个单元；
- KA_local：系统自己找出的“和变更有关的”KA 单元＝新材料里出现、但从来没训练过的包（版本号为 0）。
  C1 里正好是遗漏的包；C2、C3 里没有这样的包，KA_local 为空。
- KA_all：全部 KA 单元。

逐级加深（梯子事先固定，每级都从基线快照出发；不够用就回退到基线再试下一级）：
1. KA_local（有新单元时才有这一级）；2. CA；3. EA；4. CA＋EA；5. 全部（CA＋EA＋KA_all）。
排序依据：先修有具体触发点、范围最小的单元；没有具体触发点时，从反馈到达的上层（CA）开始往下查。
这只是一种固定的排法，结论依赖于它。
“够用”的标准（v0.56：够用就可以停）：新条件 DEV 正确率、旧条件 DEV 正确率都不低于基线在旧条件 DEV 上的正确率减去 margin。
没有一级够用时：采用旧条件仍在标准内、新条件 DEV 最高的那一级；一级都不行就保留基线。照实登记“未达到够用标准”。
失败的尝试照样写成新版本并登记（v0.53／v0.54：受阻和失败的尝试都保留），只是不采用。
"""
from __future__ import annotations

from typing import Callable

import torch

from .spiral import ChainSpiral, ka_name

LADDER = (("KA_local",), ("CA",), ("EA",), ("CA", "EA"), ("CA", "EA", "KA_all"))


def local_packages(sp: ChainSpiral, new_idx: torch.Tensor) -> list[int]:
    """新材料里出现、但还从来没训练过的包（系统自己从版本号看出来，不由出题器告诉它）。"""
    tr = sp.train
    pkgs = torch.unique(tr.ev_pkg[new_idx][tr.ev_valid[new_idx] > 0]).tolist()
    return [p for p in pkgs if sp.store.version(ka_name(p)) == 0]


def resolve_scope(layers, sp: ChainSpiral, new_idx: torch.Tensor) -> dict:
    ka = []
    if "KA_all" in layers:
        ka = list(range(sp.cfg.n_packages))
    elif "KA_local" in layers:
        ka = local_packages(sp, new_idx)
    return {"ka_packages": ka, "ea": "EA" in layers, "ca": "CA" in layers}


def is_empty(scope: dict) -> bool:
    return not (scope["ka_packages"] or scope["ea"] or scope["ca"])


def escalate(sp: ChainSpiral, base_snapshot: dict, tag: str, new_idx: torch.Tensor, old_idx: torch.Tensor, *,
             rounds: int, replay_ratio: float, check: Callable[[], dict], target: float, margin: float) -> dict:
    """按 LADDER 一级一级试。check() 返回 {"new_dev": 正确率, "old_dev": 正确率}。返回试过的每一级和最后采用的快照。"""
    bar = target - margin
    trace, adopted = [], None
    for layers in LADDER:
        sp.store.restore(base_snapshot)
        scope = resolve_scope(layers, sp, new_idx)
        step = {"layers": list(layers), "ka_packages": scope["ka_packages"]}
        if is_empty(scope):
            trace.append({**step, "skipped": "写范围为空"})
            continue
        step_tag = f"{tag}/{'+'.join(layers)}"
        sp.repair(step_tag, new_idx, old_idx, rounds=rounds, replay_ratio=replay_ratio, **scope)
        acc = check()
        ok = acc["new_dev"] >= bar and acc["old_dev"] >= bar
        trace.append({**step, "tag": step_tag, **acc, "enough": ok, "snapshot": sp.store.snapshot()})
        if ok:
            adopted = trace[-1]
            break
    status = "enough"
    if adopted is None:
        keep = [t for t in trace if "snapshot" in t and t["old_dev"] >= bar]
        adopted = max(keep, key=lambda t: t["new_dev"]) if keep else None
        status = "not_enough_best_kept" if adopted else "not_enough_base_kept"
    sp.store.restore(adopted["snapshot"] if adopted else base_snapshot)
    return {"trace": trace, "status": status, "bar": bar, "adopted": adopted["tag"] if adopted else None}
