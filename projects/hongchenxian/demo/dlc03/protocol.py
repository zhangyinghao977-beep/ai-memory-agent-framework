"""Reuse indexed event-chain fragments through a small, simulated FSM."""
from contextlib import closing
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from demo import Body


@dataclass(frozen=True)
class Step:
    name: str
    requires: tuple = ()
    provides: str | None = None
    action: str | None = None


@dataclass(frozen=True)
class Fragment:
    concrete: str
    chain: str
    version: int
    steps: tuple
    abstract: tuple
    start: int = 0


@dataclass(frozen=True)
class Witness:
    run: str
    target: str
    name: str
    frame: int
    source: str


class Catalog:
    """Concrete key = source chain/version plus slice. Abstract keys group candidates."""
    def __init__(self, db):
        self.body = Body(db)
        db.execute("CREATE TABLE IF NOT EXISTS fragment_id (key TEXT PRIMARY KEY, memory INTEGER NOT NULL)")

    def register(self, fragment):
        if self.body.db.execute("SELECT 1 FROM fragment_id WHERE key=?", (fragment.concrete,)).fetchone() or not fragment.steps:
            raise ValueError("Concrete fragment must be unique and nonempty")
        with self.body.db:
            record = self.body.db.execute(
                "INSERT INTO memory(original,source) VALUES (?,?)",
                (json.dumps(asdict(fragment), ensure_ascii=False),
                 f"{fragment.chain}@{fragment.version}")).lastrowid
            tags = {key.casefold() for key in (fragment.concrete, *fragment.abstract)}
            self.body.db.executemany("INSERT INTO tag VALUES (?,?)", ((record,k) for k in tags))
            self.body.db.execute("INSERT INTO fragment_id VALUES (?,?)", (fragment.concrete, record))

    def find(self, index):
        result = []
        for item in self.body.query(index)["matches"]:
            data = json.loads(item["original"])
            data["steps"] = tuple(Step(s["name"], tuple(s["requires"]), s["provides"], s["action"])
                                  for s in data["steps"])
            data["abstract"] = tuple(data["abstract"])
            result.append(Fragment(**data))
        return result

    def one(self, concrete):
        row = self.body.db.execute("SELECT memory FROM fragment_id WHERE key=?", (concrete,)).fetchone()
        if row is None:
            raise KeyError(concrete)
        item = self.body.original(row[0])
        return next(f for f in self.find(concrete) if f.concrete == concrete and
                    f"{f.chain}@{f.version}" == item["source"])

    def cut(self, original, start, end, concrete, *abstract):
        full = self.one(original)
        if not (0 <= start < end <= len(full.steps)):
            raise ValueError("Invalid slice")
        part = Fragment(concrete, full.chain, full.version, full.steps[start:end],
                        tuple(abstract), full.start + start)
        self.register(part)
        return part


class FSM:
    """One fragment execution in the current run. Past receipts never count as new evidence."""
    def __init__(self, fragment, run, target, start_frame):
        self.fragment, self.run, self.target = fragment, run, target
        self.start_frame = self.frame = start_frame
        self.cursor = 0
        self.execution = uuid4().hex
        self.facts = {}
        self.pending = None
        self.receipts = []

    def accept(self, witness):
        if (witness.run, witness.target) != (self.run, self.target) or (
                witness.frame < self.frame or not witness.source):
            raise ValueError("Witness must be from this run, target, and current frame or later")
        # Outcomes of actions must arrive through readback, not the general observation channel.
        if witness.name in {s.provides for s in self.fragment.steps if s.action}:
            raise ValueError("Action outcomes require a bound readback")
        self.frame = witness.frame
        self.facts[witness.name] = witness.frame

    def advance(self):
        if self.pending:
            return {"status": "awaiting-readback", **self.pending}
        if self.cursor == len(self.fragment.steps):
            return {"status": "complete"}
        step = self.fragment.steps[self.cursor]
        missing = [fact for fact in step.requires if self.facts.get(fact) != self.frame]
        if missing:
            return {"status": "blocked", "step": step.name, "missing": missing}
        if step.action:
            self.pending = {"intent": f"{self.execution}:{self.cursor}",
                            "action": step.action, "issued_at": self.frame}
            self.receipts.append({"state":"requested", **self.pending})
            return {"status": "requested", **self.pending}
        # A non-action step checks inputs; it never invents an observation.
        self.cursor += 1
        self.receipts.append({"state":"checked", "step":step.name})
        return {"status":"checked", "step":step.name}

    def readback(self, intent, witness):
        if not self.pending or self.pending["intent"] != intent:
            raise ValueError("No matching pending action")
        step = self.fragment.steps[self.cursor]
        if ((witness.run, witness.target) != (self.run, self.target) or
                witness.frame <= self.pending["issued_at"] or witness.frame < self.frame or
                witness.name != step.provides or not witness.source):
            raise ValueError("Readback must freshly witness the expected outcome")
        self.frame = witness.frame
        self.facts[witness.name] = witness.frame
        self.pending = None
        self.cursor += 1
        self.receipts.append({"state":"confirmed", "intent":intent, "evidence":asdict(witness)})


