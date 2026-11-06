"""记忆边界阀：世界、前提与工作缓存（2026-10-27 新增，设计稿 v0.3 第三节）。"""
import pytest

from _helpers import cache_with, package, source
from empirical_core.calls import CandidateInput, Decision
from empirical_core.event_ast import ChildRef, NodeKind
from empirical_core.experience import SourceType
from empirical_core.valve import PHYSICAL, ItemKind, PremiseStatus


def _user_says(experiences, text):
    return experiences.record(chain_id="talk", source_type=SourceType.EXTERNAL_STATEMENT, content=text, origin="user")


def _story_world(valve, experiences):
    valve.register_world("dragon_story", "龙的故事", "用户讲的故事", [_user_says(experiences, "我们来讲个故事")])
    return "dragon_story"


def test_unlabelled_material_defaults_to_physical_world(valve, experiences, registry):
    """没有说明的默认指向物理世界；并记下“这是默认的”。"""
    package(registry, experiences, "fruit", ["苹果", "梨"])
    assert valve.worlds_of("package", "fruit") == (frozenset({PHYSICAL}), True)
    story = _story_world(valve, experiences)
    basis = _user_says(experiences, "这个水果包是故事里的")
    valve.tag_world("package", "fruit", story, [basis], "故事设定")
    assert valve.worlds_of("package", "fruit") == (frozenset({story}), False)
    valve.untag_world("package", "fruit", story, [basis], "标错了")
    assert valve.worlds_of("package", "fruit") == (frozenset({PHYSICAL}), True)
    with pytest.raises(ValueError):
        valve.tag_world("package", "fruit", "no_such_world", [basis], "x")


def test_cache_only_takes_materials_of_its_worlds(valve, experiences, registry):
    package(registry, experiences, "dragon", ["龙", "火"])
    story = _story_world(valve, experiences)
    valve.tag_world("package", "dragon", story, [_user_says(experiences, "龙是故事里的")], "故事设定")

    real = valve.open_cache("做晚饭")
    with pytest.raises(ValueError, match="显式比较"):  # 故事里的包不能悄悄进入物理世界的计算
        valve.enter(real, ItemKind.PACKAGE, ("dragon", 1))
    valve.enter(real, ItemKind.PACKAGE, ("dragon", 1), cross_world_reason="显式比较：故事和现实里的火")
    assert valve.is_entered(real, ItemKind.PACKAGE, ("dragon", 1))

    tale = valve.open_cache("讲故事", worlds=[story])
    valve.enter(tale, ItemKind.PACKAGE, ("dragon", 1), priority=1)
    assert valve.entered(tale, ItemKind.PACKAGE) == {"dragon@v1": 1}
    with pytest.raises(ValueError):
        valve.enter(tale, ItemKind.PACKAGE, ("dragon", 1))  # 已在缓存中


def test_premise_scope_is_chosen_before_the_event(valve, experiences, structures, occurrences):
    """前提适用范围在事件发生前登记。范围到了自然结束，不需要撤销。"""
    story = _story_world(valve, experiences)
    basis = source(experiences, "结构说明")
    structures.define("dragon_talks", NodeKind.OPERATION, "龙说话", basis_ids=[basis], reason="x")
    tell = structures.define("tell_story", NodeKind.SEQUENCE, "讲故事",
                             children=[_child("dragon_talks")], basis_ids=[basis], reason="x")
    structures.define("cook", NodeKind.OPERATION, "做晚饭", basis_ids=[basis], reason="x")

    said = _user_says(experiences, "在讲故事的时候，龙会说话")
    with pytest.raises(ValueError, match="适用范围"):  # 适用范围必须事先写明
        valve.declare_premise(story, "龙会说话", {}, [said])
    pid = valve.declare_premise(story, "龙会说话", {"kind": "node", "node_id": "tell_story"}, [said])
    assert valve.premise(pid).status is PremiseStatus.ACTIVE

    cache = valve.open_cache("今晚", worlds=[story, PHYSICAL])
    t1 = occurrences.occur("tell_story", cache_id=cache, experience_id=_user_says(experiences, "开始讲故事"))
    talk = occurrences.occur("dragon_talks", cache_id=cache, parent_occurrence_id=t1,
                             experience_id=_user_says(experiences, "龙开口了"))
    dinner = occurrences.occur("cook", cache_id=cache, experience_id=_user_says(experiences, "去做晚饭"))
    assert [p.premise_id for p in valve.active_premises(cache, talk)] == [pid]
    assert valve.active_premises(cache, dinner) == []   # 故事讲完：自然不适用，没有撤销
    assert valve.active_premises(cache) == []           # 不在故事里
    assert valve.premise(pid).status is PremiseStatus.ACTIVE  # 没有被撤销，只是不在范围内
    t2 = occurrences.occur("tell_story", cache_id=cache, experience_id=_user_says(experiences, "第二天又讲"))
    assert [p.premise_id for p in valve.active_premises(cache, t2)] == [pid]

    physical_only = valve.open_cache("只有现实")
    assert valve.active_premises(physical_only) == []   # 世界没进入本轮


