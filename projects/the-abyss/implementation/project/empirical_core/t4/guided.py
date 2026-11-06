"""T4：CA 约束 EA（2026-11-04）。

研究问题：CA 如何约束 EA；状态稳定不等于已经学会，KA 仍需尝试组合。
图谱 0.48：CA 先定位核心语句、指引应关注的位置并联系上下文，EA 再判断哪个 SLOT 的关键词是需要的；
更大范围组合返回约束上一层结果，基层预设可以修正。
所以 CA 约束 EA 有两条路，下面的具体接法都是本实验的工作实现，图谱写明回修和训练的具体路由未定：

- 指引：CA 的链状态是 CA 的产品，只读地交给 EA；EA 把它投影成“这条链里每个位置该多看还是少看”，直接加在选择分数上。
  投影从零开始，所以刚从 T3 接过来时，回答和不看 CA 的 EA 完全相同。这是新长出来的连接，放大 GUIDE_GAIN 倍，学得快一些。
  guided=False 的组没有这条路。
- 回返：对整个问答的反馈经过 CA 的比较头回到 EA。T2、T3 只有软的这一条：梯度穿过 EA 的选择概率。
  main 档测速发现这条路在 EA 很确定时是断的：T3 的 EA 给后一次比前一次高约 53 分，
  只修 EA 和没修一模一样；把筛子放松（分差除以 16）也推不动。
  所以这里加上“试候选”：同一条链里关系对得上的事件都是候选，把每个候选填进去，用 CA 的比较头算出整个问答的答案，
  和收到的反馈比；只有一个候选让答案对时，这个候选就是 EA 的目标。两组都有这一步。
  这里不用隐藏真值：候选来自看得见的关系，链来自 CA 自己的选择，答案对不对来自反馈。
  比较头在数值接近时会判错，所以目标有噪声。
"""
from __future__ import annotations

import time
from typing import Optional

import torch
import torch.nn as nn

from ..t1.spiral import nbytes
from ..t2.features import take
from ..t2.spiral import ResourcePending, stable_seed
from ..t2.units import A2Config, CAUnit, EAUnit, count_params
from ..t3.spiral import MutualSpiral

GUIDE_GAIN = 10.0


def ca_states(ca: CAUnit, b) -> torch.Tensor:
    """CA 给每条链的状态 [B, C, d_ca]（同 CAUnit.select 的前半段）。"""
    x = torch.stack([b.chain_say, b.chain_set, b.set_story, b.spk_x, b.spk_y], dim=-1)
    return ca.enc(ca.inp(x) + ca.pos.weight + ca.genre(b.genre).unsqueeze(1))


class GuidedEA(EAUnit):
    """T4 的 EA：可以收到 CA 的指引。没有 guide 这一项的旧版 EA 状态可以直接载入，指引从零开始学。"""

    def __init__(self, cfg: A2Config):
        super().__init__(cfg)
        self.guide = nn.Linear(cfg.d_ca, cfg.chain_len)
        nn.init.zeros_(self.guide.weight)
        nn.init.zeros_(self.guide.bias)

    def forward(self, rel: torch.Tensor, valid: torch.Tensor, g: Optional[torch.Tensor] = None) -> torch.Tensor:
        """rel、valid：[N, L]；g：[N, d_ca] 或 None（看不到 CA）→ 选择概率 [N, L+1]，最后一项是“没有”。"""
        h = self.enc(self.inp(torch.stack([rel, valid], dim=-1)) + self.pos.weight)
        s = self.ptr(h).squeeze(-1) + self.bias * rel
        if g is not None:
            s = s + GUIDE_GAIN * self.guide(g)
        s = s.masked_fill(valid == 0, -1e4)
        return torch.softmax(torch.cat([s, self.none.expand(len(s), 1)], dim=-1), dim=-1)