class Reflexes:
    """Built-in and learned rules enter the same FSM. Triggering is not bypassing."""
    def __init__(self, catalog, builtin):
        self.catalog = catalog
        self.builtin = dict(builtin)
        self.learned = {}
        self.episodes = {}

    def mount(self, signal, scope, concrete, evidence):
        self.catalog.one(concrete)
        if signal in self.builtin or not self.catalog.body.original(evidence)["original"].strip():
            raise ValueError("Require a separate source; built-in bindings are not overwritten")
        self.learned[signal, scope] = (concrete, evidence)

    def trigger(self, signal, scope, event, run, target, frame):
        key = (scope, event, run, target, signal)
        if key in self.episodes:
            return self.episodes[key]
        learned = self.learned.get((signal, scope))
        concrete = self.builtin.get(signal) or (learned[0] if learned else None)
        if concrete is None:
            return None
        machine = FSM(self.catalog.one(concrete), run, target, frame)
        self.episodes[key] = machine
        return machine


def fixtures(db):
    catalog = Catalog(db)
    verify = Step("核对控制状态", ("target-matched","clock-running"))
    pause = Step("暂停并等回读", ("target-matched","clock-running"), "clock-paused", "pause")
    review = Step("把已暂停的现场交会诊", ("clock-paused",))
    catalog.register(Fragment("shift-a-v1-full", "shift-a", 1, (verify,pause,review), ("整班保护",)))
    catalog.cut("shift-a-v1-full", 1, 2, "shift-a-v1-pause", "先停再查")
    catalog.register(Fragment("shift-b-v2-pause", "shift-b", 2,
                              (Step("设备暂停", ("target-matched","clock-running","sensor-ready"),
                                    "clock-paused", "pause"),), ("先停再查",)))
    return catalog


def witness(run, target, name, frame):
    return Witness(run, target, name, frame, f"synthetic:{run}/{frame}/{name}")


def run():
    with closing(sqlite3.connect(":memory:")) as db:
        catalog = fixtures(db)
        full = FSM(catalog.one("shift-a-v1-full"), "A", "gate", 1)
        for fact in ("target-matched","clock-running"):
            full.accept(witness("A","gate",fact,1))
        first = full.advance()
        requested = full.advance()
        full.readback(requested["intent"], witness("A","gate","clock-paused",2))
        last = full.advance()
        routes = [f.concrete for f in catalog.find("先停再查")]
        registry = Reflexes(catalog, {"alarm":"shift-a-v1-pause"})
        no_mount = registry.trigger("low","north","low-1","B","meter",4) is None
        history = catalog.body.remember("异常到来时，先暂停再核对。", "fixture:previous-shift")
        registry.mount("low","north","shift-a-v1-pause",history)
        reused = registry.trigger("low","north","low-1","B","meter",4)
        blocked = reused.advance()
        for fact in ("target-matched","clock-running"):
            reused.accept(witness("B","meter",fact,4))
        issued = reused.advance()
        pending = reused.advance()
        reused.readback(issued["intent"], witness("B","meter","clock-paused",5))
        return {"complete_chain":{"first":first,"last":last,"state":full.advance(),"trace":full.receipts},
                "abstract_candidates":routes,"selected":reused.fragment.concrete,"before_mount":no_mount,
                "missing_current_evidence":blocked,"without_readback":pending,
                "after_readback":reused.advance(),"fragment_trace":reused.receipts}


if __name__ == "__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
