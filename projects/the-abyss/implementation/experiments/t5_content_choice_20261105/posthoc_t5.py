"""T5 事后读法：python -B posthoc_t5.py <run 目录> <输出目录>。

只读 receipts/，不训练，不加载模型。这些问题是看到结果以后才问的，不算预测。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
KIND_NAMES = {"attn": "attention", "mean": "平均交流", "token": "不交流", "flat": "摊平 MLP", "flat_big": "大 MLP"}
TASK_NAMES = {"position": "位置题", "anchor": "锚题", "mutual": "互相支持题"}
LEARNED = 80.0
RISING = 2.0


def main() -> int:
    run, out = root_path(sys.argv[1]), root_path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=False)
    plan = load_run_plan(run, HERE / "PLAN.json")
    paths = sorted((run / "receipts").glob("*.json"))
    cell = {}
    for p in paths:
        r = json.loads(p.read_text(encoding="utf-8"))
        cell[(r["task"], r["kind"], r["lattice"], r["seed"])] = r
    seeds, every = plan["seeds"], plan["eval_every"]

    def pct(task, kind, lattice, seed, split="test_iid", key="choice_two"):
        return 100 * cell[(task, kind, lattice, seed)][split][key]

    res: dict = {"curves": [], "new_gap": [], "no_lattice": [], "no_lattice_position_new": {}}
    steps = list(range(every, plan["steps"] + 1, every))
    L = ["# T5 事后读法（看到结果以后才问的，不算预测）", "",
         "- 只读回执，没有训练，也没有加载模型。数字由 `posthoc_t5.py` 生成。",
         f"- 回执 {len(paths)} 个，最早写于 {time.strftime('%H:%M:%S', time.localtime(min(p.stat().st_mtime for p in paths)))}，"
         f"最晚写于 {time.strftime('%H:%M:%S', time.localtime(max(p.stat().st_mtime for p in paths)))}。",
         "- 种子 2 的工人是用户在自己的终端启动的，所以没有 `worker2.log`；它的 30 个回执都在。", "",
         "## 一、学习曲线（dev，两个候选的题，有晶格）", "",
         f"“过 {LEARNED:.0f}%”是第一次到 {LEARNED:.0f}% 的检查点。“最后一段”是最后 {every} 步涨了多少。", "",
         "| 题型 | 做法 | 种子 | " + " | ".join(str(s) for s in steps) + f" | 过 {LEARNED:.0f}% | 最后一段 |",
         "|---|---|---:|" + "---:|" * len(steps) + "---:|---:|"]
    for task, kind in (("anchor", "attn"), ("anchor", "mean"), ("mutual", "attn"), ("mutual", "mean")):
        for s in seeds:
            dev = [100 * c["dev_choice_two"] for c in cell[(task, kind, True, s)]["curve"]]
            first = next((st for st, v in zip(steps, dev) if v >= LEARNED), None)
            rise = dev[-1] - dev[-2]
            res["curves"].append({"task": task, "kind": kind, "seed": s, "dev": dev, "first_over": first, "last_rise": rise})
            L.append(f"| {TASK_NAMES[task]} | {KIND_NAMES[kind]} | {s} | " + " | ".join(f"{v:.0f}" for v in dev)
                     + f" | {first if first else '没到'} | {rise:+.1f} |")
    still = [c for c in res["curves"] if c["last_rise"] >= RISING]
    L += ["", f"训练结束时，最后一段还涨了至少 {RISING:.0f} 点的格子：" + ("、".join(f"{TASK_NAMES[c['task']]} {KIND_NAMES[c['kind']]} 种子 {c['seed']}" for c in still) or "没有") + "。",
          "这些格子的最终数字不是它们的上限。多训练会到哪里，这次没有测。", "",
          "## 二、同一批包和没见过的包的差距（test，两个候选的题，有晶格）", "",
          "| 题型 | 做法 | 种子 | 同一批包 | 没见过的包 | 差距 |", "|---|---|---:|---:|---:|---:|"]
    for task in ("anchor", "mutual"):
        for kind in ("attn", "mean"):
            for s in seeds:
                a, b = pct(task, kind, True, s), pct(task, kind, True, s, "test_new")
                res["new_gap"].append({"task": task, "kind": kind, "seed": s, "iid": a, "new": b})
                L.append(f"| {TASK_NAMES[task]} | {KIND_NAMES[kind]} | {s} | {a:.1f} | {b:.1f} | {a - b:.1f} |")
    L += ["", "## 三、没有晶格时，哪部分自己长出来了（test_iid）", "",
          "一个候选的题只要认出“关系对得上”就能答对。两个候选的题在锚题和互相支持题上还要比较内容。",
          "没有晶格时什么位置都能选，所以两个候选的题可以低于 50%。", "",
          "| 题型 | 做法 | 一个候选（最低–最高） | 两个候选（最低–最高） |", "|---|---|---:|---:|"]
    for task in plan["tasks"]:
        for kind in KIND_NAMES:
            one = [pct(task, kind, False, s, key="choice_one") for s in seeds]
            two = [pct(task, kind, False, s) for s in seeds]
            res["no_lattice"].append({"task": task, "kind": kind, "one": one, "two": two})
            L.append(f"| {TASK_NAMES[task]} | {KIND_NAMES[kind]} | {min(one):.1f}–{max(one):.1f} | {min(two):.1f}–{max(two):.1f} |")
    L += ["", "这个实验没有把晶格拆开：关系对得上、不合法不能选、固定的参考向量是一起给或一起拿走的。",
          "所以上面只是线索，不能说明到底是哪一部分起作用。", "",
          "## 四、更正：冻结计划里有一句契约写得太宽", "",
          "原话：没有晶格时，`test_new` 里的对象嵌入没训练过，答不好是必然的。", ""]
    for kind in KIND_NAMES:
        new = [pct("position", kind, False, s, "test_new") for s in seeds]
        res["no_lattice_position_new"][kind] = new
        L.append(f"- 位置题、没有晶格、{KIND_NAMES[kind]}：没见过的包 {' / '.join(f'{x:.1f}' for x in new)}")
    L += ["", "位置题不靠对象的内容，所以这句只对靠内容选的题成立。冻结的报告脚本没有改，更正写在这里。", "",
          "## 五、这份读法说明不了什么", "",
          "- 曲线是每 3000 步一个点，跳变的准确时刻不知道。",
          "- 每格只有 3 个种子。",
          "- 没有看模型内部，所以“为什么种子 1 卡住”“平均交流怎么做到的”都不知道。", ""]
    (out / "RESULT.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    print("写好", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
