"""由本副本的新运行收据自动生成 REPORT.zh.md；数字和结论句来自凭证。

用法：python -B report_t4.py <输出目录>。流水线每完成一个种子、停下或出错时也会自动调用。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import load_plan, root_path
sys.path.insert(0, str(HERE.parent / "t2_repair_20261102"))

from report_t2 import verdict, wilson  # noqa: E402

ARMS = {"frozen": "只用不学", "survive": "清醒／睡眠（EA 受 CA 指引）", "survive_blind": "清醒／睡眠（EA 看不到 CA）",
        "survive_tight": "清醒／睡眠（EA 受 CA 指引，睡眠池小）", "full_repair": "每次睡眠全部重修（EA 受 CA 指引）"}
PROBES = {"probe_old": "旧世界", "probe_new_package": "新包", "probe_new_genre": "新体裁", "probe_new_genre_dup": "新体裁带改口"}
CHANGES = {"old": "旧", "new_package": "新包", "new_genre": "新体裁", "new_genre_dup": "带改口"}
LIMITATIONS = [
    "T4 是受控合成任务：世界的变化、规则都是出题器定的，结果只说明这个任务。",
    "这是经验主义的实验，只借用红尘仙的设计思想（固定调用协议、资源保护、快速和长期登记），结果不能当成红尘仙的证据。",
    "FSM 和资源保护的阈值都是人写的脚手架，参数固定，属于演示，不是系统自己产生的闭环。系统还不会 coding。",
    "CA 指引 EA 的接法（CA 的链状态投影以后加到事件表示上）是本实验的工作实现；图谱写明回修和训练的具体路由未定。",
    "EA 看不到 CA 时学不会“档案里链内以最早的为准”，一半是按构造必然的：它看不到体裁。这部分算契约，不算发现。",
    "“试候选”和指引的放大倍数是在种子 1、开发用的日子题上改出来的。正式运行换了日子题和探针，种子 0、2 也没调过，但世界的规则相同。",
    "“够用”的标准（最差一类不低于旧本领减 margin）、梯子的顺序、材料窗口都是事先固定的一种排法，换一种结果会不同。",
    "自检的类别只用看得见的东西：体裁、有没有过去没见过的包。这是工作解释。",
    "description 由符号模板生成，是占位，不代表语义理解。",
    "重启测试只覆盖计划里选的几个中断位置，不证明任何故障都零丢失。断电时，最后一次登记以后的资源消耗会丢，最多约 persist_every_s 秒。",
    "遗忘这次没有做，只列候选。存储增长是不删除任何东西时的数字。",
    "探针用隐藏真值，只用于报告；不进入训练和“够用”的判断。",
    "超参数沿用 T2、T3，事先固定，没有调参。三个种子的起点是 T3 的三个种子，彼此并不等价（T3 的种子 0 组合较散）。",
]


def load(out: Path) -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))}


def cell(t: dict | None, interval: bool = False) -> str:
    if not t or not t["n"]:
        return "—"
    s = f"{t['correct']}/{t['n']}（{t['correct'] / t['n']:.1%}）"
    if interval:
        lo, hi = wilson(t["correct"], t["n"])
        s += f" [{lo:.1%}–{hi:.1%}]"
    return s


def as_forced(t: dict) -> dict:
    return {"forced_correct": t["correct"], "n": t["n"]}


def pool_sum(days: list, pool: str, res: str) -> float:
    return sum(d["pools"][pool][res] for d in days)


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
    L = ["# T4 运行报告（自动生成；存活：清醒／睡眠、CA 约束 EA、资源、重启）", "",
         f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
         "- 本报告来自新的复现运行，不是历史实验回执。",
         f"- 运行状态：`{status.get('status', status.get('state', '?'))}`"
         + (f"；原因：{status.get('reason')}" if status.get("reason") else "")
         + (f"；停在：`{status.get('stage')}`" if status.get("status") not in (None, "completed") else ""),
         f"- 已完成阶段：{len(done)}/{len(stages)}",
         f"- 计划 SHA256：`{frozen.get('plan_sha256', '?')}`", "",
         "**读法**：",
         "- 探针是从不出现在日子里的题，用隐藏真值，只用于报告。格子里是“答对数/题数（比例）”，最后一天的表带 95% Wilson 区间。",
         "- 系统只收到对整个问答的反馈：这次回答对不对。",
         "- 所有数字都从 `receipts/` 生成。", ""]

    gate = rec.get("gate")
    if gate:
        w = gate["world_spec"]
        L += ["## 世界与门禁", "",
              f"- 新包 {gate['new_packages']}，第 {w['new_package_day']} 天起；新体裁第 {w['new_genre_day']} 天起；"
              f"一共 {w['days']} 天，每天 {w['questions_per_day']} 题。",
              f"- 日子里各类题：{gate['by_change']}", f"- 各部分题数：{gate['episodes_by_split']}",
              f"- 起点：{ {k: v['units'] for k, v in gate['starts'].items()} }（单元数；T3 双向做法第 20 轮）", ""]

    runs = {arm: {r["seed"]: r for k, r in rec.items() if k.startswith(f"{arm}-s")} for arm in ARMS}
    if any(runs.values()):
        L += ["## 最后一天的探针", "", "| 组 | 种子 | " + " | ".join(PROBES.values()) + " |", "|---|---:|" + "---:|" * len(PROBES)]
        for arm, label in ARMS.items():
            for seed, r in sorted(runs[arm].items()):
                p = r["summary"]["days"][-1].get("probes", {})
                L.append(f"| {label} | {seed} | " + " | ".join(cell(p.get(k), True) for k in PROBES) + " |")
        L += ["", "自动比较（每个种子的 95% 区间两两比较）："]

        def last(arm, key):
            return [as_forced(r["summary"]["days"][-1]["probes"][key]) for _, r in sorted(runs[arm].items())]
        for x, y in (("survive", "frozen"), ("survive", "survive_blind"), ("survive", "survive_tight"), ("full_repair", "survive")):
            if runs[x] and runs[y]:
                for key, name in PROBES.items():
                    L.append(f"- {ARMS[x]} 对 {ARMS[y]}，{name}：**{verdict(last(x, key), last(y, key))}**")
        L += ["", "## 每天的探针", ""]
        for arm, label in ARMS.items():
            for seed, r in sorted(runs[arm].items()):
                L += [f"**{label}，种子 {seed}**", "", "| 天 | " + " | ".join(PROBES.values()) + " | 当天答对（" + "／".join(CHANGES.values()) + "）| 缓存 | 没答 |",
                      "|---:|" + "---:|" * len(PROBES) + "---|---:|---:|"]
                for d in r["summary"]["days"]:
                    p = d.get("probes", {})
                    st = "／".join(f"{d['stream'][c][1] / d['stream'][c][0]:.0%}" if c in d["stream"] else "—" for c in CHANGES)
                    L.append(f"| {d['day']} | " + " | ".join(f"{p[k]['correct'] / p[k]['n']:.1%}" if k in p else "—" for k in PROBES)
                             + f" | {st} | {d['cache']} | {d['unanswered']} |")
                L.append("")

        L += ["## 资源（真实消耗）", "",
              "| 组 | 种子 | 清醒 CPU 秒 | 清醒显卡秒 | 睡眠 CPU 秒 | 睡眠显卡秒 | 最后一天睡眠 CPU 秒 | 单元存储 MiB | 快速登记 MiB | 长期库 MiB | 遗忘候选 | 写单元次数 | 阶段墙钟（分钟） |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for arm, label in ARMS.items():
            for seed, r in sorted(runs[arm].items()):
                s = r["summary"]
                days = s["days"]
                sg = days[-1]["storage"]
                L.append(f"| {label} | {seed} | {pool_sum(days, 'awake', 'cpu_seconds'):.0f} | {pool_sum(days, 'awake', 'gpu_seconds'):.0f} | "
                         f"{pool_sum(days, 'sleep', 'cpu_seconds'):.0f} | {pool_sum(days, 'sleep', 'gpu_seconds'):.0f} | "
                         f"{days[-1]['pools']['sleep']['cpu_seconds']:.0f} | {sg['units_bytes'] / 2 ** 20:.1f} | {sg['quick_bytes'] / 2 ** 20:.1f} | "
                         f"{sg['long_bytes'] / 2 ** 20:.1f} | {days[-1]['superseded']} | {s['unit_writes']} | {r['seconds'] / 60:.0f} |")
        L += ["", "每天的睡眠 CPU 秒：", ""]
        for arm in ARMS:
            for seed, r in sorted(runs[arm].items()):
                L.append(f"- {ARMS[arm]}，种子 {seed}：" + ", ".join(f"{d['pools']['sleep']['cpu_seconds']:.0f}" for d in r["summary"]["days"]))
        L += ["", "## 睡眠和 FSM", ""]
        for arm, label in ARMS.items():
            for seed, r in sorted(runs[arm].items()):
                s = r["summary"]
                st = Counter(x["status"] for x in s["sleeps"])
                ad = Counter(x["adopted"] for x in s["sleeps"] if x["adopted"])
                L.append(f"- {label}，种子 {seed}：FSM {s['fsm_states']}；睡眠结果 {dict(st)}；采用的层 {dict(ad)}；"
                         f"清醒小修 {len(s['awake_fixes'])} 次；被资源保护打断 {len(s['interrupts'])} 次")
        L.append("")

    crash = {k: r for k, r in rec.items() if k.startswith("crash-s")}
    if crash:
        L += ["## 重启测试（契约，不是实验结果）", ""]
        for k, r in sorted(crash.items()):
            L.append(f"- `{k}`：" + "；".join(f"{c['point']} 第 {c['nth']} 次，退出码 {c['exit']}" + (f"（{c['note']}）" if c.get("note") else "")
                                             for c in r["crashes"]))
            L.append(f"  - 恢复：" + "；".join(f"断电中断 {len(x.get('lost_calls', []))} 个调用，补报 {len(x.get('late_reports', []))} 个，"
                                            f"未采用的版本 {len(x.get('leftovers', {}).get('unadopted_versions', []))} 个，"
                                            f"临时文件 {len(x.get('leftovers', {}).get('tmp_files', []))} 个" for x in r["recoveries"]))
            L.append(f"  - 契约：{'全部满足' if not r['contract_problems'] else r['contract_problems']}")
        L.append("")
    if rec.get("check"):
        L += ["## 程序检查（契约，不是实验结果）", "",
              "- 每道题最多答完一次；答完＋没答等于总题数；资源池累计消耗只增不减；只用不学的组没有写单元；长期库和游标一致、没有缺项："
              + ("全部满足。" if not rec["check"]["problems"] else str(rec["check"]["problems"])), ""]
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
