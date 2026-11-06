"""被测模型 A 的螺旋式分层训练（A-spiral）。

依据：
- 历史训练协议 spiral_learning_001/TRAINING_PROTOCOL.md：采用逐层迭代优化的螺旋训练。
- 分治且流式启动：依赖驱动的局部激活、受限工作集、结果交接后释放。
- 名词解释 v0.23 两层训练大循环（先知识包，再事件链／EA）；v0.22 运行范围、训练写范围、行为影响范围分开。

T1 上的固定依赖图（工作解释，等实验检验）：
- 下层 L0：每个知识包一个节点 p。
  - KA_p：成员在本包参考系里的表示 o_p。参考成员固定为 0。
  - EA_p：包内比较头，包括读出向量 u_p，以及两个世界各一个方向 π_p。
  - 材料：本轮以前已到达、涉及本包成员的观察。
    - 包内观察直接使用。
    - 跨包观察借用上层上一轮发布的产品：本包的尺子转换、对方对象的共同空间表示、比较头。这样做成“投影”材料。
    - 投影材料的外部观察是真的；它属于本包哪个成员，由 CPU 侧的关系对应精确到这一次发生。
    - 投影不算新的独立证据。
    - 第一轮上层还没有产品，所以只用包内观察。
  - 产品：本包全部成员的 o_p。无答案的探针就是本包的全部成员。
- 上层 L1：只有一个节点。
  - KA_1：每个包一个尺子转换（矩阵＋偏置），把下层产品换到共同空间。
  - EA_1：事件链 attention，在事件上选出 A 和 B；再加比较头（含前提）。
  - 材料：本轮以前已到达的全部题；设了 replay_ratio 时，改为本轮新到的题加按比例抽的旧题（round_materials）。
    输入由下层本轮的产品重新生成。
- 每一轮的顺序：
  1. 新观察到达；
  2. L0 各节点依次做 KA → EA → 发布；
  3. L1 用新产品重建输入，再做 KA → EA → 发布；
  4. 本轮评价。
- 跨轮规则：
  - 模型和优化器状态跨轮保留。
  - 下层换版以后，上层必须重建；新旧版本混用时拒绝（DirtyVersion）。
  - 每一轮的状态都写盘保留。
- 写范围：L0 节点只写自己的 o_p、u_p、π_p；L1 只写转换、EA 和比较头。
  上层的错误不直接当作下层的标签：下层只用能精确对应到自己成员的外部观察。
- 工作集：
  - L0 节点激活时，内存里只有本包的参数、本包的材料，以及上层产品的只读引用。
  - L1 是最小完整单元，整体驻留。L1 不在计算时卸载到磁盘。
  - 每次激活前先按字节预留；超出预算就抛出 ResourcePending，不裁剪候选。
- 诚实边界：
  - TRAIN 数据事先整份生成并载入，“分轮到达”是用固定的到达表模拟的。
  - 训练器只读取已到达的行，但这不是真正的外部流式输入。
评价时把各节点产品组装成 ModelA，用同一个前向，和 A-joint 同口径。
"""
from __future__ import annotations

import copy
import hashlib
import math
import time
from pathlib import Path
from typing import Callable, Optional

import torch
import torch.nn as nn

from ..timing import SegmentTimer
from .features import T1Batch
from .model_a import ModelA, ModelAConfig
from .train import curve_accuracy, take, to_device

EA_PARTS = ("ea_in", "ea_pos", "ea", "ea_ptr", "ea_none", "compare")
KA1_PARTS = ("convert_w", "convert_b")


class ResourcePending(RuntimeError):
    """最小完整单元放不进预算：记录所需字节后停下，不裁剪候选、不重置预算。"""


class DirtyVersion(RuntimeError):
    """下层已经换版、上层尚未重建：拒绝混用新旧版本。"""


def nbytes(*tensors) -> int:
    return sum(t.numel() * t.element_size() for t in tensors)


def digest(t: torch.Tensor) -> str:
    return hashlib.sha256(t.detach().contiguous().numpy().tobytes()).hexdigest()[:16]


