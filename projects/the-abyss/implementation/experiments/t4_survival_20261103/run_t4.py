"""T4 正式运行的流水线：按冻结计划 PLAN.json 依次执行，中途不需要人看着。

用法：python -B run_t4.py <PLAN.json> <输出目录>

要回答的问题：
1. 边用边学：世界慢慢变，旧本领保住多少，新本领多久学会。
2. 有限资源：真实的 CPU、显卡消耗和存储有没有界，资源池有没有被重置。
3. 延续：突然断电以后，登记过的东西有没有丢，有没有重复执行，能不能接着活。
4. CA 约束 EA：EA 受 CA 指引和只有回返约束，差多少。

阶段：
- gate：出题、规则和划分检查、起点单元检查；
- 每个种子：每个组各活一遍（子进程 live_t4.py，同一目录再启动就是重启）；
- crash：按计划在指定位置硬杀进程，再用同一个入口重启，核对契约；
- check、final-report。
其余规则同 T1–T3：每个阶段写收据；人手动再次启动时跳过已完成的阶段；出错就停、不重试；报告由收据自动生成。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (RELEASE_ROOT, configure_runtime, dependency_run,
                              freeze_plan_metadata, load_plan, root_path, source_hashes)
PROJECT = HERE.parents[1] / "project"
sys.path.insert(0, str(PROJECT))
T2_RUNNER = HERE.parent / "t2_repair_20261102"
sys.path.insert(0, str(T2_RUNNER))

from run_t2 import StopRun, append_jsonl, sha256_file, write_json  # noqa: E402


def stage_list(plan: dict) -> list[dict]:
    out = [{"id": "gate", "kind": "gate"}]
    for seed in plan["seeds"]:
        for arm in plan["arms"]:
            out.append({"id": f"{arm}-s{seed}", "kind": "life", "arm": arm, "seed": seed})
        out.append({"id": f"report-s{seed}", "kind": "report"})
    for seed in plan["crash"]["seeds"]:
        out.append({"id": f"crash-s{seed}", "kind": "crash", "arm": "survive", "seed": seed})
    out += [{"id": "check", "kind": "check"}, {"id": "final-report", "kind": "report"}]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a new T4 synthetic reproduction (includes training and injected subprocess exits).")
    parser.add_argument("plan", help="PLAN.json relative to the release root")
    parser.add_argument("output", help="Fresh run directory relative to the release root")
    args = parser.parse_args()
    plan_path, out = root_path(args.plan, must_exist=True), root_path(args.output)
    plan = load_plan(plan_path)
    res = plan["resources"]
    import psutil
    proc = psutil.Process()
    runtime = configure_runtime(threads=int(os.environ.get("ABYSS_THREADS", res.get("threads", 1))),
                                cpus=res.get("cpu_affinity"))
    res.update(runtime)
    from empirical_core.timing import environment
    sys.path.insert(0, str(HERE))
    import report_t4

    out.mkdir(parents=True, exist_ok=True)
    current, start = "start", time.time()
    try:
        stages = stage_list(plan)
        sources = sorted((PROJECT / "empirical_core").rglob("*.py")) + \
            [HERE / "run_t4.py", HERE / "report_t4.py", HERE / "live_t4.py", T2_RUNNER / "run_t2.py", T2_RUNNER / "report_t2.py"]
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
        ctx = {"plan": plan, "out": out, "start": start, "cap": res["time_cap_hours"] * 3600}
        for i, stage in enumerate(stages):
            current = stage["id"]
            receipt_path = out / "receipts" / f"{stage['id']}.json"
            if receipt_path.exists():
                continue
            if time.time() - start > ctx["cap"]:
                raise StopRun(f"TIME_CAP：总时间超过 {res['time_cap_hours']} 小时")
            wait_for_memory(res)
            write_json(out / "STATUS.json", {"state": "RUNNING", "stage": stage["id"], "index": i, "of": len(stages),
                                             "time": time.strftime("%Y-%m-%d %H:%M:%S"), "pid": os.getpid()})
            append_jsonl(out / "log.jsonl", {"event": "stage_start", "stage": stage["id"], "time": time.time()})
            t0 = time.time()
            receipt = run_stage(stage, ctx)
            receipt.update({"stage": stage, "status": "done", "seconds": time.time() - t0,
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
                "hours": (time.time() - start) / 3600}
    write_json(out / "PIPELINE_EXIT.json", exit_rec)
    write_json(out / "STATUS.json", {"state": status.upper(), "stage": current, "reason": reason,
                                     "time": exit_rec["finished_at"], "pid": os.getpid()})
    try:
        report_t4.write_report(out)
    except Exception:
        append_jsonl(out / "failures.jsonl", {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "stage": "final report",
                                             "status": "failed", "traceback": traceback.format_exc()})
    return 0 if status == "completed" else 1


def wait_for_memory(res: dict) -> None:
    import psutil
    need = res["min_free_physical_gib"] * 2 ** 30
    waited = 0
    while psutil.virtual_memory().available < need:
        if waited >= res["memory_wait_minutes"] * 60:
            raise StopRun(f"RESOURCE_PENDING：空闲物理内存连续 {waited // 60} 分钟低于 {res['min_free_physical_gib']} GiB")
        time.sleep(60)
        waited += 60


def world_spec(plan: dict):
    from empirical_core.t4.world import WorldSpec
    w = plan["world"]
    return WorldSpec(**{**w, "t3_overrides": tuple(tuple(x) for x in w.get("t3_overrides", ()))})


def t3_start(plan: dict, seed: int):
    st = plan.get("start")
    if not st:
        return None
    if st.get("dependency") != "t3":
        raise ValueError("T4 start must explicitly name dependency t3; configure dependency_runs.t3")
    run = dependency_run(plan, "t3")
    rec = json.loads((run / "receipts" / f"two_way-s{seed}.json").read_text(encoding="utf-8"))
    return {"root": (run / "work" / f"s{seed}" / "two_way").relative_to(RELEASE_ROOT).as_posix(), "snapshot": rec["rounds"][-1]["versions"]}


def write_conf(stage: dict, ctx: dict) -> Path:
    plan = ctx["plan"]
    over = plan.get("arm_overrides", {}).get(stage["arm"], {})      # 例如资源紧的组：做法同 survive，只是资源池小
    conf = {"world": plan["world"], "model_size": plan["model_size"], "arm": over.get("arm", stage["arm"]), "seed": stage["seed"],
            "days": plan["days"], "life": {**plan["life"], **over.get("life", {})}, "fsm": plan["fsm"], "evaluate": True,
            "start": t3_start(plan, stage["seed"]), "resources": plan["resources"]}
    path = ctx["out"] / "conf" / f"{stage['id']}.json"
    write_json(path, conf)
    return path


def live(conf: Path, life_dir: Path, ctx: dict, stage_id: str, crash=None) -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("T4_CRASH_AT", None)
    if crash:
        env.update({"T4_CRASH_AT": crash[0], "T4_CRASH_NTH": str(crash[1])})
    left = ctx["cap"] - (time.time() - ctx["start"])
    log = ctx["out"] / "logs" / f"{stage_id}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} crash={crash}\n")
        f.flush()
        try:
            return subprocess.run([sys.executable, "-B", str(HERE / "live_t4.py"), str(conf), str(life_dir)], env=env,
                                  stdout=f, stderr=subprocess.STDOUT, timeout=max(1.0, left)).returncode
        except subprocess.TimeoutExpired:
            raise StopRun(f"TIME_CAP：阶段 {stage_id} 跑到了总时间上限")


def records(life_dir: Path) -> list:
    return [json.loads(x) for x in (life_dir / "quick.jsonl").read_text(encoding="utf-8").splitlines()]


def summarize(recs: list) -> dict:
    """从快速登记汇总这一组的一生（报告用）。"""
    days = [{k: v for k, v in r.items() if k not in ("adopted", "kind", "seq", "time")} for r in recs if r["kind"] == "day_end"]
    sleeps = [{"day": r["day"], **{k: r["result"].get(k) for k in ("status", "adopted", "base", "trace", "bar")}}
              for r in recs if r["kind"] == "sleep_end"]
    return {"records": len(recs), "days": days, "sleeps": sleeps,
            "fsm_states": dict(Counter(r["state"] for r in recs if r["kind"] == "fsm")),
            "calls": sum(r["kind"] == "call_end" for r in recs), "unit_writes": sum(r["kind"] == "unit_write" for r in recs),
            "interrupts": [r for r in recs if r["kind"] in ("interrupt", "sleep_interrupted")],
            "awake_fixes": [{"day": r["day"], "ka_packages": r["ka_packages"], "materials": r["materials"]}
                            for r in recs if r["kind"] == "adopt" and r["reason"] == "awake_fix"],
            "consolidate": [r["result"]["output"]["rows"] for r in recs if r["kind"] == "consolidate"],
            "missing": next((r["missing"] for r in reversed(recs) if r["kind"] == "consolidate"), None)}


def contracts(recs: list, life_dir: Path, plan: dict, arm: str) -> list:
    """程序契约（不是成绩）：每道题最多答完一次；资源池累计消耗只增不减；只用不学的组没有写单元；长期库和游标一致。"""
    from empirical_core.t4.records import LongStore
    problems = []
    done = [q for r in recs if r["kind"] == "call_end" and r["status"] == "done" for q in r["qids"]]
    if len(done) != len(set(done)):
        problems.append("有题被答完了不止一次")
    unanswered = sum(r["unanswered"] for r in recs if r["kind"] == "day_end")
    if len(done) + unanswered != plan["days"] * plan["world"]["questions_per_day"]:
        problems.append(f"答完 {len(done)} ＋ 没答 {unanswered} 不等于总题数")
    used: dict = {}
    for r in recs:
        if r["kind"] == "pool":
            k = (r["pool"], r["cycle"])
            if any(r["used"][x] < used.get(k, {}).get(x, 0.0) - 1e-9 for x in r["used"]):
                problems.append(f"资源池 {k} 的累计消耗变小了")
            used[k] = r["used"]
    first = next((r["seq"] for r in recs if r["kind"] == "adopt"), 0)
    if arm == "frozen" and any(r["kind"] == "unit_write" and r["seq"] > first for r in recs):
        problems.append("只用不学的组写了单元")
    ls = LongStore(life_dir / "long.sqlite")
    if ls.count() != ls.cursor():
        problems.append("长期库的条数和游标不一致")
    miss = ls.missing()
    if miss["no_description"] or miss["no_index"]:
        problems.append("长期库有缺项")
    ls.close()
    return problems


# ---------------- 阶段 ----------------
def run_stage(stage: dict, ctx: dict) -> dict:
    kind = stage["kind"]
    if kind == "gate":
        return gate_stage(ctx)
    if kind == "life":
        return life_stage(stage, ctx)
    if kind == "crash":
        return crash_stage(stage, ctx)
    if kind == "check":
        return check_stage(ctx)
    import report_t4
    report_t4.write_report(ctx["out"])
    return {"report": "REPORT.zh.md"}


def gate_stage(ctx: dict) -> dict:
    import hashlib
    from empirical_core.t3.task import PRESETS, build_t3
    from empirical_core.t4.world import build_world, resolve_t4
    plan = ctx["plan"]
    ws = world_spec(plan)
    world = build_world(ws)
    problems = []
    key = lambda e: (tuple(sorted((tuple(e["hidden"]["A"]), tuple(e["hidden"]["B"])))), e["hidden"]["world"])
    by_split = Counter(e["split"] for e in world["episodes"])
    for e in world["episodes"]:
        h = e["hidden"]
        if resolve_t4(e) != (tuple(h["A"]), tuple(h["B"]), h["world"]):
            problems.append(f"{e['id']} 不符合规则")
            break
    days = [e for e in world["episodes"] if e["split"].startswith("day")]
    day_keys = {key(e) for e in days}
    for split in ("probe_old", "probe_new_genre", "probe_new_genre_dup", "past_check"):
        hit = {key(e) for e in world["episodes"] if e["split"] == split} & day_keys
        if hit:
            problems.append(f"{split} 和日子里的题重合 {len(hit)} 个键")
    pairs = {key(e)[0] for e in days}
    if {key(e)[0] for e in world["episodes"] if e["split"] == "probe_new_package"} & pairs:
        problems.append("新包探针和日子里的题重合")
    starts = {}
    if plan.get("start"):
        t3 = build_t3(PRESETS[ws.t3_preset])
        identity = hashlib.sha256(json.dumps(t3["episodes"], sort_keys=True).encode()).hexdigest()
        for seed in sorted(set(plan["seeds"]) | set(plan["crash"]["seeds"])):
            st = t3_start(plan, seed)
            rec = json.loads((dependency_run(plan, "t3") / "receipts" / f"two_way-s{seed}.json").read_text(encoding="utf-8"))
            if rec["data_identity"] != identity:
                problems.append(f"种子 {seed} 的 T3 起点和这个世界不是同一份题")
            lost = [k for k, v in st["snapshot"].items() if int(v) and not (root_path(st["root"], must_exist=True) / k / f"v{int(v):05d}.pt").exists()]
            if lost:
                problems.append(f"种子 {seed} 的起点单元缺文件：{lost[:3]}")
            starts[seed] = {"root": st["root"], "units": sum(int(v) > 0 for v in st["snapshot"].values())}
    receipt = {"world_spec": world["world_spec"], "new_packages": world["new_packages"], "episodes_by_split": dict(by_split),
               "by_change": dict(Counter(e["change"] for e in days)), "starts": starts, "problems": problems}
    if problems:
        write_json(ctx["out"] / "receipts" / "gate.failed.json", receipt)
        raise StopRun(f"GATE_FAILED：{problems}")
    return receipt


def life_stage(stage: dict, ctx: dict) -> dict:
    conf = write_conf(stage, ctx)
    life_dir = ctx["out"] / "life" / stage["id"]
    rc = live(conf, life_dir, ctx, stage["id"])
    if rc != 0:
        raise RuntimeError(f"{stage['id']} 退出码 {rc}，见 logs/{stage['id']}.log")
    recs = records(life_dir)
    return {"arm": stage["arm"], "seed": stage["seed"], "summary": summarize(recs),
            "contract_problems": contracts(recs, life_dir, ctx["plan"], stage["arm"])}


def crash_stage(stage: dict, ctx: dict) -> dict:
    """按计划一处一处硬杀进程，每次都用同一个入口重启；断电以前保存成功的记录必须一字不改。"""
    conf = write_conf(stage, ctx)
    life_dir = ctx["out"] / "life" / stage["id"]
    trace, problems = [], []
    for point, nth in ctx["plan"]["crash"]["points"]:
        rc = live(conf, life_dir, ctx, stage["id"], crash=(point, nth))
        lines = (life_dir / "quick.jsonl").read_text(encoding="utf-8").splitlines() if (life_dir / "quick.jsonl").exists() else []
        trace.append({"point": point, "nth": nth, "exit": rc, "records": len(lines)})
        if rc == 0:
            trace[-1]["note"] = "没等到这个位置就活完了"
            break
        if rc != 86:
            raise RuntimeError(f"{stage['id']} 在 {point} 退出码 {rc}")
        ctx.setdefault("prefix", {})[point] = lines
    rc = live(conf, life_dir, ctx, stage["id"])
    if rc != 0:
        raise RuntimeError(f"{stage['id']} 最后一次重启退出码 {rc}")
    final = (life_dir / "quick.jsonl").read_text(encoding="utf-8").splitlines()
    for point, lines in ctx.get("prefix", {}).items():
        if final[:len(lines)] != lines:
            problems.append(f"{point}：断电以前保存成功的记录被改了")
    recs = [json.loads(x) for x in final]
    problems += contracts(recs, life_dir, ctx["plan"], stage["arm"])
    summaries = [{k: r[k] for k in ("lost_calls", "late_reports", "late_feedback", "leftovers") if k in r}
                 for r in recs if r["kind"] == "recovery_summary"]
    return {"arm": stage["arm"], "seed": stage["seed"], "crashes": trace, "recoveries": summaries,
            "summary": summarize(recs), "contract_problems": problems}


def check_stage(ctx: dict) -> dict:
    plan, out = ctx["plan"], ctx["out"]
    problems = []
    for st in stage_list(plan):
        if st["kind"] not in ("life", "crash"):
            continue
        path = out / "receipts" / f"{st['id']}.json"
        if not path.exists():
            problems.append(f"{st['id']} 没有收据")
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        problems += [f"{st['id']}：{p}" for p in rec["contract_problems"]]
        if len(rec["summary"]["days"]) != plan["days"]:
            problems.append(f"{st['id']}：天数不全")
    if problems:
        raise StopRun(f"PROGRAM_CHECK_FAILED：{problems}")
    return {"problems": problems}


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
