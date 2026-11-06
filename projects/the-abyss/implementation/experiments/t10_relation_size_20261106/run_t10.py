"""T10 正式运行。

python -B run_t10.py <输出目录> gate            门禁：查规则表，实跑 3000 步核对乘 1 和 T9 逐位相同，冻结源文件的 SHA256
python -B run_t10.py <输出目录> worker <i> <n>  跑第 i 份任务（共 n 份）；再跑一次就是续跑，已有回执的任务跳过

只用 CPU。默认每个工人 1 线程；亲和可选，不承诺硬件利用率上限。这些都来自 run_t9.py。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
T9 = HERE.parent / "t9_grown_rule_20261106"
sys.path.insert(0, str(T9))

import psutil  # noqa: E402
import torch  # noqa: E402

from run_t9 import PROJECT, T5Spec, build_lattice, build_task, setup, sha, shifted, sweep, table, vectors, world  # noqa: E402
from empirical_core.t6.model import evaluate, n_params  # noqa: E402
from empirical_core.t10.model import part_sizes, train_one10  # noqa: E402


def sources() -> dict:
    files = [HERE / "PLAN.json", HERE / "run_t10.py", HERE / "report_t10.py", HERE / "REPRODUCTION.md", T9 / "run_t9.py",
             *[f for name in ("t5", "t6", "t8", "t9", "t10") for f in sorted((PROJECT / "empirical_core" / name).glob("*.py"))],
             PROJECT / "tests" / "test_t10.py"]
    return source_hashes(files)


def jobs(plan: dict) -> list:
    return [{"task": t, "kind": k, "arm": a, "seed": s} for a, c in plan["arms"].items() for t in c["tasks"] for k in plan["kinds"] for s in plan["seeds"]]


def job_id(j: dict) -> str:
    return f"{j['task']}-{j['kind']}-{j['arm']}-s{j['seed']}"


def gate(out: Path, plan: dict) -> int:
    setup()
    out.mkdir(parents=True, exist_ok=False)
    spec = T5Spec(**plan["spec"])
    bit = build_lattice(spec)["bit"]
    R = spec.n_relations
    truth = torch.zeros(R, R, dtype=torch.bool)
    truth[torch.arange(R - 1), torch.arange(R - 1)] = True
    problems, res = [], {}
    for task in plan["tasks"]:
        d = build_task(task, spec)
        vec = vectors(task, d, spec, plan)
        t = table("all", d, spec, plan)
        res[task] = {"wrong_cells": int((t != truth).sum()), "anchor_events": int((d["train"]["rel"] == R - 1).sum())}
        if res[task]["wrong_cells"]:
            problems.append(f"{task}：规则表错 {res[task]['wrong_cells']} 格")
        for kind in plan["kinds"]:
            _, curve = train_one10(spec, vec, t, bit, d, kind, 0, 1.0, True, steps=plan["eval_every"], batch=plan["batch"], lr=plan["lr"], eval_every=plan["eval_every"])
            old = json.loads((dependency_run(plan, "t9") / "receipts" / f"{task}-{kind}-all-s0.json").read_text(encoding="utf-8"))
            same = curve[0] == old["curve"][0]
            res[task][f"same_as_t9_{kind}"] = same
            if not same:
                problems.append(f"{task} {kind}：乘 1 和 T9 不同")
    (out / "receipts").mkdir()
    (out / "models").mkdir()
    (out / "gate.json").write_text(json.dumps({"tasks": res, "problems": problems}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "FROZEN.json").write_text(json.dumps({**freeze_plan_metadata(HERE / "PLAN.json"), "sources": sources(), "jobs": len(jobs(plan)), "time": time.strftime("%Y-%m-%d %H:%M:%S")},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    print("gate problems:", problems, flush=True)
    return 1 if problems else 0


def worker(out: Path, plan: dict, i: int, n: int) -> int:
    require_successful_gate(out)
    setup()
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))
    if frozen["sources"] != sources():
        print("sources differ from FROZEN.json, not running", flush=True)
        return 2
    spec = T5Spec(**plan["spec"])
    bit = build_lattice(spec)["bit"]
    cache: dict = {}
    mine = jobs(plan)[i::n]
    for c, j in enumerate(mine):
        rec = out / "receipts" / f"{job_id(j)}.json"
        if rec.exists():
            continue
        if j["task"] not in cache:
            data = build_task(j["task"], spec)
            cache[j["task"]] = {"data": data, "vec": vectors(j["task"], data, spec, plan), "world": world(j["task"], data, spec, plan)}
        ctx = cache[j["task"]]
        data, arm = ctx["data"], plan["arms"][j["arm"]]
        t0, cpu0 = time.time(), psutil.Process().cpu_times()
        m, curve = train_one10(spec, ctx["vec"], table("all", data, spec, plan), bit, data, j["kind"], j["seed"], arm["scale"], arm["learn"],
                               steps=plan["steps"], batch=plan["batch"], lr=plan["lr"], eval_every=plan["eval_every"])
        extra = {"sweep": sweep(m, data, spec, plan, bit), "shift": shifted(m, data, ctx["world"], spec, plan, bit),
                 "sizes_end": part_sizes(m, {k: v[:512] for k, v in data["train"].items()}, spec.k)}
        cpu1 = psutil.Process().cpu_times()
        torch.save({k: v for k, v in m.state_dict().items() if k != "vec"}, out / "models" / f"{job_id(j)}.pt")
        res = {**j, "params": n_params(m), "curve": curve, "seconds": time.time() - t0, "cpu_seconds": cpu1.user + cpu1.system - cpu0.user - cpu0.system,
               "test_iid": evaluate(m, data["test_iid"], bit), "test_new": evaluate(m, data["test_new"], bit), **extra}
        tmp = rec.with_suffix(".tmp")
        tmp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, rec)
        print(f"{c + 1}/{len(mine)} {job_id(j)} {res['seconds']:.0f}s iid {100 * res['test_iid']['choice_two']:.1f} new {100 * res['test_new']['choice_two']:.1f}", flush=True)
    return 0


def main() -> int:
    args = runner_arguments("T10 reproduction runner", gate_trains=True)
    plan = load_plan(HERE / "PLAN.json")
    for name in plan.get("dependency_runs", {}):
        dependency_run(plan, name)
    if args.command == "gate":
        return gate(args.output, plan)
    return worker(args.output, plan, args.index, args.count)


if __name__ == "__main__":
    raise SystemExit(main())
