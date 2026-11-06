"""T3：EA↔KA 单向／双向修正的螺旋训练（2026-11-03）。

模型、单元和三层的调用顺序都同 T2（empirical_core/t2）。区别只在 KA 从哪里拿材料：
- 单向（two_way=False）：就是 T2 的做法。KA 只用 CPU 能精确对应到成员的观察；EA 读 KA 的产品去适应 KA。
  材料从不适应筛子，只有筛子适应材料。
- 双向（two_way=True）：KA 另外从“筛子”拿材料。
  - 筛子＝上一轮的 CA 选链概率 × EA 选事件概率：每道题、每个查询在每个事件上的权重 w [C, L]。
    在显卡上分块算出来，放回本地（CPU 内存）；KA 在 CPU 上读。
  - 每道 CPU 不能精确对应的题，交给权重最大的那个事件所属的包（筛子把这份材料递给那个 KA 单元）。
  - KA_p 在这份材料上的表示：c = Σ w · 产品，其中本包事件用 KA_p 正在学的产品，别的包用本轮开始时的产品（同 T2，Jacobi）。
    再用上一轮 CA 的比较头（只读）算答案。只写 KA_p 自己的成员表示 o 和尺子转换 W、b。
  - 接着 EA 读 KA 的新产品去适应 KA。这样一轮里材料适应筛子、筛子适应材料，就是 EA↔KA 相互修正。
- SLOT：EA↔KA 的结果，即 EA 在一条链上选出的表示 Σ_l sel · 产品（图谱 11-03：“EA和KA双向的结果应该是SLOT”）。
  训练 CA 时 SLOT 固定不变（T2 已有：EA 产品带版本号，版本不对就拒绝用），对应“SLOT 在 EA↔CA 这一段作不变量”。
双向时“上层的选择错误不当作下层的标签”这条 T2 规则不再成立：筛子选错，材料就会跟着错。这正是要观察的。
"""
from __future__ import annotations

import time
from typing import Optional

import torch
import torch.nn as nn

from ..t1.spiral import arrival_rounds, nbytes
from ..t2.features import take
from ..t2.spiral import ChainSpiral, ResourcePending, ka_name, stable_seed
from ..t2.units import KA_PARAMS, ka_own


