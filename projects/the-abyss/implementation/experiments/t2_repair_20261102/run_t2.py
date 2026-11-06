"""T2 正式运行的流水线：按冻结计划 PLAN.json 依次执行，中途不需要人看着。

用法：python -B run_t2.py <PLAN.json> <输出目录>

要回答的两个问题：
1. 局部修复（名词解释 v0.55 第 2 节）：条件变更后，只修和变更有关的单元，够不够用、花多少；和全部重修、从头重训比。
2. 回修深度（图谱 0.45 第 09 图“回修是否止于 EA”待验证）：变更出在 KA、EA、CA 不同层时，只修哪几层就够，
   修了不相干的层会怎样。
模型里有 KA、EA、CA 三层（empirical_core/t2/units.py）。

阶段：
- gate：出题、编码、各条件的门禁和简单基线；
- 每个种子：
  - base：从头螺旋训练（base 条件），在全部条件上评测（＝不修复）；
  - 每种变更（C1 遗漏的包、C2 链内改口、C3 新体裁）：
    - 固定写范围的修复：KA_local、CA、EA、CA＋EA、全部；
    - 逐级加深；
    - 从头重训（base＋新条件，三层都从头学）；
- check、final-report。
其余规则同 T1：
- 每个阶段写收据；人手动再次启动时跳过已完成的阶段；
- 出错就停、不重试；资源和时间有上限；
- 报告由收据自动生成。
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

CONDITIONS = ("base", "C1", "C2", "C3")
CHANGES = ("C1", "C2", "C3")


class StopRun(RuntimeError):
    """按计划的停止条件停下（时间、内存、资源一直不够、门禁或程序检查未通过）。"""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def stage_list(plan: dict) -> list[dict]:
    out = [{"id": "gate", "kind": "gate"}]
    for seed in plan["seeds"]:
        out.append({"id": f"base-s{seed}", "kind": "base", "seed": seed})
        for ch in CHANGES:
            for arm in plan["arms"]:
                out.append({"id": f"{ch}-{arm}-s{seed}", "kind": "arm", "change": ch, "arm": arm, "seed": seed})
            out.append({"id": f"{ch}-escalate-s{seed}", "kind": "escalate", "change": ch, "seed": seed})
            out.append({"id": f"{ch}-retrain-s{seed}", "kind": "retrain", "change": ch, "seed": seed})
        out.append({"id": f"report-s{seed}", "kind": "report"})
    out += [{"id": "check", "kind": "check"}, {"id": "final-report", "kind": "report"}]
    return out


class Guard:
    """训练循环每一步都会调用：总时间、进程内存超过上限就停（内存每 30 秒查一次）。
    GPU duty, when configured, inserts cooperative pauses; it does not guarantee device utilization.
    Memory and elapsed-time checks remain active."""

    def __init__(self, proc, start: float, cap_s: float, max_rss: int, gpu_duty: float | None = None):
        self.proc, self.start, self.cap_s, self.max_rss = proc, start, cap_s, max_rss
        self.last, self.peak = 0.0, 0
        self.gpu_duty = gpu_duty
        self.mark = time.perf_counter()
        self.slept = 0.0

    def __call__(self) -> None:
        if self.gpu_duty:
            import torch
            torch.cuda.synchronize()
            busy = time.perf_counter() - self.mark
            pause = busy * (1 / self.gpu_duty - 1)
            time.sleep(pause)
            self.slept += pause
            self.mark = time.perf_counter()
        now = time.time()
        if now - self.start > self.cap_s:
            raise StopRun(f"TIME_CAP：总时间超过 {self.cap_s / 3600:.1f} 小时")
        if now - self.last > 30:
            self.last = now
            rss = self.proc.memory_info().rss
            self.peak = max(self.peak, rss)
            if rss > self.max_rss:
                raise StopRun(f"RSS_LIMIT：进程内存 {rss} 字节超过上限 {self.max_rss}")


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
    import report_t2

    out.mkdir(parents=True, exist_ok=True)
    current, start = "start", time.time()
    guard = Guard(proc, start, res["time_cap_hours"] * 3600, int(res["max_rss_gib"] * 2 ** 30),
                  gpu_duty=res.get("gpu_duty") if use_gpu else None)
    try:
        stages = stage_list(plan)
        sources = sorted((PROJECT / "empirical_core").rglob("*.py")) + [HERE / "run_t2.py", HERE / "report_t2.py"]
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
        report_t2.write_report(out)
    except Exception:
        append_jsonl(out / "failures.jsonl", {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "stage": "final report",
                                             "status": "failed", "traceback": traceback.format_exc()})
    return 0 if status == "completed" else 1


def wait_for_memory(res: dict, guard: Guard) -> None:
    import psutil
    need = res["min_free_physical_gib"] * 2 ** 30
    waited = 0
    while psutil.virtual_memory().available < need:
        if waited >= res["memory_wait_minutes"] * 60:
            raise StopRun(f"RESOURCE_PENDING：空闲物理内存连续 {waited // 60} 分钟低于 {res['min_free_physical_gib']} GiB")
        time.sleep(60)
        waited += 60
        guard()


# ---------------- 数据 ----------------
def load_data(ctx: dict) -> dict:
    """出题、编码（TRAIN 拼成一份，各条件一段下标）、分层、路径推理。整次运行只做一次。"""
    if "data" in ctx["cache"]:
        return ctx["cache"]["data"]
    import torch
    from dataclasses import replace
    from empirical_core.t2 import baselines as bl
    from empirical_core.t2.features import concat, encode, take
    from empirical_core.t2.task import PRESETS, build_t2
    plan = ctx["plan"]
    spec = replace(PRESETS[plan["task"]["preset"]], **plan["task"].get("overrides", {}))
    data = build_t2(spec)
    parts = {c: encode(data, "train", (c,)) for c in CONDITIONS}
    train = concat(*(parts[c][0] for c in CONDITIONS))
    offs, o = {}, 0
    for c in CONDITIONS:
        offs[c] = torch.arange(o, o + len(parts[c][0].ids))
        o += len(parts[c][0].ids)
    evals = {(c, s): encode(data, s, (c,)) for c in CONDITIONS for s in ("dev", "test")}
    train_conds = {"base": ("base",), **{c: ("base", c) for c in CHANGES}}
    strata = {(c, s): bl.strata(data, s, (c,), train_conds[c]) for c in CONDITIONS for s in ("dev", "test")}
    identity = hashlib.sha256(json.dumps(data["episodes"], sort_keys=True).encode()).hexdigest()
    n_curve = min(plan["training"]["curve_subset"], len(evals[("base", "dev")][0].ids))
    curve = take(evals[("base", "dev")][0], torch.arange(n_curve))
    ctx["cache"]["data"] = {"data": data, "train": train, "offs": offs, "evals": evals, "strata": strata,
                            "train_conds": train_conds, "identity": identity, "curve": curve}
    return ctx["cache"]["data"]


def make_spiral(ctx: dict, seed: int, store_dir: Path):
    from empirical_core.t2.spiral import ChainSpiral
    from empirical_core.t2.units import UnitStore, config_for
    from empirical_core.timing import SegmentTimer
    plan, d = ctx["plan"], load_data(ctx)
    tr = plan["training"]
    cfg = config_for(d["data"]["spec"], plan["model"]["size"], **plan["model"].get("overrides", {}))
    bills = ctx["out"] / "bills" / f"{ctx['stage_id']}.jsonl"
    if bills.exists():
        bills.unlink()                                 # 上一次未完成的尝试已登记在 failures.jsonl，这里重新开始
    return ChainSpiral(cfg, UnitStore(store_dir), d["train"], seed=seed, epochs_per_phase=tr["epochs_per_phase"],
                       batch_size=tr["batch_size"], lr=tr["lr"], budgets=tr["budgets"], clip=tr["clip"],
                       device=plan["resources"]["device"], guard=ctx["guard"], timer=SegmentTimer(),
                       log=lambda rec: append_jsonl(bills, rec))


# ---------------- 阶段 ----------------
def run_stage(stage: dict, ctx: dict) -> dict:
    ctx["stage_id"] = stage["id"]
    kind = stage["kind"]
    if kind == "gate":
        return gate_stage(ctx)
    if kind == "base":
        return base_stage(stage, ctx)
    if kind in ("arm", "escalate"):
        return repair_stage(stage, ctx)
    if kind == "retrain":
        return retrain_stage(stage, ctx)
    if kind == "check":
        return check_stage(ctx)
    import report_t2
    report_t2.write_report(ctx["out"])
    return {"report": "REPORT.zh.md"}


def gate_stage(ctx: dict) -> dict:
    from empirical_core.t2 import baselines as bl
    plan, d = ctx["plan"], load_data(ctx)
    data, g = d["data"], plan["gates"]
    gates, baselines = {}, {}
    for c in CONDITIONS:
        rules = {"majority": bl.majority(data, d["train_conds"][c]), "path_reasoner": bl.path_reasoner(data, d["train_conds"][c])}
        for s in ("dev", "test"):
            rep = bl.gate(data, s, (c,), d["train_conds"][c], min_main=g["min_main"][c],
                          max_shortcut_accuracy=g["max_shortcut_accuracy"])
            gates[f"{c}/{s}"] = {"passed": rep.passed, "strata_counts": rep.details["strata_counts"],
                                 "main_stratum_count": rep.details["main_stratum_count"],
                                 "worst_part_rule_accuracy_on_main": rep.details["worst_part_rule_accuracy_on_main"]}
            eps = [ep for ep in data["episodes"] if ep["split"] == s and ep["condition"] == c]
            for name, rule in rules.items():
                baselines.setdefault(name, {})[f"{c}/{s}"] = tally_rule(eps, rule, d["strata"][(c, s)])
    counts = {c: {"train": len(d["offs"][c]), **{s: len(d["evals"][(c, s)][0].ids) for s in ("dev", "test")}}
              for c in CONDITIONS}
    exact = {c: int(d["train"].exact[d["offs"][c]].sum()) for c in CONDITIONS}
    receipt = {"spec": data["spec"], "missing_packages": data["missing_packages"], "data_identity": d["identity"],
               "counts": counts, "exact_train_counts": exact, "gates": gates, "baselines": baselines}
    if not all(v["passed"] for v in gates.values()):
        write_json(ctx["out"] / "receipts" / "gate.failed.json", receipt)
        raise StopRun(f"GATE_FAILED：{json.dumps({k: v['passed'] for k, v in gates.items()})}")
    return receipt


def tally_rule(eps: list, rule, strata: dict) -> dict:
    """基线的计数，口径和模型一样：返回 None（推不出）算“不知道”，强制二选一时算答错。"""
    rows = [(ep["id"], rule(ep)) for ep in eps]
    rows = [(i, p is not None and p == ep["label"], p is not None) for (i, p), ep in zip(rows, eps)]

    def t(sel):
        return {"n": len(sel), "forced_correct": sum(c for _, c, _ in sel), "answered": sum(a for _, _, a in sel),
                "answered_correct": sum(c and a for _, c, a in sel)}
    out = {"overall": t(rows), "strata": {}}
    for row in rows:
        for dim, value in strata[row[0]].items():
            out["strata"].setdefault(dim, {}).setdefault(value, []).append(row)
    out["strata"] = {dim: {v: t(sel) for v, sel in sorted(vals.items())} for dim, vals in out["strata"].items()}
    return out


def evaluate(sp, ctx: dict, conditions, splits=("dev", "test")) -> dict:
    """在指定条件、划分上评测：计分（含分层）和各层诊断。"""
    from empirical_core.t2.evaluate import layer_diagnostics, score
    d = load_data(ctx)
    out = {}
    for c in conditions:
        for s in splits:
            b, dg = d["evals"][(c, s)]
            pred = sp.predict(b, dg, chunk=ctx["plan"]["training"]["predict_chunk"])
            out[f"{c}/{s}"] = {"score": score(pred, b.labels, b.ids, d["strata"][(c, s)]),
                               "layers": layer_diagnostics(pred, b.labels, dg)}
    return out


def acc_of(ev: dict, key: str) -> float:
    o = ev[key]["score"]["overall"]
    return o["forced_correct"] / o["n"]


def store_dir(ctx: dict, seed: int, name: str = "units") -> Path:
    return ctx["out"] / "work" / f"s{seed}" / name


def gpu_record(ctx: dict, slept0: float) -> dict:
    import torch
    rec = {"device": ctx["plan"]["resources"]["device"], "throttle_sleep_seconds": ctx["guard"].slept - slept0}
    if rec["device"] == "cuda":
        rec["max_memory_allocated_bytes"] = torch.cuda.max_memory_allocated()
        torch.cuda.empty_cache()
    return rec


def reset_gpu_peak(ctx: dict) -> None:
    if ctx["plan"]["resources"]["device"] == "cuda":
        import torch
        torch.cuda.reset_peak_memory_stats()


def base_stage(stage: dict, ctx: dict) -> dict:
    from empirical_core.t2.spiral import bill_totals
    plan, d = ctx["plan"], load_data(ctx)
    seed = stage["seed"]
    reset_gpu_peak(ctx)
    slept0 = ctx["guard"].slept
    sp = make_spiral(ctx, seed, store_dir(ctx, seed))
    t0 = time.time()
    rec = sp.fit("base", d["offs"]["base"], plan["training"]["base_rounds"], plan["training"]["arrival_seed"],
                 curve=(d["curve"],))
    train_seconds = time.time() - t0
    ev = evaluate(sp, ctx, CONDITIONS)
    return {"seed": seed, "snapshot": sp.store.snapshot(), "curve": rec["curve"], "train_seconds": train_seconds,
            "bill": bill_totals(sp.bills), "losses": loss_summary(sp), "eval": ev, "gpu": gpu_record(ctx, slept0),
            "data_identity": d["identity"], "params": unit_params(sp)}


def unit_params(sp) -> dict:
    from empirical_core.t2.units import CAUnit, EAUnit, count_params
    ka = sum(t.numel() for t in sp._ka_state(0)["params"].values())
    return {"ka_per_package": ka, "ka_total": ka * sp.cfg.n_packages, "ea": count_params(EAUnit(sp.cfg)),
            "ca": count_params(CAUnit(sp.cfg))}


def loss_summary(sp) -> dict:
    def m(xs):
        return sum(xs) / len(xs) if xs else None
    return {k: {"first": m(v[:20]), "last": m(v[-20:]), "n": len(v)} for k, v in sp.losses.items()}


def base_receipt(ctx: dict, seed: int) -> dict:
    path = ctx["out"] / "receipts" / f"base-s{seed}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def repair_stage(stage: dict, ctx: dict) -> dict:
    """固定写范围的修复，或逐级加深。都从同一份基线快照出发。"""
    from empirical_core.t2.repair import escalate, is_empty, resolve_scope
    from empirical_core.t2.spiral import bill_totals
    plan, d = ctx["plan"], load_data(ctx)
    seed, ch = stage["seed"], stage["change"]
    base = base_receipt(ctx, seed)
    rp = plan["repair"]
    reset_gpu_peak(ctx)
    slept0 = ctx["guard"].slept
    sp = make_spiral(ctx, seed, store_dir(ctx, seed))
    sp.store.restore(base["snapshot"])
    new, old = d["offs"][ch], d["offs"]["base"]
    tag = stage["id"]
    t0 = time.time()
    extra = {}
    if stage["kind"] == "arm":
        layers = plan["arms"][stage["arm"]]
        scope = resolve_scope(layers, sp, new)
        extra["scope"] = scope
        if is_empty(scope):
            return {"seed": seed, "change": ch, "arm": stage["arm"], "skipped": "写范围为空（这种变更没有新单元）",
                    "scope": scope}
        sp.repair(tag, new, old, rounds=rp["rounds"], replay_ratio=rp["replay_ratio"], **scope)
    else:
        target = acc_of(base["eval"], "base/dev")

        def check():
            ev = evaluate(sp, ctx, (ch, "base"), splits=("dev",))
            return {"new_dev": acc_of(ev, f"{ch}/dev"), "old_dev": acc_of(ev, "base/dev")}
        extra["escalation"] = escalate(sp, base["snapshot"], tag, new, old, rounds=rp["rounds"],
                                       replay_ratio=rp["replay_ratio"], check=check, target=target,
                                       margin=rp["enough_margin"])
    train_seconds = time.time() - t0
    ev = evaluate(sp, ctx, (ch, "base"))
    changed = sorted(k for k, v in sp.store.snapshot().items() if base["snapshot"].get(k) != v)
    return {"seed": seed, "change": ch, "arm": stage.get("arm", "escalate"), **extra, "snapshot": sp.store.snapshot(),
            "units_changed_vs_base": changed, "train_seconds": train_seconds, "bill": bill_totals(sp.bills),
            "losses": loss_summary(sp), "eval": ev, "gpu": gpu_record(ctx, slept0)}


def retrain_stage(stage: dict, ctx: dict) -> dict:
    """全局重构：三层都从头学，材料是 base＋新条件的全部 TRAIN，轮数和基线相同。"""
    import torch
    from empirical_core.t2.spiral import bill_totals
    plan, d = ctx["plan"], load_data(ctx)
    seed, ch = stage["seed"], stage["change"]
    reset_gpu_peak(ctx)
    slept0 = ctx["guard"].slept
    sp = make_spiral(ctx, seed, store_dir(ctx, seed, f"retrain_{ch}"))
    t0 = time.time()
    pool = torch.cat([d["offs"]["base"], d["offs"][ch]])
    rec = sp.fit(stage["id"], pool, plan["training"]["base_rounds"], plan["training"]["arrival_seed"],
                 curve=(d["curve"],))
    train_seconds = time.time() - t0
    ev = evaluate(sp, ctx, (ch, "base"))
    return {"seed": seed, "change": ch, "arm": "retrain", "snapshot": sp.store.snapshot(), "curve": rec["curve"],
            "train_seconds": train_seconds, "bill": bill_totals(sp.bills), "losses": loss_summary(sp), "eval": ev,
            "gpu": gpu_record(ctx, slept0)}


def check_stage(ctx: dict) -> dict:
    """程序检查（不是成绩门槛）：每个阶段都有收据；题数对得上；
    写范围契约：固定写范围的修复只改了写范围里的单元；KA_local 修复不改变旧条件题的答案。"""
    plan, out = ctx["plan"], ctx["out"]
    d = load_data(ctx)
    problems, warnings = [], []
    for st in stage_list(plan):
        if st["kind"] not in ("base", "arm", "escalate", "retrain"):
            continue
        path = out / "receipts" / f"{st['id']}.json"
        if not path.exists():
            problems.append(f"{st['id']} 没有收据")
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("skipped"):
            continue
        for key, ev in rec["eval"].items():
            c, s = key.split("/")
            if ev["score"]["overall"]["n"] != len(d["evals"][(c, s)][0].ids):
                problems.append(f"{st['id']} 的 {key} 题数不对")
        if st["kind"] == "arm":
            sc = rec["scope"]
            allowed = {f"ka{p:04d}" for p in sc["ka_packages"]} | ({"ea"} if sc["ea"] else set()) | \
                      ({"ca"} if sc["ca"] else set())
            extra = set(rec["units_changed_vs_base"]) - allowed
            if extra:
                problems.append(f"{st['id']} 改了写范围以外的单元 {sorted(extra)}")
            if st["arm"] == "KA_local":
                base = json.loads((out / "receipts" / f"base-s{st['seed']}.json").read_text(encoding="utf-8"))
                for s in ("dev", "test"):
                    if rec["eval"][f"base/{s}"]["score"]["overall"] != base["eval"][f"base/{s}"]["score"]["overall"]:
                        problems.append(f"{st['id']}：KA_local 修复改变了旧条件 {s} 的成绩（契约不满足）")
        for layer, ls in rec["losses"].items():
            if ls["first"] is not None and ls["last"] is not None and ls["last"] >= ls["first"] and st["kind"] in ("base", "retrain"):
                warnings.append(f"{st['id']}：{layer} 损失没有下降（{ls['first']:.4f} → {ls['last']:.4f}），照实报告")
    if problems:
        raise StopRun(f"PROGRAM_CHECK_FAILED：{problems}")
    return {"problems": problems, "warnings": warnings}


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
