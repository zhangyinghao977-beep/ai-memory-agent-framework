"""T9 报告：python -B report_t9.py <输出目录>。数字都从 receipts/ 和 gate.json 生成。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _release_support import (configure_runtime, dependency_run, freeze_plan_metadata,
    load_plan, load_run_plan, root_path, runner_arguments, source_hashes, require_successful_gate)
TASK_NAMES = {"anchor": "选和锚同包的（锚题）", "mutual": "选有同包支持的（互相支持题）"}
KIND_NAMES = {"sim": "晶格比较（12 个数）", "pair": "成对比较", "attn": "attention"}


def mean(xs: list) -> float:
    return sum(xs) / len(xs)


def main() -> int:
    out = root_path(sys.argv[1])
    plan = load_run_plan(out, HERE / "PLAN.json")
    T8 = dependency_run(plan, "t8") / "receipts"
    gate = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    frozen = json.loads((out / "FROZEN.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "receipts").glob("*.json"))]
    cell = {(r["task"], r["kind"], r["cond"], r["seed"]): r for r in recs}
    seeds, tasks = plan["seeds"], plan["tasks"]
    anchor_rel = plan["spec"]["n_relations"] - 1
    done = len(recs) == frozen["jobs"]

    def got(task, kind, cond):
        return [cell[(task, kind, cond, s)] for s in seeds if (task, kind, cond, s) in cell]

    def vals(task, kind, cond, split="test_iid", key="choice_two"):
        return [100 * r[split][key] for r in got(task, kind, cond)]

    def t8(task, kind, split):
        rs = [json.loads((T8 / f"{task}-{kind}-full-s{s}.json").read_text(encoding="utf-8")) for s in seeds]
        return [100 * r[split]["choice_two"] for r in rs]

    def fmt(xs):
        return " / ".join(f"{x:.1f}" for x in xs) if xs else "—"

    def seed_means(task, kind, block, key, field="choice_two"):
        """每个种子，把几段的结果平均。"""
        return [100 * mean([x[field] for x in r[block][key]]) for r in got(task, kind, "all") if block in r]

    L = ["# T9 运行报告（自动生成；规则从事件链里长出来，世界变了能修订）", "",
         f"- 完成任务：{len(recs)}/{frozen['jobs']}", f"- 门禁问题：{gate['problems'] or '没有'}",
         f"- 总训练时间：{sum(r['seconds'] for r in recs) / 3600:.2f} 小时（各工人相加）",
         "- 主要指标是两个候选的题上选对的比例，机会水平 50%。选到别的位置也算错，所以可以低于 50%。",
         "- 向量和规则表都是长出来的，长的时候不用包的编号，也不用答案。模型不知道谁是锚。"]
    L += ["", "## 规则表", "", "| 题型 | 规则表 | 错的格子（共 64 格） | 余弦基线：同一批包 | 余弦基线：没见过的包 |", "|---|---|---:|---:|---:|"]
    for t in tasks:
        for name, x in gate["tasks"][t]["tables"].items():
            L.append(f"| {t} | {name} | {x['wrong_cells']} | {100 * x['cosine']['test_iid']:.1f} | {100 * x['cosine']['test_new']:.1f} |")
    for t in tasks:
        L += ["", f"## {TASK_NAMES[t]}：结果", "", "| 做法 | 规则表 | 同一批包 | 没见过的包 | 一个候选的题 |", "|---|---|---|---|---|"]
        for k in ("sim", "pair", "attn"):
            for c in plan["arms"][k]:
                L.append(f"| {KIND_NAMES[k]} | {c} | {fmt(vals(t, k, c))} | {fmt(vals(t, k, c, 'test_new'))} | {fmt(vals(t, k, c, key='choice_one'))} |")
            if done:
                L.append(f"| {KIND_NAMES[k]}（T8：规则是人给的） | — | {fmt(t8(t, k, 'test_iid'))} | {fmt(t8(t, k, 'test_new'))} | — |")
        L.append(f"| attention，规则写在权重里（`vec`） | — | {fmt(vals(t, 'vec', 'all'))} | {fmt(vals(t, 'vec', 'all', 'test_new'))} | — |")

    L += ["", "## 只换表：经验多少（`test_iid`，5 个种子平均，每种 8 段）", "", "| 题型 | 做法 | " + " | ".join(f"{n} 条链" for n in plan["sweep"]["chains"]) + " |",
          "|---|---|" + "---:|" * len(plan["sweep"]["chains"])]
    for t in tasks:
        for k in ("sim", "pair", "attn"):
            xs = [seed_means(t, k, "sweep", str(n)) for n in plan["sweep"]["chains"]]
            L.append(f"| {t} | {KIND_NAMES[k]} | " + " | ".join(f"{mean(x):.1f}" if x else "—" for x in xs) + " |")

    news = plan["shift"]["new_chains"]
    L += ["", f"## 世界变了：只换表，不重新训练（窗口 {plan['shift']['window']} 条，`test_iid` 换成新世界的关系，5 个种子平均，每种 8 段）", "",
          "| 题型 | 做法 | 世界没变时 | " + " | ".join(f"新链 {n} 条" for n in news) + " |", "|---|---|---:|" + "---:|" * len(news)]
    for t in tasks:
        for k in ("sim", "pair", "attn"):
            xs = [seed_means(t, k, "shift", str(n)) for n in news]
            base = vals(t, k, "all")
            L.append(f"| {t} | {KIND_NAMES[k]} | {mean(base) if base else 0:.1f} | " + " | ".join(f"{mean(x):.1f}" if x else "—" for x in xs) + " |")
        rs = got(t, "vec", "all")
        if rs:
            L.append(f"| {t} | attention，规则写在权重里 | {mean(vals(t, 'vec', 'all')):.1f} | 新世界：{fmt([100 * r['test_shift']['choice_two'] for r in rs])} |" + " |" * (len(news) - 1))

    m4 = got("mutual", "attn", "m4")
    L += ["", f"## T8 的问题：attention 跑到 {plan['m4_steps']} 步", "", f"- `test_iid`：{fmt(vals('mutual', 'attn', 'm4'))}", f"- `test_new`：{fmt(vals('mutual', 'attn', 'm4', 'test_new'))}"]
    if done:
        L.append(f"- T8 的 48000 步：`test_iid` {fmt(t8('mutual', 'attn', 'test_iid'))}")

    def verdict(ok):
        return "**成立**" if ok else "**不成立**"

    if done:
        r1i = {t: vals(t, "sim", "all") for t in tasks}
        r1a, r1m = vals("anchor", "sim", "all", "test_new"), vals("mutual", "sim", "all", "test_new")
        ws = [r["weights"]["w"] for r in got("anchor", "sim", "all")]
        margin = [w[anchor_rel] - max(x for i, x in enumerate(w) if i != anchor_rel) for w in ws]
        r3 = {t: vals(t, "sim", "relshuf") for t in tasks}
        few, many = mean(seed_means("mutual", "sim", "sweep", "64")), mean(seed_means("mutual", "sim", "sweep", "512"))
        r5p = {t: vals(t, "pair", "all") for t in tasks}
        r5a = vals("anchor", "attn", "all")
        r6 = {t: [b - x for b, x in zip(vals(t, "sim", "all"), seed_means(t, "sim", "shift", "256"))] for t in tasks}
        r7a = vals("anchor", "vec", "all")
        r7b = [100 * r["test_shift"]["choice_two"] for r in got("anchor", "vec", "all")]
        r8 = {t: [mean(seed_means(t, "sim", "shift", str(n))) for n in (0, 128, 256)] for t in tasks}
        r9 = vals("mutual", "attn", "m4")

        def two(d):
            return "；".join(f"{t} {fmt(v)}" for t, v in d.items())

        L += ["", "## 事先写下的预测", "",
              f"- **R1** 12 个数靠答案就够：同一批包 {two(r1i)}；没见过的包 anchor {fmt(r1a)}；mutual {fmt(r1m)}。{verdict(all(x >= 99 for v in r1i.values() for x in v) and all(x >= 99 for x in r1a) and all(x >= 95 for x in r1m))}",
              f"- **R2** 答案的反馈能指出谁是锚（锚的权重比第二名高多少）：{fmt(margin)}。{verdict(all(x > 1 for x in margin))}",
              f"- **R3** 规则确实来自事件链：{two(r3)}。{verdict(all(x <= 30 for v in r3.values() for x in v))}",
              f"- **R4** 经验不够时规则会错：64 条链 {few:.1f}；512 条链 {many:.1f}。{verdict(few <= 85 and many >= 99)}",
              f"- **R5** 学来的比较也能用长出来的规则：成对比较 {two(r5p)}；attention 锚题 {fmt(r5a)}。{verdict(all(sum(x >= 95 for x in v) >= 4 for v in r5p.values()) and sum(x >= 95 for x in r5a) >= 4)}",
              f"- **R6** 规则写在表里，世界变了换表就行（比世界没变时低多少）：{two(r6)}。{verdict(all(x <= 2 for v in r6.values() for x in v))}",
              f"- **R7** 规则写在权重里，世界变了就垮：世界没变 {fmt(r7a)}；世界变了 {fmt(r7b)}。{verdict(sum(x >= 90 for x in r7a) >= 4 and all(x <= 40 for x in r7b))}",
              f"- **R8** 修订有过渡（新链 0、128、256 条）：{two(r8)}。{verdict(all(v[1] <= v[2] - 10 and v[1] >= v[0] + 10 for v in r8.values()))}",
              f"- **R9** attention 只是慢：{fmt(r9)}。{verdict(sum(x >= 90 for x in r9) >= 3)}"]
    else:
        L += ["", "还没跑完，不判定预测。"]
    if recs:
        L += ["", "## 契约（按构造必然，不算发现）", ""]
        if m4:
            L.append(f"- `m4` 的前 48000 步和 T8 逐位相同：{sum(r['first_part_same_as_t8'] for r in m4)}/{len(m4)}。")
        L += ["- 长规则的函数只收关系和查询，模型的代码不读 `anchor_rel`，换表不改权重：见 `project/tests/test_t9.py`。"]
    L += ["", "## 限制", "",
          "- 不证明晶格可以不要起点。比较器的结构、长规则的公式、窗口大小都是人写的。长出来的是内容，不是形式。",
          "- 这里“规则”只是查询和关系的对应，不是语言里的合法转移。查询是看得见的，题目的格式是给的。",
          "- 同一查询的链里总有对应的关系，这是出题方式决定的，信号很强。",
          "- 系统不会发现世界变了，只是忘掉旧的。旧版本没有保留，“按承接版本保留历史”这一条没有测。",
          "- 只测一种世界变化，锚没有变。只长了“求同”，没有长“存异”。",
          "- 中点切分是看了 dev 才定的。",
          "- 受控合成任务，很小的模型，超参数没有分别调。这个实验不测量势 Φ 和事件链的熵。", ""]
    (out / "REPORT.zh.md").write_text("\n".join(L), encoding="utf-8")
    print(f"report: {len(recs)}/{frozen['jobs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
