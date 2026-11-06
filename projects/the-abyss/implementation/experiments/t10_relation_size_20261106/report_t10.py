"""T10 报告：python -B report_t10.py <输出目录>。数字都从 receipts/ 和 gate.json 生成。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
TASK_NAMES = {"anchor": "选和锚同包的（锚题）", "mutual": "选有同包支持的（互相支持题）"}
KIND_NAMES = {"pair": "成对比较", "attn": "attention"}
ARM_NAMES = {"t8": "T8（人给规则，两个标记）", "t9": "T9（嵌入乘 1）", "quarter": "`quarter`（乘 0.25）", "zero": "`zero`（从零开始）", "off": "`off`（没有这部分输入）"}


def mean(xs: list) -> float:
    return sum(xs) / len(xs)


def main() -> int:
    out = root_path(sys.argv[1])
    plan = load_run_plan(out, HERE / "PLAN.json")
    T8 = dependency_run(plan, "t8") / "receipts"
    T9 = dependency_run(plan, "t9") / "receipts"
    gate = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))]
    cell = {(r["task"], r["kind"], r["arm"], r["seed"]): r for r in recs}
    seeds, tasks, kinds = plan["seeds"], plan["tasks"], plan["kinds"]
    done = len(recs) == frozen["jobs"]

    def got(task, kind, arm):
        if arm == "t9":
            return [json.loads((T9 / f"{task}-{kind}-all-s{s}.json").read_text(encoding="utf-8")) for s in seeds]
        if arm == "t8":
            return [json.loads((T8 / f"{task}-{kind}-full-s{s}.json").read_text(encoding="utf-8")) for s in seeds]
        return [cell[(task, kind, arm, s)] for s in seeds if (task, kind, arm, s) in cell]

    def vals(task, kind, arm, split="test_iid", key="choice_two"):
        return [100 * r[split][key] for r in got(task, kind, arm)]

    def fmt(xs):
        return " / ".join(f"{x:.1f}" for x in xs) if xs else "—"

    def block(task, kind, arm, name, n):
        return [100 * mean([x["choice_two"] for x in r[name][n]]) for r in got(task, kind, arm)]

    def avg(xs):
        return f"{mean(xs):.1f}" if xs else "—"

    def arms(t):
        return ["t8", "t9", "quarter", "zero"] + (["off"] if t in plan["arms"]["off"]["tasks"] else [])

    L = ["# T10 运行报告（自动生成；只改关系嵌入开始时的大小）", "", f"- 完成任务：{len(recs)}/{frozen['jobs']}", f"- 门禁问题：{gate['problems'] or '没有'}",
         f"- 总训练时间：{sum(r['seconds'] for r in recs) / 3600:.2f} 小时（各工人相加）",
         "- 主要指标是两个候选的题上选对的比例，机会水平 50%。T8、T9 的数字来自它们的回执。"]
    for t in tasks:
        L += ["", f"## {TASK_NAMES[t]}", "", "| 做法 | 关系嵌入 | 同一批包 | 平均 | 没见过的包 | 平均 |", "|---|---|---|---:|---|---:|"]
        for k in kinds:
            for a in arms(t):
                i, n = vals(t, k, a), vals(t, k, a, "test_new")
                L.append(f"| {KIND_NAMES[k]} | {ARM_NAMES[a]} | {fmt(i)} | {avg(i)} | {fmt(n)} | {avg(n)} |")

    at = [0, 3, 7, 15]
    L += ["", "## dev 成绩（训练 3000、12000、24000、48000 步，5 个种子平均）", "", "| 题型 | 做法 | 关系嵌入 | 3000 | 12000 | 24000 | 48000 |", "|---|---|---|---:|---:|---:|---:|"]
    for t in tasks:
        for k in kinds:
            for a in arms(t):
                rs = got(t, k, a)
                if rs:
                    L.append(f"| {t} | {KIND_NAMES[k]} | {ARM_NAMES[a]} | " + " | ".join(f"{mean([100 * r['curve'][i]['dev_choice_two'] for r in rs]):.1f}" for i in at) + " |")

    L += ["", "## 训练结束时第一层的两部分（均方根，5 个种子平均）", "", "| 题型 | 做法 | 关系嵌入 | 来自关系嵌入 | 来自参考向量 |", "|---|---|---|---:|---:|"]
    for t in tasks:
        for k in kinds:
            for a in arms(t)[2:]:
                rs = got(t, k, a)
                if rs:
                    L.append(f"| {t} | {KIND_NAMES[k]} | {ARM_NAMES[a]} | {mean([r['sizes_end']['rel'] for r in rs]):.2f} | {mean([r['sizes_end']['vec'] for r in rs]):.2f} |")

    news = plan["shift"]["new_chains"]
    L += ["", f"## 世界变了：只换表，不重新训练（窗口 {plan['shift']['window']} 条，5 个种子平均，每种 8 段）", "",
          "| 题型 | 做法 | 关系嵌入 | 世界没变，256 条链 | " + " | ".join(f"新链 {n} 条" for n in news) + " |", "|---|---|---|---:|" + "---:|" * len(news)]
    for t in tasks:
        for k in kinds:
            for a in arms(t)[1:]:
                if got(t, k, a):
                    L.append(f"| {t} | {KIND_NAMES[k]} | {ARM_NAMES[a]} | {avg(block(t, k, a, 'sweep', '256'))} | " + " | ".join(avg(block(t, k, a, "shift", str(n))) for n in news) + " |")

    def verdict(ok):
        return "**成立**" if ok else "**不成立**"

    if done:
        s1, s2 = vals("mutual", "pair", "zero"), vals("mutual", "attn", "zero")
        t9m, qm, zm, om = (mean(vals("mutual", "pair", a)) for a in ("t9", "quarter", "zero", "off"))
        s4 = vals("mutual", "pair", "off")
        s5p, s5a = vals("anchor", "pair", "zero"), vals("anchor", "attn", "zero")
        s6 = {t: (mean(block(t, "pair", "zero", "sweep", "256")), mean(block(t, "pair", "zero", "shift", "256"))) for t in tasks}
        s7 = vals("mutual", "pair", "zero", "test_new")
        L += ["", "## 事先写下的预测", "",
              f"- **S1** 从零开始，成对比较回到 T8 的水平：{fmt(s1)}。{verdict(sum(x >= 95 for x in s1) >= 4)}",
              f"- **S2** 从零开始，attention 离开 50%：{fmt(s2)}，平均 {mean(s2):.1f}。{verdict(sum(x >= 60 for x in s2) >= 4 and mean(s2) >= 65)}",
              f"- **S3** 是大小的问题（T9 / `quarter` / `zero` 的平均）：{t9m:.1f} / {qm:.1f} / {zm:.1f}。{verdict(qm >= t9m + 10 and zm >= qm - 2)}",
              f"- **S4** 没有这部分输入时也一样：{fmt(s4)}，平均 {om:.1f}，和 `zero` 差 {abs(om - zm):.1f}。{verdict(sum(x >= 95 for x in s4) >= 4 and abs(om - zm) < 3)}",
              f"- **S5** 从零开始也能学到谁是锚：成对比较 {fmt(s5p)}；attention {fmt(s5a)}。{verdict(sum(x >= 95 for x in s5p) >= 4 and sum(x >= 95 for x in s5a) >= 4)}",
              "- **S6** 学来的比较也能换表（世界没变 → 世界变了）：" + "；".join(f"{t} {a:.1f} → {b:.1f}" for t, (a, b) in s6.items()) + f"。{verdict(all(b >= a - 3 for a, b in s6.values()))}",
              f"- **S7** 这不解决没见过的包：{fmt(s7)}，平均 {mean(s7):.1f}。{verdict(mean(s7) <= 85)}"]
    else:
        L += ["", "还没跑完，不判定预测。"]
    L += ["", "## 契约（按构造必然，不算发现）", "",
          "- 门禁实跑 3000 步，乘 1 和 T9 逐位相同：" + "，".join(f"{t} {k} {gate['tasks'][t]['same_as_t9_' + k]}" for t in tasks for k in kinds) + "。",
          "- 训练链里锚关系的次数：" + "，".join(f"{t} {gate['tasks'][t]['anchor_events']}" for t in tasks) + "。",
          "- 除了 `rel.weight`，开始时的权重和 T9 一样；`off` 的嵌入一直是 0：见 `project/tests/test_t10.py`。",
          "", "## 限制", "",
          "- 不解释为什么大小会有影响。只试了三种大小，没有调别的超参数。",
          "- 把大小调小是看了 T9 的结果才想到的，是针对这份题的修补，不是通用的做法。",
          "- T9 的限制都还在：比较器的结构、长规则的公式、窗口大小都是人写的。规则只是查询和关系的对应。系统不会发现世界变了。只长了求同，没有长存异。",
          "- 受控合成任务，很小的模型。这个实验不测量势 Φ 和事件链的熵。", ""]
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    print(f"report: {len(recs)}/{frozen['jobs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
