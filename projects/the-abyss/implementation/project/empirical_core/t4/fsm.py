"""T4 的 FSM 脚手架：清醒、睡眠、走神（人写的演示，不是系统自己的 FSM）。

依据：
- 名词解释 v0.57 底层 FSM：生命活动的最小触发器；可修正、像函数，不是写死的状态表（v0.11）；
  和资源池绑在一起，用连续的量；状态、触发和修正方式待定。
- 经验主义 v0.55：清醒时不做高占用的全局大改，睡眠时可以做更大范围的重组。
- 红尘仙 0.4（只借思想）：想做时可唤醒；不想做时可以睡眠或走神，不行动不算失败。
- 本实验先固定 FSM 参数，保留决策记录供后续机制研究。
所以这里是一个带参数的函数：输入是连续的量，算出三个状态各自的“想要”程度，选最大的。
参数这次固定；每次决策的输入、各项“想要”和选择都由调用方登记，留作以后按经验修正的材料。
当前系统没有自主生成这一控制层；此层是人工编写的实验脚手架。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

STATES = ("awake", "sleep", "wander")


@dataclass(frozen=True)
class FSMParams:
    queue_scale: float = 64.0         # 待回答的题有多少算“很多”
    queue_weight: float = 1.0         # 有题待答时“想醒”至少是 0.5 倍这个权重
    pressure_weight: float = 1.0      # 缓存积压（没解决的经历 / 缓存容量）→ 想睡
    fatigue_scale: float = 256.0      # 上次睡醒以后回答了多少题算“累”
    fatigue_weight: float = 0.5
    wander_base: float = 0.1          # 不想做事时的基线：走神
    min_pool: float = 0.05            # 池子可用余量（到资源保护触发点为止）低于这个比例，就不进那个状态


@dataclass(frozen=True)
class Observation:
    queue: int                        # 今天还没回答的题
    cache_pressure: float             # 缓存里没解决的经历 / 缓存容量
    awake_left: float                 # 清醒池余量（0–1）
    sleep_left: float                 # 睡眠池余量（0–1）
    answered_since_sleep: int


def drives(obs: Observation, p: FSMParams) -> dict:
    if obs.queue and obs.awake_left > p.min_pool:
        awake = p.queue_weight * (0.5 + 0.5 * min(1.0, obs.queue / p.queue_scale))
    else:
        awake = -math.inf
    if obs.sleep_left > p.min_pool and obs.cache_pressure > 0:
        sleep = p.pressure_weight * obs.cache_pressure + p.fatigue_weight * min(1.0, obs.answered_since_sleep / p.fatigue_scale)
    else:
        sleep = -math.inf
    return {"awake": awake, "sleep": sleep, "wander": p.wander_base}


def decide(obs: Observation, p: FSMParams) -> tuple[str, dict]:
    d = drives(obs, p)
    state = max(STATES, key=lambda s: (d[s], -STATES.index(s)))
    return state, d


def record(obs: Observation, p: FSMParams, prev: str) -> dict:
    """一次决策要登记的内容：输入、参数、各项“想要”、选择。"""
    state, d = decide(obs, p)
    return {"prev": prev, "state": state, "obs": asdict(obs), "drives": {k: (None if v == -math.inf else v) for k, v in d.items()},
            "params": asdict(p)}
