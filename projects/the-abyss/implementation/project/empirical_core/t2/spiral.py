"""T2 被测模型 A2 的螺旋式分层训练、分段前向、局部修复和逐级加深（2026-11-02）。

螺旋训练：每一轮依次做
1. KA：每个包一个单元，各自训练，然后发布产品（共同空间表示表 c）。
   - 所有包读同一份“本轮开始时”的上层产品，所以和包的先后次序无关。
   - 每个单元有三个相位，各只写自己那几项：
     - ka_o：成员表示 o_p；
     - ka_head：包内比较头 u_p、π_p；
     - ka_conv：尺子转换 W_p、b_p。
   - 材料只用 CPU 能精确对应到本包成员的观察（features.exact）。上层的选择错误不当作下层的标签。
   - 跨包观察借用上层上一轮的产品做投影：别的包的 c 和 CA 的比较头，都只读。
     第一轮 CA 还没有产品，所以只用包内观察，也不学尺子转换。
2. EA：读本轮的 KA 产品和上一轮的 CA（只读），在全部观察上训练。
3. CA：EA 在显卡上分块推理出每条链的产品（选中的表示），放回本地（CPU 内存），再分块读回显卡训练 CA。
模型和优化器状态跨轮、跨修复保留；每次写都存成新版本，旧版本保留。

修复（名词解释 v0.55 第 2 节）：条件变更后，从基线的单元快照出发，只允许写某几层（写范围）；
材料是新条件的观察，加上按比例固定抽出的旧观察。
逐级加深：按事先定好的梯子一级一级加大写范围（CA → CA＋EA → ＋KA 局部 → ＋KA 全部），
每级做完用 DEV 检查“够不够用”，够用就停（v0.56：够用就可以停，不追求全局最优）。

资源（v0.55 第 1 节）：
- 不建一张大网络。每个单元是超小型网络，单独载入、训练、存盘、释放。
- KA 单元留在 CPU 上算；EA 和 CA 可以放到显卡上。
- 每次激活前按字节预留，超过预算就抛出 ResourcePending，不裁剪材料。
"""
from __future__ import annotations

import copy
import hashlib
import math
import time
from typing import Callable, Optional

import torch
import torch.nn as nn

from ..t1.spiral import arrival_rounds, nbytes
from ..timing import SegmentTimer
from .features import T2Batch, take, to_device
from .units import KA_PARAMS, A2Config, CAUnit, EAUnit, UnitStore, count_params, ka_init, ka_own, ka_product


class ResourcePending(RuntimeError):
    """最小完整单元放不进预算：记录所需字节后停下，不裁剪材料、不重置预算。"""


class DirtyVersion(RuntimeError):
    """产品不是由各单元当前版本算出来的：拒绝混用新旧版本。"""


def stable_seed(*parts) -> int:
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:4], "little")


def ka_name(p: int) -> str:
    return f"ka{p:04d}"


