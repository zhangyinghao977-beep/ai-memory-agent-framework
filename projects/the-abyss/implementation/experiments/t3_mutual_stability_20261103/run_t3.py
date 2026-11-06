"""T3 正式运行的流水线：按冻结计划 PLAN.json 依次执行，中途不需要人看着。

用法：python -B run_t3.py <PLAN.json> <输出目录>

要回答的两个问题（图谱网站 2026-11-03 增补；名词解释仍是 v0.57）：
1. 筛子与材料：EA↔KA 双向修正（KA 也从 EA 的选择拿材料）和 T2 的单向做法比，能不能互相适应、稳不稳定、
   会不会来回摆、包内差异有没有被抹平。
2. 校验节奏：按“相互修正是否稳定”做统一校验，每 1 轮和每 3、4、5 轮
   校验一次，各花多少校验时间、晚几轮发现稳定、停下时成绩差多少。阈值待定，所以只报告一组候选值，不选定。

阶段：
- gate：出题、编码、门禁、间接包检查、简单基线；
- 每个种子：单向、双向各从头螺旋训练到硬上限；每轮结束做一次统一校验（只读、计时），
  另做只用于报告的评测（DEV、TEST、各层诊断、包内差异）；
- check、final-report。
其余规则同 T1、T2：每个阶段写收据；人手动再次启动时跳过已完成的阶段；出错就停、不重试；资源和时间有上限；报告由收据自动生成。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (RELEASE_ROOT, configure_runtime, dependency_run,
                              freeze_plan_metadata, load_plan, root_path, source_hashes)
PROJECT = HERE.parents[1] / "project"
sys.path.insert(0, str(PROJECT))
T2_RUNNER = HERE.parent / "t2_repair_20261102"
sys.path.insert(0, str(T2_RUNNER))

from run_t2 import Guard, StopRun, append_jsonl, sha256_file, wait_for_memory, write_json  # noqa: E402

ARMS = ("one_way", "two_way")


def stage_list(plan: dict) -> list[dict]:
    out = [{"id": "gate", "kind": "gate"}]
    for seed in plan["seeds"]:
        for arm in ARMS:
            out.append({"id": f"{arm}-s{seed}", "kind": "train", "arm": arm, "seed": seed})
        out.append({"id": f"report-s{seed}", "kind": "report"})
    out += [{"id": "check", "kind": "check"}, {"id": "final-report", "kind": "report"}]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a new synthetic reproduction experiment (includes training).")
    parser.add_argument("plan", help="PLAN.json relative to the release root")
    parser.add_argument("output", help="Fresh run directory relative to the release root")
    args = parser.parse_args()
    plan_path, out = root_path(args.plan, must_exist=True), root_path(args.output)
    plan = load_plan(plan_path)
    res = plan["resources"]
    runtime = configure_runtime(threads=int(os.environ.get("ABYSS_THREADS", res.get("threads", 1))),
                                cpus=res.get("cpu_affinity"))
    res.update(runtime)
    import psutil
    import torch
    proc = psutil.Process()
    use_gpu = res.get("device") == "cuda"

    from empirical_core.timing import environment
    import report_t3

    out.mkdir(parents=True, exist_ok=True)
    current, start = "start", time.time()
    guard = Guard(proc, start, res["time_cap_hours"] * 3600, int(res["max_rss_gib"] * 2 ** 30),
                  gpu_duty=res.get("gpu_duty") if use_gpu else None)
    try:
        stages = stage_list(plan)
        sources = sorted((PROJECT / "empirical_core").rglob("*.py")) + \
            [HERE / "run_t3.py", HERE / "report_t3.py", T2_RUNNER / "run_t2.py", T2_RUNNER / "report_t2.py"]
        frozen = {"plan_sha256": sha256_file(plan_path), **freeze_plan_metadata(plan_path),
                  "sources": source_hashes(sources),
                  "stages": [s["id"] for s in stages], "environment": environment(), "runtime": runtime, "pid": os.getpid(),
                  "started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "argv": sys.argv}
        if (out / "FROZEN.json").exists():             # 人手动续跑：计划与源码必须没变
            old = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))
            if old["plan_sha256"] != frozen["plan_sha256"] or old["sources"] != frozen["sources"] or old.get("runtime") != runtime:
                raise SystemExit("计划、源码或有效运行配置与首次启动时不同，拒绝续跑")
            append_jsonl(out / "log.jsonl", {"event": "resume", "time": frozen["started_at"], "pid": os.getpid()})
        else:
            write_json(out / "FROZEN.json", frozen)
        if use_gpu:                                    # Optional PyTorch allocator fraction; not an overall GPU limit.
            if not torch.cuda.is_available():
                raise StopRun("NO_GPU：计划要求用显卡，但这个 Python 里的 torch 用不了 CUDA")
            torch.cuda.set_per_process_memory_fraction(res["gpu_memory_fraction"], 0)
        ctx = {"plan": plan, "out": out, "guard": guard, "proc": proc, "cache": {}}
        for i, stage in enumerate(stages):
            current = stage["id"]
            receipt_path = out / "receipts" / f"{stage['id']}.json"
            if receipt_path.exists():
                continue
            wait_for_memory(res, guard)
            write_json(out / "STATUS.json", {"state": "RUNNING", "stage": stage["id"], "index": i, "of": len(stages),
                                             "time": time.strftime("%Y-%m-%d %H:%M:%S"), "pid": os.getpid()})
            append_jsonl(out / "log.jsonl", {"event": "stage_start", "stage": stage["id"], "time": time.time()})
            t0, slept0 = time.time(), guard.slept
            receipt = run_stage(stage, ctx)
            receipt.update({"stage": stage, "status": "done", "seconds": time.time() - t0,
                            "throttle_seconds": guard.slept - slept0, "peak_rss_bytes_seen": guard.peak,
                            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")})
            write_json(receipt_path, receipt)
            append_jsonl(out / "log.jsonl", {"event": "stage_done", "stage": stage["id"], "seconds": time.time() - t0})
        status, reason = "completed", None
    except StopRun as e:
        status, reason = "stopped", str(e)
    except Exception as e:                              # 出错就停，留证据，不重试
        status, reason = "failed", f"{type(e).__name__}: {e}"
    if status != "completed":
        append_jsonl(out / "failures.jsonl", {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "stage": current,
                                             "status": status, "reason": reason, "traceback": traceback.format_exc()})
    exit_rec = {"status": status, "reason": reason, "stage": current, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "hours": (time.time() - start) / 3600, "peak_rss_bytes_seen": guard.peak, "throttle_seconds": guard.slept}
    write_json(out / "PIPELINE_EXIT.json", exit_rec)
    write_json(out / "STATUS.json", {"state": status.upper(), "stage": current, "reason": reason,
                                     "time": exit_rec["finished_at"], "pid": os.getpid()})
    try:
        report_t3.write_report(out)
    except Exception:
        append_jsonl(out / "failures.jsonl", {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "stage": "final report",
                                             "status": "failed", "traceback": traceback.format_exc()})
    return 0 if status == "completed" else 1


# ---------------- 数据 ----------------
def load_data(ctx: dict) -> dict:
    """出题、编码、分层、探针。整次运行只做一次。"""
    if "data" in ctx["cache"]:
        return ctx["cache"]["data"]
    import torch
    from dataclasses import replace
    from empirical_core.t2.features import encode, take
    from empirical_core.t3 import baselines as bl
    from empirical_core.t3.task import PRESETS, build_t3
    plan = ctx["plan"]
    spec = replace(PRESETS[plan["task"]["preset"]], **plan["task"].get("overrides", {}))
    data = build_t3(spec)
    train, _ = encode(data, "train")
    evals = {s: encode(data, s) for s in ("dev", "test")}
    strata = {s: bl.strata(data, s) for s in ("dev", "test")}
    identity = hashlib.sha256(json.dumps(data["episodes"], sort_keys=True).encode()).hexdigest()
    ck = plan["check"]
    g = torch.Generator().manual_seed(ck["probe_seed"])
    probe_rows = torch.randperm(len(train.ids), generator=g)[:ck["probe_size"]].sort().values
    ctx["cache"]["data"] = {"data": data, "train": train, "evals": evals, "strata": strata, "identity": identity,
                            "probe": take(train, probe_rows), "probe_rows": probe_rows}
    return ctx["cache"]["data"]


def make_spiral(ctx: dict, seed: int, arm: str):
    from empirical_core.t2.units import UnitStore, config_for
    from empirical_core.t3.spiral import MutualSpiral
    from empirical_core.timing import SegmentTimer
    plan, d = ctx["plan"], load_data(ctx)
    tr = plan["training"]
    cfg = config_for(d["data"]["spec"], plan["model"]["size"], **plan["model"].get("overrides", {}))
    bills = ctx["out"] / "bills" / f"{ctx['stage_id']}.jsonl"
    if bills.exists():
        bills.unlink()                                 # 上一次未完成的尝试已登记在 failures.jsonl，这里重新开始
    return MutualSpiral(cfg, UnitStore(ctx["out"] / "work" / f"s{seed}" / arm), d["train"], two_way=(arm == "two_way"),
                        seed=seed, epochs_per_phase=tr["epochs_per_phase"], batch_size=tr["batch_size"], lr=tr["lr"],
                        budgets=tr["budgets"], clip=tr["clip"], device=plan["resources"]["device"], guard=ctx["guard"],
                        timer=SegmentTimer(), log=lambda rec: append_jsonl(bills, rec))


# ---------------- 阶段 ----------------
def run_stage(stage: dict, ctx: dict) -> dict:
    ctx["stage_id"] = stage["id"]
    kind = stage["kind"]
    if kind == "gate":
        return gate_stage(ctx)
    if kind == "train":
        return train_stage(stage, ctx)
    if kind == "check":
        return check_stage(ctx)
    import report_t3
    report_t3.write_report(ctx["out"])
    return {"report": "REPORT.zh.md"}


def gate_stage(ctx: dict) -> dict:
    from empirical_core.t3 import baselines as bl
    from run_t2 import tally_rule
    plan, d = ctx["plan"], load_data(ctx)
    data, g = d["data"], plan["gates"]
    gates, baselines = {}, {}
    rules = {"majority": bl.majority(data), "path_reasoner": bl.path_reasoner(data)}
    for s in ("dev", "test"):
        rep = bl.gate(data, s, min_main=g["min_main"], max_shortcut_accuracy=g["max_shortcut_accuracy"])
        st = d["strata"][s]
        ind_main = sum(1 for v in st.values() if v["gate"] == "new_conflict" and v["indirect"] != "none")
        gates[s] = {"passed": rep.passed and ind_main >= g["min_indirect_main"],
                    "audit_passed": rep.passed, "strata_counts": rep.details["strata_counts"],
                    "main_stratum_count": rep.details["main_stratum_count"],
                    "indirect_main_count": ind_main,
                    "worst_part_rule_accuracy_on_main": rep.details["worst_part_rule_accuracy_on_main"]}
        eps = [ep for ep in data["episodes"] if ep["split"] == s]
        for name, rule in rules.items():
            baselines.setdefault(name, {})[s] = tally_rule(eps, rule, st)
    train = d["train"]
    ind_exact = bl.indirect_exact_rows(train, data["indirect_packages"])
    counts = {"train": len(train.ids), **{s: len(d["evals"][s][0].ids) for s in ("dev", "test")}}
    receipt = {"spec": data["spec"], "indirect_packages": data["indirect_packages"], "data_identity": d["identity"],
               "counts": counts, "exact_train": int(train.exact.sum()),
               "train_needs_ea": int(sum(ep["hidden"]["needs_ea"] for ep in data["episodes"] if ep["split"] == "train")),
               "train_indirect": int(sum(bool(ep["hidden"]["indirect"]) for ep in data["episodes"] if ep["split"] == "train")),
               "indirect_exact_train": ind_exact, "probe_size": len(d["probe"].ids), "gates": gates,
               "baselines": baselines}
    if ind_exact != 0 or not all(v["passed"] for v in gates.values()):
        write_json(ctx["out"] / "receipts" / "gate.failed.json", receipt)
        raise StopRun(f"GATE_FAILED：间接包的精确材料 {ind_exact} 道；{json.dumps({k: v['passed'] for k, v in gates.items()})}")
    return receipt


def evaluate(sp, ctx: dict, split: str, with_strata: bool) -> dict:
    from empirical_core.t2.evaluate import layer_diagnostics, score
    d = load_data(ctx)
    b, dg = d["evals"][split]
    pred = sp.predict(b, dg, chunk=ctx["plan"]["training"]["predict_chunk"])
    return {"score": score(pred, b.labels, b.ids, d["strata"][split] if with_strata else None),
            "layers": layer_diagnostics(pred, b.labels, dg)}


def round_bill(bills: list, r: int) -> dict:
    sel = [b for b in bills if b["round"] == r]
    out = {"compute_seconds": sum(b["compute_seconds"] for b in sel), "seconds": sum(b["seconds"] for b in sel),
           "updates": sum(b["updates"] for b in sel)}
    for layer in ("KA", "EA", "CA", "SIEVE"):
        ls = [b for b in sel if b["layer"] == layer]
        out[layer] = {"compute_seconds": sum(b["compute_seconds"] for b in ls), "updates": sum(b["updates"] for b in ls),
                      "units": len({b["unit"] for b in ls})}
    out["KA"]["sieved"] = sum(b.get("sieved", 0) for b in sel if b["layer"] == "KA")
    return out


def train_stage(stage: dict, ctx: dict) -> dict:
    """从头螺旋训练到硬上限；第 0 轮（训练前）和每轮结束各做一次统一校验，另做只用于报告的评测。"""
    import torch
    from empirical_core.t3.stability import Checker, ka_differences
    plan, d = ctx["plan"], load_data(ctx)
    seed, arm = stage["seed"], stage["arm"]
    tr = plan["training"]
    if plan["resources"]["device"] == "cuda":
        torch.cuda.reset_peak_memory_stats()
    slept0 = ctx["guard"].slept
    sp = make_spiral(ctx, seed, arm)
    checker = Checker(sp, d["probe"], chunk=tr["predict_chunk"])
    rounds = []

    def after(r: int) -> None:
        rec = {"round": r, "check": checker(r), "versions": sp.store.snapshot()}
        t0, s0 = time.perf_counter(), ctx["guard"].slept
        rec["test"] = evaluate(sp, ctx, "test", True)
        rec["dev"] = evaluate(sp, ctx, "dev", False)
        rec["ka_diff"] = ka_differences(sp, d["data"]["hidden_values"], d["data"]["indirect_packages"])
        rec["report_eval_seconds"] = (time.perf_counter() - t0) - (ctx["guard"].slept - s0)
        rec["train"] = round_bill(sp.bills, r) if r > 0 else None
        rounds.append(rec)
        append_jsonl(ctx["out"] / "progress.jsonl", {"stage": stage["id"], "round": r,
                                                     "test": rec["test"]["score"]["overall"],
                                                     "lag1": rec["check"]["lag"].get(1), "time": time.time()})

    t0 = time.time()
    after(0)
    sp.fit_rounds(stage["id"], torch.arange(len(d["train"].ids)), tr["rounds_cap"], tr["arrival_over"],
                  tr["arrival_seed"], after_round=after)
    rec = {"seed": seed, "arm": arm, "rounds": rounds, "train_seconds": time.time() - t0,
           "snapshot": sp.store.snapshot(), "losses": loss_summary(sp), "data_identity": d["identity"],
           "params": unit_params(sp)}
    if plan["resources"]["device"] == "cuda":
        rec["gpu"] = {"max_memory_allocated_bytes": torch.cuda.max_memory_allocated(),
                      "throttle_sleep_seconds": ctx["guard"].slept - slept0}
        torch.cuda.empty_cache()
    return rec


def unit_params(sp) -> dict:
    from empirical_core.t2.units import CAUnit, EAUnit, count_params
    ka = sum(t.numel() for t in sp._ka_state(0)["params"].values())
    return {"ka_per_package": ka, "ka_total": ka * sp.cfg.n_packages, "ea": count_params(EAUnit(sp.cfg)),
            "ca": count_params(CAUnit(sp.cfg))}


def loss_summary(sp) -> dict:
    def m(xs):
        return sum(xs) / len(xs) if xs else None
    return {k: {"first": m(v[:20]), "last": m(v[-20:]), "n": len(v)} for k, v in sp.losses.items()}


def check_stage(ctx: dict) -> dict:
    """程序检查（不是成绩门槛）：每个阶段都有收据、轮数齐全、题数对得上；
    契约：单向时间接包的 KA 从来没写过（没有材料）；同一种子两组用同一份数据。"""
    plan, out = ctx["plan"], ctx["out"]
    d = load_data(ctx)
    problems, warnings = [], []
    cap = plan["training"]["rounds_cap"]
    for st in stage_list(plan):
        if st["kind"] != "train":
            continue
        path = out / "receipts" / f"{st['id']}.json"
        if not path.exists():
            problems.append(f"{st['id']} 没有收据")
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        if [r["round"] for r in rec["rounds"]] != list(range(cap + 1)):
            problems.append(f"{st['id']} 的轮数不全")
        if rec["data_identity"] != d["identity"]:
            problems.append(f"{st['id']} 的数据身份不对")
        for r in rec["rounds"]:
            if r["test"]["score"]["overall"]["n"] != len(d["evals"]["test"][0].ids):
                problems.append(f"{st['id']} 第 {r['round']} 轮 TEST 题数不对")
                break
        if st["arm"] == "one_way":
            written = [p for p in d["data"]["indirect_packages"] if rec["snapshot"].get(f"ka{p:04d}", 0) != 0]
            if written:
                problems.append(f"{st['id']}：单向时间接包 {written} 的 KA 被写过（契约不满足）")
        for layer, ls in rec["losses"].items():
            if ls["first"] is not None and ls["last"] is not None and ls["last"] >= ls["first"]:
                warnings.append(f"{st['id']}：{layer} 损失没有下降（{ls['first']:.4f} → {ls['last']:.4f}），照实报告")
    if problems:
        raise StopRun(f"PROGRAM_CHECK_FAILED：{problems}")
    return {"problems": problems, "warnings": warnings}


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
