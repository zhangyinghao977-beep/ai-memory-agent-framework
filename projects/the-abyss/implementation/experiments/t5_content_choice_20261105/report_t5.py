"""T5 报告：python -B report_t5.py <输出目录>。所有数字都从 receipts/ 和 gate.json 生成。"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
TASK_NAMES = {"position": "选后面的（位置题）", "anchor": "选和锚同包的（锚题）", "mutual": "选有同包支持的（互相支持题）"}
KIND_NAMES = {"attn": "attention", "mean": "平均交流", "token": "不交流", "flat": "摊平 MLP", "flat_big": "大 MLP"}


def wilson(k: int, n: int) -> tuple:
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


def main() -> int:
    out = root_path(sys.argv[1])
    plan = load_run_plan(out, HERE / "PLAN.json")
    gate = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))]
    cell = {(r["task"], r["kind"], r["lattice"], r["seed"]): r for r in recs}
    seeds = plan["seeds"]
    th = plan["thresholds"]

    def vals(task, kind, lattice, split="test_iid", key="choice_two"):
        return [100 * cell[(task, kind, lattice, s)][split][key] for s in seeds if (task, kind, lattice, s) in cell]

    def fmt(xs):
        return " / ".join(f"{x:.1f}" for x in xs) if xs else "—"

    done = len(recs) == frozen["jobs"]
    L = ["# T5 运行报告（自动生成；选择靠内容，晶格 × attention）", "",
         f"- 完成任务：{len(recs)}/{frozen['jobs']}", f"- 门禁问题：{gate['problems'] or '没有'}",
         f"- 总训练时间：{sum(r['seconds'] for r in recs) / 3600:.2f} 小时（各工人相加）",
         "- 格子里是三个种子的数字。主要指标是两个候选的题上选对的比例，机会水平 50%。", "",
         "## 基线（test_iid，两个候选的题）", "", "| 题型 | 永远选后面 | 永远选前面 | 只看对象 | 人写的规则 |", "|---|---:|---:|---:|---:|"]
    for t in plan["tasks"]:
        b = gate["tasks"][t]["baselines"]["test_iid"]
        L.append(f"| {TASK_NAMES[t]} | {100 * b['pick_last']:.1f}% | {100 * b['pick_first']:.1f}% | {100 * b['object_prior']:.1f}% | {100 * b['rule_ref']:.1f}% |")
    for t in plan["tasks"]:
        L += ["", f"## {TASK_NAMES[t]}", "", "| 晶格 | 做法 | 参数 | 同一批包 | 没见过的包 | 一个候选 | 答案全部 | 过 90% 的种子 |", "|---|---|---:|---|---|---|---|---:|"]
        for a in plan["arms"]:
            k, lat = a["kind"], a["lattice"]
            xs = vals(t, k, lat)
            params = next((cell[(t, k, lat, s)]["params"] for s in seeds if (t, k, lat, s) in cell), 0)
            L.append(f"| {'有' if lat else '没有'} | {KIND_NAMES[k]} | {params:,} | {fmt(xs)} | {fmt(vals(t, k, lat, 'test_new'))} | "
                     f"{fmt(vals(t, k, lat, 'test_iid', 'choice_one'))} | {fmt(vals(t, k, lat, 'test_iid', 'answer_all'))} | {sum(x > 90 for x in xs)}/{len(xs)} |")
    L += ["", "## 学习曲线（dev，种子 0，两个候选的题）", "", "| 题型 | 晶格 | 做法 | " + " | ".join(str(s) for s in range(plan["eval_every"], plan["steps"] + 1, plan["eval_every"])) + " |",
          "|---|---|---|" + "---:|" * (plan["steps"] // plan["eval_every"])]
    for t in plan["tasks"]:
        for a in plan["arms"]:
            r = cell.get((t, a["kind"], a["lattice"], seeds[0]))
            if r:
                L.append(f"| {t} | {'有' if a['lattice'] else '没有'} | {KIND_NAMES[a['kind']]} | " + " | ".join(f"{100 * c['dev_choice_two']:.0f}" for c in r["curve"]) + " |")

    def verdict(ok):
        return "**成立**" if ok else "**不成立**"

    if done:
        p1 = vals("position", "token", True)
        p2a = vals("mutual", "attn", True)
        p2o = {k: vals("mutual", k, True) for k in ("mean", "flat", "flat_big")}
        p3 = vals("mutual", "attn", True, "test_new")
        p4 = vals("mutual", "attn", False)
        p5 = vals("anchor", "mean", True)
        L += ["", "## 事先写下的预测", "",
              f"- **P1** 位置题不需要交流（有晶格、不交流）：{fmt(p1)}。{verdict(all(x >= th['high'] for x in p1))}",
              f"- **P2** 互相支持题只有 attention 学得会（有晶格）：attention {fmt(p2a)}；" + "；".join(f"{KIND_NAMES[k]} {fmt(v)}" for k, v in p2o.items())
              + f"。{verdict(all(x >= th['high'] for x in p2a) and all(x <= th['low'] for v in p2o.values() for x in v))}",
              f"- **P3** 比较能用到没见过的包（有晶格、attention）：{fmt(p3)}。{verdict(all(x >= th['new_package_high'] for x in p3))}",
              f"- **P4** 没有晶格，同样的预算学不会（attention）：{fmt(p4)}。{verdict(all(x <= th['low'] for x in p4))}",
              f"- **P5** 有固定的锚时平均交流就够（有晶格）：{fmt(p5)}。{verdict(all(x >= th['anchor_mean_high'] for x in p5))}"]
        lo, hi = wilson(cell[("mutual", "attn", True, seeds[0])]["test_iid"]["right_two"], cell[("mutual", "attn", True, seeds[0])]["test_iid"]["n_two"])
        L += ["", f"单个格子的 95% 区间大约是这么宽：互相支持题、attention、种子 {seeds[0]}：{lo:.1f}%–{hi:.1f}%。"]
    else:
        L += ["", "还没跑完，不判定预测。"]
    L += ["", "## 契约（按构造必然，不算发现）", "",
          "- 有晶格时一个候选的题一定选对。",
          "- 不交流的做法在锚题和互相支持题上只能在 50% 附近。",
          "- 没有晶格时，没见过的包的嵌入没训练过，答不好是必然的。", "",
          "## 限制", "",
          "- 不能证明 attention 是必须的：人写的规则就是 100%。这里说的只是规则要由系统自己学时，哪种做法学得会。",
          "- 没有穷尽别的结构；所有做法用同一套超参数，没有分别调；更多步数可能有不同结果。",
          "- 步数是看 attention 在开发时学会才定的，这对 attention 有利。",
          "- 受控合成任务，很小的模型。晶格是人给的，向量是随机生成的。",
          "- 题型是工作解释。这个实验不测量势 Φ 和事件链的熵。", ""]
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    print(f"报告写好：{len(recs)}/{frozen['jobs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
