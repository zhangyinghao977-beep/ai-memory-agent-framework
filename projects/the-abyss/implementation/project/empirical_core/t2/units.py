"""T2 被测模型 A2：KA、EA、CA 三层，每个单元都是一个超小型神经网络（2026-11-02）。

依据：
- 名词解释 v0.55 第 1 节：以超小型神经网络为计算单元，在 CPU／GPU 之间交接结果。
  每个单元单独存盘、单独载入训练；单元之间只交接产品。
- 图谱 0.45 第 09 图：KA 在知识包内基于参考系处理相对偏差；EA 参照 KA 和 SLOT 组织链内关系；
  CA（Chain Attention，原 PA 的职责改名）处理链之间的关系；使用入口由 CA 先做语义判断。

三层单元：
- KA_p（每个包一个）：
  - 成员在本包参考系里的表示 o_p，参考成员固定为 0（存异）；
  - 包内比较头 u_p、π_p（两个世界各一个方向）；
  - 尺子转换 W_p、b_p：把本包表示换到共同空间。
  - 产品：本包全部成员的共同空间表示 c[p]。
- EA（一个，所有链共用）：一条链里的事件做成 token（关系是否对得上查询＋位置），经过 self-attention，
  在事件上选出查询关系对应的那一个，另有“这条链里没有”。CPU 的身份判断（关系对得上）以固定偏置加在选择分数上，同 T1。
- CA（一个）：链做成 token（种类、说话人是否等于 x／y、设定内容＋链的位置＋体裁），经过 self-attention，
  选出 A 所在的链、B 所在的链和当前有效的设定（CA 先做语义判断，不依赖 EA 的输出）；
  最后在链间比较 A 和 B（回返）。说话人对得上、是不是设定链，同样以固定偏置加在选择分数上；
  同一说话人有几条链时，选哪一条要 CA 自己学。
这里的调用顺序（CA 选链 → EA 选事件 → KA 给表示 → CA 比较）是本实验的一个工作实现；
图谱写明“具体调用路由未定”，不把它当成已确认的全序。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import torch
import torch.nn as nn


@dataclass(frozen=True)
class A2Config:
    n_packages: int
    n_members: int
    n_chains: int
    chain_len: int
    k: int = 8                  # 包内参考系与共同空间的维数
    d_ea: int = 16
    ea_layers: int = 1
    ea_heads: int = 2
    d_ca: int = 16
    ca_layers: int = 1
    ca_heads: int = 2
    d_compare: int = 32
    ea_identity_bias: float = 6.0
    ca_identity_bias: float = 6.0
    n_genres: int = 2


SIZE_PRESETS = {
    "small": dict(k=8, d_ea=16, ea_layers=1, ea_heads=2, d_ca=16, ca_layers=1, ca_heads=2, d_compare=32),
    "main": dict(k=16, d_ea=32, ea_layers=2, ea_heads=4, d_ca=32, ca_layers=2, ca_heads=4, d_compare=64),
}


def config_for(spec: dict, size: str, **overrides) -> A2Config:
    return A2Config(spec["n_packages"], spec["n_members"], spec["n_chains"], spec["chain_len"],
                    **{**SIZE_PRESETS[size], **overrides})


# ---------------- KA ----------------
KA_PARAMS = ("o", "u", "pi", "W", "b")


def ka_init(cfg: A2Config, p: int, seed: int) -> dict:
    g = torch.Generator().manual_seed(seed * 100_003 + p)
    k, M = cfg.k, cfg.n_members
    return {"o": torch.randn(M - 1, k, generator=g) * 0.02, "u": torch.randn(k, generator=g) / math.sqrt(k),
            "pi": torch.ones(2), "W": torch.eye(k) + torch.randn(k, k, generator=g) * 0.01, "b": torch.zeros(k)}


def ka_own(o: torch.Tensor) -> torch.Tensor:
    """[M, k]：参考成员为 0。"""
    return torch.cat([torch.zeros(1, o.shape[1], dtype=o.dtype, device=o.device), o], dim=0)


def ka_product(unit: dict) -> torch.Tensor:
    """KA_p 的产品：本包全部成员在共同空间里的表示 [M, k]。"""
    return ka_own(unit["o"]) @ unit["W"] + unit["b"]


# ---------------- EA ----------------
class EAUnit(nn.Module):
    """事件链内注意力：对一条链（L 个事件），按一个查询关系选出事件，另有“这条链里没有”。"""

    def __init__(self, cfg: A2Config):
        super().__init__()
        self.bias = cfg.ea_identity_bias
        self.inp = nn.Linear(2, cfg.d_ea)
        self.pos = nn.Embedding(cfg.chain_len, cfg.d_ea)
        layer = nn.TransformerEncoderLayer(cfg.d_ea, cfg.ea_heads, 2 * cfg.d_ea, dropout=0.0, batch_first=True)
        self.enc = nn.TransformerEncoder(layer, cfg.ea_layers, enable_nested_tensor=False)
        self.ptr = nn.Linear(cfg.d_ea, 1)
        self.none = nn.Parameter(torch.zeros(1))

    def forward(self, rel: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        """rel、valid：[N, L] → 选择概率 [N, L+1]，最后一项是“没有”。"""
        h = self.enc(self.inp(torch.stack([rel, valid], dim=-1)) + self.pos.weight)
        s = self.ptr(h).squeeze(-1) + self.bias * rel
        s = s.masked_fill(valid == 0, -1e4)
        return torch.softmax(torch.cat([s, self.none.expand(len(s), 1)], dim=-1), dim=-1)


# ---------------- CA ----------------
class CAUnit(nn.Module):
    """事件链间注意力：先选链（A 所在、B 所在、当前有效的设定），最后在链间比较 A 和 B。"""

    def __init__(self, cfg: A2Config):
        super().__init__()
        self.bias = cfg.ca_identity_bias
        self.inp = nn.Linear(5, cfg.d_ca)
        self.pos = nn.Embedding(cfg.n_chains, cfg.d_ca)
        self.genre = nn.Embedding(cfg.n_genres, cfg.d_ca)
        layer = nn.TransformerEncoderLayer(cfg.d_ca, cfg.ca_heads, 2 * cfg.d_ca, dropout=0.0, batch_first=True)
        self.enc = nn.TransformerEncoder(layer, cfg.ca_layers, enable_nested_tensor=False)
        self.ptr = nn.Linear(cfg.d_ca, 3)
        self.none = nn.Parameter(torch.zeros(3))
        k = cfg.k
        self.compare = nn.Sequential(nn.Linear(3 * k + 1, cfg.d_compare), nn.GELU(),
                                     nn.Linear(cfg.d_compare, cfg.d_compare), nn.GELU(),
                                     nn.Linear(cfg.d_compare, 1))

    def select(self, b) -> torch.Tensor:
        """[B, 3, C+1]：第 0、1、2 行分别是 A 所在的链、B 所在的链、当前有效的设定；最后一项是“没有”。"""
        x = torch.stack([b.chain_say, b.chain_set, b.set_story, b.spk_x, b.spk_y], dim=-1)
        h = self.enc(self.inp(x) + self.pos.weight + self.genre(b.genre).unsqueeze(1))
        s = self.ptr(h).transpose(1, 2)
        ident = torch.stack([b.spk_x * b.chain_say, b.spk_y * b.chain_say, b.chain_set], dim=1)
        allowed = torch.stack([b.chain_say, b.chain_say, b.chain_set], dim=1)
        s = (s + self.bias * ident).masked_fill(allowed == 0, -1e4)
        none = self.none.view(1, 3, 1).expand(s.shape[0], 3, 1)
        return torch.softmax(torch.cat([s, none], dim=-1), dim=-1)

    def compare_logit(self, c_a: torch.Tensor, c_b: torch.Tensor, premise: torch.Tensor) -> torch.Tensor:
        return self.compare(torch.cat([c_a, c_b, c_a - c_b, premise.unsqueeze(-1)], dim=-1)).squeeze(-1)


def count_params(module_or_state) -> int:
    if isinstance(module_or_state, nn.Module):
        return sum(p.numel() for p in module_or_state.parameters())
    return sum(v.numel() for v in module_or_state.values())


# ---------------- 单元存取 ----------------
class UnitStore:
    """每个单元一个目录，每次写入都存成新版本文件，旧版本保留（v0.51：需要修改节点就新建承接版本，不原地改写）。
    current 记录每个单元现在用哪个版本；修复实验从同一份基线快照出发，各自往后写新版本，互不覆盖。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.current: dict[str, int] = {}
        self.latest: dict[str, int] = {}

    def _path(self, name: str, v: int) -> Path:
        return self.root / name / f"v{v:05d}.pt"

    def version(self, name: str) -> int:
        return self.current.get(name, 0)

    def read(self, name: str):
        v = self.version(name)
        return None if v == 0 else torch.load(self._path(name, v), weights_only=False, map_location="cpu")

    def write(self, name: str, state: dict) -> int:
        if name not in self.latest:                  # 换了进程续跑时，从磁盘上已有的最大版本号往后写，绝不覆盖
            self.latest[name] = max((int(p.stem[1:]) for p in (self.root / name).glob("v*.pt")), default=0)
        v = self.latest[name] + 1
        path = self._path(name, v)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(state, path)
        self.latest[name] = v
        self.current[name] = v
        return v

    def snapshot(self) -> dict:
        return dict(self.current)

    def restore(self, snap: dict) -> None:
        self.current = dict(snap)

    def describe(self) -> dict:
        return {"root": str(self.root), "current": dict(self.current)}
