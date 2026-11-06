"""T9 正式运行。

python -B run_t9.py <输出目录> gate            门禁：查题、长规则表、算余弦基线，冻结计划和源文件的 SHA256
python -B run_t9.py <输出目录> worker <i> <n>  跑第 i 份任务（共 n 份）；再跑一次就是续跑，已有回执的任务跳过

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

from empirical_core.t5.task import T5Spec, _pack, build_lattice, build_task, rule_ref, signature  # noqa: E402
from empirical_core.t6.model import evaluate, n_params, train_one6  # noqa: E402
from empirical_core.t8.experience import grown_lattice  # noqa: E402
from empirical_core.t9.model import train_one9  # noqa: E402
from empirical_core.t9.rule import cosine_choice_two9, legal_table, shift_map, shuffle_relations, window_table  # noqa: E402
from empirical_core.t9.world import later_questions  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sources() -> dict:
    files = [HERE / "PLAN.json", HERE / "run_t9.py", HERE / "report_t9.py", HERE / "REPRODUCTION.md",
             *[f for name in ("t5", "t6", "t7", "t8", "t9") for f in sorted((PROJECT / "empirical_core" / name).glob("*.py"))],
             PROJECT / "tests" / "test_t9.py"]
    return source_hashes(files)


def jobs(plan: dict) -> list:
    out = [{"task": "mutual", "kind": "attn", "cond": "m4", "seed": s} for s in plan["seeds"]]
    for kind in ("vec", "pair", "attn", "sim"):
        for task in plan["tasks"]:
            for cond in plan["arms"][kind]:
                for seed in plan["seeds"]:
                    out.append({"task": task, "kind": kind, "cond": cond, "seed": seed})
    return out


def job_id(j: dict) -> str:
    return f"{j['task']}-{j['kind']}-{j['cond']}-s{j['seed']}"


def setup() -> None:
    configure_runtime(THREADS)


def vectors(task: str, data: dict, spec: T5Spec, plan: dict) -> torch.Tensor:
    v = plan["vectors"]
    return grown_lattice(task, data, spec, v["chains"], v["dilute"], v["n_life"])


def table(cond: str, data: dict, spec: T5Spec, plan: dict) -> torch.Tensor:
    c = plan["tables"][cond]
    rel, query = data["train"]["rel"][:c["chains"]], data["train"]["query"][:c["chains"]]
    if c["shuffle"]:
        rel = shuffle_relations(rel, plan["shuffle_seed"])
    return legal_table(rel, query, spec.n_relations)


def world(task: str, data: dict, spec: T5Spec, plan: dict) -> dict:
    """新世界：普通关系换了对应。返回新世界的事件链和新世界的测试题。"""
    s = plan["shift"]
    p = shift_map(spec.n_relations - 1, spec.n_relations, s["seed"])
    avoid = {signature(q) for q in data["raw"]["test_iid"]}
    later = _pack(later_questions(task, spec, s["window"] * s["streams"], avoid))
    return {"map": p, "rel": p[later["rel"]], "query": later["query"], "test": {**data["test_iid"], "rel": p[data["test_iid"]["rel"]]}}


def row(m, test: dict, bit: torch.Tensor, keep: torch.Tensor) -> dict:
    ev = evaluate(m, test, bit)
    return {"choice_two": ev["choice_two"], "choice_one": ev["choice_one"], "cells": int(m.legal.sum()), "changed_cells": int((m.legal != keep).sum())}


def sweep(m, data: dict, spec: T5Spec, plan: dict, bit: torch.Tensor) -> dict:
    keep, tr, out = m.legal, data["train"], {}
    for n in plan["sweep"]["chains"]:
        rows = []
        for w in range(plan["sweep"]["windows"]):
            s = slice(w * n, (w + 1) * n)
            m.legal = legal_table(tr["rel"][s], tr["query"][s], spec.n_relations)
            rows.append(row(m, data["test_iid"], bit, keep))
        out[str(n)] = rows
    m.legal = keep
    return out


def shifted(m, data: dict, w: dict, spec: T5Spec, plan: dict, bit: torch.Tensor) -> dict:
    keep, tr, sh, out = m.legal, data["train"], plan["shift"], {}
    for n in sh["new_chains"]:
        rows = []
        for i in range(sh["streams"]):
            s = slice(i * sh["window"], (i + 1) * sh["window"])
            m.legal = window_table((tr["rel"][s], tr["query"][s]), (w["rel"][s], w["query"][s]), n, sh["window"], spec.n_relations)
            rows.append(row(m, w["test"], bit, keep))
        out[str(n)] = rows
    m.legal = keep
    return out


def gate(out: Path, plan: dict) -> int:
    setup()
    out.mkdir(parents=True, exist_ok=False)
    spec = T5Spec(**plan["spec"])
    R = spec.n_relations
    truth = torch.zeros(R, R, dtype=torch.bool)
    truth[torch.arange(R - 1), torch.arange(R - 1)] = True
    problems, res = [], {}
    for task in plan["tasks"]:
        d = build_task(task, spec)
        raw = d["raw"]
        train_sig = {signature(q) for q in raw["train"]}
        overlap = sum(signature(q) in train_sig for k in ("dev", "test_iid", "test_new") for q in raw[k])
        wrong = sum(rule_ref(task, q, spec) != q["target"] for k in raw for q in raw[k])
        leak = {p for q in raw["train"] for p in q["pkg"]} & {p for q in raw["test_new"] for p in q["pkg"]}
        vec = vectors(task, d, spec, plan)
        tabs = {}
        for name in plan["tables"]:
            t = table(name, d, spec, plan)
            tabs[name] = {"wrong_cells": int((t != truth).sum()), "cosine": {k: cosine_choice_two9(d[k], vec, t) for k in ("dev", "test_iid", "test_new")}}
        w = world(task, d, spec, plan)
        ok = bool((w["test"]["rel"] != d["test_iid"]["rel"]).any()) and int((w["map"][:R - 1] == torch.arange(R - 1)).sum()) == 0
        res[task] = {"tables": tabs, "overlap": overlap, "rule_wrong": wrong, "shared_new_packages": len(leak), "shift": w["map"].tolist()}
        if overlap or wrong or leak or tabs["all"]["wrong_cells"] or not ok:
            problems.append(f"{task}：重复 {overlap}，规则错 {wrong}，新包泄漏 {len(leak)}，规则表错 {tabs['all']['wrong_cells']}")
    (out / "receipts").mkdir()
    (out / "models").mkdir()
    (out / "gate.json").write_text(json.dumps({"tasks": res, "problems": problems}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "FROZEN.json").write_text(json.dumps({**freeze_plan_metadata(HERE / "PLAN.json"), "sources": sources(), "jobs": len(jobs(plan)), "time": time.strftime("%Y-%m-%d %H:%M:%S")},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    print("gate problems:", problems, flush=True)
    return 1 if problems else 0


def run_job(j: dict, ctx: dict, spec: T5Spec, plan: dict, bit: torch.Tensor) -> tuple:
    data, vec, w = ctx["data"], ctx["vec"], ctx["world"]
    common = {"batch": plan["batch"], "lr": plan["lr"], "eval_every": plan["eval_every"]}
    extra = {}
    if j["cond"] == "m4":
        m, curve = train_one6(spec, {"vec": vec, "bit": bit}, data, "attn", "full", j["seed"], steps=plan["m4_steps"], **common)
        old = json.loads((dependency_run(plan, "t8") / "receipts" / f"mutual-attn-full-s{j['seed']}.json").read_text(encoding="utf-8"))
        extra["first_part_same_as_t8"] = curve[:len(old["curve"])] == old["curve"]
    elif j["kind"] == "vec":
        m, curve = train_one6(spec, {"vec": vec, "bit": bit}, data, "attn", "vec", j["seed"], steps=plan["steps"], **common)
        extra["test_shift"] = evaluate(m, w["test"], bit)
    else:
        m, curve = train_one9(spec, vec, table(j["cond"], data, spec, plan), bit, data, j["kind"], j["seed"], steps=plan["steps"], **common)
        if j["cond"] == "all":
            extra["sweep"] = sweep(m, data, spec, plan, bit)
            extra["shift"] = shifted(m, data, w, spec, plan, bit)
        if j["kind"] == "sim":
            extra["weights"] = {k: v.detach().tolist() for k, v in m.named_parameters()}
    return m, curve, extra


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
        t0, cpu0 = time.time(), psutil.Process().cpu_times()
        m, curve, extra = run_job(j, ctx, spec, plan, bit)
        cpu1 = psutil.Process().cpu_times()
        torch.save({k: v for k, v in m.state_dict().items() if k != "vec"}, out / "models" / f"{job_id(j)}.pt")
        res = {**j, "params": n_params(m), "curve": curve, "seconds": time.time() - t0,
               "cpu_seconds": cpu1.user + cpu1.system - cpu0.user - cpu0.system,
               "test_iid": evaluate(m, ctx["data"]["test_iid"], bit), "test_new": evaluate(m, ctx["data"]["test_new"], bit), **extra}
        tmp = rec.with_suffix(".tmp")
        tmp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, rec)
        print(f"{c + 1}/{len(mine)} {job_id(j)} {res['seconds']:.0f}s iid {100 * res['test_iid']['choice_two']:.1f} new {100 * res['test_new']['choice_two']:.1f}", flush=True)
    return 0


def main() -> int:
    args = runner_arguments("T9 reproduction runner", gate_trains=False)
    plan = load_plan(HERE / "PLAN.json")
    for name in plan.get("dependency_runs", {}):
        dependency_run(plan, name)
    if args.command == "gate":
        return gate(args.output, plan)
    return worker(args.output, plan, args.index, args.count)


if __name__ == "__main__":
    raise SystemExit(main())
