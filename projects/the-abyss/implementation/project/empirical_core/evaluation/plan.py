"""训练前冻结计划：预先固定基线、数据、训练步骤与评测标准。

计划必须事先写明：指标、每个指标要比较的简单基线、对照组、数据身份与种子。
冻结后记录计划哈希与源码哈希；同一路径不能覆盖，改计划就要用新身份。
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Sequence

REQUIRED_KEYS = ("name", "task", "data", "seed", "metrics", "baselines", "ablations")


class PlanError(ValueError):
    pass


def validate_plan(plan: dict) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in plan]
    if missing:
        raise PlanError(f"计划缺少字段：{missing}")
    baselines = plan["baselines"]
    if not baselines:
        raise PlanError("至少要有一个简单基线")
    names = {b["name"] for b in baselines}
    if not plan["metrics"]:
        raise PlanError("至少要有一个指标")
    for m in plan["metrics"]:
        compare = m.get("compare_to") or []
        if not compare:
            raise PlanError(f"指标 {m.get('name')} 没有指定要比较的基线")
        unknown = set(compare) - names
        if unknown:
            raise PlanError(f"指标 {m['name']} 引用了未定义的基线：{sorted(unknown)}")
    if not isinstance(plan["ablations"], list):
        raise PlanError("ablations 必须是列表（没有对照组也要写空列表并说明原因）")


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def freeze_plan(plan: dict, source_paths: Sequence[str], out_path: str) -> dict:
    validate_plan(plan)
    if os.path.exists(out_path):
        raise PlanError(f"{out_path} 已存在；冻结后的计划不能覆盖，请使用新身份")
    sources = {os.path.abspath(p).replace("\\", "/"): file_sha256(p) for p in source_paths}
    frozen = {"plan": plan, "plan_sha256": canonical_hash(plan), "sources": sources}
    frozen["identity"] = canonical_hash(frozen)
    with open(out_path, "x", encoding="utf-8") as f:
        json.dump(frozen, f, ensure_ascii=False, indent=2, sort_keys=True)
    return frozen


def verify_plan(path: str) -> dict:
    """重新核对计划与源码；任何变化都抛出 PlanError。"""
    with open(path, encoding="utf-8") as f:
        frozen = json.load(f)
    if canonical_hash(frozen["plan"]) != frozen["plan_sha256"]:
        raise PlanError("计划内容与冻结哈希不一致")
    changed = [p for p, h in frozen["sources"].items() if not os.path.exists(p) or file_sha256(p) != h]
    if changed:
        raise PlanError(f"冻结后源码有变化：{changed}")
    body = {k: frozen[k] for k in ("plan", "plan_sha256", "sources")}
    if canonical_hash(body) != frozen["identity"]:
        raise PlanError("计划身份哈希不一致")
    return frozen
