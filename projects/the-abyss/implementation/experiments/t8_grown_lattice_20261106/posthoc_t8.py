"""T8 事后分析：python -B posthoc_t8.py <输出目录>。只读回执，不训练。

这不是事先写下的预测，是看了报告以后才想问的：
M4 里 attention 没到线，是因为向量是长出来的，还是因为 T8 只跑 48000 步（T6 是 72000 步）？
做法：和 T6 的干净向量比同样的步数。两边的向量不同，所以这只是比较，不是对照实验。
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


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dev_at(r: dict, step: int) -> float:
    return 100 * next(c for c in r["curve"] if c["step"] == step)["dev_choice_two"]


def main() -> int:
    out = root_path(sys.argv[1])
    plan = load_run_plan(out, HERE / "PLAN.json")
    T6 = dependency_run(plan, "t6")
    seeds, steps = plan["seeds"], plan["steps"]
    marks = [12000, 24000, 36000, steps]
    head = "| 向量 | 做法 | 种子 | " + " | ".join(f"{m} 步" for m in marks) + " | 最后 12000 步涨了 | T6 的 72000 步 | train_loss |"
    L = ["# T8 事后分析（看了结果才问的，不是预测）", "", "- 只读回执，没有训练。互相支持题，dev 选对的比例。",
         "- `train_loss` 是最后 5 个记录点的平均。", "- 长出来的向量和 T6 的干净向量不同，种子相同不代表起点相同。这只是比较，不是对照实验。", "",
         "## 互相支持题：每个种子的 dev", "", head, "|---|---|---:|" + "---:|" * len(marks) + "---:|---:|---:|"]
    rising = {}
    for k in KIND_NAMES:
        for s in seeds:
            for name, r in (("长出来", load(out / "receipts" / f"mutual-{k}-full-s{s}.json")),
                            ("T6 干净", load(T6 / "receipts" / f"mutual-{k}-full-s{s}.json"))):
                d = [dev_at(r, m) for m in marks]
                gain = d[-1] - d[-2]
                loss = sum(c["train_loss"] for c in r["curve"][-5:]) / 5
                last = f"{dev_at(r, 72000):.1f}" if name == "T6 干净" else "—"
                L.append(f"| {name} | {KIND_NAMES[k]} | {s} | " + " | ".join(f"{x:.1f}" for x in d) + f" | {gain:+.1f} | {last} | {loss:.3f} |")
                if name == "长出来":
                    rising[(k, s)] = gain > RISING
    n = sum(v for (k, _), v in rising.items() if k == "attn")
    L += ["", f"- 长出来的向量上，attention 有 {n}/{len(seeds)} 个种子在最后 12000 步涨了超过 {RISING} 点。"]
    posthoc = root_path(sys.argv[2]) if len(sys.argv) > 2 else root_path(out.parent / "posthoc_reproduction")
    posthoc.mkdir(parents=True, exist_ok=False)
    (posthoc / "REPORT.zh.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
