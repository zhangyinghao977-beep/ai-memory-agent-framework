"""T8 正式运行。

python -B run_t8.py <输出目录> gate            门禁：查题、长向量、算余弦基线，冻结计划和源文件的 SHA256
python -B run_t8.py <输出目录> worker <i> <n>  跑第 i 份任务（共 n 份）；再跑一次就是续跑，已有回执的任务跳过

只用 CPU。默认每个工人 1 线程；亲和可选，不承诺硬件利用率上限。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

THREADS = int(os.environ.get("ABYSS_THREADS", "1"))
os.environ["OMP_NUM_THREADS"] = os.environ["MKL_NUM_THREADS"] = str(THREADS)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
PROJECT = HERE.parents[1] / "project"
sys.path.insert(0, str(PROJECT))

import psutil  # noqa: E402
import torch  # noqa: E402

from empirical_core.t5.task import T5Spec, build_lattice, build_task, rule_ref, signature  # noqa: E402
from empirical_core.t6.model import evaluate, n_params, train_one6  # noqa: E402
from empirical_core.t7.baseline import cosine_choice_two  # noqa: E402
from empirical_core.t8.experience import grown_lattice, separation  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sources() -> dict:
    files = [HERE / "PLAN.json", HERE / "run_t8.py", HERE / "report_t8.py", HERE / "REPRODUCTION.md",
             *[f for name in ("t5", "t6", "t7", "t8") for f in sorted((PROJECT / "empirical_core" / name).glob("*.py"))],
             PROJECT / "tests" / "test_t8.py"]
    return source_hashes(files)


def jobs(plan: dict) -> list:
    out = []
    for task in plan["tasks"]:
        for kind, conds in plan["arms"].items():
            for cond in conds:
                for seed in plan["seeds"]:
                    out.append({"task": task, "kind": kind, "cond": cond, "seed": seed})
    return out


def job_id(j: dict) -> str:
    return f"{j['task']}-{j['kind']}-{j['cond']}-s{j['seed']}"


def setup() -> None:
    configure_runtime(THREADS)


def vectors(task: str, data: dict, spec: T5Spec, plan: dict, cond: str) -> torch.Tensor:
    c = plan["conditions"][cond]
    return grown_lattice(task, data, spec, c["chains"], c["dilute"], plan["n_life"])


def gate(out: Path, plan: dict) -> int:
    setup()
    out.mkdir(parents=True, exist_ok=False)
    spec = T5Spec(**plan["spec"])
    train_range = range(spec.n_train_packages)
    new_range = range(spec.n_train_packages, spec.n_train_packages + spec.n_new_packages)
    problems, res = [], {}
    for task in plan["tasks"]:
        d = build_task(task, spec)
        raw = d["raw"]
        train_sig = {signature(q) for q in raw["train"]}
        overlap = sum(signature(q) in train_sig for k in ("dev", "test_iid", "test_new") for q in raw[k])
        wrong = sum(rule_ref(task, q, spec) != q["target"] for k in raw for q in raw[k])
        leak = {p for q in raw["train"] for p in q["pkg"]} & {p for q in raw["test_new"] for p in q["pkg"]}
        conds = {}
        for name in plan["conditions"]:
            vec = vectors(task, d, spec, plan, name)
            conds[name] = {"cosine": {k: cosine_choice_two(task, d[k], vec, spec) for k in ("dev", "test_iid", "test_new")},
                           "old": separation(vec, spec, train_range), "new": separation(vec, spec, new_range)}
        res[task] = {"conditions": conds, "overlap": overlap, "rule_wrong": wrong, "shared_new_packages": len(leak)}
        if overlap or wrong or leak:
            problems.append(f"{task}：重复 {overlap}，规则错 {wrong}，新包泄漏 {len(leak)}")
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
    vecs: dict = {}
    mine = jobs(plan)[i::n]
    for c, j in enumerate(mine):
        rec = out / "receipts" / f"{job_id(j)}.json"
        if rec.exists():
            continue
        if j["task"] not in cache:
            cache, vecs = {j["task"]: build_task(j["task"], spec)}, {}
        data = cache[j["task"]]
        if j["cond"] not in vecs:
            vecs[j["cond"]] = vectors(j["task"], data, spec, plan, j["cond"])
        lat = {"vec": vecs[j["cond"]], "bit": bit}
        t0, cpu0 = time.time(), psutil.Process().cpu_times()
        m, curve = train_one6(spec, lat, data, j["kind"], "full", j["seed"], steps=plan["steps"], batch=plan["batch"], lr=plan["lr"],
                              eval_every=plan["eval_every"])
        cpu1 = psutil.Process().cpu_times()
        torch.save({k: v for k, v in m.state_dict().items() if k != "vec"}, out / "models" / f"{job_id(j)}.pt")
        res = {**j, "params": n_params(m), "curve": curve, "seconds": time.time() - t0,
               "cpu_seconds": cpu1.user + cpu1.system - cpu0.user - cpu0.system,
               "test_iid": evaluate(m, data["test_iid"], bit), "test_new": evaluate(m, data["test_new"], bit)}
        tmp = rec.with_suffix(".tmp")
        tmp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, rec)
        print(f"{c + 1}/{len(mine)} {job_id(j)} {res['seconds']:.0f}s iid {100 * res['test_iid']['choice_two']:.1f} new {100 * res['test_new']['choice_two']:.1f}", flush=True)
    return 0


def main() -> int:
    args = runner_arguments("T8 reproduction runner", gate_trains=False)
    plan = load_plan(HERE / "PLAN.json")
    for name in plan.get("dependency_runs", {}):
        dependency_run(plan, name)
    if args.command == "gate":
        return gate(args.output, plan)
    return worker(args.output, plan, args.index, args.count)


if __name__ == "__main__":
    raise SystemExit(main())