def test_time_scope(valve, experiences):
    said = _user_says(experiences, "今晚八点到十点停电")
    pid = valve.declare_premise(PHYSICAL, "停电", {"kind": "time", "from": "2026-10-27T20:00", "until": "2026-10-27T22:00"}, [said])
    cache = valve.open_cache("晚上")
    assert [p.premise_id for p in valve.active_premises(cache, at="2026-10-27T21:00")] == [pid]
    assert valve.active_premises(cache, at="2026-10-27T22:30") == []
    assert valve.active_premises(cache) == []  # 不知道现在几点，就不能说它适用


def test_system_proposal_is_only_a_candidate_until_confirmed(valve, experiences):
    story = _story_world(valve, experiences)
    guess = experiences.record(chain_id="talk", source_type=SourceType.CANDIDATE_INFERENCE,
                               content="看到“从前有一条龙”，可能在讲故事", origin="model")
    with pytest.raises(ValueError, match="不是外部反馈"):  # 系统的推断不能直接登记成生效的前提
        valve.declare_premise(story, "现在在讲故事", {"kind": "world"}, [guess])
    pid = valve.propose_premise(story, "现在在讲故事", {"kind": "world"}, [guess])
    cache = valve.open_cache("对话", worlds=[story])
    assert valve.premise(pid).status is PremiseStatus.CANDIDATE and valve.active_premises(cache) == []
    with pytest.raises(ValueError):
        valve.confirm_premise(pid, [guess], "系统自己确认")
    valve.confirm_premise(pid, [_user_says(experiences, "对，我在讲故事")], "用户确认")
    assert [p.premise_id for p in valve.active_premises(cache)] == [pid]


def test_revoking_or_exiting_flags_calls_for_recheck(valve, experiences, registry, calls):
    story = _story_world(valve, experiences)
    pv = package(registry, experiences, "fire", ["火", "烟", "光"])
    valve.tag_world("package", "fire", story, [_user_says(experiences, "故事里的火")], "设定")
    cache = valve.open_cache("讲故事", worlds=[story])
    valve.enter(cache, ItemKind.PACKAGE, ("fire", pv.version))
    pid = valve.declare_premise(story, "龙会喷火", {"kind": "world"}, [_user_says(experiences, "龙会喷火")])
    call = calls.record_call(cache_id=cache, chain_id="s", package_id="fire", purpose="龙喷出什么", context={},
                             inputs={"context": "龙"}, origin="model",
                             candidates=[CandidateInput(0, 0.9, Decision.SELECTED)])
    assert valve.pending_rechecks(cache) == []

    with pytest.raises(ValueError):
        valve.revoke_premise(pid, [calls.get(call).experience_id], "计算经历不能撤销前提")
    valve.revoke_premise(pid, [_user_says(experiences, "改设定：龙不会喷火")], "中途改设定")
    assert valve.premise(pid).status is PremiseStatus.REVOKED and valve.active_premises(cache) == []
    flagged = valve.pending_rechecks(cache)
    assert [r["call_id"] for r in flagged] == [call] and flagged[0]["trigger"]["premise_revoked"] == pid
    valve.resolve_recheck(flagged[0]["recheck_id"], "重算后结论不变")
    assert valve.pending_rechecks(cache) == []

    valve.exit(cache, ItemKind.PACKAGE, ("fire", pv.version), "这一段不再需要")
    assert [r["call_id"] for r in valve.pending_rechecks(cache)] == [call]
    assert registry.latest("fire").version == pv.version  # 退出不删除全局内容
    with pytest.raises(ValueError, match="没有进入工作缓存"):  # 退出后不能再在本轮调用
        calls.record_call(cache_id=cache, chain_id="s", package_id="fire", purpose="p", context={},
                          inputs={"context": "x"}, origin="model", candidates=[CandidateInput(0, 0.5)])


def test_closed_cache_takes_nothing(valve, experiences, registry, calls):
    pv = package(registry, experiences, "p", ["a", "b"])
    cache = cache_with(valve, ("p", pv.version))
    valve.close_cache(cache)
    with pytest.raises(ValueError):
        valve.enter(cache, ItemKind.WORLD, PHYSICAL)
    with pytest.raises(ValueError):
        calls.record_call(cache_id=cache, chain_id="c", package_id="p", purpose="p", context={},
                          inputs={"context": "x"}, origin="model", candidates=[CandidateInput(0, 0.5)])


def _child(node_id, version=1, **slot_map):
    return ChildRef(node_id, version, slot_map)
