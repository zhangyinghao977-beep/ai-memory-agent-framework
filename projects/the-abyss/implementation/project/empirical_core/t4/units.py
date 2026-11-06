"""T4 的单元存储：在 T2 的 UnitStore 上加原子写入、写入登记和“采用”。

- 原子写入：先写临时文件，再改名。断电时最多留下一个 .tmp，不会留下写了一半的版本文件。
- 每次写入登记为中间产物（unit_write）。对外使用（回答问题）的是“采用”的版本：
  一轮或一级修复做完、通过检查，才登记 adopt；中途被打断或不采用，就回到上次采用的版本。
  这样“新版本承接、旧版本保留”，回答问题时也不会用到半轮的混合版本。
- 重启后，按快速登记里最后一次 adopt 恢复；磁盘上有、但从没被采用的版本记作“未采用的中间产物”，不删除。
"""
from __future__ import annotations

import os
from pathlib import Path

import torch

from ..t2.units import UnitStore

from .records import QuickLog, crashpoint


class LoggedUnitStore(UnitStore):
    def __init__(self, root: Path, log: QuickLog):
        super().__init__(root)
        self.log = log
        adopts = log.of_kind("adopt")
        if adopts:
            self.current = {k: int(v) for k, v in adopts[-1]["snapshot"].items()}
        self.adopted = dict(self.current)

    def write(self, name: str, state: dict) -> int:
        if name not in self.latest:                  # 从磁盘上已有的最大版本号往后写（含未采用的），绝不覆盖
            self.latest[name] = max((int(p.stem[1:]) for p in (self.root / name).glob("v*.pt")), default=0)
        v = self.latest[name] + 1
        path = self._path(name, v)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".pt.{os.getpid()}.tmp")          # 每个进程自己的临时名：断电留下的不会被下次覆盖
        torch.save(state, tmp)
        crashpoint("unit_tmp_written")
        os.replace(tmp, path)
        self.latest[name] = v
        self.current[name] = v
        self.log.append("unit_write", unit=name, version=v)
        return v

    def adopt(self, reason: str, **info) -> dict:
        self.adopted = dict(self.current)
        return self.log.append("adopt", snapshot=self.adopted, reason=reason, **info)

    def rollback(self) -> None:
        self.current = dict(self.adopted)

    def leftovers(self) -> dict:
        """没写完的临时文件、从没被采用过的版本（都只登记，不删除）。"""
        ever = {(u, int(v)) for r in self.log.of_kind("adopt") for u, v in r["snapshot"].items()}
        tmp = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*.tmp"))
        unadopted = sorted(f"{p.parent.name}/{p.name}" for p in self.root.rglob("v*.pt")
                           if (p.parent.name, int(p.stem[1:])) not in ever)
        return {"tmp_files": tmp, "unadopted_versions": unadopted}

    def bytes_on_disk(self) -> int:
        return sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())

    def superseded(self) -> list[str]:
        """遗忘的候选（本阶段只列出，不执行删除）：
        已经有更新的版本被采用、当前采用的快照不再引用的旧版本。"""
        cur = {(u, v) for u, v in self.adopted.items()}
        out = []
        for p in sorted(self.root.rglob("v*.pt")):
            u, v = p.parent.name, int(p.stem[1:])
            if (u, v) not in cur and v < self.adopted.get(u, 0):
                out.append(f"{u}/{p.name}")
        return out
