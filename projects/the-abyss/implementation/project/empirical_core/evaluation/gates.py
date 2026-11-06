"""训练前门禁：输入可辨识性与训练／评测隔离。

1. 输入碰撞：只看模型真正收到的输入算签名；同签名却有不同答案的训练样本无法靠输入区分，
   同签名同时出现在训练与评测中则是泄漏。（依据 v16／v19 R6 的历史实验审查。）
2. 文本重合：不只查完全相同的字符串，也报告字符 n-gram 重合、最近邻训练句与共享片段，
   用来发现同一作者编写的近义改写。（依据 v0.9 的历史复核。）
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, Iterable, Sequence


@dataclass(frozen=True)
class Example:
    example_id: str
    split: str
    inputs: Any   # 模型实际收到的全部输入，不含答案
    label: Any


@dataclass
class GateReport:
    name: str
    passed: bool
    details: dict = field(default_factory=dict)


def canonical_signature(inputs: Any) -> str:
    return hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def input_collision_audit(
    examples: Iterable[Example],
    signature_fn: Callable[[Any], Hashable] = canonical_signature,
    train_split: str = "train",
    allow_label_distribution: bool = False,
) -> GateReport:
    """allow_label_distribution=True 用于本来就要学条件分布的任务（同一输入可有多种结果）；
    此时训练内冲突只报告、不判失败，跨划分重合仍判失败。"""
    examples = list(examples)
    # 先只用输入算签名，再读答案。
    signatures = [signature_fn(ex.inputs) for ex in examples]
    groups: dict[Hashable, list[Example]] = defaultdict(list)
    for sig, ex in zip(signatures, examples):
        groups[sig].append(ex)

    train_conflicts, cross_split = [], []
    for sig, group in groups.items():
        train = [ex for ex in group if ex.split == train_split]
        labels = {json.dumps(ex.label, ensure_ascii=False, sort_keys=True) for ex in train}
        if len(labels) > 1:
            train_conflicts.append({
                "signature": str(sig),
                "example_ids": [ex.example_id for ex in train],
                "labels": sorted(labels),
            })
        others = [ex for ex in group if ex.split != train_split]
        if train and others:
            cross_split.append({
                "signature": str(sig),
                "train_ids": [ex.example_id for ex in train],
                "other_ids": [f"{ex.split}:{ex.example_id}" for ex in others],
            })

    passed = not cross_split and (allow_label_distribution or not train_conflicts)
    return GateReport("input_collision", passed, {
        "examples": len(examples),
        "distinct_signatures": len(groups),
        "train_label_conflicts": train_conflicts,
        "train_eval_overlap": cross_split,
        "allow_label_distribution": allow_label_distribution,
    })


def char_ngrams(text: str, n: int) -> set[str]:
    s = "".join(ch for ch in text if not ch.isspace())
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set, b: set) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def shared_substrings(a: str, b: str, min_len: int = 2) -> list[str]:
    """a 与 b 共有的、长度不小于 min_len 的极大公共片段。"""
    found = set()
    for i in range(len(a)):
        for j in range(i + min_len, len(a) + 1):
            if a[i:j] in b:
                found.add(a[i:j])
            else:
                break
    return sorted((s for s in found if not any(s != t and s in t for t in found)), key=lambda s: (-len(s), s))


def text_overlap_audit(
    train: Sequence[tuple[str, str, Any]],
    evals: Sequence[tuple[str, str, Any]],
    review_jaccard2: float = 0.10,
    review_shared_len: int = 4,
    max_jaccard5: float = 0.20,
) -> GateReport:
    """train / evals: (id, text, label)。完全相同或 5-gram 重合过高判失败；
    二元组重合或共享片段较长的题目列入 needs_review，需要人工确认是否为近义改写。"""
    train_grams = [(tid, text, label, char_ngrams(text, 2), char_ngrams(text, 5)) for tid, text, label in train]
    train_texts = {text.strip() for _, text, _ in train}
    items, needs_review = [], []
    exact = 0
    worst5 = 0.0
    nn_agree = 0
    for eid, text, label in evals:
        g2, g5 = char_ngrams(text, 2), char_ngrams(text, 5)
        is_exact = text.strip() in train_texts
        exact += is_exact
        best = max(train_grams, key=lambda t: (jaccard(g2, t[3]), t[0]))
        j5 = max((jaccard(g5, t[4]) for t in train_grams), default=0.0)
        worst5 = max(worst5, j5)
        same_label = [t for t in train_grams if t[2] == label]
        best_same = max(same_label, key=lambda t: (jaccard(g2, t[3]), t[0])) if same_label else None
        shared = shared_substrings(text, best_same[1]) if best_same else []
        agree = best[2] == label
        nn_agree += agree
        item = {
            "eval_id": eid,
            "exact_in_train": is_exact,
            "max_jaccard5": round(j5, 4),
            "nearest_train_id": best[0],
            "nearest_jaccard2": round(jaccard(g2, best[3]), 4),
            "nearest_label_matches": agree,
            "closest_same_label_id": best_same[0] if best_same else None,
            "shared_with_same_label": shared,
        }
        items.append(item)
        if item["nearest_jaccard2"] >= review_jaccard2 or (shared and len(shared[0]) >= review_shared_len):
            needs_review.append(eid)
    passed = exact == 0 and worst5 < max_jaccard5
    return GateReport("text_overlap", passed, {
        "exact_matches": exact,
        "max_jaccard5": round(worst5, 4),
        "bigram_nearest_neighbor_label_agreement": nn_agree,
        "evals": len(evals),
        "needs_review": needs_review,
        "items": items,
    })


# ---------- 决定因素重合与单部分捷径（测试方案 v0.1 第三节；v19 DEV 历史复核） ----------

def fit_part_rules(
    train: Iterable[Example], part_fns: dict[str, Callable[[Any], Hashable]],
) -> dict[str, Callable[[Any], Any]]:
    """每个部分各拟合一条“只看这一部分”的规则：这一部分取某个值时，训练集里最常见的答案。
    训练里没见过的值返回 None（悲观：算答错）；并列时也返回 None。"""
    train = list(train)
    rules = {}
    for name, fn in part_fns.items():
        table: dict[Hashable, Counter] = defaultdict(Counter)
        for ex in train:
            table[fn(ex.inputs)][json.dumps(ex.label, sort_keys=True)] += 1
        best = {}
        for value, counts in table.items():
            top = counts.most_common(2)
            best[value] = None if len(top) > 1 and top[0][1] == top[1][1] else json.loads(top[0][0])
        rules[name] = (lambda b, f: (lambda inputs: b.get(f(inputs))))(best, fn)
    return rules


def stratify(
    examples: Iterable[Example], key_fn: Callable[[Any], Hashable],
    part_fns: dict[str, Callable[[Any], Hashable]], train_split: str = "train",
) -> dict[str, str]:
    """把每道评测题分到四类（外加“无法判断”）：
    决定答案的关键值在训练里 seen／new × 各部分单独给出的答案 agree／conflict（有部分没见过就是 undetermined）。"""
    examples = list(examples)
    train = [ex for ex in examples if ex.split == train_split]
    seen_keys = {key_fn(ex.inputs) for ex in train}
    rules = fit_part_rules(train, part_fns)
    strata = {}
    for ex in examples:
        if ex.split == train_split:
            continue
        votes = [rule(ex.inputs) for rule in rules.values()]
        if any(v is None for v in votes):
            agreement = "undetermined"
        else:
            agreement = "agree" if len({json.dumps(v, sort_keys=True) for v in votes}) == 1 else "conflict"
        strata[ex.example_id] = f"{'seen' if key_fn(ex.inputs) in seen_keys else 'new'}_{agreement}"
    return strata


def decisive_factor_audit(
    examples: Iterable[Example],
    key_fn: Callable[[Any], Hashable],
    part_fns: dict[str, Callable[[Any], Hashable]],
    train_split: str = "train",
    main_stratum: str = "new_conflict",
    min_main: int = 1,
    max_shortcut_accuracy: float = 0.75,
) -> GateReport:
    """训练前门禁：只比完整输入是否相同还不够，要看决定答案的关键值有没有在训练里出现过，
    以及“只看某一部分”的规则能不能在主要指标那一类上拿高分。

    失败条件：主要指标那一类（默认“新组合 × 各部分冲突”）题数少于 min_main，
    或任一单部分规则在这一类上的正确率高于 max_shortcut_accuracy。"""
    examples = list(examples)
    train = [ex for ex in examples if ex.split == train_split]
    rules = fit_part_rules(train, part_fns)
    strata = stratify(examples, key_fn, part_fns, train_split)
    by_id = {ex.example_id: ex for ex in examples}
    counts = Counter(strata.values())
    shortcut: dict[str, dict] = {}
    for name, rule in rules.items():
        per = {}
        for stratum in sorted(set(strata.values()) | {main_stratum}):
            ids = [i for i, s in strata.items() if s == stratum]
            hits = sum(rule(by_id[i].inputs) == by_id[i].label for i in ids)
            per[stratum] = {"n": len(ids), "correct": hits}
        all_ids = list(strata)
        per["all"] = {"n": len(all_ids), "correct": sum(rule(by_id[i].inputs) == by_id[i].label for i in all_ids)}
        shortcut[name] = per
    main_n = counts.get(main_stratum, 0)
    worst = max((v[main_stratum]["correct"] / v[main_stratum]["n"] for v in shortcut.values()
                 if v[main_stratum]["n"]), default=0.0)
    passed = main_n >= min_main and worst <= max_shortcut_accuracy
    return GateReport("decisive_factor", passed, {
        "strata_counts": dict(sorted(counts.items())),
        "main_stratum": main_stratum,
        "main_stratum_count": main_n,
        "min_main": min_main,
        "part_rule_results": shortcut,
        "worst_part_rule_accuracy_on_main": round(worst, 4),
        "max_shortcut_accuracy": max_shortcut_accuracy,
        "strata": strata,
    })
