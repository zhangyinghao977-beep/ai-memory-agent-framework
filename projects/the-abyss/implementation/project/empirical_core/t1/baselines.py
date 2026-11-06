"""T1 的门禁、分层与简单基线（设计稿 T1_DESIGN.md 第二、三节；测试方案 v0.1 第二、三节）。

基线（都只用 TRAIN 的反馈，不看隐藏数值）：
- majority：恒选 TRAIN 里最常见的答案。
- 单部分规则：只看 A＋世界，或只看 B＋世界（evaluation.gates.fit_part_rules；没见过的值或并列算答错）。
- 路径推理（“逻辑就是可达路径”）：把 TRAIN 的每道题换成物理世界里的“x 大于 y”，按传递关系推；
  推不出来就算答错（悲观）。它需要知道“故事世界里小的赢”这条前提，这条前提本来就写在题目的世界里。
理论最优（知道隐藏数值）：100%。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable, Optional

from ..evaluation.gates import Example, decisive_factor_audit, fit_part_rules
from .task import resolve

KEY = lambda x: (tuple(sorted((x["A"], x["B"]))), x["world"])   # 关键值：（无序对象对, 世界）
PARTS = {"A+world": lambda x: (x["A"], x["world"]), "B+world": lambda x: (x["B"], x["world"])}


def examples(data: dict, splits=("train", "dev", "test")) -> list[Example]:
    """审计用的样例：A、B 由可见信息解析（resolve），不读隐藏数值。"""
    out = []
    for ep in data["episodes"]:
        if ep["split"] in splits:
            a, b = resolve(ep)
            out.append(Example(ep["id"], ep["split"], {"world": ep["world"], "A": a, "B": b}, ep["label"]))
    return out


def gate(data: dict, split: str = "test", min_main: int = 200, max_shortcut_accuracy: float = 0.75):
    """对某个留出集做“决定因素重合＋单部分捷径”门禁。"""
    return decisive_factor_audit(examples(data, ("train", split)), KEY, PARTS, min_main=min_main,
                                 max_shortcut_accuracy=max_shortcut_accuracy)


def majority(data: dict) -> Callable[[dict], int]:
    label = Counter(ep["label"] for ep in data["episodes"] if ep["split"] == "train").most_common(1)[0][0]
    return lambda ep: label


def part_rules(data: dict) -> dict[str, Callable[[dict], Optional[int]]]:
    rules = fit_part_rules(examples(data, ("train",)), PARTS)

    def wrap(rule):
        def predict(ep):
            a, b = resolve(ep)
            return rule({"world": ep["world"], "A": a, "B": b})
        return predict
    return {name: wrap(rule) for name, rule in rules.items()}


def path_reasoner(data: dict) -> Callable[[dict], Optional[int]]:
    """只用 TRAIN 比较过的关系做传递推理；推不出来返回 None（算答错）。

    先把“x 大于 y”的关系图按拓扑序处理，用位集合一次算出每个对象能推到的所有更小对象（传递闭包），
    对象有几千个时也算得动。关系图出现环（训练反馈互相矛盾）时直接报错，不悄悄挑一个。
    """
    index = {tuple(o): i for i, o in enumerate(map(tuple, data["objects"]))}
    succ = defaultdict(set)                          # x -> {比 x 小的对象}
    for ep in data["episodes"]:
        if ep["split"] != "train":
            continue
        a, b = resolve(ep)
        a_bigger = bool(ep["label"]) if ep["world"] == "physical" else not ep["label"]
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
    for x in reversed(order):                        # 先处理更小的一端
        r = 0
        for y in succ[x]:
            r |= reach[y] | (1 << y)
        reach[x] = r

    def predict(ep):
        a, b = (index[o] for o in resolve(ep))
        if reach[a] >> b & 1:
            a_bigger = True
        elif reach[b] >> a & 1:
            a_bigger = False
        else:
            return None
        return int(a_bigger) if ep["world"] == "physical" else int(not a_bigger)
    return predict


def strata(data: dict, split: str) -> dict[str, dict]:
    """留出题的分层标签：门禁类别（seen／new × agree／conflict）、同包／跨包、这一对见过与否、路径能否推出。"""
    report = gate(data, split, min_main=0)
    path = path_reasoner(data)
    out = {}
    for ep in data["episodes"]:
        if ep["split"] != split:
            continue
        out[ep["id"]] = {
            "gate": report.details["strata"][ep["id"]],
            "package": "same_package" if ep["hidden"]["same_package"] else "cross_package",
            "pair": ep["hidden"]["pair_kind"],
            "path": "path_implied" if path(ep) is not None else "path_not_implied",
        }
    return out


def score(data: dict, split: str, predict: Callable[[dict], Optional[int]]) -> dict[str, bool]:
    """{题号: 是否答对}；返回 None 的预测算答错。"""
    return {ep["id"]: predict(ep) == ep["label"] for ep in data["episodes"] if ep["split"] == split}
