"""T3 的事后分析：从显式指定的复现运行 receipts 重新算，不训练、不改收据。

这不是冻结计划里的指标，只是看完报告以后补算的，写进文档时标“事后分析”。
用法：python -B analyze_t3.py <本副本根相对运行目录>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN: Path | None = None
sys.path.insert(0, str(HERE.parent))
from _release_support import root_path
from report_t3 import reproduction_plan
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "project"))
from empirical_core.t3.stability import simulate_stop  # noqa: E402

ARMS = ("one_way", "two_way")
SEEDS = (0, 1, 2)
CADENCES = (1, 3, 4, 5)
TOLS = (0.1, 0.05, 0.02, 0.01, 0.005)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(arm: str, seed: int) -> dict:
    return json.loads((RUN / "receipts" / f"{arm}-s{seed}.json").read_text(encoding="utf-8"))


def acc(t: dict) -> float:
    return t["forced_correct"] / t["n"]


def lag(rec: dict, k: int):
    return rec["check"]["lag"].get(str(k))


def checks(rounds: list, normalize: bool) -> list:
    """把收据里的 lag 变成 simulate_stop 要的格式；normalize 时除以间隔轮数（每轮平均变化）。"""
    out = []
    for r in rounds:
        lags = {}
        for k, v in r["check"]["lag"].items():
            k = int(k)
            lags[k] = {m: (x / k if normalize else x) for m, x in v.items()}
        out.append({"round": r["round"], "lag": lags})
    return out


def main_acc(r: dict) -> float:
    return acc(r["test"]["score"]["strata"]["gate"]["new_conflict"])


def main() -> None:
    global RUN
    if len(sys.argv) != 2:
        raise SystemExit("Usage: analyze_t3.py <run-directory-relative-to-release-root>")
    RUN = root_path(sys.argv[1], must_exist=True)
    frozen = json.loads((RUN / "FROZEN.json").read_text(encoding="utf-8"))
    print("## 凭证核对")
    reproduction_plan(frozen)  # Reject old absolute plan references.
    print("计划 SHA 一致：", sha(root_path(frozen["plan_path"], must_exist=True)) == frozen["plan_sha256"])
    bad = [k for k, v in frozen["sources"].items() if sha(root_path(k, must_exist=True)) != v]
    print("源码文件数：", len(frozen["sources"]), "；和启动时不同的：", bad)
    data = {(a, s): load(a, s) for a in ARMS for s in SEEDS}
    lines = (RUN / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    prog = {}
    for ln in lines:
        p = json.loads(ln)
        prog[(p["stage"], p["round"])] = p["test"]["forced_correct"]
    same = all(prog[(f"{a}-s{s}", r["round"])] == r["test"]["score"]["overall"]["forced_correct"]
               for (a, s), rec in data.items() for r in rec["rounds"])
    print("收据和 progress.jsonl 每轮 TEST 答对数一致：", same, "；条数", len(lines))
    print("每个阶段墙钟（分钟）：", {f"{a}-s{s}": round(d["seconds"] / 60) for (a, s), d in data.items()})
    gpu_peaks = [d["gpu"]["max_memory_allocated_bytes"] for d in data.values()
                 if "gpu" in d and "max_memory_allocated_bytes" in d["gpu"]]
    if gpu_peaks:
        print("显存峰值 MiB（仅有记录的阶段）：", max(round(value / 2 ** 20) for value in gpu_peaks))
    else:
        print("显存峰值：未记录；CPU 运行不提供显存指标。")

    print("\n## 第 20 轮各分层的正确率（TEST；三个种子）")
    for dim in ("package", "pair", "path", "needs", "gate"):
        vals = sorted(data[("two_way", 0)]["rounds"][-1]["test"]["score"]["strata"][dim])
        for v in vals:
            row = []
            for a in ARMS:
                ts = [data[(a, s)]["rounds"][-1]["test"]["score"]["strata"][dim][v] for s in SEEDS]
                row.append(f"{a} " + "/".join(f"{acc(t):.1%}" for t in ts))
            print(f"{dim}={v}（{ts[0]['n']} 题）：", "；".join(row))

    print("\n## “不知道”（第 20 轮 TEST）：回答的比例｜回答了的正确率")
    for a in ARMS:
        for s in SEEDS:
            sc = data[(a, s)]["rounds"][-1]["test"]["score"]
            parts = [("全部", sc["overall"])] + [(v, sc["strata"]["indirect"][v]) for v in ("none", "one", "both")]
            print(a, s, "；".join(f"{n} {t['answered'] / t['n']:.1%}｜"
                                 f"{(t['answered_correct'] / t['answered']) if t['answered'] else 0:.1%}" for n, t in parts))

    print("\n## 每轮答案改变的比例（探针，和上一轮比）")
    for (a, s), d in data.items():
        print(a, s, ", ".join(f"{lag(r, 1)['answer']:.4f}" for r in d["rounds"][1:]))

    print("\n## 时间（秒，计算时间，不含限流）")
    for a in ARMS:
        tr = [r["train"]["compute_seconds"] for s in SEEDS for r in data[(a, s)]["rounds"] if r["round"] > 4]
        ka = [r["train"]["KA"]["compute_seconds"] for s in SEEDS for r in data[(a, s)]["rounds"] if r["round"] > 4]
        ck = [r["check"]["snapshot_seconds"] + r["check"].get("measure_seconds", 0) for s in SEEDS
              for r in data[(a, s)]["rounds"] if r["round"] > 0]
        ev = [r["report_eval_seconds"] for s in SEEDS for r in data[(a, s)]["rounds"] if r["round"] > 0]
        print(f"{a}：材料到齐后每轮训练 {sum(tr) / len(tr):.1f}（KA {sum(ka) / len(ka):.1f}）；一次校验 {sum(ck) / len(ck):.2f}；"
              f"报告用评测一次 {sum(ev) / len(ev):.2f}；校验/训练 {sum(ck) / len(ck) / (sum(tr) / len(tr)):.2%}")

    print("\n## 第 20 轮成绩的 0.5 个百分点以内，最早是第几轮（TEST 主要指标；隐藏真值，只作参照）")
    for (a, s), d in data.items():
        last = main_acc(d["rounds"][-1])
        first = next(r["round"] for r in d["rounds"] if main_acc(r) >= last - 0.005)
        print(a, s, f"第 20 轮 {last:.1%}，最早第 {first} 轮")

    for title, measure, normalize in (("SLOT，每轮平均变化（除以间隔轮数）", "slot", True),
                                      ("整个模型的答案，和上一次校验比（不除）", "answer", False),
                                      ("整个模型的答案，每轮平均变化（除以间隔轮数）", "answer", True)):
        for w in (1, 2):
            print(f"\n## 事后模拟：{title}，连续 {w} 次低于阈值")
            print("格子：各种子停在第几轮｜平均总秒数｜停下时 TEST 主要指标平均")
            for a in ARMS:
                print("-", a, f"跑满 20 轮：主要指标平均 {sum(main_acc(data[(a, s)]['rounds'][-1]) for s in SEEDS) / 3:.1%}")
                for tol in TOLS:
                    cells = []
                    for c in CADENCES:
                        stops, secs, accs = [], [], []
                        for s in SEEDS:
                            rounds = data[(a, s)]["rounds"]
                            st = simulate_stop(checks(rounds, normalize), measure, c, tol, w, 20)
                            end = st if st is not None else 20
                            train = [r["train"]["compute_seconds"] for r in rounds if r["round"] > 0]
                            ck = [r["check"]["snapshot_seconds"] + r["check"].get("measure_seconds", 0)
                                  for r in rounds if r["round"] > 0]
                            secs.append(sum(train[:end]) + (end // c + 1) * sum(ck) / len(ck))
                            accs.append(main_acc(rounds[end]))
                            stops.append(str(st) if st is not None else "未停")
                        cells.append(f"每{c}轮 {'/'.join(stops)}｜{sum(secs) / 3:.0f}｜{sum(accs) / 3:.1%}")
                    print(f"  阈值 {tol:g}：", "  ".join(cells))

    print("\n## 包内差异（第 20 轮；同包两成员谁大判断对的比例｜成员平均距离）")
    for (a, s), d in data.items():
        kd = d["rounds"][-1]["ka_diff"]
        print(a, s, {g: (round(v["order_correct"] / v["order_n"], 3), round(v["spread"], 3)) for g, v in kd.items()})
    print("\n## 双向：包内大小判断每轮（间接／其他），种子 1")
    print(", ".join(f"{r['ka_diff']['indirect']['order_correct'] / r['ka_diff']['indirect']['order_n']:.2f}/"
                    f"{r['ka_diff']['direct']['order_correct'] / r['ka_diff']['direct']['order_n']:.2f}"
                    for r in data[("two_way", 1)]["rounds"]))


if __name__ == "__main__":
    main()
