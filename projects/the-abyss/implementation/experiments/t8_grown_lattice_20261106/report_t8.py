"""T8 报告：python -B report_t8.py <输出目录>。数字都从 receipts/ 和 gate.json 生成。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
TASK_NAMES = {"anchor": "选和锚同包的（锚题）", "mutual": "选有同包支持的（互相支持题）"}
KIND_NAMES = {"sim": "晶格比较（6 个数）", "pair": "成对比较", "attn": "attention"}
COND_NAMES = {"full": "16384 条链", "n4096": "4096 条链", "n1024": "1024 条链", "dil80": "打乱 80%", "shuffled": "全部打乱（反向对照）"}


def main() -> int:
    out = root_path(sys.argv[1])
    plan = load_run_plan(out, HERE / "PLAN.json")
    gate = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))]
    cell = {(r["task"], r["kind"], r["cond"], r["seed"]): r for r in recs}
    seeds, tasks = plan["seeds"], plan["tasks"]

    def vals(task, kind, cond, split="test_iid", key="choice_two"):
        return [100 * cell[(task, kind, cond, s)][split][key] for s in seeds if (task, kind, cond, s) in cell]

    def fmt(xs):
        return " / ".join(f"{x:.1f}" for x in xs) if xs else "—"

    done = len(recs) == frozen["jobs"]
    L = ["# T8 运行报告（自动生成；晶格从经验里长出来）", "",
         f"- 完成任务：{len(recs)}/{frozen['jobs']}", f"- 门禁问题：{gate['problems'] or '没有'}",
         f"- 总训练时间：{sum(r['seconds'] for r in recs) / 3600:.2f} 小时（各工人相加）",
         "- 主要指标是两个候选的题上选对的比例，机会水平 50%。长向量时不用包的编号，也不用答案。"]
    for t in tasks:
        g = gate["tasks"][t]["conditions"]
        L += ["", f"## {TASK_NAMES[t]}：长出来的向量", "", "| 经验 | 同包余弦（旧包） | 异包余弦（旧包） | 同包余弦（新包） | 余弦基线：同一批包 | 余弦基线：没见过的包 |", "|---|---:|---:|---:|---:|---:|"]
        for c in plan["conditions"]:
            x = g[c]
            L.append(f"| {COND_NAMES[c]} | {x['old']['same_cos']:.3f} | {x['old']['other_abs_cos']:.3f} | {x['new']['same_cos']:.3f} | {100 * x['cosine']['test_iid']:.1f} | {100 * x['cosine']['test_new']:.1f} |")
        L += ["", f"## {TASK_NAMES[t]}：结果", "", "| 做法 | 经验 | 同一批包 | 没见过的包 |", "|---|---|---|---|"]
        for k, conds in plan["arms"].items():
            for c in conds:
                L.append(f"| {KIND_NAMES[k]} | {COND_NAMES[c]} | {fmt(vals(t, k, c))} | {fmt(vals(t, k, c, 'test_new'))} |")

    def verdict(ok):
        return "**成立**" if ok else "**不成立**"

    if done:
        m1i = {t: vals(t, "sim", "full") for t in tasks}
        m1n = {t: vals(t, "sim", "full", "test_new") for t in tasks}
        m2 = {t: vals(t, "sim", "shuffled") for t in tasks}
        m3 = vals("mutual", "sim", "n1024")
        m4p, m4a = vals("mutual", "pair", "full"), vals("mutual", "attn", "full")
        m5s, m5p, m5a = (vals("mutual", k, "full", "test_new") for k in ("sim", "pair", "attn"))
        m6a, m6m = vals("anchor", "sim", "dil80"), vals("mutual", "sim", "dil80")

        def two(d):
            return "；".join(f"{t} {fmt(v)}" for t, v in d.items())

        L += ["", "## 事先写下的预测", "",
              f"- **M1** 长出来的晶格够用：同一批包 {two(m1i)}；没见过的包 {two(m1n)}。{verdict(all(x >= 99 for v in m1i.values() for x in v) and all(x >= 95 for v in m1n.values() for x in v))}",
              f"- **M2** 信号确实来自事件链：{two(m2)}。{verdict(all(x <= 55 for v in m2.values() for x in v))}",
              f"- **M3** 经验的多少有影响：{fmt(m3)}。{verdict(all(x <= 95 for x in m3))}",
              f"- **M4** 学来的比较也能用长出来的晶格：成对比较 {fmt(m4p)}；attention {fmt(m4a)}。{verdict(sum(x >= 95 for x in m4p) >= 4 and sum(x >= 90 for x in m4a) >= 3)}",
              f"- **M5** 新包不用重训，但只有晶格比较不掉分：晶格比较 {fmt(m5s)}；成对比较 {fmt(m5p)}；attention {fmt(m5a)}。{verdict(all(x >= 95 for x in m5s) and sum(x <= 90 for x in m5p) >= 4 and sum(x <= 90 for x in m5a) >= 4)}",
              f"- **M6** 信号被稀释时，锚题比互相支持题扛得住：锚题 {fmt(m6a)}；互相支持题 {fmt(m6m)}。{verdict(all(x >= 95 for x in m6a) and all(x <= 85 for x in m6m))}"]
    else:
        L += ["", "还没跑完，不判定预测。"]
    if recs:
        L += ["", "## 契约（按构造必然，不算发现）", "", f"- 给规则时一个候选的题，最低 {100 * min(r['test_iid']['choice_one'] for r in recs):.1f}%。",
              "- 新经历不改旧向量，长向量的函数只收对象编号：见 `project/tests/test_t8.py`。"]
    L += ["", "## 限制", "",
          "- 同包的事件常在同一条链里，是这份题的出题方式决定的，信号很强。真实经验里有没有这么强，不知道。",
          "- 只长了“求同”，没有长“存异”。规则（关系对不对得上）还是给的。",
          "- 新旧对象的向量不在同一组坐标里，新旧对象混在一条链里时没有测。",
          "- 共现 + SVD 是一种工作解释，不是构造里的求同，也不代表 KA 的最终做法。",
          "- 新经历只长新对象的做法是看了 dev 才定的。",
          "- 受控合成任务，很小的模型，超参数没有分别调。这个实验不测量势 Φ 和事件链的熵。", ""]
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    print(f"report: {len(recs)}/{frozen['jobs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
