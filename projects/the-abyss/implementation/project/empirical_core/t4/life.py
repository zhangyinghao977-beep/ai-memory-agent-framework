"""T4 的存活循环：一天天地活，清醒回答、睡眠重组、走神整理（2026-11-03）。

一天的流程（FSM 脚手架每一步做一次决定，决定登记进快速登记）：
- 清醒：每次调用回答一小批题，按固定调用协议登记；报告之后收到对整个问答的反馈，
  答错的、回答“不知道”的进缓存（经历入口，指向原始记录）。
  清醒小修：只用清醒池，只写从没训练过、但已经在经历里出现的包的 KA。
- 睡眠：缓存里的经历是入口，触发睡眠；材料是最近的经历（答对的、答错的都算），加上按比例抽的更早的经历；
  按 T2 的梯子先局部、再加深，每级从上次采用的版本出发。只用睡眠池。
  “够不够用”只看系统自己知道的东西：按题号固定留出、从不训练的最近的题，和过去没训练过的一份题，不用隐藏真值。
  只留答错的题当材料或自检，自检会永远是 0%，所以不这样做（2026-11-04 small 档开发检查发现）。
  最近的题要按看得见的类别（体裁、有没有过去没见过的包）分开看，最差的一类够用才算够用：
  合在一起算时，旧题占多数，新题的错被平均掉了（同一次开发检查发现）。
- 走神：后台整理：把快速登记整理进长期记录库，补索引和占位 description，查缺项；然后这一天结束。
资源保护随时可以打断清醒或睡眠：打断时回到上次采用的版本，登记中断，累计消耗照样保存，不重置。
每天结束时在四份探针上评测（隐藏真值，只用于报告，不计入资源池）。

对照组：
- frozen（只用不学）：只回答，不修、不睡；
- survive（清醒／睡眠，EA 受 CA 指引）：用 FSM 脚手架；
- survive_blind（清醒／睡眠，EA 看不到 CA）：同上，但 EA 只有回返约束，和 T3 相同；
- full_repair（每次睡眠全部重修，EA 受 CA 指引）：清醒小修同 survive，睡眠时不分局部，三层都写，作为成本参照。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch

from ..t2.evaluate import decide
from ..t2.features import encode, take
from ..t2.repair import LADDER, is_empty
from ..t2.spiral import ka_name
from ..t2.units import A2Config

from . import fsm as F
from .guided import GuidedSpiral
from .records import CallProtocol, LongStore, QuickLog, crashpoint, recover
from .resources import Meter, Pool, Protector, ResourceInterrupt, Throttle
from .units import LoggedUnitStore

ARMS = ("frozen", "survive", "survive_blind", "full_repair")
GUIDED_ARMS = ("survive", "full_repair")


@dataclass
class LifeConf:
    arm: str
    batch_per_call: int = 32
    cache_capacity: int = 64
    pools: dict = field(default_factory=lambda: {"awake": {"cpu_seconds": 600.0, "gpu_seconds": 120.0},
                                                 "sleep": {"cpu_seconds": 1800.0, "gpu_seconds": 600.0}})
    trigger: float = 0.85
    max_rss_bytes: int = 16 * 2 ** 30
    persist_every_s: float = 10.0
    awake_fix_rounds: int = 1
    sleep_rounds: int = 2
    replay_ratio: float = 1.0
    margin: float = 0.02
    self_check_every: int = 5
    learn_window: int = 1024
    min_group: int = 20
    fsm: F.FSMParams = F.FSMParams()
    seed: int = 0
    epochs: dict = field(default_factory=lambda: {"ka": 10, "ea": 3, "ca": 3})
    batch_size: int = 256
    lr: dict = field(default_factory=lambda: {"ka": 0.003, "ea": 0.001, "ca": 0.001})
    budgets: dict = field(default_factory=lambda: {"ka": 1 << 27, "ea": 1 << 31, "ca": 1 << 31})
    predict_chunk: int = 2048


class _Spiral(GuidedSpiral):
    """KA 在 CPU 上算：这段时间不把耗时算成显卡忙碌（CPU 时间另由进程读数计）。"""
    throttle: Optional[Throttle] = None

    def _ka_phase(self, *args, **kwargs):
        th = self.throttle
        if th is not None:
            th.gpu_phase = False
        try:
            return super()._ka_phase(*args, **kwargs)
        finally:
            if th is not None:
                th.gpu_phase = True


def encode_ids(world: dict, ids: list) -> tuple:
    """按题号编码（可以跨天）；结果的顺序和 ids 相同。"""
    want = {q: i for i, q in enumerate(ids)}
    eps = sorted((dict(ep, split="x") for ep in world["episodes"] if ep["id"] in want), key=lambda ep: want[ep["id"]])
    return encode({"spec": world["spec"], "episodes": eps}, "x")


class Life:
    def __init__(self, root: Path, world: dict, cfg: A2Config, conf: LifeConf, *, device: str, proc,
                 gpu_duty: Optional[float]):
        if conf.arm not in ARMS:
            raise ValueError(f"未知的组 {conf.arm}")
        self.root, self.world, self.cfg, self.conf, self.device = Path(root), world, cfg, conf, device
        self.log = QuickLog(self.root / "quick.jsonl")
        self.store = LoggedUnitStore(self.root / "units", self.log)
        self.long = LongStore(self.root / "long.sqlite")
        self.proto = CallProtocol(self.log)
        self.meter = Meter(proc, device == "cuda")
        self.protector = Protector(self.meter, conf.trigger, conf.max_rss_bytes)
        self.throttle = Throttle(self.meter, self.protector, gpu_duty)
        self.episodes = {ep["id"]: ep for ep in world["episodes"]}
        self.past = [ep["id"] for ep in world["episodes"] if ep["split"] == "past"]
        self.past_check = [ep["id"] for ep in world["episodes"] if ep["split"] == "past_check"]
        self.known_packages = {e[1] for q in self.past for ch in self.episodes[q]["chains"]
                               if ch["kind"] == "say" for e in ch["events"]}
        self._day_cache: dict = {}
        self._answerer: Optional[GuidedSpiral] = None
        self._last_persist = time.time()
        self.state = "wander"

    # ---------- 起点 ----------
    def seed_units(self, source_root: Optional[Path], snapshot: Optional[dict]) -> None:
        """第一次启动：把起点单元（例如 T3 双向做法第 20 轮）复制成本存储的第 1 版，登记来源，然后采用。"""
        if self.log.of_kind("adopt"):
            return
        if source_root is not None:
            for name, v in sorted(snapshot.items()):
                if int(v) == 0:
                    continue
                state = torch.load(Path(source_root) / name / f"v{int(v):05d}.pt", weights_only=False, map_location="cpu")
                self.store.write(name, state)
        self.store.adopt("start", source=str(source_root) if source_root else None, source_snapshot=snapshot)

    # ---------- 从快速登记重建状态 ----------
    def answered(self) -> dict:
        """已经回答完（结束记录是 done）的题：{题号: 调用号}。"""
        return {q: r["call"] for r in self.log.of_kind("call_end")
                if r["status"] == "done" and r.get("call_kind") == "answer" for q in r["qids"]}

    def feedback(self) -> dict:
        """收到反馈的题：{题号: (回答, 对不对)}。"""
        return {q: (a, ok) for r in self.log.of_kind("feedback") for q, a, ok in r["items"]}

    def cache(self) -> list:
        done = {q for r in self.log.of_kind("cache_done") for q in r["qids"]}
        out, seen = [], set()
        for r in self.log.of_kind("cache_add"):
            for q in r["qids"]:
                if q not in done and q not in seen:
                    seen.add(q)
                    out.append(q)
        return out

    def answered_since_sleep(self) -> int:
        last = max((r["seq"] for r in self.log.of_kind("sleep_end", "sleep_interrupted")), default=-1)
        return sum(len(r["qids"]) for r in self.log.of_kind("call_end")
                   if r["seq"] > last and r["status"] == "done" and r.get("call_kind") == "answer")

    def _on_report(self, end_rec: dict) -> None:
        """报告给上层（这里的“逻辑”就是存活循环本身）。状态都从快速登记重建，所以报告只是交付，不另改状态。"""

    # ---------- 资源 ----------
    def usable(self, pool: Pool) -> float:
        """到资源保护触发点为止还能用多少（0–1）。触发以后是 0，FSM 不会再选这个状态。"""
        return max(0.0, (self.conf.trigger - pool.frac_used()) / self.conf.trigger)

    def _enter(self, pool: Pool) -> None:
        self.protector.active = pool
        pool.open(self.meter)

    def _leave(self, pool: Pool) -> None:
        pool.close(self.meter)
        self.protector.active = None

    def guard(self) -> None:
        self.throttle()
        if self.protector.active is not None and time.time() - self._last_persist > self.conf.persist_every_s:
            self.protector.active.persist()                 # 定期把累计消耗写进快速登记：断电时最多丢这一小段
            self._last_persist = time.time()

    def spiral(self, train) -> GuidedSpiral:
        c = self.conf
        sp = _Spiral(self.cfg, self.store, train, two_way=True, guided=c.arm in GUIDED_ARMS, seed=c.seed,
                     epochs_per_phase=c.epochs, batch_size=c.batch_size, lr=c.lr, budgets=c.budgets, device=self.device,
                     guard=self.guard)
        sp.throttle = self.throttle
        return sp

    # ---------- 清醒 ----------
    def _day_batch(self, d: int):
        if d not in self._day_cache:
            b, _ = encode(self.world, f"day{d}")
            self._day_cache = {d: (b, {q: i for i, q in enumerate(b.ids)})}
        return self._day_cache[d]

    def _answer(self, d: int, qids: list) -> dict:
        b, pos = self._day_batch(d)
        sub = take(b, torch.tensor([pos[q] for q in qids]))
        if self._answerer is None:                         # 回答时不用训练材料；留着它，KA 产品不变就不用重建
            self._answerer = self.spiral(None)
        dec = decide(self._answerer.predict(sub, chunk=self.conf.predict_chunk))
        crashpoint("inside_answer")
        return {"qids": qids, "answers": dec["forced"].tolist(), "unknown": dec["unknown"].tolist()}

    def _give_feedback(self, end_rec: dict) -> None:
        """世界对整个问答的反馈：这次回答对不对。答错的、回答“不知道”的进缓存。"""
        items = [[q, a, int(a == self.episodes[q]["label"])] for q, a in zip(end_rec["qids"], end_rec["answers"])]
        self.log.append("feedback", call=end_rec["call"], day=self.episodes[end_rec["qids"][0]]["day"], items=items)
        bad = [q for (q, a, ok), unk in zip(items, end_rec["unknown"]) if not ok or unk]
        if bad:
            self.log.append("cache_add", call=end_rec["call"], qids=bad)

    def awake(self, d: int, qids: list, pool: Pool) -> None:
        self._enter(pool)
        try:
            end = self.proto.run("answer", lambda: self._answer(d, qids), self._on_report,
                                 interrupt=(ResourceInterrupt,), day=d, qids=qids)
            self._give_feedback(end)
            if self.conf.arm != "frozen":
                self._awake_fix(d, qids)
        except ResourceInterrupt as e:
            self.store.rollback()
            self.log.append("interrupt", day=d, state="awake", reason=str(e))
        finally:
            self._leave(pool)

    def _experience(self, qids: list):
        """经历编码成训练材料；标签只从收到的反馈推出来（二选一：答对就是这个答案，答错就是另一个）。
        过去的材料（出生以前的训练经历）的反馈早就知道了，用它们自己的答案。"""
        fb = self.feedback()
        b, _ = encode_ids(self.world, qids)
        b.labels = torch.tensor([float(fb[q][0] if fb[q][1] else 1 - fb[q][0]) if q in fb else float(self.episodes[q]["label"])
                                 for q in b.ids])
        return b

    def _awake_fix(self, d: int, qids: list) -> None:
        """这次问答里出现、但 KA 从没训练过的包：用全部带反馈的经历里涉及它们的题，只写它们的 KA。"""
        pk = {e[1] for q in qids for ch in self.episodes[q]["chains"] if ch["kind"] == "say" for e in ch["events"]}
        local = sorted(p for p in pk if self.store.version(ka_name(p)) == 0)
        if not local:
            return
        b = self._experience(list(self.feedback()))
        rows = torch.nonzero(torch.isin(b.ev_pkg, torch.tensor(local)).flatten(1).any(1)).squeeze(-1)
        sp = self.spiral(b)
        sp.repair(f"day{d}/awake_fix/{self.log.seq}", rows, rows[:0], ka_packages=local, ea=False, ca=False,
                  rounds=self.conf.awake_fix_rounds, replay_ratio=0.0)
        self.store.adopt("awake_fix", day=d, ka_packages=local, materials=len(rows))

    # ---------- 睡眠 ----------
    def _group(self, q: str) -> str:
        """自检的类别，只用题目里看得见的东西：体裁、有没有过去没见过的包。"""
        ep = self.episodes[q]
        fresh = any(e[1] not in self.known_packages for ch in ep["chains"] if ch["kind"] == "say" for e in ch["events"])
        return f"genre{ep['genre']}" + ("+new_package" if fresh else "")

    def _is_check(self, q: str) -> bool:
        """每 self_check_every 道题固定留 1 道当自检，从不拿来训练。按题号定，和答得对不对无关，所以没有选择偏差。"""
        return int(q.split("-")[1]) % self.conf.self_check_every == 0

    def _scope(self, layers, sp, learn: torch.Tensor) -> dict:
        """写范围。KA_local＝材料里出现的、过去的经历里没有的包（出生以后才遇到的包）：
        清醒小修碰过一次以后它们也还算局部（main 档测速发现，按“版本号是 0”算的话，局部这一级会被跳过）。"""
        ka = []
        if "KA_all" in layers:
            ka = list(range(self.cfg.n_packages))
        elif "KA_local" in layers:
            tr = sp.train
            pk = torch.unique(tr.ev_pkg[learn][tr.ev_valid[learn] > 0]).tolist()
            ka = [p for p in pk if p not in self.known_packages]
        return {"ka_packages": ka, "ea": "EA" in layers, "ca": "CA" in layers}

    def _ladder(self, sp, d: int, learn: torch.Tensor, replay: torch.Tensor, check) -> dict:
        """T2 的梯子，每级从上次采用的版本出发。够用就停（v0.56）。
        一级都不够用时，只采用新经历确实变好、旧本领没有变差的那一级；否则什么都不改。"""
        c = self.conf
        base_snap = dict(self.store.adopted)
        base = check()
        bar = base["old"] - c.margin
        if base["new"] >= bar:
            return {"status": "already_enough", "base": base, "bar": bar, "trace": [], "adopted": None}
        trace, chosen = [], None
        for layers in LADDER:
            self.store.restore(base_snap)
            scope = self._scope(layers, sp, learn)
            step = {"layers": list(layers), "ka_packages": scope["ka_packages"]}
            if is_empty(scope):
                trace.append({**step, "skipped": "写范围为空"})
                continue
            sp.repair(f"day{d}/sleep/{'+'.join(layers)}/{self.log.seq}", learn, replay, rounds=c.sleep_rounds,
                      replay_ratio=c.replay_ratio, **scope)
            acc = check()
            t = {**step, **acc, "enough": acc["new"] >= bar and acc["old"] >= bar}
            trace.append(t)
            if t["enough"]:
                chosen = (t, self.store.snapshot())
                break
            if acc["old"] >= bar and acc["new"] >= base["new"] + c.margin and (chosen is None or acc["new"] > chosen[0]["new"]):
                chosen = (t, self.store.snapshot())
        self.store.restore(chosen[1] if chosen else base_snap)
        status = "enough" if chosen and chosen[0]["enough"] else "improved_kept" if chosen else "nothing_kept"
        return {"status": status, "base": base, "bar": bar, "trace": trace,
                "adopted": "+".join(chosen[0]["layers"]) if chosen else None}

    def sleep(self, d: int, pool: Pool) -> None:
        """材料：最近 learn_window 道带反馈的经历（答对的、答错的都算），加上按比例抽的更早的经历和过去的训练材料。
        自检：最近留出的题，以及过去从没训练过的一份题；都不看隐藏真值，只用已经知道的反馈。"""
        c = self.conf
        entries = self.cache()
        if not entries:
            return
        lived = list(self.feedback())
        usable = [q for q in lived if not self._is_check(q)]
        learn = usable[-c.learn_window:]
        check = [q for q in lived if self._is_check(q)][-max(1, c.learn_window // c.self_check_every):] or learn
        pool_old = usable[:-c.learn_window] + self.past
        g = torch.Generator().manual_seed(len(self.log.records))
        pick = torch.randperm(len(pool_old), generator=g)[:2 * len(learn)].tolist()
        replay = [pool_old[i] for i in pick]
        ids = learn + replay + check + self.past_check
        n1, n2, n3 = len(learn), len(learn) + len(replay), len(learn) + len(replay) + len(check)
        learn_idx, replay_idx = torch.arange(0, n1), torch.arange(n1, n2)
        check_idx, old_idx = torch.arange(n2, n3), torch.arange(n3, len(ids))
        self.log.append("sleep_start", day=d, entries=len(entries), learn=len(learn), replay=len(replay), check=len(check),
                        old_check=len(self.past_check))
        self._enter(pool)
        try:
            b = self._experience(ids)
            sp = self.spiral(b)

            def right(idx):
                sub = take(b, idx)
                return ((sp.predict(sub, chunk=c.predict_chunk)["logit"] > 0).float() == sub.labels).float()

            groups: dict = {}
            for pos, q in enumerate(check):
                groups.setdefault(self._group(q), []).append(pos)

            def self_check():
                ok = right(check_idx)
                accs = {g: float(ok[pos].mean()) for g, pos in groups.items() if len(pos) >= c.min_group}
                return {"new": min(accs.values()) if accs else float(ok.mean()), "old": float(right(old_idx).mean()),
                        "groups": accs}

            if c.arm == "full_repair":
                base = self_check()
                sp.repair(f"day{d}/sleep_all/{self.log.seq}", learn_idx, replay_idx, ka_packages=list(range(self.cfg.n_packages)),
                          ea=True, ca=True, rounds=c.sleep_rounds, replay_ratio=c.replay_ratio)
                res = {"status": "full_repair", "base": base, "trace": [], "adopted": "ALL", "after": self_check()}
            else:
                res = self._ladder(sp, d, learn_idx, replay_idx, self_check)
            crashpoint("sleep_before_adopt")
            self.store.adopt("sleep", day=d, status=res["status"])
            self.log.append("sleep_end", day=d, result=res)
            self.log.append("cache_done", qids=entries, outcome=res["status"])
        except ResourceInterrupt as e:
            self.store.rollback()
            self.log.append("sleep_interrupted", day=d, reason=str(e))
        finally:
            self._leave(pool)

    # ---------- 走神 ----------
    def wander(self, d: int) -> dict:
        res = self.long.consolidate(self.log)
        miss = self.long.missing()
        return self.log.append("consolidate", day=d, result=res, missing={k: len(v) for k, v in miss.items()})

    # ---------- 重启恢复 ----------
    def recover_on_start(self) -> dict:
        if not self.log.records:
            return {"lost_calls": [], "late_reports": [], "fresh": True}
        out = recover(self.log, self._on_report)
        fbcalls = {r["call"] for r in self.log.of_kind("feedback")}
        late_fb = []
        for r in self.log.of_kind("call_end"):           # 已回答、还没收到反馈：现在给（世界的回应，不是重新执行）
            if r["status"] == "done" and r.get("call_kind") == "answer" and r["call"] not in fbcalls:
                self._give_feedback(r)
                late_fb.append(r["call"])
        starts = self.log.of_kind("sleep_start")
        ends = self.log.of_kind("sleep_end", "sleep_interrupted")
        if starts and (not ends or starts[-1]["seq"] > ends[-1]["seq"]):
            self.log.append("sleep_interrupted", day=starts[-1]["day"], reason="断电（重启后发现）")
        out.update({"late_feedback": late_fb, "leftovers": self.store.leftovers()})
        out.pop("record", None)
        self.log.append("recovery_summary", **out)
        return out

    # ---------- 一天 ----------
    def live_day(self, d: int, evaluate=None) -> dict:
        c = self.conf
        if not [r for r in self.log.of_kind("day_start") if r["day"] == d]:
            self.log.append("day_start", day=d)
        pools = {name: Pool(name, c.pools[name], self.log, d) for name in ("awake", "sleep")}
        b, _ = self._day_batch(d)
        while True:
            done = self.answered()
            queue = [q for q in b.ids if q not in done]
            if c.arm == "frozen":
                state = "awake" if queue and self.usable(pools["awake"]) > c.fsm.min_pool else "wander"
                self.log.append("fsm", day=d, prev=self.state, state=state, rule="frozen：有题就答，答完就结束")
            else:
                obs = F.Observation(len(queue), len(self.cache()) / c.cache_capacity, self.usable(pools["awake"]),
                                    self.usable(pools["sleep"]), self.answered_since_sleep())
                rec = F.record(obs, c.fsm, self.state)
                self.log.append("fsm", day=d, **rec)
                state = rec["state"]
            self.state = state
            if state == "awake":
                self.awake(d, queue[:c.batch_per_call], pools["awake"])
            elif state == "sleep":
                self.sleep(d, pools["sleep"])
            else:
                self.wander(d)
                break
        metrics = {"day": d, "unanswered": len([q for q in b.ids if q not in self.answered()]),
                   "stream": self.stream_scores(d),
                   "cache": len(self.cache()), "pools": {k: p.used for k, p in pools.items()},
                   "storage": self.storage(), "superseded": len(self.store.superseded()),
                   "adopted": dict(self.store.adopted)}
        if evaluate is not None:
            metrics["probes"] = evaluate(self)
        self.log.append("day_end", **metrics)
        return metrics

    def stream_scores(self, d: int) -> dict:
        """这一天每类题答对多少（从反馈算）。"""
        out: dict = {}
        for r in self.log.of_kind("feedback"):
            if r["day"] == d:
                for q, _, ok in r["items"]:
                    t = out.setdefault(self.episodes[q]["change"], [0, 0])
                    t[0] += 1
                    t[1] += ok
        return out

    def storage(self) -> dict:
        def size(p):
            return p.stat().st_size if p.exists() else 0
        return {"units_bytes": self.store.bytes_on_disk(), "quick_bytes": size(self.log.path),
                "long_bytes": size(self.long.path)}

    def live(self, days: int, evaluate=None) -> list:
        self.recover_on_start()
        ended = {r["day"] for r in self.log.of_kind("day_end")}
        return [self.live_day(d, evaluate) for d in range(1, days + 1) if d not in ended]


def probe_eval(life: Life) -> dict:
    """每天结束时在四份探针上评测：隐藏真值，只用于报告；不计入资源池，不登记成经历。"""
    out = {}
    for split in ("probe_old", "probe_new_package", "probe_new_genre", "probe_new_genre_dup"):
        b, diag = encode(life.world, split)
        pred = life.spiral(b).predict(b, diag, chunk=life.conf.predict_chunk)
        out[split] = {"n": len(b.ids), "correct": int(((pred["logit"] > 0).long() == b.labels.long()).sum())}
    return out
