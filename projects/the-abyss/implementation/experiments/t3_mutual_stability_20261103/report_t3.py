"""由本副本的新运行收据自动生成 REPORT.zh.md；数字和结论句来自凭证。

用法：python -B report_t3.py <输出目录>。流水线每完成一个种子、停下或出错时也会自动调用。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import load_plan, root_path
sys.path.insert(0, str(HERE.parents[1] / "project"))
sys.path.insert(0, str(HERE.parent / "t2_repair_20261102"))

from report_t2 import cell, ratio, verdict  # noqa: E402

ARMS = {"one_way": "单向（T2 做法：KA 只用 CPU 能精确对应的材料）", "two_way": "双向（KA 也从 EA、CA 的选择拿材料）"}
SHORT = {"one_way": "单向", "two_way": "双向"}
INDIRECT = {"none": "不含间接包", "one": "含一个间接包", "both": "两个都是间接包"}
MEASURE_LABELS = {"slot": "SLOT（EA↔KA 的结果）", "ka": "KA 产品", "ea": "EA 的选择", "answer": "整个模型的答案"}
LIMITATIONS = [
    "T3 是受控合成任务（T2 的 base 条件，另加链内改口和间接包）；规则都是出题器定的，结果只说明这个任务。",
    "间接包是故意设计的：TRAIN 里它们的题那一边一定带链内改口，CPU 不能精确对应。单向时这些包的 KA 没有任何材料、"
    "从来不训练，所以单向在间接包上学不会是**按构造必然的**（契约），不算实验发现；要看的是双向能不能学会、"
    "会不会把原来学得好的包带坏、稳不稳定。",
    "双向的做法（筛子递材料：每道题交给权重最大的事件所属的包；KA_p 只写自己的 o、W、b；读上一轮的 EA、CA，只读）"
    "是本实验的一种工作实现，不是图谱定下的算法。图谱写明不据筛子类比补造公式。",
    "“相互修正是否稳定”用什么量、阈值多少、连续几次，图谱写明待定。本报告的四种变化量（SLOT、KA 产品、EA 的选择、答案）"
    "和一组候选阈值都只是候选观察，不是选定的停止规则；“停在第几轮”是按这些候选事后模拟出来的。",
    "训练总是跑到硬上限；每轮都做一次只读的校验，所以“每 k 轮校验一次”可以事后精确模拟停在哪一轮，"
    "校验时间按“每次校验的平均成本 × 校验次数”算。",
    "固定轮数只是硬上限：跑到上限还没满足候选条件的，记作“未停（截断）”，不等于收敛，也不等于不收敛。",
    "报告用的评测（每轮的 DEV、TEST、各层诊断、包内差异）用隐藏真值，只用于报告，不参与训练和停止，也不计入校验时间。",
    "学习率、epoch 数等超参数沿用 T2，事先固定，没有调参。三个种子只改初始化和抽样顺序，题目相同。",
    "计算秒数不含限流时歇的时间；本机同时有别的程序在跑时，秒数会有波动。",
]


def load(out: Path) -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))}


def strat(ev: dict, dim: str, value: str):
    return ev["score"].get("strata", {}).get(dim, {}).get(value)


def frac(t: dict) -> str:
    return f"{t['order_correct'] / t['order_n']:.1%}" if t["order_n"] else "—"


def stop_round(rounds: list, measure: str, cadence: int, tol: float, window: int, cap: int):
    from empirical_core.t3.stability import simulate_stop
    checks = [{"round": r["round"], "lag": {int(k): v for k, v in r["check"]["lag"].items()}} for r in rounds]
    return simulate_stop(checks, measure, cadence, tol, window, cap)


def costs(rounds: list) -> tuple[list, float]:
    """每轮训练的计算秒数（第 1..cap 轮），和一次校验的平均成本（取状态＋算一次变化量）。"""
    train = [r["train"]["compute_seconds"] for r in rounds if r["round"] > 0]
    checks = [r["check"]["snapshot_seconds"] + r["check"].get("measure_seconds", 0.0) for r in rounds if r["round"] > 0]
    return train, sum(checks) / len(checks)


def main_acc(rec: dict) -> float:
    t = strat(rec["test"], "gate", "new_conflict")
    return t["forced_correct"] / t["n"]


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
    status = json.loads((out / "PIPELINE_EXIT.json").read_text(encoding="utf-8")) \
        if (out / "PIPELINE_EXIT.json").exists() else json.loads((out / "STATUS.json").read_text(encoding="utf-8")) \
        if (out / "STATUS.json").exists() else {}
    plan = reproduction_plan(frozen) if frozen else {}
    rec = load(out)
    stages = frozen.get("stages", [])
    done = [s for s in stages if s in rec]
    L = ["# T3 运行报告（自动生成；EA↔KA 双向修正与统一校验；模型有 KA、EA、CA 三层）", "",
         f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
         "- 本报告来自新的复现运行，不是历史实验回执。",
         f"- 运行状态：`{status.get('status', status.get('state', '?'))}`"
         + (f"；原因：{status.get('reason')}" if status.get("reason") else "")
         + (f"；停在：`{status.get('stage')}`" if status.get("status") not in (None, "completed") else ""),
         f"- 已完成阶段：{len(done)}/{len(stages)}",
         f"- 计划 SHA256：`{frozen.get('plan_sha256', '?')}`", "",
         "**读法**：",
         "- 格子里是“强制二选一答对数/题数（比例）”。主要一列是 TEST 的“新组合 × 冲突”（这一对和世界在训练里没出现过、"
         "只看一部分的规则互相矛盾），另附 95% Wilson 区间。",
         "- 间接包：TRAIN 里只能经过 EA 的选择（筛子）才拿得到材料的包。",
         "- 各层诊断、包内差异用隐藏真值，只用于报告。",
         "- 所有数字都从 `receipts/` 生成。", ""]

    gate = rec.get("gate")
    if gate:
        L += ["## 数据与门禁", "",
              f"- 数据身份：`{gate['data_identity'][:16]}…`；间接包：{gate['indirect_packages']}",
              f"- 题数：{gate['counts']}；TRAIN 里 CPU 能精确对应的题 {gate['exact_train']}；带链内改口的 {gate['train_needs_ea']}；"
              f"含间接包的 {gate['train_indirect']}（其中能精确对应的 {gate['indirect_exact_train']}，按出题规则应为 0）",
              f"- 统一校验的探针：TRAIN 里固定抽 {gate['probe_size']} 道（不看答案）",
              "- 门禁：" + "；".join(f"{k} {'通过' if v['passed'] else '未通过'}（新组合×冲突 {v['main_stratum_count']} 题，其中含间接包 "
                                  f"{v['indirect_main_count']} 题；单部分规则最高 {v['worst_part_rule_accuracy_on_main']:.1%}）"
                                  for k, v in gate["gates"].items()),
              "", "| 基线（TEST） | 全部 | " + " | ".join(INDIRECT.values()) + " |", "|---|---:|---:|---:|---:|"]
        for name, label in (("majority", "恒选多数"), ("path_reasoner", "路径推理（知道话语规则；推不出算错）")):
            t = gate["baselines"][name]["test"]
            L.append(f"| {label} | {cell(t['overall'])} | " +
                     " | ".join(cell(t["strata"].get("indirect", {}).get(v)) for v in INDIRECT) + " |")
        L.append("")

    runs = {arm: {r["seed"]: r for k, r in rec.items() if k.startswith(f"{arm}-s")} for arm in ARMS}
    cap = plan.get("training", {}).get("rounds_cap")
    if any(runs.values()):
        any_run = next(r for v in runs.values() for r in v.values())
        p = any_run["params"]
        L += ["## 问题一：筛子与材料（硬上限那一轮，TEST）", "",
              f"- 参数：KA 每个包 {p['ka_per_package']}（共 {p['ka_total']:,}）；EA {p['ea']:,}；CA {p['ca']:,}。"
              f"硬上限 {cap} 轮。", "",
              "| 做法 | 种子 | 全部 | 新组合×冲突（主要） | " + " | ".join(INDIRECT.values()) +
              " | EA 选对事件（需要 EA） | CA 选对链（需要 CA） | 都选对时答案对 | 包内大小判断：间接／其他 | 包内差异：间接／其他 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for arm, label in ARMS.items():
            for seed, r in sorted(runs[arm].items()):
                last = r["rounds"][-1]
                ev, lay, kd = last["test"], last["test"]["layers"], last["ka_diff"]
                L.append(f"| {SHORT[arm]} | {seed} | {cell(ev['score']['overall'])} | {cell(strat(ev, 'gate', 'new_conflict'), True)} | "
                         + " | ".join(cell(strat(ev, "indirect", v)) for v in INDIRECT)
                         + f" | {ratio(lay['ea_all_needs_ea'])} | {ratio(lay['ca_all_needs_ca'])} | "
                         f"{ratio(lay['answer_given_selection_right'])} | {frac(kd['indirect'])}／{frac(kd['direct'])} | "
                         f"{kd['indirect']['spread']:.3f}／{kd['direct']['spread']:.3f} |")
        if runs["one_way"] and runs["two_way"]:
            L += ["", "自动比较（双向对单向；每个种子的 95% 区间两两比较）："]

            def pick(arm, dim, value):
                return [strat(r["rounds"][-1]["test"], dim, value) for _, r in sorted(runs[arm].items())]
            for dim, value, name in (("gate", "new_conflict", "主要指标"), *(("indirect", v, n) for v, n in INDIRECT.items())):
                xs, ys = pick("two_way", dim, value), pick("one_way", dim, value)
                if all(xs) and all(ys):
                    L.append(f"- {name}：**{verdict(xs, ys)}**")
        L += ["", "每轮的变化（第 1 轮起；TEST 全部的正确率｜SLOT 相对变化｜EA 的选择改变的比例｜SLOT 相邻两次变化方向的余弦）：", ""]
        for arm in ARMS:
            for seed, r in sorted(runs[arm].items()):
                rs = r["rounds"][1:]
                acc = ", ".join(f"{x['test']['score']['overall']['forced_correct'] / x['test']['score']['overall']['n']:.3f}" for x in rs)
                slot = ", ".join(f"{lag1(x)['slot']:.3f}" for x in rs)
                ea = ", ".join(f"{lag1(x)['ea']:.3f}" for x in rs)
                cos = ", ".join(f"{x['check']['oscillation']['slot_cos']:+.2f}" for x in rs if x["check"].get("oscillation"))
                L += [f"- {SHORT[arm]}，种子 {seed}：", f"  - TEST：{acc}", f"  - SLOT 变化：{slot}",
                      f"  - EA 选择改变：{ea}", f"  - 变化方向余弦：{cos}"]
        L += ["", "来回摆动（后一半轮次）：", ""]
        for arm in ARMS:
            for seed, r in sorted(runs[arm].items()):
                tail = [x["check"]["oscillation"] for x in r["rounds"] if x["round"] > cap // 2 and x["check"].get("oscillation")]
                if tail:
                    neg = sum(o["slot_cos"] < 0 for o in tail)
                    back = sum(o["ea_back"] for o in tail) / len(tail)
                    L.append(f"- {SHORT[arm]}，种子 {seed}：SLOT 往回摆（余弦为负）{neg}/{len(tail)} 次；"
                             f"EA 选择改了又改回去，平均 {back:.2%}")
        L.append("")

        cad, tols, wins = plan["check"]["cadences"], plan["check"]["tolerances"], plan["check"]["windows"]
        L += ["## 问题二：每几轮校验一次", "",
              "校验的对象是“EA/KA 相互修正是否稳定”。下表按候选条件“SLOT 相对变化（和上一次校验比）连续 w 次低于阈值”事后模拟。"
              "阈值和 w 都是候选值，图谱写明待定。", ""]
        for arm in ARMS:
            if not runs[arm]:
                continue
            per_seed = {s: costs(r["rounds"]) for s, r in sorted(runs[arm].items())}
            tr_mean = sum(sum(t) / len(t) for t, _ in per_seed.values()) / len(per_seed)
            ck_mean = sum(c for _, c in per_seed.values()) / len(per_seed)
            L += [f"### {ARMS[arm]}", "",
                  f"- 每轮训练平均 {tr_mean:.1f} 秒；一次校验平均 {ck_mean:.2f} 秒（约为一轮训练的 {ck_mean / tr_mean:.1%}）。", ""]
            for w in wins:
                L += [f"连续 {w} 次低于阈值才停。格子：各种子停在第几轮｜平均总秒数（训练＋校验）｜停下时 TEST 主要指标的平均。"
                      f"跑满 {cap} 轮的主要指标平均 {sum(main_acc(r['rounds'][-1]) for r in runs[arm].values()) / len(runs[arm]):.1%}。", "",
                      "| 阈值 | " + " | ".join(f"每 {c} 轮校验一次" for c in cad) + " |",
                      "|---:|" + "---|" * len(cad)]
                for tol in tols:
                    cells = []
                    for c in cad:
                        stops, secs, accs = [], [], []
                        for s, r in sorted(runs[arm].items()):
                            stop = stop_round(r["rounds"], "slot", c, tol, w, cap)
                            end = stop if stop is not None else cap
                            train, ck = per_seed[s]
                            secs.append(sum(train[:end]) + (end // c + 1) * ck)
                            accs.append(main_acc(r["rounds"][end]))
                            stops.append(str(stop) if stop is not None else "未停")
                        cells.append(f"{'/'.join(stops)}｜{sum(secs) / len(secs):.0f} 秒｜{sum(accs) / len(accs):.1%}")
                    L.append(f"| {tol:g} | " + " | ".join(cells) + " |")
                L.append("")
            L += ["其他候选量（连续 1 次低于阈值；只列各种子停在第几轮）：", "",
                  "| 变化量 | 阈值 | " + " | ".join(f"每 {c} 轮" for c in cad) + " |", "|---|---:|" + "---|" * len(cad)]
            for m in ("ka", "ea", "answer"):
                for tol in tols:
                    row = []
                    for c in cad:
                        st = [stop_round(r["rounds"], m, c, tol, 1, cap) for _, r in sorted(runs[arm].items())]
                        row.append("/".join(str(x) if x is not None else "未停" for x in st))
                    L.append(f"| {MEASURE_LABELS[m]} | {tol:g} | " + " | ".join(row) + " |")
            L.append("")

    check = rec.get("check")
    if check:
        L += ["## 程序检查（契约，不是实验结果）", "",
              "- 每个阶段都有收据、轮数齐全、TEST 题数对得上；单向时间接包的 KA 从来没写过；统一校验只读（不改单元版本）。"
              + ("通过。" if not check.get("problems") else f"问题：{check['problems']}")]
        L += [f"- 提醒：{w}" for w in check.get("warnings", [])]
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


def lag1(x: dict) -> dict:
    lag = x["check"]["lag"]
    return lag["1"] if "1" in lag else lag[1]


if __name__ == "__main__":
    print(write_report(Path(sys.argv[1]))[:3000])
