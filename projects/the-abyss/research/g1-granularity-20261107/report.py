"""Summarize every planned arm; no project imports or training."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
def read(name): return json.loads((ROOT / name).read_text(encoding="utf-8"))
def sha(data): return hashlib.sha256(data).hexdigest()
def write(name, value): (ROOT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
def stats(values):
    return {"mean": statistics.mean(values), "sample_std": statistics.stdev(values) if len(values) > 1 else None, "min": min(values), "max": max(values), "n_seeds": len(values)}
def value(r, field): return r["metrics"]["strata"][field]["expected_accuracy"]

def main():
    plan, frozen, status = read("PLAN.json"), read("FROZEN.json"), read("RUN_STATUS.json")
    for name, expected in {**frozen["sources"], **frozen["data"]}.items():
        assert sha((ROOT / name).read_bytes()) == expected, "Frozen bytes changed: " + name
    receipts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "receipts").glob("*.json"))]
    keyed = {(r["seed"], r["train_pairs"], r["arm"]["name"]): r for r in receipts}
    assert len(keyed) == len(receipts)
    wanted = {(s, b, a["name"]) for s in plan["seeds"] for b in plan["train_pairs"] for a in plan["arms"]}
    assert set(keyed).issubset(wanted)
    complete = [s for s in plan["seeds"] if all((s, b, a["name"]) in keyed for b in plan["train_pairs"] for a in plan["arms"])]
    if status["status"] == "COMPLETED": assert set(keyed) == wanted
    for s in complete:
        for b in plan["train_pairs"]:
            group = [keyed[s, b, a["name"]] for a in plan["arms"]]
            for field in ["dataset_sha256", "learner_observations_sha256", "update_order_sha256", "allocated_slots"]:
                assert len({r[field] for r in group}) == 1, field
            assert all(r["dataset_sha256"] == frozen["data"][f"data/seed-{s}.json"] for r in group)
            assert all(r["training"]["presentations"] == plan["learner"]["steps"] for r in group)
            assert all(r["active_shared_scores"] == r["allocated_slots"] // r["arm"]["size"] for r in group)
            assert all(all(math.isfinite(x) for x in r["weights"]) for r in group)
            assert len({r["metrics"]["strata"]["all"]["n"] for r in group}) == 1
    summary = {"status": status["status"], "complete_balanced_seeds": complete, "planned_seeds": plan["seeds"], "receipts_total": len(receipts), "partial_seeds_excluded_from_aggregation": sorted({r['seed'] for r in receipts} - set(complete)), "statistical_scope": "Descriptive seed-level paired differences; sample SD is not a confidence interval; two worlds repeat one unordered pair.", "cells": [], "family_vs_random": []}
    lines = ["# G1 固定任务粒度小试 / Fixed-task granularity pilot", "", f"状态：**{status['status']}**；完整平衡种子 {len(complete)}/{len(plan['seeds'])}；回执 {len(receipts)}/{len(wanted)}。", "", "复用已审 T1 出题器；新增共享标量比较学习器。所有结果仅适用于这个合成诊断，未验证原神经模型、自然语言知识、动态成包或完整人工智能方案。", "", "所有数字为种子级均值，百分比。± 是种子间样本标准差，不是置信区间；Δ 是相对同种子 atomic 的配对百分点差。没有选择最好种子或最好粒度。", ""]
    for b in plan["train_pairs"]:
        lines += [f"## 固定训练对数 {b}", "", "| 分组 | 原子准确率 ± SD | Δ atomic | 源包内 | 源包间 | 同槽题比例 | 跨槽冲突题比例 | 事后查表参照 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for arm in plan["arms"]:
            if not complete: continue
            rs = [keyed[s, b, arm["name"]] for s in complete]
            deltas = [value(keyed[s, b, arm["name"]], "all") - value(keyed[s, b, "atomic"], "all") for s in complete]
            cell = {"train_pairs": b, "arm": arm, "overall": stats([value(r, 'all') for r in rs]), "within_reference": stats([value(r, 'within_reference') for r in rs]), "cross_reference": stats([value(r, 'cross_reference') for r in rs]), "paired_delta_atomic": stats(deltas), "delta_positive_seeds": sum(x > 0 for x in deltas), "delta_negative_seeds": sum(x < 0 for x in deltas), "shared_slot_fraction": stats([r['metrics']['shared_slot_fraction'] for r in rs]), "conflicting_row_fraction": stats([r['metrics']['group_pair_conflicts']['conflicting_fraction_of_all_rows'] for r in rs]), "posthoc_lookup_reference": stats([r['metrics']['group_pair_conflicts']['posthoc_test_label_majority_lookup_reference'] for r in rs]), "per_seed": [{"seed": r['seed'], "overall":value(r,'all'), "within_reference":value(r,'within_reference'), "cross_reference":value(r,'cross_reference'), "delta_atomic":d, "graph":r['graph'], "stratum_denominators":{k:v['n'] for k,v in r['metrics']['strata'].items()}} for r,d in zip(rs,deltas)]}
            summary['cells'].append(cell)
            sd = cell['overall']['sample_std'] or 0
            lines.append(f"| {arm['name']} | {100*cell['overall']['mean']:.2f} ± {100*sd:.2f} | {100*cell['paired_delta_atomic']['mean']:+.2f} | {100*cell['within_reference']['mean']:.2f} | {100*cell['cross_reference']['mean']:.2f} | {100*cell['shared_slot_fraction']['mean']:.2f} | {100*cell['conflicting_row_fraction']['mean']:.2f} | {100*cell['posthoc_lookup_reference']['mean']:.2f} |")
        lines += [""]
        for size in [2,4,8]:
            if not complete: continue
            delta = [value(keyed[s,b,f'family{size}'],'all')-value(keyed[s,b,f'random{size}'],'all') for s in complete]
            summary['family_vs_random'].append({'train_pairs':b,'size':size,'paired_difference':stats(delta)})
    lines += ["## 如何理解", "", "- 包内/包间始终按不变的源参考家族计算；当前共享分组不会改变这两种错误的定义。逐种子分母、图连通性和完整分层在 SUMMARY.json 与 receipts/。", "- 同槽候选按 0.5 计分；跨槽也可能要求相反赢家。事后查表参照使用测试标签，较共享标量模型更宽松，仅诊断信息损失，未用于训练或选择实验臂。", "- family 分组使用了生成器提供的相关性先验；random 是相同大小的随机共享对照。不能把先验传播、桥接未见原子或断开的比较图说成发现了知识结构。", "- 世界反转规则和 A/B 对应由程序给定；两个世界是同一对象对的重复测量。有效自由度随分组改变，尽管每臂分配同样的96个标量槽和同样的更新预算。", "- 64/512训练对属于预先指定的两档条件；不根据结果追加学习率、种子或分组搜索。失败和未达预期结果全部保留。", "", "## 复现与证据", "", "方案：[PREREG.md](PREREG.md)；配置：[PLAN.json](PLAN.json)；冻结：[FROZEN.json](FROZEN.json)；核验：[VERIFICATION.json](VERIFICATION.json)。", "", "运行资源分别见 RESOURCES_prepare.json 和 RESOURCES_run.json。仅本进程使用低优先级、单CPU亲和及软节流；没有导入torch、使用GPU或操作已有实验进程。", "", "## English boundary", "", "This is a fixed-task synthetic pilot of hard score sharing. All planned arms and balanced seeds are reported. Atomic answers are preserved. Results do not establish optimal granularity for real knowledge, learned group formation, or superiority of an attention architecture. Shared-slot ties, conflicting group-pair labels, unseen atoms and disconnected comparison graphs remain explicit. The post-hoc lookup reference uses test labels only for diagnosis, never training or selection.", ""]
    write("SUMMARY.json", summary)
    write("VERIFICATION.json", {"status":"passed", "frozen_sources_and_data_match": True, "same_data_observations_order_and_allocated_slots_within_each_condition":True, "same_presentation_budget":True, "finite_weights":True, "only_balanced_seeds_aggregated":True, "complete_balanced_seeds":complete, "receipt_count":len(receipts), "runtime_status":status['status']})
    (ROOT / 'REPORT.md').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
    print(json.dumps({'status':status['status'],'complete_seeds':len(complete),'receipts':len(receipts),'verification':'passed'}))

if __name__ == '__main__': main()