def resolved_pairs(batch: T1Batch) -> dict:
    """CPU 侧的关系对应：每道题里查询关系 r_A、r_B 各对应哪个事件，取出 (包, 成员)。只用可见输入。"""
    ia, ib = batch.rel_match[..., 0].argmax(dim=1), batch.rel_match[..., 1].argmax(dim=1)
    rows = torch.arange(len(batch.ids))
    return {"a_pkg": batch.package[rows, ia], "a_mem": batch.member[rows, ia],
            "b_pkg": batch.package[rows, ib], "b_mem": batch.member[rows, ib],
            "world": batch.world, "premise": batch.premise, "label": batch.labels}


def arrival_rounds(n: int, rounds: int, seed: int) -> torch.Tensor:
    """固定的到达表：第几轮到达（1..rounds），每轮大致一样多。"""
    perm = torch.randperm(n, generator=torch.Generator().manual_seed(seed))
    arrival = torch.empty(n, dtype=torch.long)
    arrival[perm] = torch.arange(n) * rounds // n + 1
    return arrival


class SpiralA:
    def __init__(self, cfg: ModelAConfig, workdir: Path, *, seed: int, rounds: int, epochs_per_phase: int,
                 batch_size: int, lr: float, arrival_seed: int, l0_budget_bytes: int, l1_budget_bytes: int,
                 clip: float = 1.0, guard: Optional[Callable[[], None]] = None, timer: Optional[SegmentTimer] = None,
                 log: Optional[Callable[[dict], None]] = None, replay_ratio: Optional[float] = None,
                 device: str = "cpu"):
        self.cfg, self.workdir, self.seed = cfg, Path(workdir), seed
        self.rounds, self.epochs, self.bs, self.lr, self.clip = rounds, epochs_per_phase, batch_size, lr, clip
        self.arrival_seed = arrival_seed
        self.replay_ratio = replay_ratio      # None：每轮学全部已到达的观察；数值：本轮新到的＋按比例抽的旧观察
        self.device = torch.device(device)    # 只用于 L1；L0 节点很小，留在 CPU
        self.train_dev: Optional[T1Batch] = None
        self.l0_budget, self.l1_budget = l0_budget_bytes, l1_budget_bytes
        self.guard = guard or (lambda: None)
        self.timer = timer or SegmentTimer()
        self.log = log or (lambda rec: None)
        self.l0_version = [0] * cfg.n_packages        # 每个节点最近一次发布的轮次（0＝初始值）
        self.l1_consumed: Optional[list] = None       # L1 最近一次重建时读到的 L0 版本
        self.l1_round = 0
        self.upper: Optional[dict] = None             # L1 上一轮产品的只读引用，供 L0 投影材料使用
        self.updates = {"l0_ka": 0, "l0_ea": 0, "l1_ka": 0, "l1_ea": 0}
        self.examples = {"l0_ka": 0, "l0_ea": 0, "l1_ka": 0, "l1_ea": 0}
        self.bills: list[dict] = []
        self.l1_losses: list[float] = []

    # ---------- 节点状态的存取 ----------
    def _node_path(self, r: int, p: int) -> Path:
        return self.workdir / "L0" / f"r{r:02d}" / f"p{p:04d}.pt"

    def _init_node(self, p: int) -> dict:
        g = torch.Generator().manual_seed(self.seed * 100_003 + p)
        k, M = self.cfg.k, self.cfg.n_members
        return {"o": torch.randn(M - 1, k, generator=g) * 0.02, "u": torch.randn(k, generator=g) / math.sqrt(k),
                "pi": torch.ones(2), "opt_ka": None, "opt_ea": None}

    def _load_node(self, p: int) -> dict:
        r = self.l0_version[p]
        return self._init_node(p) if r == 0 else torch.load(self._node_path(r, p), weights_only=False)

    def node_product(self, p: int) -> torch.Tensor:
        o = self._load_node(p)["o"]
        return torch.cat([torch.zeros(1, self.cfg.k), o], dim=0)          # [M, k]，参考成员为 0

    # ---------- L0：一个包节点 ----------
    def _l0_phase(self, r: int, p: int, mats: dict, arrived: torch.Tensor) -> None:
        t0 = time.perf_counter()
        touch = arrived & ((mats["a_pkg"] == p) | (mats["b_pkg"] == p))
        direct_idx = torch.nonzero(touch & (mats["a_pkg"] == p) & (mats["b_pkg"] == p)).flatten()
        cross_idx = torch.nonzero(touch & (mats["a_pkg"] != mats["b_pkg"])).flatten() if self.upper else \
            torch.empty(0, dtype=torch.long)
        node = self._load_node(p)
        o = nn.Parameter(node["o"].clone())
        u = nn.Parameter(node["u"].clone())
        pi = nn.Parameter(node["pi"].clone())
        sub = {key: v[torch.cat([direct_idx, cross_idx])] for key, v in mats.items()}
        n_direct = len(direct_idx)
        ctx = []
        if self.upper:
            ctx = [self.upper["W"][p], self.upper["b"][p], self.upper["c"], *self.upper["compare"].parameters()]
        act = self.bs * (3 * self.cfg.k + 1 + 2 * self.cfg.d_compare) * 4 * 3
        reserved = 4 * nbytes(o, u, pi) + nbytes(*sub.values()) + nbytes(*ctx) + act
        if reserved > self.l0_budget:
            raise ResourcePending(f"L0 节点 {p} 第 {r} 轮需要 {reserved} 字节，超过预算 {self.l0_budget}")

        def own(mem):
            return torch.cat([torch.zeros(1, self.cfg.k), o], dim=0)[mem]

        def ka_loss(i):
            a_own, b_own = sub["a_pkg"][i] == p, sub["b_pkg"][i] == p
            is_direct = a_own & b_own
            losses = []
            if is_direct.any():
                j = i[is_direct]
                diff = own(sub["a_mem"][j]) @ u - own(sub["b_mem"][j]) @ u
                losses.append(nn.functional.binary_cross_entropy_with_logits(
                    pi[sub["world"][j]] * diff, sub["label"][j], reduction="sum"))
            if (~is_direct).any():                                       # 投影材料：上层产品只读
                j = i[~is_direct]
                W, b, c, cmp = self.upper["W"][p], self.upper["b"][p], self.upper["c"], self.upper["compare"]
                c_a = torch.where((sub["a_pkg"][j] == p).unsqueeze(-1), own(sub["a_mem"][j]) @ W + b,
                                  c[sub["a_pkg"][j], sub["a_mem"][j]])
                c_b = torch.where((sub["b_pkg"][j] == p).unsqueeze(-1), own(sub["b_mem"][j]) @ W + b,
                                  c[sub["b_pkg"][j], sub["b_mem"][j]])
                logit = cmp(torch.cat([c_a, c_b, c_a - c_b, sub["premise"][j].unsqueeze(-1)], dim=-1)).squeeze(-1)
                losses.append(nn.functional.binary_cross_entropy_with_logits(logit, sub["label"][j], reduction="sum"))
            return sum(losses) / len(i)

        def ea_loss(i):                                                  # KA 已更新并固定，只学包内比较头
            diff = own(sub["a_mem"][i]).detach() @ u - own(sub["b_mem"][i]).detach() @ u
            return nn.functional.binary_cross_entropy_with_logits(pi[sub["world"][i]] * diff, sub["label"][i])

        opt_ka_state, ka_updates = self._run_phase([o], node["opt_ka"], len(sub["label"]), ka_loss, ("l0", r, p, "ka"))
        ea_state, ea_updates = self._run_phase([u, pi], node["opt_ea"], n_direct, ea_loss, ("l0", r, p, "ea"))
        self.updates["l0_ka"] += ka_updates
        self.updates["l0_ea"] += ea_updates
        self.examples["l0_ka"] += self.epochs * len(sub["label"])
        self.examples["l0_ea"] += self.epochs * n_direct
        path = self._node_path(r, p)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"o": o.detach(), "u": u.detach(), "pi": pi.detach(), "opt_ka": opt_ka_state, "opt_ea": ea_state},
                   path)
        self.l0_version[p] = r
        measured = 4 * nbytes(o, u, pi) + nbytes(*sub.values())
        self._bill({"layer": "L0", "round": r, "node": p, "direct": n_direct, "projected": len(cross_idx),
                    "updates_ka": ka_updates, "updates_ea": ea_updates, "seconds": time.perf_counter() - t0,
                    "reserved_bytes": reserved, "measured_bytes": measured,
                    "read_upper_round": self.l1_round if self.upper else None,
                    "write_scope": [f"o[{p}]", f"u[{p}]", f"pi[{p}]"], "product_digest": digest(o.detach())})

    def _run_phase(self, params, opt_state, n, loss_fn, key) -> tuple:
        """一个局部相位：在 n 条材料上训练 epochs 轮。n＝0 时不更新，原样保留优化器状态。"""
        if n == 0:
            return opt_state, 0
        opt = torch.optim.Adam(params, lr=self.lr)
        if opt_state is not None:
            opt.load_state_dict(opt_state)
        g = torch.Generator().manual_seed(_stable_seed(self.seed, *key))
        steps = 0
        for _ in range(self.epochs):
            perm = torch.randperm(n, generator=g)
            for s in range(0, n, self.bs):
                with self.timer.segment("l0_neural"):
                    loss = loss_fn(perm[s:s + self.bs])
                    opt.zero_grad(set_to_none=True)
                    loss.backward()
                    nn.utils.clip_grad_norm_(params, self.clip)
                    opt.step()
                if not math.isfinite(float(loss.detach())):
                    raise FloatingPointError(f"{key} 损失出现非有限值")
                steps += 1
                self.guard()
        return opt.state_dict(), steps

    # ---------- L1：上层节点 ----------
    def _l1_path(self, r: int) -> Path:
        return self.workdir / "L1" / f"r{r:02d}.pt"

    def _load_l1(self) -> tuple:
        torch.manual_seed(self.seed)
        model = ModelA(self.cfg)
        opt_states = {"ka": None, "ea": None}
        if self.l1_round > 0:
            saved = torch.load(self._l1_path(self.l1_round), weights_only=False, map_location="cpu")
            model.load_state_dict(saved["model"])
            opt_states = saved["opt"]
        return model, opt_states

    def _l1_phase(self, r: int, train: T1Batch, arrived: torch.Tensor, curve_batch: Optional[T1Batch]) -> dict:
        t0 = time.perf_counter()
        model, opt_states = self._load_l1()
        with torch.no_grad():                                             # 用下层本轮产品重建输入
            for p in range(self.cfg.n_packages):
                model.member_offset[p] = self.node_product(p)[1:]
        self.l1_consumed = list(self.l0_version)
        idx = torch.nonzero(arrived).flatten()
        reserved = 4 * sum(x.numel() * 4 for x in model.parameters()) + nbytes(
            *(getattr(train, f)[idx] for f in ("rel_match", "package", "member", "position", "world", "premise",
                                               "labels"))) + self.bs * self.cfg.history_len * (
            self.cfg.k * self.cfg.k + 8 * self.cfg.d_event) * 4 * 3
        if reserved > self.l1_budget:
            raise ResourcePending(f"L1 第 {r} 轮需要 {reserved} 字节，超过预算 {self.l1_budget}")
        model.to(self.device)                                             # L1 可以放到显卡上；L0 留在 CPU
        train = self.train_dev
        named = dict(model.named_parameters())
        ka_params = [named[n] for n in KA1_PARTS]
        ea_params = [p for n, p in named.items() if n.split(".")[0] in EA_PARTS]
        for p in model.parameters():
            p.requires_grad_(False)
        out = {}
        for phase, params in (("ka", ka_params), ("ea", ea_params)):
            for p in params:
                p.requires_grad_(True)
            opt = torch.optim.Adam(params, lr=self.lr)
            if opt_states[phase] is not None:
                opt.load_state_dict(opt_states[phase])
            g = torch.Generator().manual_seed(self.seed * 1_000 + r * 10 + (phase == "ea"))
            steps = 0
            for _ in range(self.epochs):
                perm = idx[torch.randperm(len(idx), generator=g)]
                for s in range(0, len(perm), self.bs):
                    b = take(train, perm[s:s + self.bs])
                    with self.timer.segment(f"l1_{phase}_neural"):
                        loss = nn.functional.binary_cross_entropy_with_logits(model(b)["logit"], b.labels)
                        opt.zero_grad(set_to_none=True)
                        loss.backward()
                        nn.utils.clip_grad_norm_(params, self.clip)
                        opt.step()
                    if not math.isfinite(float(loss.detach())):
                        raise FloatingPointError(f"L1 第 {r} 轮 {phase} 损失出现非有限值")
                    if phase == "ea":
                        self.l1_losses.append(float(loss.detach()))
                    steps += 1
                    self.guard()
            opt_states[phase] = opt.state_dict()
            self.updates[f"l1_{phase}"] += steps
            self.examples[f"l1_{phase}"] += self.epochs * len(idx)
            out[phase] = steps
            for p in params:
                p.requires_grad_(False)
        self.l1_round = r
        path = self._l1_path(r)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"model": model.state_dict(), "opt": opt_states, "consumed_l0": self.l1_consumed}, path)
        with torch.no_grad():                                             # 发布给下一轮 L0 的只读产品
            o_all = model.offsets()
            c = torch.einsum("pmk,pkj->pmj", o_all, model.convert_w) + model.convert_b.unsqueeze(1)
            self.upper = {"W": model.convert_w.detach().cpu().clone(), "b": model.convert_b.detach().cpu().clone(),
                          "c": c.cpu(), "compare": copy.deepcopy(model.compare).cpu().requires_grad_(False)}
        acc = curve_accuracy(model, curve_batch, self.guard)
        self._bill({"layer": "L1", "round": r, "node": "top", "materials": len(idx), "updates_ka": out["ka"],
                    "updates_ea": out["ea"], "seconds": time.perf_counter() - t0, "reserved_bytes": reserved,
                    "measured_bytes": 4 * sum(x.numel() * 4 for x in model.parameters()),
                    "write_scope": ["convert_w", "convert_b", *EA_PARTS], "consumed_l0_rounds": sorted(set(self.l1_consumed)),
                    "dev_subset_accuracy": acc})
        del model
        return {"round": r, "dev_subset_accuracy": acc}

    def _bill(self, rec: dict) -> None:
        """账单（v0.44–v0.46：代价＝损失＝账单）：随结构登记每个相位的更新次数、墙钟和字节。"""
        self.bills.append(rec)
        self.log(rec)

    # ---------- 整体 ----------
    def fit(self, train: T1Batch, curve_batch: Optional[T1Batch] = None) -> dict:
        mats = resolved_pairs(train)
        self.train_dev = to_device(train, self.device)
        arrival = arrival_rounds(len(train.ids), self.rounds, self.arrival_seed)
        curve = []
        for r in range(1, self.rounds + 1):
            arrived = self.round_materials(arrival, r)
            for p in range(self.cfg.n_packages):
                self._l0_phase(r, p, mats, arrived)
            curve.append(self._l1_phase(r, train, arrived, curve_batch))
        return {"updates": sum(self.updates.values()), "updates_by_phase": dict(self.updates),
                "examples_seen": dict(self.examples), "rounds": self.rounds, "curve": curve,
                "loss_first": _mean(self.l1_losses[:20]), "loss_last": _mean(self.l1_losses[-20:]),
                "loss_trace": self.l1_losses[:: max(1, len(self.l1_losses) // 200)],
                "max_reserved_bytes": {layer: max(b["reserved_bytes"] for b in self.bills if b["layer"] == layer)
                                       for layer in ("L0", "L1")},
                "timing": self.timer.summary(warmup=0)}

    def round_materials(self, arrival: torch.Tensor, r: int) -> torch.Tensor:
        """本轮要学的观察。
        - 不设 replay_ratio：全部已到达的观察。
        - 设了 replay_ratio：本轮新到的观察，加上从旧观察里固定抽出的 replay_ratio 倍（继续学原有的条件，但总量有限）。
          这样每轮的工作量不随轮数增长，多转几轮不会让总量变成平方级。"""
        if self.replay_ratio is None:
            return arrival <= r
        new = arrival == r
        old = torch.nonzero(arrival < r).flatten()
        k = min(len(old), int(round(self.replay_ratio * int(new.sum()))))
        chosen = new.clone()
        if k:
            g = torch.Generator().manual_seed(_stable_seed(self.seed, "replay", r))
            chosen[old[torch.randperm(len(old), generator=g)[:k]]] = True
        return chosen

    def assemble(self) -> ModelA:
        """组装评价用的 ModelA。L1 必须是用各节点最新版本重建过的，否则拒绝（不混用新旧版本）。"""
        if self.l1_consumed != self.l0_version:
            raise DirtyVersion("下层已换版，上层还没有重建，拒绝组装")
        model, _ = self._load_l1()
        model.eval()
        return model


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _stable_seed(*parts) -> int:
    """跨进程稳定的种子（Python 自带的 hash 对字符串每次进程都不同）。"""
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:4], "little")
