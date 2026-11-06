"""简单基线：模型不比这些好，就不能说“学会了”。

每个排序器返回 [(label, score), ...]，分数越高越靠前。命中按“悲观并列”计算：
与正确答案同分的其他候选都排在它前面，避免并列时偷偷算作命中。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Mapping, Sequence

from .gates import char_ngrams, fit_part_rules, jaccard  # noqa: F401  fit_part_rules：单部分规则基线（定义在 gates，避免循环引用）

Ranking = list[tuple[Any, float]]
Ranker = Callable[[str], Ranking]


def lexical_ranker(lexicon: Mapping[str, Sequence[Any]]) -> Ranker:
    """词面匹配：文本中出现的不同词条，各为其所属标签加 1 分。"""
    def rank(text: str) -> Ranking:
        scores: Counter = Counter()
        for term, labels in lexicon.items():
            if term and term in text:
                for label in set(labels):
                    scores[label] += 1
        return _sorted(scores)
    return rank


def ngram_nn_ranker(train: Sequence[tuple[str, Any]], n: int = 2) -> Ranker:
    """字符 n-gram 最近邻：每个标签取其训练句与查询的最大 Jaccard 作为分数。"""
    grams = [(char_ngrams(text, n), label) for text, label in train]

    def rank(text: str) -> Ranking:
        q = char_ngrams(text, n)
        best: dict[Any, float] = defaultdict(float)
        for g, label in grams:
            best[label] = max(best[label], jaccard(q, g))
        return _sorted({k: v for k, v in best.items() if v > 0})
    return rank


def majority_ranker(train_labels: Sequence[Any]) -> Ranker:
    """多数类：不看输入，按训练标签频次排序。"""
    ranking = _sorted(Counter(train_labels))
    return lambda text: list(ranking)


def evaluate_ranker(items: Sequence[tuple[str, Any]], ranker: Ranker, ks: Sequence[int] = (1, 3)) -> dict:
    hits = {k: 0 for k in ks}
    for text, expected in items:
        rank = pessimistic_rank(ranker(text), expected)
        for k in ks:
            if rank is not None and rank <= k:
                hits[k] += 1
    return {"n": len(items), **{f"top{k}": hits[k] for k in ks}}


def pessimistic_rank(ranking: Ranking, expected: Any) -> int | None:
    scores = dict(ranking)
    if expected not in scores:
        return None
    s = scores[expected]
    ahead = sum(1 for label, v in ranking if label != expected and v >= s)
    return ahead + 1


def _sorted(scores: Mapping[Any, float]) -> Ranking:
    return sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0])))
