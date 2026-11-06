"""T5 的题：一条链里有几个关系都对得上的候选，选哪一个由题型决定（2026-11-05）。

研究假设：知识参考系、事件链算子与 SLOT 提供初始晶格，后续结构从此形成。
研究问题：链内选择需要参考包内内容；attention 的必要性仍待对照实验检验。
T4 的选择只看位置和体裁，1 比特规则就够（拆 attention 小检查）。所以这里的题让选择靠内容。三种题型都是工作解释：

- position：选后面的那个。两个候选都有同包的事件陪着，内容不给信息。
- anchor：链里有一个“锚”事件（固定的特殊关系），选和锚同包的候选。另有一个普通事件和错的候选同包，
  所以“有没有同包的事件”没有用，要看的是锚。
- mutual：没有锚。对的候选在链里有另一个同包的事件，错的候选没有。
  另有两个无关的事件彼此同包，所以“链里有没有重复的包”也没有用。

每种题型里，有一部分题只有一个候选（single_fraction）。
答案＝被选中的对象的比特（KA 给的，固定）。系统只收到对整个答案的反馈，没有“该选哪个”的标签。
选错的候选比特相同时，这道题没有信息，这是真实情况，不做处理。

晶格（对有晶格的做法给出）：
- 包的参考向量和成员偏差：同包的对象向量接近，参考成员偏差为 0；
- 关系是否对得上查询（CPU 判断），是不是锚。
新包：从不出现在训练题里，但有自己的参考向量。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import torch

TASKS = ("position", "anchor", "mutual")


@dataclass(frozen=True)
class T5Spec:
    n_train_packages: int = 48
    n_new_packages: int = 16
    n_members: int = 4
    n_relations: int = 8        # 最后一个是锚
    chain_len: int = 8
    k: int = 16
    member_offset: float = 0.2
    single_fraction: float = 0.2
    n_train: int = 16384
    n_dev: int = 2048
    n_test: int = 4096
    seed: int = 20261106

    @property
    def n_objects(self) -> int:
        return (self.n_train_packages + self.n_new_packages) * self.n_members

    @property
    def anchor_rel(self) -> int:
        return self.n_relations - 1


def build_lattice(spec: T5Spec) -> dict:
    g = torch.Generator().manual_seed(spec.seed)
    P = spec.n_train_packages + spec.n_new_packages
    ref = torch.nn.functional.normalize(torch.randn(P, spec.k, generator=g), dim=-1)
    off = torch.randn(P, spec.n_members, spec.k, generator=g) * (spec.member_offset / math.sqrt(spec.k))
    off[:, 0] = 0.0
    return {"vec": (ref[:, None, :] + off).reshape(-1, spec.k),
            "bit": torch.randint(0, 2, (spec.n_objects,), generator=g).float()}


def make_question(task: str, pkgs: list, spec: T5Spec, rng: random.Random, single: bool) -> dict:
    good, bad, dis, u1, u2, u3 = rng.sample(pkgs, 6)
    if task == "position":
        plan = [("cand", "x"), ("cand", "y"), ("ord", "x"), ("ord", "y"), ("ord", dis), ("ord", dis), ("ord", u1), ("ord", u2)]
        names = {"x": good, "y": bad}
    elif task == "anchor":
        plan = [("good", good), ("cand", bad), ("anchor", good), ("ord", bad), ("ord", dis), ("ord", dis), ("ord", u1), ("ord", u2)]
        names = {}
    elif task == "mutual":
        plan = [("good", good), ("cand", bad), ("ord", good), ("ord", dis), ("ord", dis), ("ord", u1), ("ord", u2), ("ord", u3)]
        names = {}
    else:
        raise ValueError(task)
    if len(plan) != spec.chain_len:
        raise ValueError("这三种题型按 8 个事件设计")
    if single:                                    # 只有一个候选：另一个候选变成普通事件；位置题留下的那个就是目标
        i = next(i for i, (kind, _) in enumerate(plan) if kind == "cand" and (task != "position" or plan[i][1] == "y"))
        plan[i] = ("ord", plan[i][1])
    rng.shuffle(plan)
    rq = rng.randrange(spec.n_relations - 1)
    ordinary = [r for r in range(spec.n_relations - 1) if r != rq]
    used: dict = {}
    rel, obj, pkg = [], [], []
    for kind, p in plan:
        p = names.get(p, p)
        members = [m for m in range(spec.n_members) if m not in used.setdefault(p, set())]
        m = rng.choice(members)
        used[p].add(m)
        rel.append(spec.anchor_rel if kind == "anchor" else rq if kind in ("cand", "good") else rng.choice(ordinary))
        obj.append(p * spec.n_members + m)
        pkg.append(p)
    cands = [i for i, r in enumerate(rel) if r == rq]
    if task == "position":
        target = cands[-1]
    else:
        target = next(i for i, (kind, _) in enumerate(plan) if kind == "good")
    return {"rel": rel, "obj": obj, "pkg": pkg, "query": rq, "target": target, "n_cand": len(cands)}


def rule_ref(task: str, q: dict, spec: T5Spec) -> int:
    """人写的参照规则：只用看得见的东西。不是系统学来的。"""
    cands = [i for i, r in enumerate(q["rel"]) if r == q["query"]]
    if len(cands) == 1 or task == "position":
        return cands[-1]
    if task == "anchor":
        a = q["rel"].index(spec.anchor_rel)
        return next(i for i in cands if q["pkg"][i] == q["pkg"][a])
    others = [i for i in range(len(q["rel"])) if i not in cands]
    return next(i for i in cands if any(q["pkg"][j] == q["pkg"][i] for j in others))


def _pack(qs: list) -> dict:
    return {"rel": torch.tensor([q["rel"] for q in qs]), "obj": torch.tensor([q["obj"] for q in qs]),
            "pkg": torch.tensor([q["pkg"] for q in qs]), "query": torch.tensor([q["query"] for q in qs]),
            "target": torch.tensor([q["target"] for q in qs]), "n_cand": torch.tensor([q["n_cand"] for q in qs])}


def signature(q: dict) -> tuple:
    return (q["query"], tuple(q["rel"]), tuple(q["obj"]))


def build_task(task: str, spec: T5Spec) -> dict:
    """所有种子共用同一份题。test_iid 和 train 同一批包，题不同；test_new 全是从没训练过的包。"""
    rng = random.Random(f"{spec.seed}-{task}")
    train_pk = list(range(spec.n_train_packages))
    new_pk = list(range(spec.n_train_packages, spec.n_train_packages + spec.n_new_packages))
    seen: set = set()

    def split(n: int, pkgs: list) -> list:
        out = []
        while len(out) < n:
            q = make_question(task, pkgs, spec, rng, rng.random() < spec.single_fraction)
            s = signature(q)
            if s not in seen:
                seen.add(s)
                out.append(q)
        return out

    raw = {"train": split(spec.n_train, train_pk), "dev": split(spec.n_dev, train_pk),
           "test_iid": split(spec.n_test, train_pk), "test_new": split(spec.n_test, new_pk)}
    return {"raw": raw, **{k: _pack(v) for k, v in raw.items()}}


def baselines(task: str, data: dict, spec: T5Spec) -> dict:
    """简单基线：两个候选的题上选对的比例。"""
    two = {k: [q for q in data["raw"][k] if q["n_cand"] == 2] for k in ("train", "test_iid", "test_new")}
    hit: dict = {}
    for q in two["train"]:
        for i, r in enumerate(q["rel"]):
            if r == q["query"]:
                n, k = hit.get(q["obj"][i], (0, 0))
                hit[q["obj"][i]] = (n + 1, k + int(i == q["target"]))

    def prior(o):
        n, k = hit.get(o, (0, 0))
        return (k + 1) / (n + 2)

    out = {}
    for split in ("test_iid", "test_new"):
        qs = two[split]
        res = {"pick_last": 0, "pick_first": 0, "object_prior": 0, "rule_ref": 0}
        for q in qs:
            c = [i for i, r in enumerate(q["rel"]) if r == q["query"]]
            res["pick_last"] += c[-1] == q["target"]
            res["pick_first"] += c[0] == q["target"]
            res["object_prior"] += max(c, key=lambda i: (prior(q["obj"][i]), i)) == q["target"]
            res["rule_ref"] += rule_ref(task, q, spec) == q["target"]
        out[split] = {k: v / len(qs) for k, v in res.items()}
    return out