class ChainSpiral:
    def __init__(self, cfg: A2Config, store: UnitStore, train: T2Batch, *, seed: int, epochs_per_phase: int,
                 batch_size: int, lr: dict, budgets: dict, clip: float = 1.0, device: str = "cpu",
                 guard: Optional[Callable[[], None]] = None, timer: Optional[SegmentTimer] = None,
                 log: Optional[Callable[[dict], None]] = None):
        self.cfg, self.store, self.train, self.seed = cfg, store, train, seed
        self.bs, self.lr, self.budgets, self.clip = batch_size, lr, budgets, clip
        # 每个相位的 epoch 数：一个整数（三层相同），或 {"ka": .., "ea": .., "ca": ..}（KA 单元很小，可以多学几遍）
        self.epochs = epochs_per_phase if isinstance(epochs_per_phase, dict) else \
            {layer: epochs_per_phase for layer in ("ka", "ea", "ca")}
        self.device = torch.device(device)
        self.train_dev = to_device(train, self.device)
        self.guard = guard or (lambda: None)
        self.timer = timer or SegmentTimer()
        self.log = log or (lambda rec: None)
        self._ctable: Optional[torch.Tensor] = None
        self._ctable_from: Optional[tuple] = None
        self.bills: list[dict] = []
        self.losses: dict[str, list] = {"KA": [], "EA": [], "CA": []}

    # ---------- 单元与产品 ----------
    def ka_versions(self) -> tuple:
        return tuple(self.store.version(ka_name(p)) for p in range(self.cfg.n_packages))

    def _ka_state(self, p: int) -> dict:
        st = self.store.read(ka_name(p))
        return st if st is not None else {"params": ka_init(self.cfg, p, self.seed), "opt": {}}

    def ctable(self) -> torch.Tensor:
        """KA 产品：[P, M, k] 共同空间表示。只要有任何 KA 单元换了版本，就按当前版本重建。"""
        now = self.ka_versions()
        if self._ctable_from != now:
            self._ctable = torch.stack([ka_product(self._ka_state(p)["params"]) for p in range(self.cfg.n_packages)])
            self._ctable_from = now
        return self._ctable

    def _load_module(self, name: str):
        cls = EAUnit if name == "ea" else CAUnit
        torch.manual_seed(stable_seed(self.seed, name, "init"))
        module = cls(self.cfg)
        st = self.store.read(name)
        if st is not None:
            module.load_state_dict(st["model"])
        return module, (st["opt"] if st is not None else None)

    def _frozen(self, name: str):
        module, _ = self._load_module(name)
        module.eval()
        return module.requires_grad_(False)

    # ---------- 分段前向 ----------
    def ea_reps(self, ea: EAUnit, b: T2Batch, ct: torch.Tensor, slot: str) -> tuple:
        """EA 在每条链上按查询关系选事件：返回每条链的表示 [B, C, k]、“没有”的概率 [B, C]、选择概率 [B, C, L+1]。"""
        B, C, L = b.ev_pkg.shape
        rel = (b.rel_a if slot == "a" else b.rel_b).reshape(B * C, L)
        sel = ea(rel, b.ev_valid.reshape(B * C, L)).view(B, C, L + 1)
        reps = ct[b.ev_pkg, b.ev_mem]                                                   # [B, C, L, k]
        return torch.einsum("bcl,bclk->bck", sel[..., :L], reps), sel[..., L], sel

    @staticmethod
    def combine(ca: CAUnit, sel: torch.Tensor, b: T2Batch, rep_a, rep_b) -> tuple:
        C = rep_a.shape[1]
        c_a = torch.einsum("bc,bck->bk", sel[:, 0, :C], rep_a)
        c_b = torch.einsum("bc,bck->bk", sel[:, 1, :C], rep_b)
        premise = (sel[:, 2, :C] * b.set_story).sum(-1)
        return ca.compare_logit(c_a, c_b, premise), premise

    @torch.no_grad()
    def predict(self, batch: T2Batch, diag: Optional[dict] = None, chunk: int = 1024) -> dict:
        """分段推理：CA 先选链 → EA 在链内选事件 → 查 KA 产品 → CA 在链间比较。结果放回 CPU。
        diag（隐藏真值）给定时，另外记下 CA、EA 的选择是否对，只用于报告。"""
        ea, ca = self._frozen("ea").to(self.device), self._frozen("ca").to(self.device)
        ct = self.ctable().to(self.device)
        out = {"logit": [], "none": [], "ca_arg": [], "ea_arg": []}
        n = len(batch.ids)
        for s in range(0, n, chunk):
            rows = torch.arange(s, min(s + chunk, n))
            b = to_device(take(batch, rows), self.device)
            sel = ca.select(b)
            rep_a, none_a, sel_a = self.ea_reps(ea, b, ct, "a")
            rep_b, none_b, sel_b = self.ea_reps(ea, b, ct, "b")
            logit, _ = self.combine(ca, sel, b, rep_a, rep_b)
            C = rep_a.shape[1]
            none = torch.stack([sel[:, 0, C] + (sel[:, 0, :C] * none_a).sum(-1),
                                sel[:, 1, C] + (sel[:, 1, :C] * none_b).sum(-1)], dim=-1)
            out["logit"].append(logit.float().cpu())
            out["none"].append(none.float().cpu())
            out["ca_arg"].append(sel.argmax(-1).cpu())
            if diag is not None:
                r = torch.arange(len(rows), device=self.device)
                ac, bc = diag["a_chain"][rows].to(self.device), diag["b_chain"][rows].to(self.device)
                out["ea_arg"].append(torch.stack([sel_a[r, ac].argmax(-1), sel_b[r, bc].argmax(-1)], -1).cpu())
            self.guard()
        res = {k: torch.cat(v) for k, v in out.items() if v}
        return res

    # ---------- KA ----------
    def _ka_phase(self, tag: str, r: int, p: int, idx: torch.Tensor, upper: Optional[dict]) -> None:
        t0, slept0 = time.perf_counter(), getattr(self.guard, "slept", 0.0)
        tr = self.train
        rows = idx[tr.exact[idx]]
        a_pkg, b_pkg = tr.ex_a[rows, 0], tr.ex_b[rows, 0]
        touch = (a_pkg == p) | (b_pkg == p)
        direct = touch & (a_pkg == p) & (b_pkg == p)
        cross = touch & ~direct if upper is not None else torch.zeros_like(touch)
        rows_d, rows_c = rows[direct], rows[cross]
        if len(rows_d) + len(rows_c) == 0:
            return                                                          # 没有材料：不激活、不写新版本
        st = self._ka_state(p)
        prm = {n: nn.Parameter(st["params"][n].clone()) for n in KA_PARAMS}
        mats = torch.cat([rows_d, rows_c])
        is_direct = torch.cat([torch.ones(len(rows_d), dtype=torch.bool), torch.zeros(len(rows_c), dtype=torch.bool)])
        ctx = [upper["c"], *upper["compare"].parameters()] if upper is not None else []
        act = self.bs * (3 * self.cfg.k + 1 + 2 * self.cfg.d_compare) * 4 * 3
        reserved = 4 * nbytes(*prm.values()) + len(mats) * 8 * 6 + nbytes(*ctx) + act
        if reserved > self.budgets["ka"]:
            raise ResourcePending(f"KA 单元 {p}（{tag} 第 {r} 轮）需要 {reserved} 字节，超过预算 {self.budgets['ka']}")

        def loss_on(i, use_direct=True, use_cross=True):
            m = mats[i]
            d = is_direct[i]
            a_mem, b_mem = tr.ex_a[m, 1], tr.ex_b[m, 1]
            story, label = tr.ex_story[m], tr.labels[m]
            own = ka_own(prm["o"])
            parts = []
            if use_direct and d.any():
                diff = (own[a_mem[d]] - own[b_mem[d]]) @ prm["u"]
                parts.append(nn.functional.binary_cross_entropy_with_logits(
                    prm["pi"][story[d].long()] * diff, label[d], reduction="sum"))
            if use_cross and (~d).any():
                j = ~d
                mine = own @ prm["W"] + prm["b"]
                ap, bp = tr.ex_a[m[j], 0], tr.ex_b[m[j], 0]
                c_a = torch.where((ap == p).unsqueeze(-1), mine[a_mem[j]], upper["c"][ap, a_mem[j]])
                c_b = torch.where((bp == p).unsqueeze(-1), mine[b_mem[j]], upper["c"][bp, b_mem[j]])
                logit = upper["compare"](torch.cat([c_a, c_b, c_a - c_b, story[j].unsqueeze(-1)], -1)).squeeze(-1)
                parts.append(nn.functional.binary_cross_entropy_with_logits(logit, label[j], reduction="sum"))
            return sum(parts) / len(i) if parts else None

        n_d, n_c = len(rows_d), len(rows_c)
        updates = {}
        phases = (("ka_o", ["o"], torch.arange(n_d + n_c), True, True),
                  ("ka_head", ["u", "pi"], torch.arange(n_d), True, False),
                  ("ka_conv", ["W", "b"], torch.arange(n_d, n_d + n_c), False, True))
        for phase, names, pool, ud, uc in phases:
            if len(pool) == 0:
                updates[phase] = 0
                continue
            for n_, t in prm.items():
                t.requires_grad_(n_ in names)
            params = [prm[n_] for n_ in names]
            opt = torch.optim.Adam(params, lr=self.lr["ka"])
            if phase in st["opt"]:
                opt.load_state_dict(st["opt"][phase])
            g = torch.Generator().manual_seed(stable_seed(self.seed, tag, r, p, phase))
            steps = 0
            for _ in range(self.epochs["ka"]):
                perm = pool[torch.randperm(len(pool), generator=g)]
                for s in range(0, len(perm), self.bs):
                    with self.timer.segment("ka_neural"):
                        loss = loss_on(perm[s:s + self.bs], ud, uc)
                        opt.zero_grad(set_to_none=True)
                        loss.backward()
                        nn.utils.clip_grad_norm_(params, self.clip)
                        opt.step()
                    self._check(loss, f"KA {p} {phase}")
                    self.losses["KA"].append(float(loss.detach()))
                    steps += 1
                    self.guard()
            st["opt"][phase] = opt.state_dict()
            updates[phase] = steps
        state = {"params": {n_: t.detach().clone() for n_, t in prm.items()}, "opt": st["opt"]}
        v = self.store.write(ka_name(p), state)
        self._bill(tag, {"layer": "KA", "unit": ka_name(p), "round": r, "version": v, "direct": n_d, "projected": n_c,
                         "updates": sum(updates.values()), "updates_by_phase": updates,
                         "examples": self.epochs["ka"] * (2 * n_d + 2 * n_c), "params_written": sum(t.numel() for t in prm.values()),
                         "reserved_bytes": reserved,
                         "read": {"ca": upper["ca_version"] if upper else None}}, t0, slept0)

    # ---------- EA ----------
    def _ea_phase(self, tag: str, r: int, idx: torch.Tensor) -> None:
        t0, slept0 = time.perf_counter(), getattr(self.guard, "slept", 0.0)
        ea, opt_state = self._load_module("ea")
        ca = self._frozen("ca")
        ct = self.ctable().to(self.device)
        reserved = 4 * nbytes(*ea.parameters()) + nbytes(*ca.parameters()) + nbytes(ct) + self._batch_bytes()
        if reserved > self.budgets["ea"]:
            raise ResourcePending(f"EA（{tag} 第 {r} 轮）需要 {reserved} 字节，超过预算 {self.budgets['ea']}")
        ea.to(self.device).train()
        ca.to(self.device)
        opt = torch.optim.Adam(ea.parameters(), lr=self.lr["ea"])
        if opt_state is not None:
            opt.load_state_dict(opt_state)
        g = torch.Generator().manual_seed(stable_seed(self.seed, tag, r, "ea"))
        steps = 0
        for _ in range(self.epochs["ea"]):
            perm = idx[torch.randperm(len(idx), generator=g)]
            for s in range(0, len(perm), self.bs):
                b = take(self.train_dev, perm[s:s + self.bs])
                with self.timer.segment("ea_neural"):
                    with torch.no_grad():
                        sel = ca.select(b)
                    rep_a, _, _ = self.ea_reps(ea, b, ct, "a")
                    rep_b, _, _ = self.ea_reps(ea, b, ct, "b")
                    logit, _ = self.combine(ca, sel, b, rep_a, rep_b)
                    loss = nn.functional.binary_cross_entropy_with_logits(logit, b.labels)
                    opt.zero_grad(set_to_none=True)
                    loss.backward()
                    nn.utils.clip_grad_norm_(ea.parameters(), self.clip)
                    opt.step()
                self._check(loss, "EA")
                self.losses["EA"].append(float(loss.detach()))
                steps += 1
                self.guard()
        v = self.store.write("ea", {"model": {k: t.cpu() for k, t in ea.state_dict().items()}, "opt": opt.state_dict()})
        self._bill(tag, {"layer": "EA", "unit": "ea", "round": r, "version": v, "materials": len(idx), "updates": steps,
                         "examples": self.epochs["ea"] * len(idx), "params_written": count_params(ea),
                         "reserved_bytes": reserved,
                         "read": {"ka": list(self._ctable_from), "ca": self.store.version("ca")}}, t0, slept0)
        del ea, ca, opt

    # ---------- CA ----------
    @torch.no_grad()
    def ea_products(self, idx: torch.Tensor, chunk: int = 2048) -> dict:
        """EA 的产品：每道题每条链对 A、B 两个查询选出的表示。在显卡上分块推理，结果放回 CPU（本地）。"""
        ea = self._frozen("ea").to(self.device)
        ct = self.ctable().to(self.device)
        rep_a, rep_b = [], []
        for s in range(0, len(idx), chunk):
            b = take(self.train_dev, idx[s:s + chunk])
            rep_a.append(self.ea_reps(ea, b, ct, "a")[0].cpu())
            rep_b.append(self.ea_reps(ea, b, ct, "b")[0].cpu())
            self.guard()
        return {"a": torch.cat(rep_a), "b": torch.cat(rep_b), "idx": idx,
                "versions": {"ea": self.store.version("ea"), "ka": self.ka_versions()}}

    def _ca_phase(self, tag: str, r: int, idx: torch.Tensor, products: Optional[dict] = None) -> None:
        t0, slept0 = time.perf_counter(), getattr(self.guard, "slept", 0.0)
        prod = products if products is not None else self.ea_products(idx)
        if prod["versions"] != {"ea": self.store.version("ea"), "ka": self.ka_versions()} or \
                not torch.equal(prod["idx"], idx):
            raise DirtyVersion("EA 产品不是由当前的 EA、KA 版本算出来的，拒绝用来训练 CA")
        ca, opt_state = self._load_module("ca")
        reserved = 4 * nbytes(*ca.parameters()) + self._batch_bytes() + \
            2 * self.bs * self.cfg.n_chains * self.cfg.k * 4
        if reserved > self.budgets["ca"]:
            raise ResourcePending(f"CA（{tag} 第 {r} 轮）需要 {reserved} 字节，超过预算 {self.budgets['ca']}")
        ca.to(self.device).train()
        opt = torch.optim.Adam(ca.parameters(), lr=self.lr["ca"])
        if opt_state is not None:
            opt.load_state_dict(opt_state)
        g = torch.Generator().manual_seed(stable_seed(self.seed, tag, r, "ca"))
        steps = 0
        for _ in range(self.epochs["ca"]):
            perm = torch.randperm(len(idx), generator=g)
            for s in range(0, len(perm), self.bs):
                pos = perm[s:s + self.bs]
                b = take(self.train_dev, idx[pos])
                rep_a, rep_b = prod["a"][pos].to(self.device), prod["b"][pos].to(self.device)    # 本地产品读回显卡
                with self.timer.segment("ca_neural"):
                    logit, _ = self.combine(ca, ca.select(b), b, rep_a, rep_b)
                    loss = nn.functional.binary_cross_entropy_with_logits(logit, b.labels)
                    opt.zero_grad(set_to_none=True)
                    loss.backward()
                    nn.utils.clip_grad_norm_(ca.parameters(), self.clip)
                    opt.step()
                self._check(loss, "CA")
                self.losses["CA"].append(float(loss.detach()))
                steps += 1
                self.guard()
        v = self.store.write("ca", {"model": {k: t.cpu() for k, t in ca.state_dict().items()}, "opt": opt.state_dict()})
        self._bill(tag, {"layer": "CA", "unit": "ca", "round": r, "version": v, "materials": len(idx), "updates": steps,
                         "examples": self.epochs["ca"] * len(idx), "params_written": count_params(ca),
                         "reserved_bytes": reserved, "read": prod["versions"] | {"ka": list(prod["versions"]["ka"])},
                         "handoff_bytes": nbytes(prod["a"], prod["b"])}, t0, slept0)
        del ca, opt

    # ---------- 一轮 ----------
    def run_round(self, tag: str, r: int, idx: torch.Tensor, ka_packages: list, ea: bool, ca: bool) -> None:
        if ka_packages:
            upper = None
            if self.store.version("ca") > 0:                    # 本轮开始时的上层产品，所有包读同一份
                upper = {"c": self.ctable().clone(), "compare": copy.deepcopy(self._frozen("ca").compare),
                         "ca_version": self.store.version("ca")}
            for p in ka_packages:
                self._ka_phase(tag, r, p, idx, upper)
        if ea:
            self._ea_phase(tag, r, idx)
        if ca:
            self._ca_phase(tag, r, idx)

    def fit(self, tag: str, pool: torch.Tensor, rounds: int, arrival_seed: int,
            curve: Optional[tuple] = None) -> dict:
        """从头螺旋训练：pool 里的观察按固定到达表分轮到达；每轮学全部已到达的观察，三层都写。"""
        arrival = arrival_rounds(len(pool), rounds, arrival_seed)
        points = []
        for r in range(1, rounds + 1):
            self.run_round(tag, r, pool[arrival <= r], list(range(self.cfg.n_packages)), True, True)
            if curve is not None:
                points.append({"round": r, "dev_subset_accuracy": self.accuracy(*curve)})
        return {"curve": points}

    def repair(self, tag: str, new: torch.Tensor, old: torch.Tensor, *, ka_packages: list, ea: bool, ca: bool,
               rounds: int, replay_ratio: float) -> None:
        """修复：只写指定的层；每轮材料＝全部新观察＋从旧观察里固定抽 replay_ratio 倍。"""
        for r in range(1, rounds + 1):
            k = min(len(old), int(round(replay_ratio * len(new))))
            g = torch.Generator().manual_seed(stable_seed(self.seed, tag, "replay", r))
            idx = torch.cat([new, old[torch.randperm(len(old), generator=g)[:k]]])
            self.run_round(tag, r, idx, ka_packages, ea, ca)

    def accuracy(self, batch: T2Batch, diag: Optional[dict] = None) -> float:
        pred = self.predict(batch)
        return float(((pred["logit"] > 0).long() == batch.labels.long()).float().mean())

    # ---------- 记账 ----------
    def _batch_bytes(self) -> int:
        C, L = self.cfg.n_chains, self.cfg.chain_len
        return self.bs * (C * L * (8 * 2 + 4 * 3) + C * 4 * 5) + 2 * self.bs * C * L * self.cfg.k * 4 * 4

    def _check(self, loss, where: str) -> None:
        if not math.isfinite(float(loss.detach())):
            raise FloatingPointError(f"{where} 损失出现非有限值")

    def _bill(self, tag: str, rec: dict, t0: float, slept0: float) -> None:
        """账单（v0.44–v0.46：代价＝损失＝账单）：每个单元每个相位的更新次数、见题次数、计算时间、写了多少参数。"""
        total = time.perf_counter() - t0
        slept = getattr(self.guard, "slept", 0.0) - slept0
        rec = {"tag": tag, **rec, "seconds": total, "throttle_seconds": slept, "compute_seconds": total - slept}
        self.bills.append(rec)
        self.log(rec)


def bill_totals(bills: list, tag: Optional[str] = None) -> dict:
    sel = [b for b in bills if tag is None or b["tag"] == tag]
    out = {"phases": len(sel), "units_written": len({(b["unit"], b["version"]) for b in sel}),
           "distinct_units": len({b["unit"] for b in sel}),
           "updates": sum(b["updates"] for b in sel), "examples": sum(b["examples"] for b in sel),
           "params_written": sum(b["params_written"] for b in sel),
           "compute_seconds": sum(b["compute_seconds"] for b in sel),
           "seconds": sum(b["seconds"] for b in sel)}
    for layer in ("KA", "EA", "CA"):
        ls = [b for b in sel if b["layer"] == layer]
        out[layer] = {"phases": len(ls), "units": len({b["unit"] for b in ls}), "updates": sum(b["updates"] for b in ls),
                      "compute_seconds": sum(b["compute_seconds"] for b in ls)}
    return out