class GuidedSpiral(MutualSpiral):
    """双向螺旋（T3），另加 CA 约束 EA。guided=False 时 EA 看不到 CA，只有回返这一条路。"""

    def __init__(self, *args, guided: bool, trial_weight: float = 1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.guided = guided
        self.trial_weight = trial_weight
        self._guide_ca: Optional[CAUnit] = None
        self._guide_version: Optional[int] = None

    def _load_module(self, name: str):
        if name != "ea":
            return super()._load_module(name)
        torch.manual_seed(stable_seed(self.seed, name, "init"))
        module = GuidedEA(self.cfg)
        st = self.store.read(name)
        if st is None:
            return module, None
        missing = module.load_state_dict(st["model"], strict=False).missing_keys
        return module, (None if missing else st["opt"])     # 旧版 EA 的优化器状态和新参数对不上，重新开始

    def guidance(self, b) -> torch.Tensor:
        v = self.store.version("ca")
        if self._guide_ca is None or self._guide_version != v:
            self._guide_ca, self._guide_version = self._frozen("ca").to(self.device), v
        with torch.no_grad():
            return ca_states(self._guide_ca, b)

    def select_events(self, ea, b, slot: str) -> torch.Tensor:
        B, C, L = b.ev_pkg.shape
        rel = (b.rel_a if slot == "a" else b.rel_b).reshape(B * C, L)
        valid = b.ev_valid.reshape(B * C, L)
        g = self.guidance(b).reshape(B * C, -1) if self.guided else None
        return ea(rel, valid, g).view(B, C, L + 1)

    def ea_reps(self, ea, b, ct: torch.Tensor, slot: str) -> tuple:
        L = b.ev_pkg.shape[2]
        sel = self.select_events(ea, b, slot)
        reps = ct[b.ev_pkg, b.ev_mem]
        return torch.einsum("bcl,bclk->bck", sel[..., :L], reps), sel[..., L], sel

    @torch.no_grad()
    def try_candidates(self, ca: CAUnit, b, ct: torch.Tensor, rep_a: torch.Tensor, rep_b: torch.Tensor, sel: torch.Tensor) -> dict:
        """试候选：在 CA 选中的链上，把每个对得上关系的事件填进去，看整个问答的答案和反馈对不对得上。
        返回 {"a": (链, 目标位置, 这道题用不用), "b": ...}。只有一个候选让答案对时才用。"""
        C = rep_a.shape[1]
        L = b.ev_pkg.shape[2]
        rows = torch.arange(len(b.labels), device=b.labels.device)
        c_a = torch.einsum("bc,bck->bk", sel[:, 0, :C], rep_a)
        c_b = torch.einsum("bc,bck->bk", sel[:, 1, :C], rep_b)
        premise = (sel[:, 2, :C] * b.set_story).sum(-1)
        out = {}
        for i, slot, rel in ((0, "a", b.rel_a), (1, "b", b.rel_b)):
            chain = sel[:, i, :C].argmax(-1)
            cand = rel[rows, chain] > 0
            reps = ct[b.ev_pkg[rows, chain], b.ev_mem[rows, chain]]         # [B, L, k]
            good = torch.zeros_like(cand)
            for pos in range(L):
                logit = ca.compare_logit(reps[:, pos], c_b, premise) if slot == "a" else ca.compare_logit(c_a, reps[:, pos], premise)
                good[:, pos] = cand[:, pos] & ((logit > 0).float() == b.labels)
            out[slot] = (chain, good.float().argmax(-1), (cand.sum(-1) >= 2) & (good.sum(-1) == 1))
        return out

    def _ea_phase(self, tag: str, r: int, idx: torch.Tensor) -> None:
        """同 T2 的 EA 训练（CA 只读，答案的损失经过比较头回到 EA），另加试候选的目标。"""
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
        steps = trials = 0
        for _ in range(self.epochs["ea"]):
            perm = idx[torch.randperm(len(idx), generator=g)]
            for s in range(0, len(perm), self.bs):
                b = take(self.train_dev, perm[s:s + self.bs])
                with self.timer.segment("ea_neural"):
                    with torch.no_grad():
                        sel = ca.select(b)
                    rep_a, _, sel_a = self.ea_reps(ea, b, ct, "a")
                    rep_b, _, sel_b = self.ea_reps(ea, b, ct, "b")
                    logit, _ = self.combine(ca, sel, b, rep_a, rep_b)
                    loss = nn.functional.binary_cross_entropy_with_logits(logit, b.labels)
                    tried = self.try_candidates(ca, b, ct, rep_a.detach(), rep_b.detach(), sel)
                    for key, sel_e in (("a", sel_a), ("b", sel_b)):
                        chain, target, use = tried[key]
                        if use.any():
                            rows = torch.nonzero(use).squeeze(-1)
                            p = sel_e[rows, chain[rows], target[rows]]
                            loss = loss - self.trial_weight * (p + 1e-30).log().mean()
                            trials += len(rows)
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
                         "examples": self.epochs["ea"] * len(idx), "params_written": count_params(ea), "trials": trials,
                         "reserved_bytes": reserved,
                         "read": {"ka": list(self._ctable_from), "ca": self.store.version("ca")}}, t0, slept0)
        del ea, ca, opt

    @torch.no_grad()
    def sieve(self, idx: torch.Tensor, chunk: int = 2048) -> dict:
        """同 T3 的筛子，只是 EA 的选择带上 CA 的指引。"""
        ea, ca = self._frozen("ea").to(self.device), self._frozen("ca").to(self.device)
        C, L = self.cfg.n_chains, self.cfg.chain_len
        w_a, w_b, premise = [torch.zeros(0, C, L)], [torch.zeros(0, C, L)], [torch.zeros(0)]    # 这批材料可能全都能精确对应
        for s in range(0, len(idx), chunk):
            b = take(self.train_dev, idx[s:s + chunk])
            sel = ca.select(b)
            w_a.append((sel[:, 0, :C, None] * self.select_events(ea, b, "a")[..., :L]).cpu())
            w_b.append((sel[:, 1, :C, None] * self.select_events(ea, b, "b")[..., :L]).cpu())
            premise.append((sel[:, 2, :C] * b.set_story).sum(-1).cpu())
            self.guard()
        w_a, w_b, premise = torch.cat(w_a), torch.cat(w_b), torch.cat(premise)
        rows = torch.arange(len(idx))
        pkg = self.train.ev_pkg[idx].reshape(len(idx), C * L)
        return {"idx": idx, "w_a": w_a, "w_b": w_b, "premise": premise,
                "owner_a": pkg[rows, w_a.reshape(len(idx), C * L).argmax(-1)],
                "owner_b": pkg[rows, w_b.reshape(len(idx), C * L).argmax(-1)],
                "versions": {"ea": self.store.version("ea"), "ca": self.store.version("ca")}}
