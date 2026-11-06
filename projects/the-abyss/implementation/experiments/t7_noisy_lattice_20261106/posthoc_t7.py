"""T7 事后分析：python -B posthoc_t7.py <输出目录>。只读回执，不训练。

这不是事先写下的预测，是看了报告以后才想问的两件事：
1. 学来的比较掉分时，是学不会，还是步数不够（dev 到最后还在涨吗）？
2. 见过的包比余弦基线高时，高出来的部分能带到没见过的包吗？
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
KIND_NAMES = {"attn": "attention", "pair": "成对比较"}
RISING = 1.0


def main() -> int:
    out = root_path(sys.argv[1])
    plan = load_run_plan(out, HERE / "PLAN.json")
    gate = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))]
    cell = {(r["task"], r["kind"], r["sigma"], r["seed"]): r for r in recs}
    steps = plan["steps"]
    marks = [steps // 6, steps // 3, 2 * steps // 3, 5 * steps // 6, steps]

    def dev_at(r, step):
        return 100 * min(r["curve"], key=lambda c: abs(c["step"] - step))["dev_choice_two"]

    def mean(xs):
        return sum(xs) / len(xs)

    L = ["# T7 事后分析（看了结果才问的，不是预测）", "", "- 读取指定复现运行的 receipts，没有训练。",
         f"- “还在涨”：最后 {steps // 6} 步里，dev 的 5 个种子平均涨了超过 {RISING} 点。",
         "- `train_loss` 是最后 5 个记录点的平均，5 个种子再平均。", "",
         "## 1. dev 的走向（5 个种子平均）", "",
         "| 题型 | 噪声 | 做法 | " + " | ".join(f"{m} 步" for m in marks) + " | 最后一段涨了 | 还在涨吗 | train_loss |",
         "|---|---:|---|" + "---:|" * len(marks) + "---:|---|---:|"]
    for t in plan["tasks"]:
        for n in plan["sigmas"]:
            for k in KIND_NAMES:
                rs = [cell[(t, k, n, s)] for s in plan["seeds"]]
                dev = [mean([dev_at(r, m) for r in rs]) for m in marks]
                loss = mean([mean([c["train_loss"] for c in r["curve"][-5:]]) for r in rs])
                gain = dev[-1] - dev[-2]
                L.append(f"| {t} | {n} | {KIND_NAMES[k]} | " + " | ".join(f"{x:.1f}" for x in dev) + f" | {gain:+.1f} | {'是' if gain > RISING else '否'} | {loss:.3f} |")

    L += ["", "## 2. 比余弦基线高的部分，能不能带到没见过的包（5 个种子平均）", "",
          "| 题型 | 噪声 | 做法 | 同一批包比基线 | 没见过的包比基线 |", "|---|---:|---|---:|---:|"]
    for t in plan["tasks"]:
        for n in plan["sigmas"]:
            cos = gate["tasks"][t]["cosine"][str(n)]
            for k in KIND_NAMES:
                rs = [cell[(t, k, n, s)] for s in plan["seeds"]]
                iid = mean([100 * r["test_iid"]["choice_two"] for r in rs]) - 100 * cos["test_iid"]
                new = mean([100 * r["test_new"]["choice_two"] for r in rs]) - 100 * cos["test_new"]
                L.append(f"| {t} | {n} | {KIND_NAMES[k]} | {iid:+.1f} | {new:+.1f} |")
    posthoc = root_path(sys.argv[2]) if len(sys.argv) > 2 else root_path(out.parent / "posthoc_reproduction")
    posthoc.mkdir(parents=True, exist_ok=False)
    (posthoc / "REPORT.zh.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
