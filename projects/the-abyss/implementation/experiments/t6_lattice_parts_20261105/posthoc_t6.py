"""T6 事后读法：python -B posthoc_t6.py <run 目录> <输出目录>。

只读 T6 和 T5 的回执，不训练，不加载模型。这些问题是看到结果以后才问的，不算预测。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
TASK_NAMES = {"anchor": "锚题", "mutual": "互相支持题"}
ARMS = (("attn", "full", "attention"), ("pair", "full", "成对比较"), ("sim", "full", "晶格比较"), ("mean", "full", "平均交流"), ("attn", "vec", "attention，只给参考向量"))
LEARNED = 90.0
MOVED = 10.0


def main() -> int:
    run, out = root_path(sys.argv[1]), root_path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=False)
    plan = load_run_plan(run, HERE / "PLAN.json")
    T5 = dependency_run(plan, "t5") / "receipts"
    cell = {}
    for p in sorted((run / "receipts").glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        cell[(r["task"], r["kind"], r["part"], r["seed"])] = r
    seeds = plan["seeds"]

    def dev(task, kind, part, seed):
        return {c["step"]: 100 * c["dev_choice_two"] for c in cell[(task, kind, part, seed)]["curve"]}

    def test(task, kind, part, seed, split):
        return 100 * cell[(task, kind, part, seed)][split]["choice_two"]

    def first(curve):
        return next((s for s in sorted(curve) if curve[s] >= LEARNED), None)

    res: dict = {"speed": [], "seed1": {}, "t5_no_product": {}}
    L = ["# T6 事后读法（看到结果以后才问的，不算预测）", "",
         "只读回执，没有训练，也没有加载模型。数字由 `posthoc_t6.py` 生成。", "",
         "## 一、P4 的判定要小心读", ""]
    c1 = dev("mutual", "attn", "full", 1)
    marks = [s for s in sorted(c1) if s % 6000 == 0]
    final = test("mutual", "attn", "full", 1, "test_iid")
    moved = c1[max(c1)] - c1[24000]
    res["seed1"] = {"dev": c1, "test_iid": final, "moved_after_24000": moved}
    L += ["| 步数 | " + " | ".join(str(s) for s in marks) + " |", "|---|" + "---:|" * len(marks),
          "| dev | " + " | ".join(f"{c1[s]:.0f}" for s in marks) + " |", "",
          f"冻结的线是 90%。种子 1 的 `test_iid` 是 {final:.1f}%，所以 P4 按线判定是“{'成立' if final < LEARNED else '不成立'}”。"]
    if moved >= MOVED:
        L.append(f"但 24000 步以后它又涨了 {moved:.1f} 点。所以“卡住了”这个说法不对，它更像是很慢。按线判定的结果不能当成“卡住”的证据。")
    else:
        L.append(f"24000 步以后它只涨了 {moved:.1f} 点。")
    L += ["", "## 二、快慢和新包", "",
          f"“过 {LEARNED:.0f}%”是每个种子第一次到 {LEARNED:.0f}% 的检查点（dev，每 3000 步看一次）。", "",
          f"| 题型 | 做法 | 过 {LEARNED:.0f}% | 同一批包平均 | 没见过的包平均 | 差距平均 |", "|---|---|---|---:|---:|---:|"]
    for task in plan["tasks"]:
        for kind, part, name in ARMS:
            f = [first(dev(task, kind, part, s)) for s in seeds]
            iid = [test(task, kind, part, s, "test_iid") for s in seeds]
            new = [test(task, kind, part, s, "test_new") for s in seeds]
            a, b = sum(iid) / len(iid), sum(new) / len(new)
            res["speed"].append({"task": task, "kind": kind, "part": part, "first_over": f, "iid": iid, "new": new})
            L.append(f"| {TASK_NAMES[task]} | {name} | {' / '.join(str(x) if x else '没到' for x in f)} | {a:.1f} | {b:.1f} | {a - b:.1f} |")

    def mean_of(task, kind, split):
        xs = [test(task, kind, "full", s, split) for s in seeds]
        return sum(xs) / len(xs)

    pa, at = mean_of("mutual", "pair", "test_new"), mean_of("mutual", "attn", "test_new")
    L += ["", f"互相支持题上，没见过的包：成对比较平均 {pa:.1f}%，attention 平均 {at:.1f}%。"
          + ("成对比较学得快，但在新包上更差，所以不能说它全面更好。" if pa < at else "成对比较在新包上也不差。"), "",
          "## 三、学得好的做法有什么共同点（事后的工作假设）", "",
          "互相支持题、全给晶格。“相乘”指的是模型结构里有没有两个 token 直接相乘这一步。", "",
          "| 做法 | 来源 | 两个 token 直接相乘 | 同一批包（最低–最高） |", "|---|---|---|---:|"]
    for kind, name, product in (("sim", "晶格比较", "有（固定余弦）"), ("pair", "成对比较", "有（没有 softmax）"), ("attn", "attention", "有（Q·K）"), ("mean", "平均交流", "没有")):
        xs = [test("mutual", kind, "full", s, "test_iid") for s in seeds]
        L.append(f"| {name} | T6，72000 步 | {product} | {min(xs):.1f}–{max(xs):.1f} |")
    for kind, name in (("flat_big", "大 MLP"), ("flat", "摊平 MLP"), ("token", "不交流")):
        xs = [100 * json.loads((T5 / f"mutual-{kind}-L1-s{s}.json").read_text(encoding="utf-8"))["test_iid"]["choice_two"] for s in (0, 1, 2)]
        res["t5_no_product"][kind] = xs
        L.append(f"| {name} | T5，24000 步 | 没有 | {min(xs):.1f}–{max(xs):.1f} |")
    L += ["", "这只是看到结果以后的观察，没有单独测过。T5 的三行步数更少，只有 3 个种子。", "",
          "## 四、这份读法说明不了什么", "",
          "- 没有看模型内部。种子 1 为什么慢、成对比较为什么在新包上差，都不知道。",
          "- 成对比较的结构和 attention 很近：去掉了 softmax，留下了相乘。",
          "- 晶格比较用的向量很干净：同包的余弦很高。向量有噪声时会怎样，没有测。",
          "- 只给参考向量的做法只试了 attention，没有试成对比较。", ""]
    (out / "RESULT.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    print("done", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
