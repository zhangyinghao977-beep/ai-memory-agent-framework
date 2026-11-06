"""由运行凭证生成报告：契约检查与实验结果分开，结论随结果变化。

- 数字和结论句都由凭证计算，不写固定的 PASS。
- 契约检查（按构造必然成立的检查）单独成节，不计入实验结果。
- 门禁未通过时，结论只能写“不能解释为学习效果”。

凭证格式：
{
  "plan_identity": str,
  "run_status": str,
  "gates": [{"name": str, "passed": bool}],
  "contract_checks": [{"name": str, "passed": bool, "note": str}],
  "metrics": [{"name": str, "kind": "proportion", "n": int, "model": int, "baselines": {name: int}}
              | {"name": str, "kind": "value", "higher_is_better": bool, "model": float, "baselines": {name: float},
                 "difference_intervals": {name: [lo, hi]}  # 可选：模型减基线的 95% 区间
                }],
  "ablations": [{"name": str, "metric": str, "value": number}],
  "reference_points": [str],   # 可选：理论最优、训练前成绩等
  "limitations": [str]
}
"""
from __future__ import annotations

from math import sqrt

ABOVE_CLEAR = "优于全部基线（区间不重叠）"
ABOVE_OVERLAP = "点估计优于全部基线，但区间重叠，不能下结论"
ABOVE_POINT = "点估计优于全部基线（无区间，不能下结论）"
NOT_ABOVE = "未超过至少一个基线"


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n 必须大于 0")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def compare_to_baselines(metric: dict) -> dict:
    model, baselines = metric["model"], metric["baselines"]
    if not baselines:
        raise ValueError(f"指标 {metric['name']} 没有基线结果")
    if metric.get("kind", "proportion") == "proportion":
        n = metric["n"]
        lo, hi = wilson_interval(model, n)
        intervals = {b: wilson_interval(k, n) for b, k in baselines.items()}
        if any(model <= k for k in baselines.values()):
            verdict = NOT_ABOVE
        elif all(lo > iv[1] for iv in intervals.values()):
            verdict = ABOVE_CLEAR
        else:
            verdict = ABOVE_OVERLAP
        return {"verdict": verdict, "model_interval": (lo, hi), "baseline_intervals": intervals}
    better = (lambda a, b: a > b) if metric["higher_is_better"] else (lambda a, b: a < b)
    if not all(better(model, v) for v in baselines.values()):
        return {"verdict": NOT_ABOVE}
    diffs = metric.get("difference_intervals")  # {基线: [下界, 上界]}，模型减基线
    if not diffs:
        return {"verdict": ABOVE_POINT}
    sign = 1 if metric["higher_is_better"] else -1
    clear = all(min(sign * lo, sign * hi) > 0 for lo, hi in (diffs[b] for b in baselines))
    return {"verdict": ABOVE_CLEAR if clear else ABOVE_OVERLAP, "difference_intervals": diffs}


def overall_conclusion(receipt: dict, comparisons: list[dict]) -> str:
    if receipt.get("run_status") != "completed":
        return f"运行状态为 {receipt.get('run_status')}，没有可解释的结果。"
    if not all(g["passed"] for g in receipt.get("gates", [])):
        return "训练前门禁未全部通过：结果不能解释为学习效果。"
    verdicts = [c["verdict"] for c in comparisons]
    if not verdicts:
        return "没有登记指标，不能下结论。"
    if any(v == NOT_ABOVE for v in verdicts):
        return "模型未超过至少一个预定基线：不能说“学会了”。"
    if all(v == ABOVE_CLEAR for v in verdicts):
        return "在本计划的评测上，模型优于全部预定基线（特例成立，不代表一般能力）。"
    return "模型点估计优于基线，但证据不足以排除偶然，需要更多样本或区间。"


def render_report(receipt: dict, title: str) -> str:
    comparisons = [compare_to_baselines(m) for m in receipt.get("metrics", [])]
    lines = [f"# {title}", "", f"- 计划身份：`{receipt.get('plan_identity')}`", f"- 运行状态：`{receipt.get('run_status')}`", ""]

    lines += ["## 训练前门禁", ""]
    for g in receipt.get("gates", []):
        lines.append(f"- {g['name']}：{'通过' if g['passed'] else '未通过'}")
    if not receipt.get("gates"):
        lines.append("- （未登记门禁）")

    lines += ["", "## 契约检查（按构造成立，不计入实验结果）", ""]
    for c in receipt.get("contract_checks", []):
        lines.append(f"- {c['name']}：{'满足' if c['passed'] else '不满足'}。{c.get('note', '')}")
    if not receipt.get("contract_checks"):
        lines.append("- （无）")

    lines += ["", "## 结果与基线", ""]
    for m, cmp in zip(receipt.get("metrics", []), comparisons):
        if m.get("kind", "proportion") == "proportion":
            lo, hi = cmp["model_interval"]
            base = "；".join(
                f"{b} {k}/{m['n']}（{cmp['baseline_intervals'][b][0]:.1%}–{cmp['baseline_intervals'][b][1]:.1%}）"
                for b, k in m["baselines"].items()
            )
            lines.append(f"- **{m['name']}**：模型 {m['model']}/{m['n']}（{lo:.1%}–{hi:.1%}）；{base}。判定：{cmp['verdict']}。")
        else:
            base = "；".join(f"{b} {v}" for b, v in m["baselines"].items())
            lines.append(f"- **{m['name']}**：模型 {m['model']}；{base}。判定：{cmp['verdict']}。")

    if receipt.get("ablations"):
        lines += ["", "## 对照组", ""]
        for a in receipt["ablations"]:
            lines.append(f"- {a['name']}（{a['metric']}）：{a['value']}")

    if receipt.get("reference_points"):
        lines += ["", "## 参照点（理论最优、训练前等，不是基线）", ""]
        lines += [f"- {p}" for p in receipt["reference_points"]]

    lines += ["", "## 结论", "", overall_conclusion(receipt, comparisons)]

    lines += ["", "## 限制", ""]
    for item in receipt.get("limitations", []) or ["（未登记）"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def stratified_metrics(
    name: str,
    model_correct: dict,
    baseline_correct: dict[str, dict],
    strata: dict,
    chance: float | None = None,
    ties: dict | None = None,
) -> list[dict]:
    """按类别分开的比例指标（测试方案 v0.1 第四节）：每一类单独和每条基线比较，避免容易的题掩盖难的题。

    model_correct／baseline_correct[b]：{题号: 是否答对}；strata：{题号: 类别}（见 gates.stratify）。
    ties（可选）：{题号: 是否平局}——平局按答错计，同时单独写出平局数；chance：随机水平，写进指标名旁的说明。
    返回的每一项都能直接放进凭证的 metrics。"""
    out = []
    for stratum in sorted(set(strata.values())):
        ids = [i for i, s in strata.items() if s == stratum]
        metric = {
            "name": f"{name}［{stratum}］",
            "kind": "proportion",
            "n": len(ids),
            "model": sum(bool(model_correct.get(i)) for i in ids),
            "baselines": {b: sum(bool(hits.get(i)) for i in ids) for b, hits in baseline_correct.items()},
        }
        if ties is not None:
            metric["ties"] = sum(bool(ties.get(i)) for i in ids)
        if chance is not None:
            metric["chance"] = chance
        out.append(metric)
    return [m for m in out if m["n"] > 0]
