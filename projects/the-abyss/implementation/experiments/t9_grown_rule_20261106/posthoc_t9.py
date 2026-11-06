"""T9 事后检查：python -B posthoc_t9.py <run 目录> <输出目录>。

不训练。数字来自 receipts/，第 2 节另外载入存好的小模型（约 2 万个参数）看第一层的输入。
这些检查都是看了结果以后才做的，事先没有写下预测。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

import torch

from run_t9 import HERE, T5Spec, build_lattice, build_task, setup, table, vectors  # noqa: F401
from _release_support import dependency_run, load_plan, load_run_plan, root_path
from empirical_core.t9.model import Selector9



def load(d: Path, name: str) -> dict:
    return json.loads((d / f"{name}.json").read_text(encoding="utf-8"))


def fmt(xs: list, n: int = 1) -> str:
    return " / ".join(f"{x:.{n}f}" for x in xs)


def part_sizes(m: Selector9, b: dict, k: int) -> tuple:
    """第一层里，来自关系嵌入和来自参考向量的部分，各有多大（每个位置的均方根）。"""
    W = m.inp.weight.detach()
    rel = m.rel(b["rel"]).detach() @ W[:, 1:1 + k].T
    vec = m.vec[b["obj"]] @ W[:, 1 + k:].T
    return float(rel.pow(2).sum(-1).mean().sqrt()), float(vec.pow(2).sum(-1).mean().sqrt())


def main() -> int:
    setup()
    run, out = root_path(sys.argv[1]), root_path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=False)
    R = run / "receipts"
    plan = load_run_plan(run, HERE / "PLAN.json")
    T8 = dependency_run(plan, "t8") / "receipts"
    seeds, tasks = plan["seeds"], plan["tasks"]
    spec = T5Spec(**plan["spec"])
    A = spec.n_relations - 1
    data = {t: build_task(t, spec) for t in tasks}
    vec = {t: vectors(t, data[t], spec, plan) for t in tasks}
    res: dict = {}

    L = ["# T9 事后检查（看了结果才做的，事先没有预测）", "", "不训练。数字由 `posthoc_t9.py` 从回执和存好的模型生成。", ""]

    # 1. 互相支持题里有没有锚
    L += ["## 1. 互相支持题里根本没有锚", "", "| 题型 | 训练链里锚关系出现的次数 | 晶格比较学到的锚权重（5 个种子） | 普通关系权重的范围（种子 0） |", "|---|---:|---|---|"]
    for t in tasks:
        n = int((data[t]["train"]["rel"] == A).sum())
        ws = [load(R, f"{t}-sim-all-s{s}")["weights"]["w"] for s in seeds]
        L.append(f"| {t} | {n} | {fmt([w[A] for w in ws], 2)} | {min(ws[0][:A]):.2f} 到 {max(ws[0][:A]):.2f} |")
        res[f"anchor_events_{t}"] = n

    # 2. 第一层的输入
    L += ["", "## 2. 成对比较和 attention：T9 和 T8 的差别", "",
          "规则表 `all` 没有错的格子，所以候选和 T8 完全一样。两边的差别只在输入：T8 是两个标记加向量，T9 是一个标记、16 维关系嵌入加向量。",
          "", "dev 成绩（训练 3000、12000、24000、48000 步）：", "", "| 题型 | 做法 | 种子 | T8 | T9 |", "|---|---|---:|---|---|"]
    at = [0, 3, 7, 15]
    for t in tasks:
        for k in ("pair", "attn"):
            for s in seeds:
                a, b = load(T8, f"{t}-{k}-full-s{s}")["curve"], load(R, f"{t}-{k}-all-s{s}")["curve"]
                L.append(f"| {t} | {k} | {s} | {fmt([100 * a[i]['dev_choice_two'] for i in at])} | {fmt([100 * b[i]['dev_choice_two'] for i in at])} |")
    L += ["", "第一层里两部分的大小（均方根，训练题前 512 道，5 个种子平均）：", "", "| 题型 | 做法 | 时刻 | 来自关系嵌入 | 来自参考向量 | 比值 |", "|---|---|---|---:|---:|---:|"]
    res["sizes"] = {}
    for t in tasks:
        d = data[t]
        b = {k: v[:512] for k, v in d["train"].items() if torch.is_tensor(v)}
        legal = table("all", d, spec, plan)
        for k in ("pair", "attn"):
            for when in ("开始", "结束"):
                xs = []
                for s in seeds:
                    torch.manual_seed(s)
                    m = Selector9(spec, vec[t], legal, k)
                    if when == "结束":
                        m.load_state_dict(torch.load(run / "models" / f"{t}-{k}-all-s{s}.pt", weights_only=True), strict=False)
                    xs.append(part_sizes(m, b, spec.k))
                r, v = mean(x[0] for x in xs), mean(x[1] for x in xs)
                res["sizes"][f"{t}-{k}-{when}"] = [r, v]
                L.append(f"| {t} | {k} | {when} | {r:.2f} | {v:.2f} | {r / v:.1f} |")

    # 3. R6 换一个比较对象
    L += ["", "## 3. R6：和同样大小的窗口比", "", "R6 拿窗口 256 的新表和全部 16384 条链的表比。窗口 256 本身就不总是准的，所以这里加上世界没变、同样 256 条链的成绩。", "",
          "| 题型 | 做法 | 全部链的表 | 世界没变，256 条链 | 世界变了，新链 256 条 |", "|---|---|---:|---:|---:|"]
    for t in tasks:
        for k in ("sim", "pair", "attn"):
            rs = [load(R, f"{t}-{k}-all-s{s}") for s in seeds]
            full = mean(100 * r["test_iid"]["choice_two"] for r in rs)
            same = mean(100 * mean(x["choice_two"] for x in r["sweep"]["256"]) for r in rs)
            new = mean(100 * mean(x["choice_two"] for x in r["shift"]["256"]) for r in rs)
            res[f"swap-{t}-{k}"] = [full, same, new]
            L.append(f"| {t} | {k} | {full:.1f} | {same:.1f} | {new:.1f} |")

    # 4. 规则写在权重里
    L += ["", "## 4. 规则写在权重里（`vec`）", "", "| 题型 | 种子 | 世界没变 | 世界变了 | 一个候选的题：世界没变 | 一个候选的题：世界变了 |", "|---|---:|---:|---:|---:|---:|"]
    for t in tasks:
        for s in seeds:
            r = load(R, f"{t}-vec-all-s{s}")
            L.append(f"| {t} | {s} | {100 * r['test_iid']['choice_two']:.1f} | {100 * r['test_shift']['choice_two']:.1f} | {100 * r['test_iid']['choice_one']:.1f} | {100 * r['test_shift']['choice_one']:.1f} |")

    # 5. m4
    L += ["", "## 5. attention 跑到 96000 步", "", "| 种子 | T8 同一批包 | 96000 步同一批包 | T8 没见过的包 | 96000 步没见过的包 | 最后的训练损失 |", "|---:|---:|---:|---:|---:|---:|"]
    gaps = []
    for s in seeds:
        a, b = load(T8, f"mutual-attn-full-s{s}"), load(R, f"mutual-attn-m4-s{s}")
        gaps.append(100 * (b["test_iid"]["choice_two"] - b["test_new"]["choice_two"]))
        L.append(f"| {s} | {100 * a['test_iid']['choice_two']:.1f} | {100 * b['test_iid']['choice_two']:.1f} | {100 * a['test_new']['choice_two']:.1f} | {100 * b['test_new']['choice_two']:.1f} | {b['curve'][-1]['train_loss']:.4f} |")
    res["m4_gap"] = gaps
    sim_new = mean(100 * load(R, f"mutual-sim-all-s{s}")["test_new"]["choice_two"] for s in seeds)
    L += ["", f"同一批包和没见过的包差 {fmt(gaps)} 分。晶格比较在没见过的包上是 {sim_new:.1f}。"]

    # 6. 时间
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(R.glob("*.json"))]
    slow = sorted((r for r in recs if r["cpu_seconds"] / r["seconds"] < 1), key=lambda r: -r["seconds"])
    L += ["", "## 6. 为什么跑了比预计长", "", "CPU 时间与墙钟时间的比值受线程数和调度影响；本复现默认一个线程，下面仅列比值小于 1 的任务，不据此推断异常原因。", "", "| 任务 | 墙钟秒 | CPU 秒 | 比例 |", "|---|---:|---:|---:|"]
    for r in slow:
        L.append(f"| {r['task']}-{r['kind']}-{r['cond']}-s{r['seed']} | {r['seconds']:.0f} | {r['cpu_seconds']:.0f} | {r['cpu_seconds'] / r['seconds']:.2f} |")
    L.append("")
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    (out / "numbers.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
