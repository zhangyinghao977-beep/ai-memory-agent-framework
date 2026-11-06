"""测试共用的小工具（不是测试本身）。"""
from empirical_core.experience import SourceType
from empirical_core.registry import MemberSpec
from empirical_core.valve import ItemKind

COMPUTATION = {
    "computation_id": "ka_stub",
    "inputs": [{"name": "context", "meaning": "本次调用送入的上下文表示"}],
    "candidate_mapping": "每个成员一行候选",
    "output_meaning": "成员吻合度，不是事实概率",
    "output_evaluation": {"scale": {"name": "ka_stub_match", "low": 0.0, "high": 1.0},
                          "direction": "higher_matches_more"},
    "training_basis": "untrained",
    "layer": 1,
    "parameter_version": {"kind": "none"},
}


def source(experiences, text="语料"):
    return experiences.record(chain_id="form", source_type=SourceType.EXTERNAL_STATEMENT, content=text, origin="corpus")


def package(registry, experiences, pid, words, diffs=None):
    mats = [registry.add_raw(w) for w in words]
    diffs = diffs or [None] * len(words)
    members = [MemberSpec(m, d) for m, d in zip(mats, diffs)]
    return registry.register_package(pid, pid, members, COMPUTATION, [source(experiences)], "测试成包")


def cache_with(valve, *package_versions, purpose="测试"):
    """开一个物理世界的工作缓存，并放进给定的包版本。"""
    cid = valve.open_cache(purpose)
    for pid, ver in package_versions:
        valve.enter(cid, ItemKind.PACKAGE, (pid, ver), reason="测试准入")
    return cid
