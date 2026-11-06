"""T10 事后检查：python -B posthoc_t10.py <run 目录> <输出目录>。

不训练。只载入存好的小模型（约 2 万个参数），在训练链和测试题上算分。
这些检查都是看了结果以后才做的，事先没有写下预测。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

import psutil
import torch

from run_t10 import HERE, T5Spec, build_lattice, build_task, setup, table, vectors
from _release_support import dependency_run, load_plan, load_run_plan, root_path
from empirical_core.t5.model import take
from empirical_core.t6.model import Selector6, evaluate
from empirical_core.t9.model import Selector9

N_TRAIN = 4096
NAMES = {"t8": "T8（人给规则）", "m4": "T8 跑到 96000 步", "t9": "T9（乘 1）", "quarter": "`quarter`", "zero": "`zero`", "off": "`off`"}
KINDS = {"pair": "成对比较", "attn": "attention"}


def fmt(xs: list) -> str:
    return " / ".join(f"{x:.1f}" for x in xs)


def main() -> int:
    setup()
    run, out = root_path(sys.argv[1]), root_path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=False)
    plan = load_run_plan(run, HERE / "PLAN.json")
    T8 = dependency_run(plan, "t8")
    T9 = dependency_run(plan, "t9")
    seeds, tasks = plan["seeds"], plan["tasks"]
    spec = T5Spec(**plan["spec"])
    bit = build_lattice(spec)["bit"]
    data = {t: build_task(t, spec) for t in tasks}
    vec = {t: vectors(t, data[t], spec, plan) for t in tasks}
    legal = {t: table("all", data[t], spec, plan) for t in tasks}
    train = {t: {k: v[:N_TRAIN] for k, v in data[t]["train"].items() if torch.is_tensor(v)} for t in tasks}

    def model(t: str, k: str, a: str, s: int):
        if a in ("t8", "m4"):
            m = Selector6(spec, vec[t], k, "full")
            p = T8 / "models" / f"{t}-{k}-full-s{s}.pt" if a == "t8" else T9 / "models" / f"mutual-attn-m4-s{s}.pt"
        else:
            m = Selector9(spec, vec[t], legal[t], k)
            p = T9 / "models" / f"{t}-{k}-all-s{s}.pt" if a == "t9" else run / "models" / f"{t}-{k}-{a}-s{s}.pt"
        m.load_state_dict(torch.load(p, weights_only=True), strict=False)
        return m.eval()

    def score(m, t: str, split) -> float:
        with torch.no_grad():
            return 100 * evaluate(m, split, bit)["choice_two"]

    L = ["# T10 事后检查（看了结果才做的，事先没有预测）", "", "不训练。数字由 `posthoc_t10.py` 从存好的模型生成。", "",
         f"分数都是两个候选的题上选对的比例，机会水平 50%。“训练链”是训练集的前 {N_TRAIN} 条，模型每条大约看过 375 遍（m4 约 750 遍）。"]
    res: dict = {"train_vs_test": {}, "no_rel": {}}

    # 0. 载入的模型和回执对得上吗
    ok = total = 0
    for t in tasks:
        for k in KINDS:
            for a in ("quarter", "zero") + (("off",) if t == "mutual" else ()):
                for s in seeds:
                    r = json.loads((run / "receipts" / f"{t}-{k}-{a}-s{s}.json").read_text(encoding="utf-8"))
                    ok += abs(score(model(t, k, a, s), t, data[t]["test_iid"]) - 100 * r["test_iid"]["choice_two"]) < 1e-9
                    total += 1
    res["reload_ok"] = [ok, total]
    L += ["", "## 0. 契约", "", f"- 载入的模型在测试题上的分数和回执一样：{ok}/{total}。"]
    tr = data["mutual"]["train"]
    same = bool((legal["mutual"][tr["query"].unsqueeze(1), tr["rel"]] == (tr["rel"] == tr["query"].unsqueeze(1))).all())
    res["mutual_cand_equals_t8_flag"] = same
    L.append(f"- 互相支持题上，表给的候选和 T8 的 `is_q` 标记处处相同：{same}。这道题的 `is_a` 一直是 0。所以 `off` 和 T8 的输入信息一样，差别只在输入的维数和开始时的随机权重。")

    # 1. 训练链和测试题
    L += ["", "## 1. 训练链上的分数和测试题上的分数", "", "| 题型 | 做法 | 关系嵌入 | 训练链 | 平均 | 同一批包的测试题 | 平均 | 差 |", "|---|---|---|---|---:|---|---:|---:|"]
    for t in ("mutual", "anchor"):
        for k in KINDS:
            arms = ["t8"] + (["m4"] if (t, k) == ("mutual", "attn") else []) + ["t9", "quarter", "zero"] + (["off"] if t == "mutual" else [])
            for a in arms:
                ms = [model(t, k, a, s) for s in seeds]
                a_tr = [score(m, t, train[t]) for m in ms]
                a_te = [score(m, t, data[t]["test_iid"]) for m in ms]
                res["train_vs_test"][f"{t}-{k}-{a}"] = {"train": a_tr, "test": a_te}
                L.append(f"| {t} | {KINDS[k]} | {NAMES[a]} | {fmt(a_tr)} | {mean(a_tr):.1f} | {fmt(a_te)} | {mean(a_te):.1f} | {mean(a_tr) - mean(a_te):.1f} |")

    # 2. 去掉关系嵌入
    L += ["", "## 2. 只在评测时把关系嵌入换成 0", "", "看模型靠不靠这部分输入。没有重新训练。", "", "| 题型 | 做法 | 关系嵌入 | 训练链：原来 → 去掉 | 测试题：原来 → 去掉 |", "|---|---|---|---|---|"]
    for t in ("mutual", "anchor"):
        for k in KINDS:
            for a in ("t9", "quarter", "zero"):
                b_tr, b_te = [], []
                for s in seeds:
                    m = model(t, k, a, s)
                    with torch.no_grad():
                        m.rel.weight.zero_()
                    b_tr.append(score(m, t, train[t]))
                    b_te.append(score(m, t, data[t]["test_iid"]))
                x = res["train_vs_test"][f"{t}-{k}-{a}"]
                res["no_rel"][f"{t}-{k}-{a}"] = {"train": b_tr, "test": b_te}
                L.append(f"| {t} | {KINDS[k]} | {NAMES[a]} | {mean(x['train']):.1f} → {mean(b_tr):.1f} | {mean(x['test']):.1f} → {mean(b_te):.1f} |")

    # 3. 训练到底奖励了什么
    def split(m, t: str, d: dict) -> tuple:
        """两个候选的题，按两个候选的答案同不同分开算选对的比例。答案只有一位，答案相同时选哪个都不扣分。"""
        n = len(d["target"])
        with torch.no_grad():
            pick = torch.cat([m(take(d, torch.arange(s, min(s + 2048, n)))).argmax(-1) for s in range(0, n, 2048)])
        cand = legal[t][d["query"].unsqueeze(1), d["rel"]]
        ones = (bit[d["obj"]] * cand.float()).sum(-1)
        two = d["n_cand"] == 2
        diff, same = two & (ones == 1), two & (ones != 1)
        right = (pick == d["target"]).float()
        return 100 * float(right[diff].mean()), 100 * float(right[same].mean()), 100 * float(diff.sum()) / float(two.sum())

    L += ["", "## 3. 把两个候选的题按答案同不同分开", "",
          "答案是对象的一位。两个候选的答案相同时，选哪个都不扣分，训练没有告诉模型该选谁。只有答案不同的题才有信号。",
          "如果模型只是把训练链的答案背下来：训练链上答案不同的题约 100，答案相同的题约 50，合起来约 75；测试题两边都约 50。",
          "如果模型学到了规则：两边都高，训练链和测试题都一样。", "",
          "| 题型 | 做法 | 关系嵌入 | 训练链：答案不同 | 训练链：答案相同 | 测试题：答案不同 | 测试题：答案相同 | 答案不同的题占比 |", "|---|---|---|---:|---:|---:|---:|---:|"]
    res["split"] = {}
    for t in ("mutual", "anchor"):
        for k in KINDS:
            arms = ["t8"] + (["m4"] if (t, k) == ("mutual", "attn") else []) + ["t9", "quarter", "zero"] + (["off"] if t == "mutual" else [])
            for a in arms:
                ms = [model(t, k, a, s) for s in seeds]
                x, y = [split(m, t, train[t]) for m in ms], [split(m, t, data[t]["test_iid"]) for m in ms]
                res["split"][f"{t}-{k}-{a}"] = {"train": x, "test": y}
                L.append(f"| {t} | {KINDS[k]} | {NAMES[a]} | {mean(v[0] for v in x):.1f} | {mean(v[1] for v in x):.1f} | {mean(v[0] for v in y):.1f} | {mean(v[1] for v in y):.1f} | {mean(v[2] for v in y):.1f} |")

    (out / "REPORT.zh.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out / "numbers.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("posthoc done", ok, total, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
