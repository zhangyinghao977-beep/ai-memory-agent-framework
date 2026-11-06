"""T6 报告：python -B report_t6.py <输出目录>。所有数字都从 receipts/、gate.json 和 T5 的回执生成。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
TASK_NAMES = {"anchor": "选和锚同包的（锚题）", "mutual": "选有同包支持的（互相支持题）"}
KIND_NAMES = {"attn": "attention", "mean": "平均交流", "pair": "成对比较（没有 softmax）", "sim": "晶格比较（6 个数）"}
PART_NAMES = {"full": "全给", "vec": "只给参考向量", "rule": "只给规则", "none": "都不给"}


def main() -> int:
    out = root_path(sys.argv[1])
    plan = load_run_plan(out, HERE / "PLAN.json")
    T5_RECEIPTS = dependency_run(plan, "t5") / "receipts"
    gate = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))]
    cell = {(r["task"], r["kind"], r["part"], r["seed"]): r for r in recs}
    seeds, th, every = plan["seeds"], plan["thresholds"], plan["eval_every"]

    def vals(task, kind, part, split="test_iid", key="choice_two"):
        return [100 * cell[(task, kind, part, s)][split][key] for s in seeds if (task, kind, part, s) in cell]

    def fmt(xs):
        return " / ".join(f"{x:.1f}" for x in xs) if xs else "—"

    done = len(recs) == frozen["jobs"]
    L = ["# T6 运行报告（自动生成；拆开晶格，多跑步数，试不是 attention 的比较）", "",
         f"- 完成任务：{len(recs)}/{frozen['jobs']}", f"- 门禁问题：{gate['problems'] or '没有'}",
         f"- 总训练时间：{sum(r['seconds'] for r in recs) / 3600:.2f} 小时（各工人相加）",
         f"- 格子里是 {len(seeds)} 个种子的数字。主要指标是两个候选的题上选对的比例，机会水平 50%。", "",
         "## 基线（test_iid，两个候选的题）", "", "| 题型 | 永远选后面 | 永远选前面 | 只看对象 | 人写的规则 |", "|---|---:|---:|---:|---:|"]
    for t in plan["tasks"]:
        b = gate["tasks"][t]["baselines"]["test_iid"]
        L.append(f"| {TASK_NAMES[t]} | {100 * b['pick_last']:.1f}% | {100 * b['pick_first']:.1f}% | {100 * b['object_prior']:.1f}% | {100 * b['rule_ref']:.1f}% |")
    for t in plan["tasks"]:
        L += ["", f"## {TASK_NAMES[t]}", "", f"| 做法 | 晶格 | 参数 | 同一批包 | 没见过的包 | 一个候选 | 过 {th['learned']:.0f}% 的种子 |", "|---|---|---:|---|---|---|---:|"]
        for a in plan["arms"]:
            k, p = a["kind"], a["part"]
            xs = vals(t, k, p)
            params = next((cell[(t, k, p, s)]["params"] for s in seeds if (t, k, p, s) in cell), 0)
            L.append(f"| {KIND_NAMES[k]} | {PART_NAMES[p]} | {params:,} | {fmt(xs)} | {fmt(vals(t, k, p, 'test_new'))} | "
                     f"{fmt(vals(t, k, p, 'test_iid', 'choice_one'))} | {sum(x >= th['learned'] for x in xs)}/{len(xs)} |")
    marks = [s for s in range(every, plan["steps"] + 1, every) if s % (4 * every) == 0 or s == every]
    L += ["", "## 学习曲线（dev，两个候选的题）", "", "| 题型 | 做法 | 晶格 | 种子 | " + " | ".join(str(s) for s in marks) + " |", "|---|---|---|---:|" + "---:|" * len(marks)]
    for t in plan["tasks"]:
        for a in plan["arms"]:
            for s in seeds:
                r = cell.get((t, a["kind"], a["part"], s))
                if r:
                    by = {c["step"]: c["dev_choice_two"] for c in r["curve"]}
                    L.append(f"| {t} | {KIND_NAMES[a['kind']]} | {PART_NAMES[a['part']]} | {s} | " + " | ".join(f"{100 * by[m]:.0f}" for m in marks) + " |")

    def verdict(ok):
        return "**成立**" if ok else "**不成立**"

    def count(xs, limit):
        return sum(x >= limit for x in xs)

    if done:
        p1 = {t: vals(t, "attn", "vec") for t in plan["tasks"]}
        p2 = {t: vals(t, "attn", "rule") for t in plan["tasks"]}
        p3 = {t: vals(t, "attn", "none") for t in plan["tasks"]}
        p4 = 100 * cell[("mutual", "attn", "full", 1)]["test_iid"]["choice_two"]
        p5, p6, p7 = vals("anchor", "mean", "full"), vals("mutual", "mean", "full"), vals("mutual", "pair", "full")
        p8 = {(t, sp): vals(t, "sim", "full", sp) for t in plan["tasks"] for sp in ("test_iid", "test_new")}

        def two(d):
            return "；".join(f"{TASK_NAMES[t]} {fmt(v)}" for t, v in d.items())

        L += ["", "## 事先写下的预测", "",
              f"- **P1** 只给参考向量也学得会：{two(p1)}。{verdict(all(count(v, th['learned']) >= 3 for v in p1.values()))}",
              f"- **P2** 只给规则学不会：{two(p2)}。{verdict(all(x <= th['low'] for v in p2.values() for x in v))}",
              f"- **P3** 什么都不给，3 倍步数也学不会：{two(p3)}。{verdict(all(x <= th['low'] for v in p3.values() for x in v))}",
              f"- **P4** 种子 1 是卡住了（互相支持题、attention、全给、种子 1）：{p4:.1f}。{verdict(p4 < th['learned'])}",
              f"- **P5** 平均交流在锚题上只是慢：{fmt(p5)}。{verdict(count(p5, th['learned']) >= 4)}",
              f"- **P6** 平均交流在互相支持题上学不会：{fmt(p6)}。{verdict(all(x <= th['low'] for x in p6))}",
              f"- **P7** 不用 softmax 也学得会比较：{fmt(p7)}。{verdict(count(p7, th['high']) >= 4)}",
              "- **P8** 比较可以由晶格给：" + "；".join(f"{t} {sp} {fmt(v)}" for (t, sp), v in p8.items())
              + f"。{verdict(all(x >= th['exact'] for v in p8.values() for x in v))}"]
    else:
        L += ["", "还没跑完，不判定预测。"]

    L += ["", "## 契约（按构造必然，不算发现）", ""]
    ruled = [r for r in recs if r["part"] in ("full", "rule")]
    if ruled:
        L.append(f"- 给规则时一个候选的题，最低 {100 * min(r['test_iid']['choice_one'] for r in ruled):.1f}%。")
    same = total = 0
    worst = 0.0
    for r in recs:
        if r["kind"] not in ("attn", "mean") or r["part"] not in ("full", "none") or r["seed"] > 2:
            continue
        p = T5_RECEIPTS / f"{r['task']}-{r['kind']}-L{int(r['part'] == 'full')}-s{r['seed']}.json"
        old = json.loads(p.read_text(encoding="utf-8"))["curve"]
        new = {c["step"]: c["dev_choice_two"] for c in r["curve"]}
        gaps = [abs(c["dev_choice_two"] - new[c["step"]]) for c in old]
        total += 1
        same += max(gaps) == 0
        worst = max(worst, 100 * max(gaps))
    L.append(f"- 和 T5 走同一条路：{same}/{total} 个任务前 24000 步的 dev 完全一样，最大差 {worst:.2f} 点。")
    L += ["- `rule`、`none` 在没见过的包上靠内容选不了：新包的嵌入没训练过。", "",
          "## 限制", "",
          "- 不能说明有没有比 attention 更好的算法：这里只试了两种，`sim` 的结构是人按题目写的。",
          "- 不能证明 attention 是必须的或不必须的：人写的规则就是 100%。",
          "- 所有做法用同一套超参数，没有分别调；更多步数可能有不同结果。",
          "- 受控合成任务，很小的模型。晶格是人给的，向量是随机生成的。",
          "- 题型是工作解释。这个实验不测量势 Φ 和事件链的熵。", ""]
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    print(f"报告写好：{len(recs)}/{frozen['jobs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
