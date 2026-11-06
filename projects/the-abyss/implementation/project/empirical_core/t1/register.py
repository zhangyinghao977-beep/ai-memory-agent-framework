"""把 T1 登记进经验主义架构（T1 设计稿第四节；被测模型 A 设计稿第三、六节）。不训练。

- 经验：出题器规格作为一条外部陈述（依据）。
- 知识库（B3）：第 1 轮组合，放进 60 个对象素材；登记 10 个包，每包首成员是参考。
  成员的值（B4）一律记未知——数值是要学的，不能直接告诉模型。
  T1-a：包内偏差作为已登记的存异结果写回（record_differences，尺子“T1 数值”）；T1-b：偏差保持未知。
- 记忆边界阀：注册故事世界；前提“小的赢”的适用范围是事件链节点“讲故事”（事先选定）。
- 事件链 AST：结构“比较(A, B)”，以及“讲故事”顺序节点（把比较的 A、B 接到自己的 A、B）。
- 每道题（可只取一部分）：一条经验记下题面，在工作缓存里登记一次发生；A、B 由关系匹配绑定（CPU 的身份判断）。
"""
from __future__ import annotations

import json
from typing import Optional

from ..event_ast import ChildRef, NodeKind, Occurrences, ProcessStructures, bound
from ..experience import ExperienceLog, SourceType
from ..registry import MemberSpec, PackageRegistry
from ..store import Store
from ..valve import PHYSICAL, MemoryValve
from .features import registered_offsets
from .task import resolve, visible

STORY = "t1_story"
OFFSET_SCALE = "T1 数值"
KA_COMPUTATION = {
    "computation_id": "t1_ka_v0",
    "inputs": [{"name": "selected_member", "meaning": "EA 选出的对象在本包中的位置"},
               {"name": "member_offset", "meaning": "该成员相对本包参考的偏差（T1-a 来自已登记的存异结果）"}],
    "candidate_mapping": "本包每个成员一行",
    "output_meaning": "成员在本包参考下的偏差读数；跨包比较前须经尺子转换",
    "output_evaluation": {"scale": {"name": "t1_ka_match", "low": 0.0, "high": 1.0}, "direction": "higher_matches_more"},
    "training_basis": "untrained",
    "layer": 1,
    "parameter_version": {"kind": "not_trained", "note": "模型 A 尚未实现"},
}


def object_material(registry: PackageRegistry, p: int, m: int) -> str:
    return registry.add_raw(f"t1:obj:{p},{m}")


def package_id(p: int) -> str:
    return f"t1_pkg_{p}"


def register_t1(store: Store, data: dict, variant: str = "a", episode_limit: Optional[int] = None) -> dict:
    if variant not in ("a", "b"):
        raise ValueError("variant 只能是 a（给出存异结果）或 b（不给）")
    exp = ExperienceLog(store)
    reg = PackageRegistry(store, exp)
    valve = MemoryValve(store, exp)
    structures = ProcessStructures(store, exp)
    occ = Occurrences(store, exp, structures, valve)
    spec = data["spec"]
    with store.transaction():
        basis = exp.record(chain_id="t1", source_type=SourceType.EXTERNAL_STATEMENT,
                           content=json.dumps({"t1_spec": spec}, ensure_ascii=False, sort_keys=True), origin="t1_generator")
        mats = {(p, m): object_material(reg, p, m) for p in range(spec["n_packages"]) for m in range(spec["n_members"])}
        round_id = reg.open_round(1, list(mats.values()), "T1 第一轮：对象组成知识包", [basis])
        for p in range(spec["n_packages"]):
            reg.register_package(package_id(p), f"T1 包 {p}", [MemberSpec(mats[(p, m)]) for m in range(spec["n_members"])],
                                 KA_COMPUTATION, [basis], "T1 按设计成包（不是从经验中求同形成）", round_id=round_id)
        if variant == "a":
            offsets = registered_offsets(data)
            for p in range(spec["n_packages"]):
                reg.record_differences(package_id(p), {
                    m: {"kind": "registered_offset", "scale": OFFSET_SCALE, "value": offsets[(p, m)]}
                    for m in range(1, spec["n_members"])}, [basis], "T1-a：包内偏差作为已登记的存异结果")
        reg.close_round(round_id)

        valve.register_world(STORY, "T1 故事世界", "前提：小的赢", [basis])
        obj_slot = {"ref_kinds": ["material"]}
        structures.define("t1_compare", NodeKind.OPERATION, "比较(A, B)", slots={"A": obj_slot, "B": obj_slot},
                          basis_ids=[basis], reason="T1 题型")
        structures.define("t1_tell_story", NodeKind.SEQUENCE, "讲故事", slots={"A": obj_slot, "B": obj_slot},
                          children=[ChildRef("t1_compare", 1, {"A": "A", "B": "B"})], basis_ids=[basis], reason="T1 题型")
        premise = valve.declare_premise(STORY, "小的赢", {"kind": "node", "node_id": "t1_tell_story"}, [basis])

        caches = {"physical": valve.open_cache("T1 物理世界的题"), "story": valve.open_cache("T1 故事世界的题",
                                                                                           worlds=[STORY, PHYSICAL])}
        for p in range(spec["n_packages"]):
            ver = reg.latest(package_id(p)).version
            for cache in caches.values():
                valve.enter(cache, "package", (package_id(p), ver), reason="T1 本轮使用")
        occurrences = {}
        for ep in data["episodes"][:episode_limit]:
            a, b = resolve(ep)
            ev = exp.record(chain_id=f"t1:{ep['id']}", source_type=SourceType.EXTERNAL_STATEMENT,
                            content=json.dumps(visible(ep), ensure_ascii=False, sort_keys=True), origin="t1_generator")
            binds = {"A": bound({"kind": "material", "id": mats[a]}), "B": bound({"kind": "material", "id": mats[b]})}
            if ep["world"] == "story":
                story = occ.occur("t1_tell_story", cache_id=caches["story"], experience_id=ev, bindings=binds)
                occurrences[ep["id"]] = occ.occur("t1_compare", cache_id=caches["story"], experience_id=ev,
                                                  parent_occurrence_id=story)
            else:
                occurrences[ep["id"]] = occ.occur("t1_compare", cache_id=caches["physical"], experience_id=ev,
                                                  bindings=binds)
    return {"basis": basis, "round_id": round_id, "premise": premise, "caches": caches, "occurrences": occurrences,
            "materials": {f"{p},{m}": mid for (p, m), mid in mats.items()}}
