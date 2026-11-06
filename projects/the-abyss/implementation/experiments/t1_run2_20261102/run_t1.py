"""T1 第二次正式运行（run2）的流水线：按冻结计划 PLAN.json 依次执行，中途不需要人看着。

用法：python -B run_t1.py <PLAN.json> <输出目录>

和第一次（t1_run_20261101/run_t1.py）相比：
- 本复现入口不读取旧进程或等待原机器上的实验。
- 模型按 plan.models[*].kind 构建：同一种模型可以用不同设置出现多次，例如螺旋 8 轮和 24 轮。
- 每个模型另算一份“逻辑优先”组合成绩：
  - 训练事实用传递关系能推出的题，直接用推理的答案；
  - 推不出的题，用模型的答案。
  - 这是推理阶段的组合，不另外训练。
其余规则不变：
- 每个阶段写收据；
- 人手动再次启动时跳过已完成的阶段；
- 出错就停、不重试；
- 资源和时间有上限；
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
    out = []
    for size in plan["sizes"]:
        out.append({"id": f"{size}-gate", "kind": "gate", "size": size})
        for group in plan["seed_groups"][size]:
            for seed in group:
                for model in plan["model_order_by_size"][size]:
                    out.append({"id": f"{size}-{model}-s{seed}", "kind": "train", "size": size, "model": model,
                                "seed": seed})
            out.append({"id": f"{size}-report-s{'_'.join(map(str, group))}", "kind": "report"})
        out.append({"id": f"{size}-check", "kind": "check", "size": size})
    out.append({"id": "final-report", "kind": "report"})
    return out


class Guard:
    """训练循环每一步都会调用：总时间、进程内存超过上限就停。内存每 30 秒查一次。
    GPU duty, when configured, inserts cooperative pauses; it does not guarantee device utilization."""

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
    import report_t1

    out.mkdir(parents=True, exist_ok=True)
    current, start = "start", time.time()
    guard = Guard(proc, start, res["time_cap_hours"] * 3600, int(res["max_rss_gib"] * 2 ** 30),
                  gpu_duty=res.get("gpu_duty") if use_gpu else None)
    try:
        stages = stage_list(plan)
        sources = sorted((PROJECT / "empirical_core").rglob("*.py")) + [HERE / "run_t1.py", HERE / "report_t1.py"]
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
        start = time.time()                            # 时间上限从真正开始训练算起，不含等待
        guard.start = start
        guard.mark = time.perf_counter()
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
            t0 = time.time()
            receipt = run_stage(stage, ctx)
            receipt.update({"stage": stage, "status": "done", "seconds": time.time() - t0,
                            "peak_rss_bytes_seen": guard.peak, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")})
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
                "hours": (time.time() - start) / 3600, "peak_rss_bytes_seen": guard.peak}
    write_json(out / "PIPELINE_EXIT.json", exit_rec)
    write_json(out / "STATUS.json", {"state": status.upper(), "stage": current, "reason": reason,
                                     "time": exit_rec["finished_at"], "pid": os.getpid()})
    try:
        report_t1.write_report(out)
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


# ---------------- 阶段 ----------------
def run_stage(stage: dict, ctx: dict) -> dict:
    if stage["kind"] == "gate":
        return gate_stage(stage["size"], ctx)
    if stage["kind"] == "train":
        return train_stage(stage, ctx)
    if stage["kind"] == "check":
        return check_stage(stage["size"], ctx)
    import report_t1
    report_t1.write_report(ctx["out"])
    return {"report": "REPORT.zh.md"}


def load_size(size: str, ctx: dict) -> dict:
    """出题、编码、分层、路径推理；只缓存当前这一档，换档时释放上一档。"""
    if size in ctx["cache"]:
        return ctx["cache"][size]
    ctx["cache"].clear()
    import torch
    from empirical_core.t1 import baselines as bl
    from empirical_core.t1.features import encode
    from empirical_core.t1.task import PRESETS, build_t1
    from empirical_core.t1.train import take
    data = build_t1(PRESETS[size])
    batches = {s: encode(data, s) for s in ("train", "dev", "test")}       # T1-b：不给已登记偏差
    strata = {s: bl.strata(data, s) for s in ("dev", "test")}
    path = bl.path_reasoner(data)
    path_pred = {}
    for s in ("dev", "test"):
        by_id = {ep["id"]: path(ep) for ep in data["episodes"] if ep["split"] == s}
        path_pred[s] = torch.tensor([-1 if by_id[i] is None else by_id[i] for i in batches[s].ids])
    n_curve = min(ctx["plan"]["training"]["curve_subset"], len(batches["dev"].ids))
    curve = take(batches["dev"], torch.arange(n_curve))
    identity = hashlib.sha256(json.dumps(data["episodes"], sort_keys=True).encode()).hexdigest()
    ctx["cache"][size] = {"data": data, "batches": batches, "strata": strata, "curve": curve, "identity": identity,
                          "path_pred": path_pred}
    return ctx["cache"][size]


def gate_stage(size: str, ctx: dict) -> dict:
    from empirical_core.t1 import baselines as bl
    gates_cfg = ctx["plan"]["gates"]
    d = load_size(size, ctx)
    data = d["data"]
    gates = {}
    for split in ("dev", "test"):
        rep = bl.gate(data, split, min_main=gates_cfg["min_main"], max_shortcut_accuracy=gates_cfg["max_shortcut_accuracy"])
        gates[split] = {"passed": rep.passed, "strata_counts": rep.details["strata_counts"],
                        "main_stratum_count": rep.details["main_stratum_count"],
                        "worst_part_rule_accuracy_on_main": rep.details["worst_part_rule_accuracy_on_main"]}
    baselines = {}
    rules = {"majority": bl.majority(data), **bl.part_rules(data), "path_reasoner": bl.path_reasoner(data)}
    for split in ("dev", "test"):
        eps = [ep for ep in data["episodes"] if ep["split"] == split]
        for name, rule in rules.items():
            baselines.setdefault(name, {})[split] = tally_rule(eps, rule, d["strata"][split])
    counts = {s: len(b.ids) for s, b in d["batches"].items()}
    receipt = {"size": size, "spec": data["spec"], "data_identity": d["identity"], "split_counts": counts,
               "gates": gates, "baselines": baselines,
               "theoretical_optimum": {s: counts[s] for s in ("dev", "test")}}
    if not all(g["passed"] for g in gates.values()):
        write_json(ctx["out"] / "receipts" / f"{size}-gate.failed.json", receipt)
        raise StopRun(f"GATE_FAILED：{size} 档门禁未通过 {json.dumps({k: v['passed'] for k, v in gates.items()})}")
    return receipt


def tally_rule(eps: list, rule, strata: dict) -> dict:
    """基线的计数，口径和模型一样：返回 None（没见过／推不出）算“不知道”，强制二选一时算答错。"""
    rows = []
    for ep in eps:
        pred = rule(ep)
        rows.append((ep["id"], pred is not None and pred == ep["label"], pred is not None))

    def t(sel):
        return {"n": len(sel), "forced_correct": sum(c for _, c, _ in sel), "answered": sum(a for _, _, a in sel),
                "answered_correct": sum(c and a for _, c, a in sel)}
    out = {"overall": t(rows), "strata": {}}
    for row in rows:
        for dim, value in strata[row[0]].items():
            out["strata"].setdefault(dim, {}).setdefault(value, []).append(row)
    out["strata"] = {dim: {v: t(sel) for v, sel in sorted(vals.items())} for dim, vals in out["strata"].items()}
    return out


def a_config(spec: dict, size: str, plan: dict, entry: dict):
    from empirical_core.t1.model_a import config_for
    bias = 0.0 if entry["kind"] == "A_joint_noid" else entry.get("identity_bias", plan["model_a"]["identity_bias"])
    return config_for(spec, size, identity_bias=bias)


def build_model(name: str, spec: dict, size: str, plan: dict):
    import torch
    from empirical_core.t1.controls import (EmbedMLPControl, EmbedTransformerControl, LinearPriorControl,
                                            count_params, match_size)
    from empirical_core.t1.model_a import ModelA, config_for
    entry = plan["models"][name]
    kind = entry["kind"]
    P, M, L = spec["n_packages"], spec["n_members"], spec["history_len"]
    if kind in ("A_joint", "A_spiral", "A_joint_noid"):
        return ModelA(a_config(spec, size, plan, entry)), None
    if kind == "LinearPrior":
        return LinearPriorControl(P, M), None
    with torch.device("meta"):
        target = count_params(ModelA(config_for(spec, size)))
    cs = plan["control_sizes"][size]
    if kind == "MLP":
        m = match_size(lambda h: EmbedMLPControl(P, M, L, cs["mlp_d"], h), range(*cs["mlp_range"]), target)
        return EmbedMLPControl(P, M, L, cs["mlp_d"], m["size"]), m
    if kind == "TFM":
        m = match_size(lambda dm: EmbedTransformerControl(P, M, L, dm, cs["tfm_layers"], cs["tfm_heads"]),
                       range(*cs["tfm_range"]), target)
        return EmbedTransformerControl(P, M, L, m["size"], cs["tfm_layers"], cs["tfm_heads"]), m
    raise ValueError(kind)


def hybrid_pred(pred: dict, path_pred) -> dict:
    """逻辑优先：路径推理推得出的题用推理答案（当作确定作答），推不出的保留模型的输出。"""
    import torch
    decided = path_pred >= 0
    logit = torch.where(decided, torch.where(path_pred == 1, 20.0, -20.0), pred["logit"])
    none = None
    if pred.get("none") is not None:
        none = torch.where(decided.unsqueeze(-1), torch.zeros_like(pred["none"]), pred["none"])
    return {"logit": logit, "none": none}


def train_stage(stage: dict, ctx: dict) -> dict:
    import numpy as np
    import torch
    from empirical_core.t1.controls import count_params
    from empirical_core.t1.spiral import SpiralA
    from empirical_core.t1.train import predict, score, train_joint
    from empirical_core.timing import SegmentTimer
    plan, out, guard = ctx["plan"], ctx["out"], ctx["guard"]
    size, name, seed = stage["size"], stage["model"], stage["seed"]
    entry = plan["models"][name]
    tr = plan["training"]
    device = plan["resources"].get("device", "cpu")
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    slept0 = guard.slept
    d = load_size(size, ctx)
    spec = d["data"]["spec"]
    torch.manual_seed(seed)
    model, matched = build_model(name, spec, size, plan)
    lr = entry["lr"]
    timer = SegmentTimer()
    t0 = time.time()
    if entry["kind"] == "A_spiral":
        sp_cfg = entry["spiral"]
        bills = out / "bills" / f"{stage['id']}.jsonl"
        if bills.exists():
            bills.unlink()                             # 上一次未完成的尝试已登记在 failures.jsonl，这里重新开始
        trainer = SpiralA(a_config(spec, size, plan, entry), out / "spiral" / stage["id"], seed=seed,
                          rounds=sp_cfg["rounds"], epochs_per_phase=sp_cfg["epochs_per_phase"][size],
                          batch_size=tr["batch_size"], lr=lr, arrival_seed=sp_cfg["arrival_seed"],
                          l0_budget_bytes=sp_cfg["l0_budget_bytes"], l1_budget_bytes=sp_cfg["l1_budget_bytes"],
                          clip=tr["clip"], guard=guard, timer=timer, log=lambda rec: append_jsonl(bills, rec),
                          replay_ratio=sp_cfg.get("replay_ratio"), device=device)
        record = trainer.fit(d["batches"]["train"], d["curve"])
        model = trainer.assemble()
    else:
        record = train_joint(model, d["batches"]["train"], epochs=tr["epochs"][size], batch_size=tr["batch_size"],
                             lr=lr, seed=seed, curve_batch=d["curve"], curve_points=tr["curve_points"],
                             clip=tr["clip"], guard=guard, timer=timer, device=device)
    train_seconds = time.time() - t0
    t1 = time.time()
    model.to(device)
    preds = {s: predict(model, d["batches"][s], chunk=tr["predict_chunk"], after_chunk=guard) for s in ("dev", "test")}
    predict_seconds = time.time() - t1
    model.cpu()
    gpu = {"device": device, "throttle_sleep_seconds": guard.slept - slept0}
    if device == "cuda":
        gpu["max_memory_allocated_bytes"] = torch.cuda.max_memory_allocated()
        torch.cuda.empty_cache()
    scores = {s: score(preds[s], d["batches"][s], d["strata"][s]) for s in ("dev", "test")}
    scores_hybrid = {s: score(hybrid_pred(preds[s], d["path_pred"][s]), d["batches"][s], d["strata"][s])
                     for s in ("dev", "test")}
    contract = []
    if entry["kind"].startswith("A_"):
        contract.append({"name": "参考成员偏差恒为 0", "passed": bool(torch.all(model.offsets()[:, 0] == 0))})
    pred_dir = out / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    arrays = {f"{s}_logit": preds[s]["logit"].numpy() for s in preds}
    arrays.update({f"{s}_none": preds[s]["none"].numpy() for s in preds if preds[s]["none"] is not None})
    np.savez_compressed(pred_dir / f"{stage['id']}.npz", **arrays)
    weights = out / "weights" / f"{stage['id']}.pt"
    weights.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), weights)
    record.pop("timing", None)
    return {"model": name, "kind": entry["kind"], "size": size, "seed": seed, "params": count_params(model),
            "param_matching": matched, "lr": lr, "training": record, "train_seconds": train_seconds,
            "predict_seconds": predict_seconds, "gpu": gpu,
            "timing": {k: {"median_s": v["median_s"], "n": v["n"]} for k, v in timer.summary(warmup=0).items()},
            "scores": scores, "scores_hybrid": scores_hybrid, "contract_checks": contract,
            "data_identity": d["identity"],
            "split_ids_sha256": {s: hashlib.sha256("\n".join(d["batches"][s].ids).encode()).hexdigest()
                                 for s in ("dev", "test")},
            "weights_sha256": sha256_file(weights), "predictions": f"predictions/{stage['id']}.npz",
            "model_bytes": sum(p.numel() * p.element_size() for p in model.parameters())}


def check_stage(size: str, ctx: dict) -> dict:
    """程序检查（不是成绩门槛）：本档每个训练阶段都有收据、预测题数对得上、契约检查都满足。"""
    plan, out = ctx["plan"], ctx["out"]
    d = load_size(size, ctx)
    problems, warnings = [], []
    for st in stage_list(plan):
        if st["kind"] != "train" or st["size"] != size:
            continue
        path = out / "receipts" / f"{st['id']}.json"
        if not path.exists():
            problems.append(f"{st['id']} 没有收据")
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        for s in ("dev", "test"):
            if rec["scores"][s]["overall"]["n"] != len(d["batches"][s].ids):
                problems.append(f"{st['id']} 的 {s} 题数不对")
        problems += [f"{st['id']}：{c['name']} 不满足" for c in rec["contract_checks"] if not c["passed"]]
        tr = rec["training"]
        if tr.get("loss_first") is not None and tr["loss_last"] >= tr["loss_first"]:
            warnings.append(f"{st['id']}：训练损失没有下降（{tr['loss_first']:.4f} → {tr['loss_last']:.4f}），照实报告")
    if problems:
        raise StopRun(f"PROGRAM_CHECK_FAILED：{size} 档 {problems}")
    return {"size": size, "problems": problems, "warnings": warnings}


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
