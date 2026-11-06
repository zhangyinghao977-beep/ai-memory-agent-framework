"""T2 的门禁、分层与简单基线。都只用 TRAIN 的反馈，不看隐藏数值。

- 门禁（同 T1）：对每个条件的留出集，按（无序对象对, 当前世界）做“决定因素重合＋单部分捷径”审计。
  A、B 和当前世界用出题规则解析（theory_resolve）：这是理论侧的审计，不是模型能看到的信息。
- majority：恒选 TRAIN 里最常见的答案。
- 路径推理（知道话语规则）：用出题规则解析 TRAIN 的每道题，换成物理世界里的“x 大于 y”，按传递关系推；推不出返回 None。
  它知道 CA、EA 要学的那两条规则，所以只是“逻辑可达”的参照，不是同条件的竞争者。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable, Optional

from ..evaluation.gates import Example, decisive_factor_audit
from .task import theory_resolve

KEY = lambda x: (tuple(sorted((x["A"], x["B"]))), x["world"])
PARTS = {"A+world": lambda x: (x["A"], x["world"]), "B+world": lambda x: (x["B"], x["world"])}


def _examples(data: dict, train_conditions, split: str, conditions) -> list[Example]:
    out = []
    for ep in data["episodes"]:
        if (ep["split"] == "train" and ep["condition"] in train_conditions) or \
                (ep["split"] == split and ep["condition"] in conditions):
            a, b, w = theory_resolve(ep)
            out.append(Example(ep["id"], ep["split"], {"world": w, "A": a, "B": b}, ep["label"]))
    return out


def gate(data: dict, split: str, conditions, train_conditions, min_main: int = 200, max_shortcut_accuracy: float = 0.75):
    return decisive_factor_audit(_examples(data, train_conditions, split, conditions), KEY, PARTS,
                                 min_main=min_main, max_shortcut_accuracy=max_shortcut_accuracy)


def majority(data: dict, train_conditions) -> Callable[[dict], int]:
    label = Counter(ep["label"] for ep in data["episodes"]
                    if ep["split"] == "train" and ep["condition"] in train_conditions).most_common(1)[0][0]
    return lambda ep: label


def path_reasoner(data: dict, train_conditions) -> Callable[[dict], Optional[int]]:
    """传递闭包（位集合，按拓扑序）；训练反馈出现环时报错。"""
    index = {tuple(o): i for i, o in enumerate(map(tuple, data["objects"]))}
    succ = defaultdict(set)
    for ep in data["episodes"]:
        if ep["split"] != "train" or ep["condition"] not in train_conditions:
            continue
        a, b, w = theory_resolve(ep)
        a_bigger = bool(ep["label"]) if w == "physical" else not ep["label"]
        hi, lo = (a, b) if a_bigger else (b, a)
        succ[index[hi]].add(index[lo])
    indeg = Counter(y for ys in succ.values() for y in ys)
    order, queue = [], [x for x in range(len(index)) if indeg[x] == 0]
    while queue:
        x = queue.pop()
        order.append(x)
        for y in succ[x]:
            indeg[y] -= 1
            if indeg[y] == 0:
                queue.append(y)
    if len(order) != len(index):
        raise ValueError("训练反馈互相矛盾：比较关系里有环")
    reach = [0] * len(index)
    for x in reversed(order):
        r = 0
        for y in succ[x]:
            r |= reach[y] | (1 << y)
        reach[x] = r

    def predict(ep):
        a, b, w = theory_resolve(ep)
        ia, ib = index[a], index[b]
        if reach[ia] >> ib & 1:
            a_bigger = True
        elif reach[ib] >> ia & 1:
            a_bigger = False
        else:
            return None
        return int(a_bigger) if w == "physical" else int(not a_bigger)
    return predict


def strata(data: dict, split: str, conditions, train_conditions) -> dict[str, dict]:
    """分层标签：门禁类别、这一对见过与否、路径能否推出、需要哪一层、同包／跨包。"""
    report = gate(data, split, conditions, train_conditions, min_main=0)
    path = path_reasoner(data, train_conditions)
    out = {}
    for ep in data["episodes"]:
        if ep["split"] != split or ep["condition"] not in conditions:
            continue
        h = ep["hidden"]
        out[ep["id"]] = {"gate": report.details["strata"][ep["id"]], "pair": h["pair_kind"],
                         "path": "path_implied" if path(ep) is not None else "path_not_implied",
                         "needs": "needs_ea" if h["needs_ea"] else ("needs_ca" if h["needs_ca"] else "simple"),
                         "package": "same_package" if h["same_package"] else "cross_package"}
    return out
