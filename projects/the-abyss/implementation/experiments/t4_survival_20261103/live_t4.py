"""T4 一个组、一个种子的存活运行：python -B live_t4.py <CONF.json> <输出目录>

同一个输出目录再次启动，就是重启：从快速登记恢复，接着活（重启测试就是这样做的）。
CONF.json 的字段：
- world：WorldSpec 的字段；model_size：A2 的大小档；arm、seed、days；
- life：LifeConf 的其余字段（pools、trigger、epochs……）；fsm：FSMParams 的字段；
- start：null（从头开始，所有单元版本 0）或 {"root": 起点单元目录, "snapshot": {单元: 版本}}；
- resources：device、threads、cpu_affinity、gpu_memory_fraction、gpu_duty；
- evaluate：每天结束时是否在探针上评测（只用于报告）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import fields
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import configure_runtime, root_path
sys.path.insert(0, str(HERE.parents[1] / "project"))


def main() -> int:
    conf_path, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    conf = json.loads(conf_path.read_text(encoding="utf-8"))
    res = conf["resources"]
    configure_runtime(threads=int(os.environ.get("ABYSS_THREADS", res.get("threads", 1))),
                      cpus=res.get("cpu_affinity"))
    import psutil
    import torch
    proc = psutil.Process()
    device = res.get("device", "cpu")
    if device == "cuda":
        torch.cuda.set_per_process_memory_fraction(res["gpu_memory_fraction"], 0)

    from empirical_core.t2.units import config_for
    from empirical_core.t4 import fsm as F
    from empirical_core.t4.life import Life, LifeConf, probe_eval
    from empirical_core.t4.world import WorldSpec, build_world

    ws = conf["world"]
    world = build_world(WorldSpec(**{**ws, "t3_overrides": tuple(tuple(x) for x in ws.get("t3_overrides", ()))}))
    cfg = config_for(world["spec"], conf["model_size"])
    known = {f.name for f in fields(LifeConf)}
    lc = LifeConf(arm=conf["arm"], seed=conf["seed"], fsm=F.FSMParams(**conf.get("fsm", {})),
                  **{k: v for k, v in conf.get("life", {}).items() if k in known})
    out.mkdir(parents=True, exist_ok=True)
    life = Life(out, world, cfg, lc, device=device, proc=proc, gpu_duty=res.get("gpu_duty") if device == "cuda" else None)
    st = conf.get("start")
    life.seed_units(root_path(st["root"], must_exist=True) if st else None, st["snapshot"] if st else None)
    t0 = time.time()
    days = life.live(conf["days"], evaluate=probe_eval if conf.get("evaluate") else None)
    result = {"arm": conf["arm"], "seed": conf["seed"], "days_run_now": [m["day"] for m in days],
              "seconds": time.time() - t0, "records": life.log.seq,
              "day_end": [r for r in life.log.of_kind("day_end")]}
    (out / "RESULT.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
