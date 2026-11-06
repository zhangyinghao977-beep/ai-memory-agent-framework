"""T7 报告：python -B report_t7.py <输出目录>。数字都从 receipts/、gate.json 和 T6 的回执生成。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
TASK_NAMES = {"anchor": "选和锚同包的（锚题）", "mutual": "选有同包支持的（互相支持题）"}
KIND_NAMES = {"attn": "attention", "pair": "成对比较", "sim": "晶格比较（6 个数）"}


def main() -> int:
    out = root_path(sys.argv[1])
    plan = load_run_plan(out, HERE / "PLAN.json")
    T6 = dependency_run(plan, "t6") / "receipts"
    gate = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))]
    cell = {(r["task"], r["kind"], r["sigma"], r["seed"]): r for r in recs}
    clean = plan["spec"]["member_offset"]
    seeds, sigmas, tasks, kinds = plan["seeds"], plan["sigmas"], plan["tasks"], plan["kinds"]
    for t in tasks:
        for k in kinds:
            for s in seeds:
                cell[(t, k, clean, s)] = json.loads((T6 / f"{t}-{k}-full-s{s}.json").read_text(encoding="utf-8"))
    levels = [clean, *sigmas]

    def vals(task, kind, sigma, split):
        return [100 * cell[(task, kind, sigma, s)][split]["choice_two"] for s in seeds if (task, kind, sigma, s) in cell]

    def cos(task, sigma, split):
        return 100 * gate["tasks"][task]["cosine"][str(sigma)][split]

    def avg(xs):
        return f"{sum(xs) / len(xs):.1f}" if xs else "—"

    def fmt(xs):
        return " / ".join(f"{x:.1f}" for x in xs) if xs else "—"

    done = len(recs) == frozen["jobs"]
    L = ["# T7 运行报告（自动生成；参考向量变模糊时，比较靠不靠得住）", "",
         f"- 完成任务：{len(recs)}/{frozen['jobs']}", f"- 门禁问题：{gate['problems'] or '没有'}",
         f"- 总训练时间：{sum(r['seconds'] for r in recs) / 3600:.2f} 小时（各工人相加）",
         f"- σ = {clean} 的数字读的是 T6 的回执。主要指标是两个候选的题上选对的比例，机会水平 50%。"]
    for t in tasks:
        for split, name in (("test_iid", "同一批包"), ("test_new", "没见过的包")):
            L += ["", f"## {TASK_NAMES[t]}：{name}（{len(seeds)} 个种子的平均）", "", "| 做法 | " + " | ".join(f"σ={x}" for x in levels) + " |", "|---|" + "---:|" * len(levels),
                  "| 余弦基线（不训练） | " + " | ".join(f"{cos(t, x, split):.1f}" for x in levels) + " |"]
            for k in kinds:
                L.append(f"| {KIND_NAMES[k]} | " + " | ".join(avg(vals(t, k, x, split)) for x in levels) + " |")
    L += ["", "## 每个种子", "", "| 题型 | 噪声 | 做法 | 同一批包 | 没见过的包 |", "|---|---:|---|---|---|"]
    for t in tasks:
        for x in sigmas:
            for k in kinds:
                L.append(f"| {t} | {x} | {KIND_NAMES[k]} | {fmt(vals(t, k, x, 'test_iid'))} | {fmt(vals(t, k, x, 'test_new'))} |")

    def verdict(ok):
        return "**成立**" if ok else "**不成立**"

    if done:
        n1 = [abs(v - cos(t, x, sp)) for t in tasks for x in sigmas for sp in ("test_iid", "test_new") for v in vals(t, "sim", x, sp)]
        n2 = [v - cos(t, x, "test_new") for t in tasks for x in sigmas for k in ("attn", "pair") for v in vals(t, k, x, "test_new")]
        n3 = [v - cos("mutual", 2.0, "test_iid") for v in vals("mutual", "pair", 2.0, "test_iid")]
        n4 = {(t, x): sum(a >= b for a, b in zip(vals(t, "sim", x, "test_new"), vals(t, "attn", x, "test_new"))) for t in tasks for x in sigmas}
        n5 = sum(a > b for a, b in zip(vals("mutual", "pair", 1.25, "test_iid"), vals("mutual", "attn", 1.25, "test_iid")))
        L += ["", "## 事先写下的预测", "",
              f"- **N1** 晶格比较跟着向量走：离基线最远 {max(n1):.1f} 点。{verdict(max(n1) <= 3)}",
              f"- **N2** 新包上，学来的比较赢不了余弦：最多比基线高 {max(n2):+.1f} 点。{verdict(max(n2) <= 2)}",
              f"- **N3** 见过的包上，学习能补上模糊（成对比较、互相支持题、σ=2.0，比基线高）：{' / '.join(f'{x:+.1f}' for x in n3)}。{verdict(sum(x >= 5 for x in n3) >= 4)}",
              "- **N4** 新包上，晶格比较不比 attention 差（不输的种子数）：" + "；".join(f"{t} σ={x} {c}/{len(seeds)}" for (t, x), c in n4.items()) + f"。{verdict(all(c >= 4 for c in n4.values()))}",
              f"- **N5** attention 比成对比较更受噪声影响（互相支持题、σ=1.25，成对比较更高的种子数）：{n5}/{len(seeds)}。{verdict(n5 >= 4)}"]
    else:
        L += ["", "还没跑完，不判定预测。"]
    if recs:
        L += ["", "## 契约（按构造必然，不算发现）", "", f"- 给规则时一个候选的题，最低 {100 * min(r['test_iid']['choice_one'] for r in recs):.1f}%。", "- 题和答案比特在各档噪声下一样，见 `project/tests/test_t7.py`。"]
    L += ["", "## 限制", "",
          "- 只试了一种噪声：每个对象固定的偏移。对象被放错包、每次观察都不一样的噪声，都没有测。",
          "- 向量是人给的，不是 KA 长出来的。",
          "- 不能说明有没有比 attention 更好的算法。",
          "- 受控合成任务，很小的模型，超参数没有分别调。",
          "- 这个实验不测量势 Φ 和事件链的熵。", ""]
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    print(f"report: {len(recs)}/{frozen['jobs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