class MutualSpiral(ChainSpiral):
    def __init__(self, *args, two_way: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.two_way = two_way

    # ---------- 筛子 ----------
    @torch.no_grad()
    def sieve(self, idx: torch.Tensor, chunk: int = 2048) -> dict:
        """上一轮 EA、CA 的选择，在显卡上分块算，放回本地：A、B 两个查询在每个事件上的权重 [N, C, L]、
        当前设定的前提 [N]、权重最大的事件所属的包 [N]（这道题交给哪个 KA 单元）。"""
        ea, ca = self._frozen("ea").to(self.device), self._frozen("ca").to(self.device)
        C, L = self.cfg.n_chains, self.cfg.chain_len
        w_a, w_b, premise = [], [], []
        for s in range(0, len(idx), chunk):
            b = take(self.train_dev, idx[s:s + chunk])
            n = len(b.ids)
            sel = ca.select(b)
            ea_a = ea(b.rel_a.reshape(n * C, L), b.ev_valid.reshape(n * C, L)).view(n, C, L + 1)
            ea_b = ea(b.rel_b.reshape(n * C, L), b.ev_valid.reshape(n * C, L)).view(n, C, L + 1)
            w_a.append((sel[:, 0, :C, None] * ea_a[..., :L]).cpu())
            w_b.append((sel[:, 1, :C, None] * ea_b[..., :L]).cpu())
            premise.append((sel[:, 2, :C] * b.set_story).sum(-1).cpu())
            self.guard()
        w_a, w_b, premise = torch.cat(w_a), torch.cat(w_b), torch.cat(premise)
        rows = torch.arange(len(idx))
        pkg = self.train.ev_pkg[idx].reshape(len(idx), C * L)
        owner_a = pkg[rows, w_a.reshape(len(idx), C * L).argmax(-1)]
        owner_b = pkg[rows, w_b.reshape(len(idx), C * L).argmax(-1)]
        return {"idx": idx, "w_a": w_a, "w_b": w_b, "premise": premise, "owner_a": owner_a, "owner_b": owner_b,
                "versions": {"ea": self.store.version("ea"), "ca": self.store.version("ca")}}

    # ---------- 一轮 ----------
    def run_round(self, tag: str, r: int, idx: torch.Tensor, ka_packages: list, ea: bool, ca: bool) -> None:
        if not self.two_way:
            return super().run_round(tag, r, idx, ka_packages, ea, ca)
        if ka_packages:
            upper = None
            if self.store.version("ca") > 0:                # 本轮开始时的上层产品，所有包读同一份
                upper = {"c": self.ctable().clone(), "compare": self._frozen("ca").compare,
                         "ca_version": self.store.version("ca")}
                if self.store.version("ea") > 0:
                    t0, slept0 = time.perf_counter(), getattr(self.guard, "slept", 0.0)
                    upper["sieve"] = self.sieve(idx[~self.train.exact[idx]])
                    sv = upper["sieve"]
                    self._bill(tag, {"layer": "SIEVE", "unit": "sieve", "round": r, "version": 0,
                                     "materials": len(sv["idx"]), "updates": 0, "examples": len(sv["idx"]),
                                     "params_written": 0, "read": sv["versions"],
                                     "handoff_bytes": nbytes(sv["w_a"], sv["w_b"], sv["premise"])}, t0, slept0)
            for p in ka_packages:
                self._ka_phase(tag, r, p, idx, upper)
        if ea:
            self._ea_phase(tag, r, idx)
        if ca:
            self._ca_phase(tag, r, idx)

    def fit_rounds(self, tag: str, pool: torch.Tensor, rounds: int, arrival_over: int, arrival_seed: int, after_round=None):
        """从头螺旋训练到硬上限 rounds 轮：观察在前 arrival_over 轮按固定到达表陆续到达，之后每轮学全部。
        每轮结束调用 after_round(r)（统一校验、报告用的评测都放在那里，只读）。"""
        arrival = arrival_rounds(len(pool), arrival_over, arrival_seed)
        for r in range(1, rounds + 1):
            self.run_round(tag, r, pool[arrival <= r], list(range(self.cfg.n_packages)), True, True)
            if after_round is not None:
                after_round(r)

    # ---------- KA ----------
    def _ka_phase(self, tag: str, r: int, p: int, idx: torch.Tensor, upper: Optional[dict]) -> None:
        if not self.two_way or upper is None or "sieve" not in upper:
            return super()._ka_phase(tag, r, p, idx, upper)
        t0, slept0 = time.perf_counter(), getattr(self.guard, "slept", 0.0)
        tr, sv = self.train, upper["sieve"]
        rows = idx[tr.exact[idx]]
        a_pkg, b_pkg = tr.ex_a[rows, 0], tr.ex_b[rows, 0]
        touch = (a_pkg == p) | (b_pkg == p)
        direct = touch & (a_pkg == p) & (b_pkg == p)
        rows_d, rows_c = rows[direct], rows[touch & ~direct]
        pos_m = torch.nonzero((sv["owner_a"] == p) | (sv["owner_b"] == p)).squeeze(-1)    # 筛子递给本包的题
        n_d, n_c, n_m = len(rows_d), len(rows_c), len(pos_m)
        if n_d + n_c + n_m == 0:
            return
        st = self._ka_state(p)
        prm = {n: nn.Parameter(st["params"][n].clone()) for n in KA_PARAMS}
        C, L, k = self.cfg.n_chains, self.cfg.chain_len, self.cfg.k
        ctx = [upper["c"], *upper["compare"].parameters()]
        act = self.bs * (3 * k + 1 + 2 * self.cfg.d_compare) * 4 * 3 + 2 * self.bs * C * L * k * 4 * 3
        reserved = 4 * nbytes(*prm.values()) + (n_d + n_c) * 8 * 6 + n_m * (2 * C * L * 4 + 4 + 8) + nbytes(*ctx) + act
        if reserved > self.budgets["ka"]:
            raise ResourcePending(f"KA 单元 {p}（{tag} 第 {r} 轮）需要 {reserved} 字节，超过预算 {self.budgets['ka']}")
        # 材料编号：0..n_d−1 包内精确，n_d..n_d+n_c−1 跨包精确，其后是筛子递来的
        kinds = torch.cat([torch.zeros(n_d, dtype=torch.long), torch.ones(n_c, dtype=torch.long),
                           torch.full((n_m,), 2, dtype=torch.long)])
        ref = torch.cat([rows_d, rows_c, pos_m])

        def loss_on(i):
            kd, rf = kinds[i], ref[i]
            own = ka_own(prm["o"])
            mine = own @ prm["W"] + prm["b"]
            parts = []
            d = kd == 0
            if d.any():
                m = rf[d]
                diff = (own[tr.ex_a[m, 1]] - own[tr.ex_b[m, 1]]) @ prm["u"]
                parts.append(nn.functional.binary_cross_entropy_with_logits(
                    prm["pi"][tr.ex_story[m].long()] * diff, tr.labels[m], reduction="sum"))
            c = kd == 1
            if c.any():
                m = rf[c]
                ap, bp, am, bm = tr.ex_a[m, 0], tr.ex_b[m, 0], tr.ex_a[m, 1], tr.ex_b[m, 1]
                c_a = torch.where((ap == p).unsqueeze(-1), mine[am], upper["c"][ap, am])
                c_b = torch.where((bp == p).unsqueeze(-1), mine[bm], upper["c"][bp, bm])
                logit = upper["compare"](torch.cat([c_a, c_b, c_a - c_b, tr.ex_story[m].unsqueeze(-1)], -1)).squeeze(-1)
                parts.append(nn.functional.binary_cross_entropy_with_logits(logit, tr.labels[m], reduction="sum"))
            s = kd == 2
            if s.any():
                j = rf[s]
                m = sv["idx"][j]
                pkg, mem = tr.ev_pkg[m], tr.ev_mem[m]
                reps = torch.where((pkg == p).unsqueeze(-1), mine[mem], upper["c"][pkg, mem])     # [n, C, L, k]
                c_a = torch.einsum("ncl,nclk->nk", sv["w_a"][j], reps)
                c_b = torch.einsum("ncl,nclk->nk", sv["w_b"][j], reps)
                logit = upper["compare"](torch.cat([c_a, c_b, c_a - c_b, sv["premise"][j].unsqueeze(-1)], -1)).squeeze(-1)
                parts.append(nn.functional.binary_cross_entropy_with_logits(logit, tr.labels[m], reduction="sum"))
            return sum(parts) / len(i)

        updates = {}
        phases = (("ka_o", ["o"], torch.arange(n_d + n_c + n_m)),
                  ("ka_head", ["u", "pi"], torch.arange(n_d)),
                  ("ka_conv", ["W", "b"], torch.arange(n_d, n_d + n_c + n_m)))
        for phase, names, pool in phases:
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
                        loss = loss_on(perm[s:s + self.bs])
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
                         "sieved": n_m, "updates": sum(updates.values()), "updates_by_phase": updates,
                         "examples": self.epochs["ka"] * (2 * n_d + 2 * (n_c + n_m)),
                         "params_written": sum(t.numel() for t in prm.values()), "reserved_bytes": reserved,
                         "read": {"ca": upper["ca_version"], "sieve": sv["versions"]}}, t0, slept0)
