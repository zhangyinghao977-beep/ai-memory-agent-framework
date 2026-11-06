"""T8：从事件链里长出参考向量（2026-11-06）。

T1 的注册代码写着“T1 按设计成包（不是从经验中求同形成）”。T1–T7 的包和参考系都是人给的。
T6 说明参考向量最不能少，而且靠答案反馈长不出来。这里试另一条路：只看事件链本身。

工作解释（不是构造里“求同”的定义）：
经常出现在同一条事件链里的对象，算作相似。做法是共现计数 → PPMI → SVD。
只读对象编号。不读包的编号，不读答案，不用梯度。
没在经验里出现过的对象，向量是 0。
"""
from __future__ import annotations

import torch


def cooccurrence(obj: torch.Tensor, n_objects: int) -> torch.Tensor:
    """obj：[N, L] 的对象编号。返回 [n, n] 的共现次数，对角线为 0。"""
    onehot = torch.nn.functional.one_hot(obj, n_objects).to(torch.float64).sum(1).clamp(max=1.0)
    c = onehot.T @ onehot
    return c - torch.diag(torch.diag(c))


def ppmi(c: torch.Tensor) -> torch.Tensor:
    total = c.sum()
    if total == 0:
        return torch.zeros_like(c)
    row = c.sum(1, keepdim=True)
    expected = row * row.T / total
    pmi = torch.log(torch.where((c > 0) & (expected > 0), c / expected.clamp(min=1e-12), torch.ones_like(c)))
    return pmi.clamp(min=0.0)


def grow_vectors(obj: torch.Tensor, n_objects: int, k: int) -> torch.Tensor:
    """返回 [n, k] 的单位向量；没出现过的对象是 0。"""
    m = ppmi(cooccurrence(obj, n_objects))
    u, s, _ = torch.linalg.svd(m)
    v = u[:, :k] * s[:k].sqrt()
    return torch.nn.functional.normalize(v, dim=-1).to(torch.float32)


def seen_objects(obj: torch.Tensor, n_objects: int) -> torch.Tensor:
    seen = torch.zeros(n_objects, dtype=torch.bool)
    seen[obj.unique()] = True
    return seen


def grow_new(vec: torch.Tensor, obj_new: torch.Tensor, seen: torch.Tensor, k: int) -> torch.Tensor:
    """新的经历只长没见过的对象，旧向量一点不动。

    开发检查发现：新旧事件链混在一起算时，“新对象只和新对象同链”这件事占满了维度，
    所有新对象被压成同一个方向，旧对象也会变差。所以只在没见过的对象之间算共现。
    这样新旧对象的向量不在同一组坐标里：同一条链里既有新对象又有旧对象时，余弦没有意义。
    """
    new_ids = [i for i in obj_new.unique().tolist() if not seen[i]]
    out = vec.clone()
    if len(new_ids) < 2:
        return out
    local = torch.full((len(seen),), len(new_ids), dtype=torch.long)
    local[torch.tensor(new_ids)] = torch.arange(len(new_ids))
    c = cooccurrence(local[obj_new], len(new_ids) + 1)[:-1, :-1]
    u, s, _ = torch.linalg.svd(ppmi(c))
    v = u[:, :k] * s[:k].sqrt()
    out[torch.tensor(new_ids)] = torch.nn.functional.pad(torch.nn.functional.normalize(v, dim=-1), (0, vec.shape[1] - v.shape[1])).to(vec.dtype)
    return out


def dilute(obj: torch.Tensor, fraction: float, seed: int) -> torch.Tensor:
    """把一部分事件链里的对象打乱到别的链：对象出现的次数不变，这些链里的同包信息没有了。"""
    g = torch.Generator().manual_seed(seed)
    out = obj.clone()
    rows = torch.randperm(len(obj), generator=g)[: int(len(obj) * fraction)]
    flat = out[rows].flatten()
    out[rows] = flat[torch.randperm(len(flat), generator=g)].view(out[rows].shape)
    return out
