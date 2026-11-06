"""由本副本的新运行收据自动生成 REPORT.zh.md；数字和结论句来自凭证。

用法：python -B report_t2.py <输出目录>。流水线每完成一个种子、停下或出错时也会自动调用。
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

CHANGES = {"C1": "C1 遗漏的包（KA 层的变更）", "C2": "C2 链内改口（EA 层的变更）", "C3": "C3 新体裁（CA 层的变更）"}
ARM_LABELS = {"none": "不修复", "KA_local": "只修 KA_local（新出现的包）", "CA": "只修 CA", "EA": "只修 EA",
              "CA+EA": "修 CA＋EA", "ALL": "全部重修（三层都写，接着基线训练）", "escalate": "逐级加深（够用就停）",
              "retrain": "从头重训（全局重构）"}
LIMITATIONS = [
    "T2 是受控合成任务：三条规则（包内数值、链内改口、链间覆盖）都是出题器定的，理论最优可算；结果只说明这个任务。",
    "三种变更各自只落在一层，是出题时故意这样设计的；真实的变更可能同时跨几层。",
    "KA 只用 CPU 能精确对应到成员的观察（上层的选择错误不当作下层的标签）。所以 C2、C3 的新材料里没有 KA 能用的观察，"
    "“KA 要不要回修”主要看各层诊断（选对链、选对事件以后答案对不对），不只看 KA 修复组的成绩。",
    "EA、CA 带 CPU 身份约束（关系对得上、说话人对得上、是不是设定链），以固定偏置加在选择分数上；"
    "同一说话人有几条链时选哪一条、同一关系出现两次时选哪一次，要模型自己学。",
    "调用顺序（CA 先选链 → EA 选事件 → KA 给表示 → CA 比较）是本实验的工作实现；图谱写明具体调用路由未定。",
    "“局部”＝系统自己从版本号看出的新单元（从来没训练过、但新材料里出现的包）。没有用出题器的隐藏信息。",
    "逐级加深的梯子（KA_local → CA → EA → CA＋EA → 全部）和“够用”标准（DEV 上不低于基线旧条件 DEV 减 margin）是事先固定的一种排法；"
    "换一种排法，成本会不同。",
    "修复的材料是新条件的全部 TRAIN，加上同样多的旧 TRAIN（固定抽样）；修复的轮数、epoch 数事先固定，没有调。",
    "“从头重训”和基线用同样的轮数和 epoch 数，材料是 base＋新条件的全部 TRAIN。",
    "学习率等超参数事先固定，没有调参；某组不好，也可能是超参数不合适。三个种子只改初始化和抽样顺序，题目相同。",
    "成本只记训练：更新次数、见题次数、计算秒数（不含限流时歇的时间）、写了几个单元和多少参数。评测的开销没有算进去。",
    "“不知道”的规则是事先固定的常数（|p−0.5|<0.1，或任一边“没有合适的链或事件”的概率>0.5），没有用 DEV 标定。",
]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def pct(t: dict | None) -> str:
    if not t or not t["n"]:
        return "—"
    return f"{t['forced_correct'] / t['n']:.1%}"


def cell(t: dict | None, interval: bool = False) -> str:
    if not t or not t["n"]:
        return "—"
    s = f"{t['forced_correct']}/{t['n']}（{t['forced_correct'] / t['n']:.1%}）"
    if interval:
        lo, hi = wilson(t["forced_correct"], t["n"])
        s += f" [{lo:.1%}–{hi:.1%}]"
    return s


def ratio(t: dict | None) -> str:
    if not t or not t["n"]:
        return "—"
    return f"{t['correct'] / t['n']:.1%}（{t['n']}）"


def main_of(ev: dict, key: str) -> dict | None:
    return ev[key]["score"].get("strata", {}).get("gate", {}).get("new_conflict")


def verdict(xs: list[dict], ys: list[dict]) -> str:
    """X 的每个种子都和 Y 的每个种子比 95% 区间：都在上方才说“高于”，都在下方才说“低于”。"""
    xi = [wilson(t["forced_correct"], t["n"]) for t in xs]
    yi = [wilson(t["forced_correct"], t["n"]) for t in ys]
    if all(a[0] > b[1] for a in xi for b in yi):
        return "高于"
    if all(a[1] < b[0] for a in xi for b in yi):
        return "低于"
    return "区间重叠，分不出高下"


def load(out: Path) -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))}


def runs_for(rec: dict, ch: str) -> dict:
    """{arm: {seed: (eval, bill, receipt)}}；“不修复”取基线收据。"""
    out: dict = {}
    for key, r in rec.items():
        if key.startswith("base-s"):
            out.setdefault("none", {})[r["seed"]] = r
        elif r.get("change") == ch and not r.get("skipped"):
            out.setdefault(r["arm"], {})[r["seed"]] = r
    return out


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
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8")) if (out / "FROZEN.json").exists() else {}
    if frozen:
        reproduction_plan(frozen)  # Validate the local plan reference even when the table does not need it.
    status = json.loads((out / "PIPELINE_EXIT.json").read_text(encoding="utf-8")) \
        if (out / "PIPELINE_EXIT.json").exists() else json.loads((out / "STATUS.json").read_text(encoding="utf-8")) \
        if (out / "STATUS.json").exists() else {}
    rec = load(out)
    stages = frozen.get("stages", [])
    done = [s for s in stages if s in rec]
    L = ["# T2 运行报告（自动生成；局部修复＋回修深度；模型有 KA、EA、CA 三层）", "",
         f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
         "- 本报告来自新的复现运行，不是历史实验回执。",
         f"- 运行状态：`{status.get('status', status.get('state', '?'))}`"
         + (f"；原因：{status.get('reason')}" if status.get("reason") else "")
         + (f"；停在：`{status.get('stage')}`" if status.get("status") not in (None, "completed") else ""),
         f"- 已完成阶段：{len(done)}/{len(stages)}",
         f"- 计划 SHA256：`{frozen.get('plan_sha256', '?')}`", "",
         "**读法**：",
         "- “新条件”＝发生变更的那一类题；“旧条件”＝base 的题（看修复有没有把原来会的弄坏）。",
         "- 格子里是“强制二选一答对数/题数（比例）”。主要一列是 TEST 的“新组合 × 冲突”（这一对和世界在训练里没出现过、"
         "只看一部分的规则互相矛盾），另附 95% Wilson 区间。",
         "- 各层诊断用隐藏真值，只用于报告：CA 选对链的比例（只算需要 CA 的题）、EA 选对事件的比例（只算需要 EA 的题）、"
         "CA 和 EA 都选对的题里答案对的比例（≈ KA＋比较的质量）。括号里是题数。",
         "- 所有数字都从 `receipts/` 生成。", ""]

    gate = rec.get("gate")
    if gate:
        L += ["## 数据与门禁", "",
              f"- 数据身份：`{gate['data_identity'][:16]}…`；遗漏的包：{gate['missing_packages']}",
              "- 题数：" + "；".join(f"{c} {v}" for c, v in gate["counts"].items()),
              "- TRAIN 里 CPU 能精确对应的题（KA 的材料）：" + "；".join(f"{c} {v}" for c, v in gate["exact_train_counts"].items()),
              "- 门禁：" + "；".join(f"{k} {'通过' if v['passed'] else '未通过'}（新组合×冲突 {v['main_stratum_count']} 题，"
                                  f"单部分规则最高 {v['worst_part_rule_accuracy_on_main']:.1%}）" for k, v in gate["gates"].items()),
              "", "| 基线（TEST） | base | C1 | C2 | C3 |", "|---|---:|---:|---:|---:|"]
        for name, label in (("majority", "恒选多数"), ("path_reasoner", "路径推理（知道话语规则；推不出算错）")):
            L.append(f"| {label} | " + " | ".join(cell(gate["baselines"][name][f"{c}/test"]["overall"])
                                                for c in ("base", "C1", "C2", "C3")) + " |")
        L.append("")

    bases = {r["seed"]: r for k, r in rec.items() if k.startswith("base-s")}
    if bases:
        any_base = next(iter(bases.values()))
        p = any_base["params"]
        L += ["## 基线模型（只在 base 条件上螺旋训练）", "",
              f"- 参数：KA 每个包 {p['ka_per_package']}（共 {p['ka_total']:,}）；EA {p['ea']:,}；CA {p['ca']:,}。"
              "每个单元单独存盘、单独训练。", "",
              "| 种子 | 条件（TEST） | 全部 | 新组合×冲突（主要） | CA 选对链（需要 CA 的题） | EA 选对事件（需要 EA 的题） | 都选对时答案对 |",
              "|---:|---|---:|---:|---:|---:|---:|"]
        for seed, r in sorted(bases.items()):
            for c in ("base", "C1", "C2", "C3"):
                ev = r["eval"][f"{c}/test"]
                lay = ev["layers"]
                L.append(f"| {seed} | {c} | {cell(ev['score']['overall'])} | {cell(main_of(r['eval'], f'{c}/test'), True)} | "
                         f"{ratio(lay['ca_all_needs_ca'])} | {ratio(lay['ea_all_needs_ea'])} | "
                         f"{ratio(lay['answer_given_selection_right'])} |")
        L += ["", "学习曲线（DEV 固定子集，每轮一点）："]
        for seed, r in sorted(bases.items()):
            L.append(f"- 种子 {seed}：" + ", ".join(f"{c['dev_subset_accuracy']:.3f}" for c in r["curve"]))
        L.append("")

    for ch, title in CHANGES.items():
        runs = runs_for(rec, ch)
        if set(runs) <= {"none"}:
            continue
        L += [f"## {title}", "",
              "| 修复 | 种子 | 新条件 TEST 全部 | 新条件 新组合×冲突（主要） | 旧条件 TEST 全部 | CA 选对链 | EA 选对事件 | 都选对时答案对 | "
              "更新次数 | 写过的单元 | 写的参数 | 计算秒数 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for arm in ARM_LABELS:
            for seed, r in sorted(runs.get(arm, {}).items()):
                ev, lay = r["eval"], r["eval"][f"{ch}/test"]["layers"]
                b = r.get("bill") if arm != "none" else None
                cost = (f"{b['updates']:,} | {b['distinct_units']} | {b['params_written']:,} | {b['compute_seconds']:.0f}"
                        if b else "0 | 0 | 0 | 0")
                L.append(f"| {ARM_LABELS[arm]} | {seed} | {cell(ev[f'{ch}/test']['score']['overall'])} | "
                         f"{cell(main_of(ev, f'{ch}/test'), True)} | {cell(ev['base/test']['score']['overall'])} | "
                         f"{ratio(lay['ca_all_needs_ca'])} | {ratio(lay['ea_all_needs_ea'])} | "
                         f"{ratio(lay['answer_given_selection_right'])} | {cost} |")
        skipped = sorted({k.split('-')[1] for k, r in rec.items() if r.get("change") == ch and r.get("skipped")})
        if skipped:
            L.append(f"\n跳过：{'、'.join(ARM_LABELS.get(a, a) for a in skipped)}——写范围为空（这种变更没有新出现的单元）。")

        L += ["", "主要指标的自动比较（每个种子的 95% 区间两两比较）："]

        def mains(arm, key):
            return [main_of(r["eval"], key) for _, r in sorted(runs.get(arm, {}).items()) if main_of(r["eval"], key)]
        for arm in ARM_LABELS:
            if arm in ("none", "retrain") or not mains(arm, f"{ch}/test"):
                continue
            for ref in ("none", "retrain"):
                if mains(ref, f"{ch}/test"):
                    L.append(f"- 新条件：{ARM_LABELS[arm]} 对 {ARM_LABELS[ref]}：**{verdict(mains(arm, f'{ch}/test'), mains(ref, f'{ch}/test'))}**")
            if mains("none", "base/test"):
                L.append(f"- 旧条件：{ARM_LABELS[arm]} 对 不修复：**{verdict(mains(arm, 'base/test'), mains('none', 'base/test'))}**")

        esc = runs.get("escalate", {})
        if esc:
            L += ["", "逐级加深的过程（DEV；每级从基线出发，不够用就回退）："]
            for seed, r in sorted(esc.items()):
                e = r["escalation"]
                steps = []
                for t in e["trace"]:
                    name = "＋".join(t["layers"])
                    if t.get("skipped"):
                        steps.append(f"{name}（跳过：{t['skipped']}）")
                    else:
                        steps.append(f"{name}：新 {t['new_dev']:.1%}／旧 {t['old_dev']:.1%}{'，够用' if t['enough'] else ''}")
                adopted = e["adopted"].split("/")[-1].replace("+", "＋") if e["adopted"] else "无（保留基线）"
                st = {"enough": "够用", "not_enough_best_kept": "未达到够用标准，采用最好的一级",
                      "not_enough_base_kept": "未达到够用标准，保留基线"}[e["status"]]
                L.append(f"- 种子 {seed}（标准 {e['bar']:.1%}）：" + " → ".join(steps) + f"。结果：{st}；采用 {adopted}。")
        L.append("")

    check = rec.get("check")
    if check and check.get("warnings"):
        L += ["## 程序检查的提醒", "", *[f"- {w}" for w in check["warnings"]], ""]
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
    print(write_report(Path(sys.argv[1]))[:3000])
