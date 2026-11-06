"""由本副本的新运行收据自动生成 REPORT.zh.md；数字和结论句来自凭证。

用法：python -B report_t1.py <输出目录>。流水线每完成一档、停下或出错时也会自动调用。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from math import sqrt
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import load_plan, root_path

MAIN = ("gate", "new_conflict")
COLUMNS = [("全部", None), ("新组合×冲突（主要）", ("gate", "new_conflict")),
           ("路径推不出", ("path", "path_not_implied")), ("跨包", ("package", "cross_package")),
           ("同包", ("package", "same_package"))]
MODEL_NAMES: dict = {}          # 由 write_report 按计划里的 label 填写，顺序同计划
FOCUS: list = []                # 计划里 report_focus：要和其他组逐一比较的模型
BASELINE_NAMES = {"majority": "恒选多数", "A+world": "只看 A＋世界", "B+world": "只看 B＋世界",
                  "path_reasoner": "路径推理（推不出算错）"}
LIMITATIONS = [
    "只有 T1-b（不给已登记偏差）；T1-a、按训练题比例的学习曲线、可修正性（R2）实验这次没有跑。",
    "复现配置默认 CPU 单线程，设备以本次收据为准；可选 GPU 等待不保证利用率上限。学习率等超参数未分别调优，低分也可能来自超参数不适合。",
    "模型 A 带 CPU 身份约束（identity_bias=6）：哪个事件对得上查询关系，由符号侧直接给出；不能说成 EA 自己学会了选事件。",
    "A-spiral 的“分轮到达”是用固定到达表模拟的：TRAIN 事先整份生成，训练器只读已到达的行，不是真正的外部流式输入。",
    "本次 A-spiral 每轮学“本轮新到的题＋同样多的旧题（固定抽样）”，8 轮和 24 轮见题总量相同、只差轮数。",
    "A-spiral 的跨包材料是借上层上一轮产品做的投影，不是新的独立证据；L1 是最小完整单元，整体驻留内存。",
    "A-spiral 和 A-joint 见到的题次数不完全相等（见成本表的 examples_seen），两者都照实报告。",
    "“＋逻辑优先”行是推理阶段的组合：训练事实用传递关系推得出的题用推理答案，其余用模型；不另外训练，也不是模型自己学会的。",
    "xl 档时间有限：种子 0 优先，种子 1、2 若被时间上限截断，照实只报告已完成的。",
    "三个种子只改模型初始化和抽样顺序，题目相同；种子之间的差别不代表换一批题的差别。",
    "“不知道”的规则是事先固定的常数（|p−0.5|<0.1，或 EA 的“没有合适事件”概率>0.5），没有用 DEV 标定。",
    "T1 是受控合成任务，理论最优可算；结果只说明这个任务，不代表一般能力。",
]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def cell(t: dict | None, interval: bool = False) -> str:
    if not t or not t["n"]:
        return "—"
    s = f"{t['forced_correct']}/{t['n']}（{t['forced_correct'] / t['n']:.1%}）"
    if interval:
        lo, hi = wilson(t["forced_correct"], t["n"])
        s += f" [{lo:.1%}–{hi:.1%}]"
    return s


def pick(score: dict, col) -> dict | None:
    if col is None:
        return score["overall"]
    return score.get("strata", {}).get(col[0], {}).get(col[1])


def load(out: Path) -> dict:
    rec = {}
    for p in sorted((out / "receipts").glob("*.json")):
        rec[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return rec


def verdict(xs: list[dict], ys: list[dict]) -> str:
    """X 的每个种子都和 Y 的每个种子比 95% 区间：都在上方才说“高于”，都在下方才说“低于”。"""
    xi = [wilson(t["forced_correct"], t["n"]) for t in xs]
    yi = [wilson(t["forced_correct"], t["n"]) for t in ys]
    if all(a[0] > b[1] for a in xi for b in yi):
        return "高于"
    if all(a[1] < b[0] for a in xi for b in yi):
        return "低于"
    return "区间重叠，分不出高下"


def reproduction_plan(frozen: dict) -> dict:
    """Reject machine-specific or escaping plan paths from historical metadata."""
    value = frozen.get("plan_path")
    if not value:
        raise ValueError("Missing reproduction plan_path in FROZEN.json")
    ref = Path(value)
    if ref.is_absolute() or PureWindowsPath(str(value)).drive:
        raise ValueError("FROZEN plan_path must be relative to the release root")
    if frozen.get("reproduction_config") is not True:
        raise ValueError("This report requires metadata from a new reproduction run")
    path = root_path(ref, must_exist=True)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != frozen.get("plan_sha256"):
        raise ValueError("Reproduction plan changed after this run was frozen")
    return load_plan(path)


def write_report(out: Path) -> str:
    out = root_path(out)
    plan_sha = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))["plan_sha256"] \
        if (out / "FROZEN.json").exists() else "?"
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8")) if (out / "FROZEN.json").exists() else {}
    status = json.loads((out / "PIPELINE_EXIT.json").read_text(encoding="utf-8")) \
        if (out / "PIPELINE_EXIT.json").exists() else json.loads((out / "STATUS.json").read_text(encoding="utf-8")) \
        if (out / "STATUS.json").exists() else {}
    rec = load(out)
    if frozen:
        plan = reproduction_plan(frozen)
        MODEL_NAMES.clear()
        MODEL_NAMES.update({k: v["label"] for k, v in plan["models"].items()})
        FOCUS[:] = plan.get("report_focus", [])
    stages = frozen.get("stages", [])
    done = [s for s in stages if s in rec]
    L = ["# T1 第二次运行报告（自动生成；放大＋螺旋多转几轮）", "",
         f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
         "- 本报告来自新的复现运行，不是历史实验回执。",
         f"- 运行状态：`{status.get('status', status.get('state', '?'))}`"
         + (f"；原因：{status.get('reason')}" if status.get("reason") else "")
         + (f"；停在：`{status.get('stage')}`" if status.get("status") not in (None, "completed") else ""),
         f"- 已完成阶段：{len(done)}/{len(stages)}",
         f"- 计划 SHA256：`{plan_sha}`", "",
         "**读法**：主要指标是 TEST 里“新组合 × 冲突”这一类（这一对对象和世界在训练里没出现过，只看一部分的规则互相矛盾）。",
         "格子里是“强制二选一答对数/题数（比例）”，主要一列另附 95% Wilson 区间。所有数字都从 `receipts/` 生成。", ""]

    sizes = [s.split("-")[0] for s in stages if s.endswith("-gate")]
    for size in sizes:
        gate = rec.get(f"{size}-gate")
        if not gate:
            continue
        L += [f"## {size} 档", ""]
        g = gate["gates"]
        L.append("- 门禁：" + "；".join(
            f"{s.upper()} {'通过' if v['passed'] else '未通过'}（新组合×冲突 {v['main_stratum_count']} 题，"
            f"单部分规则在这一类最高 {v['worst_part_rule_accuracy_on_main']:.1%}）" for s, v in g.items()))
        L.append(f"- 数据身份：`{gate['data_identity'][:16]}…`；题数 {gate['split_counts']}")
        runs = {k: v for k, v in rec.items() if v.get("size") == size and "model" in v}
        L += ["", "### TEST 结果", "", "| 模型 | 种子 | 参数量 | " + " | ".join(c for c, _ in COLUMNS) + " |",
              "|---|---:|---:|" + "---:|" * len(COLUMNS)]
        for model in MODEL_NAMES:
            for key in sorted(k for k, v in runs.items() if v["model"] == model):
                r = runs[key]
                L.append(f"| {MODEL_NAMES[model]} | {r['seed']} | {r['params']:,} | "
                         + " | ".join(cell(pick(r["scores"]["test"], col), col == MAIN) for _, col in COLUMNS) + " |")
        for model in MODEL_NAMES:
            for key in sorted(k for k, v in runs.items() if v["model"] == model and "scores_hybrid" in v):
                r = runs[key]
                L.append(f"| {MODEL_NAMES[model]}＋逻辑优先 | {r['seed']} | — | "
                         + " | ".join(cell(pick(r["scores_hybrid"]["test"], col), col == MAIN) for _, col in COLUMNS)
                         + " |")
        for name, label in BASELINE_NAMES.items():
            b = gate["baselines"][name]["test"]
            L.append(f"| {label} | — | — | " + " | ".join(cell(pick(b, col), col == MAIN) for _, col in COLUMNS) + " |")
        n_test = gate["theoretical_optimum"]["test"]
        L.append(f"| 理论最优（知道隐藏数值） | — | — | {n_test}/{n_test} |" + " — |" * (len(COLUMNS) - 1))

        def main_of(model):
            return [pick(runs[k]["scores"]["test"], MAIN) for k in sorted(runs) if runs[k]["model"] == model
                    and pick(runs[k]["scores"]["test"], MAIN)]
        L += ["", "### 主要指标的自动比较（每个种子的 95% 区间两两比较）", ""]
        refs = {"路径推理": [gate["baselines"]["path_reasoner"]["test"]["strata"]["gate"].get("new_conflict")]}
        for m in MODEL_NAMES:
            if main_of(m):
                refs[MODEL_NAMES[m]] = main_of(m)
        for a in FOCUS:
            xs = main_of(a)
            if not xs:
                continue
            for ref, ys in refs.items():
                if ref == MODEL_NAMES[a] or not all(ys):
                    continue
                L.append(f"- {MODEL_NAMES[a]}（{len(xs)} 个种子）对 {ref}：**{verdict(xs, ys)}**")
        L += ["", "### “不知道”（TEST；作答数/题数，作答题里答对的比例）", "",
              "| 模型 | 种子 | 全部 | 路径推不出 |", "|---|---:|---:|---:|"]

        def ans(t):
            if not t or not t["n"]:
                return "—"
            acc = f"{t['answered_correct'] / t['answered']:.1%}" if t["answered"] else "—"
            return f"{t['answered']}/{t['n']}，答对 {acc}"
        for model in MODEL_NAMES:
            for key in sorted(k for k, v in runs.items() if v["model"] == model):
                sc = runs[key]["scores"]["test"]
                L.append(f"| {MODEL_NAMES[model]} | {runs[key]['seed']} | {ans(sc['overall'])} | "
                         f"{ans(pick(sc, ('path', 'path_not_implied')))} |")
        pr = gate["baselines"]["path_reasoner"]["test"]
        L.append(f"| 路径推理 | — | {ans(pr['overall'])} | {ans(pick(pr, ('path', 'path_not_implied')))} |")

        L += ["", "### 成本（账单）", "",
              "| 模型 | 种子 | 更新次数 | 见题次数 | 训练墙钟 | 每步中位数 | 模型字节 | 最大预留（A-spiral） |",
              "|---|---:|---:|---:|---:|---|---:|---|"]
        for model in MODEL_NAMES:
            for key in sorted(k for k, v in runs.items() if v["model"] == model):
                r = runs[key]
                t = r["training"]
                seen = t["examples_seen"] if isinstance(t["examples_seen"], int) else sum(t["examples_seen"].values())
                med = "；".join(f"{k} {v['median_s'] * 1000:.1f}ms" for k, v in r["timing"].items())
                res = "；".join(f"{k} {v / 2 ** 20:.1f}MiB" for k, v in t.get("max_reserved_bytes", {}).items()) or "—"
                L.append(f"| {MODEL_NAMES[model]} | {r['seed']} | {t['updates']:,} | {seen:,} | "
                         f"{r['train_seconds'] / 60:.1f} 分 | {med} | {r['model_bytes'] / 2 ** 20:.1f}MiB | {res} |")
        L += ["", "### 学习曲线（DEV 固定子集的强制二选一正确率；A-spiral 每轮一点，其他每 1/10 训练一点）", ""]
        for model in MODEL_NAMES:
            for key in sorted(k for k, v in runs.items() if v["model"] == model):
                curve = runs[key]["training"]["curve"]
                pts = ", ".join(f"{c['dev_subset_accuracy']:.3f}" for c in curve if c.get("dev_subset_accuracy") is not None)
                L.append(f"- {MODEL_NAMES[model]} 种子 {runs[key]['seed']}：{pts}")
        L += ["", "### DEV 结果（次要，只作参照）", "", "| 模型 | 种子 | 全部 | 新组合×冲突 |", "|---|---:|---:|---:|"]
        for model in MODEL_NAMES:
            for key in sorted(k for k, v in runs.items() if v["model"] == model):
                sc = runs[key]["scores"]["dev"]
                L.append(f"| {MODEL_NAMES[model]} | {runs[key]['seed']} | {cell(sc['overall'])} | {cell(pick(sc, MAIN))} |")
        check = rec.get(f"{size}-check")
        if check and check.get("warnings"):
            L += ["", "程序检查的提醒：", *[f"- {w}" for w in check["warnings"]]]
        L.append("")

    failures = out / "failures.jsonl"
    L += ["## 停止、失败与受阻的尝试（v0.54：都登记，不折叠）", ""]
    if failures.exists():
        for line in failures.read_text(encoding="utf-8").splitlines():
            f = json.loads(line)
            L.append(f"- {f.get('time')}｜阶段 `{f.get('stage')}`｜{f.get('status')}｜{f.get('reason')}")
    else:
        L.append("- 没有。")
    L += ["", "## 限制", "", *[f"- {x}" for x in LIMITATIONS], ""]
    text = "\n".join(L)
    (out / "REPORT.zh.md").write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(write_report(Path(sys.argv[1]))[:2000])
