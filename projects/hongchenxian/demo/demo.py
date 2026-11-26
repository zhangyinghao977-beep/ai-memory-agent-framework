"""Hongchenxian public research demo. No model, network, or real actuator."""
import argparse
from contextlib import closing
from dataclasses import dataclass
import json
import re
import sqlite3
import tempfile
from pathlib import Path

TOKENS = re.compile(r"[+|!]?[\w-]+", re.UNICODE)


class Body:
    """One evidence store with independent cursors for multiple event chains."""

    def __init__(self, db):
        self.db = db
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS memory (
          id INTEGER PRIMARY KEY, original TEXT NOT NULL, source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tag (
          id INTEGER NOT NULL REFERENCES memory(id), word TEXT NOT NULL, PRIMARY KEY(id, word));
        CREATE TABLE IF NOT EXISTS alias (
          surface TEXT PRIMARY KEY, word TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS chain (
          name TEXT PRIMARY KEY, owner TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS node (
          seq INTEGER PRIMARY KEY, chain TEXT REFERENCES chain(name),
          evidence INTEGER REFERENCES memory(id), value TEXT NOT NULL,
          UNIQUE(chain, evidence));
        """)
        self.db.execute("PRAGMA foreign_keys = ON")

    def remember(self, original, source, *keywords):
        with self.db:
            key = self.db.execute(
                "INSERT INTO memory(original,source) VALUES (?,?)", (original, source)
            ).lastrowid
            self.db.executemany("INSERT INTO tag VALUES (?,?)",
                                [(key, word.casefold()) for word in set(keywords)])
        return key

    def register_word(self, surface, index_word):
        with self.db:
            self.db.execute("INSERT INTO alias VALUES (?,?)", (surface.casefold(), index_word.casefold()))

    def original(self, key):
        row = self.db.execute("SELECT original,source FROM memory WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return {"id": key, "original": row[0], "source": row[1]}

    def query(self, expression):
        """Parse the small query grammar, resolve its codebook, then decode record IDs."""
        groups = {"+": [], "|": [], "!": []}
        for token in expression.split():
            if not TOKENS.fullmatch(token):
                raise ValueError("Expected space-delimited words with optional + | ! prefixes")
            op, term = (token[0], token[1:]) if token[0] in groups else ("+", token)
            key = term.casefold()
            mapping = self.db.execute("SELECT word FROM alias WHERE surface=?", (key,)).fetchone()
            groups[op].append(mapping[0] if mapping else key)
        if not groups["+"] and not groups["|"]:
            raise ValueError("Expected at least one positive term")
        def ids(word):
            return {row[0] for row in self.db.execute("SELECT id FROM tag WHERE word=?", (word,))}
        candidates = None
        for word in groups["+"]:
            candidates = ids(word) if candidates is None else candidates & ids(word)
        if groups["|"]:
            union = set().union(*(ids(word) for word in groups["|"]))
            candidates = union if candidates is None else candidates & union
        for word in groups["!"]:
            candidates -= ids(word)
        return {"indices": groups, "matches": [self.original(key) for key in sorted(candidates)]}

    def open_chain(self, name, owner):
        with self.db:
            self.db.execute("INSERT INTO chain(name,owner) VALUES (?,?)", (name, owner))

    def observe(self, name, evidence, value):
        with self.db:
            self.db.execute("INSERT INTO node(chain,evidence,value) VALUES (?,?,?)",
                            (name, evidence, value))

    def handoff(self, name, current, relief):
        with self.db:
            if self.db.execute("UPDATE chain SET owner=? WHERE name=? AND owner=?",
                               (relief, name, current)).rowcount != 1:
                raise ValueError("Handoff requires the current owner")

    def read_chain(self, name):
        owner, reviewed = self.db.execute("SELECT owner,reviewed FROM chain WHERE name=?", (name,)).fetchone()
        nodes = [{"value": value, "evidence": self.original(evidence)} for evidence, value
                 in self.db.execute("SELECT evidence,value FROM node WHERE chain=? ORDER BY seq", (name,))]
        return {"owner": owner, "reviewed": reviewed, "nodes": nodes}

    def review(self, name, owner, through):
        stream = self.read_chain(name)
        if stream["owner"] != owner or not stream["reviewed"] <= through <= len(stream["nodes"]):
            raise ValueError("Only the current owner can move the cursor across witnessed nodes")
        with self.db:
            cursor = self.db.execute(
                "UPDATE chain SET reviewed=? WHERE name=? AND owner=? AND reviewed=?",
                (through, name, owner, stream["reviewed"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("Owner or cursor changed; reread the chain")


@dataclass(frozen=True)
class Signal:
    event: str
    scope: str
    kind: str


class ReflexFSM:
    """A built-in guard plus an explicitly mounted, source-backed scoped reflex."""

    def __init__(self, body):
        self.body = body
        self.mounts = {}
        self.attempted = {}

    def register(self, kind, scope, evidence):
        self.mounts[(kind, scope)] = self.body.original(evidence)["id"]

    def handle(self, signal, clock):
        evidence = self.mounts.get((signal.kind, signal.scope))
        if signal.kind != "alarm" and evidence is None:
            return {"status": "not-mounted"}
        identity = (signal.scope, signal.event, signal.kind)
        if identity in self.attempted:
            return dict(self.attempted[identity], duplicate=True)
        before = clock.read()
        if before != "running":
            return {"status": "already-paused" if before == "paused" else "clock-unknown"}
        # Mark the attempt before acting. A missing readback is not success.
        result = self.attempted[identity] = {"status": "pause-unconfirmed", "learned_from": evidence}
        clock.request_pause()
        if clock.read() == "paused":
            result["status"] = "pause-confirmed"
        return dict(result)


class DemoClock:
    def __init__(self, accepts=True, state="running"):
        self.accepts, self.state, self.requests = accepts, state, 0

    def read(self):
        return self.state

    def request_pause(self):
        self.requests += 1
        if self.accepts:
            self.state = "paused"


def run(path):
    with closing(sqlite3.connect(path)) as db:
        body = Body(db)
        prior = body.remember("A low charge was missed while attention was on the gate.",
                              "fixture:prior-shift", "shift", "charge", "review")
        f1 = body.remember("Meter 40/100. Marker visible at gate C.\n",
                           "fixture:1", "shift", "gate", "charge")
        f2 = body.remember("Meter 65/100. Marker no longer visible at gate C.",
                           "fixture:2", "shift", "gate", "charge")
        body.register_word("battery", "charge")
        memory = body.query("shift")
        retrieval = body.query('+shift |battery !review')
        fsm = ReflexFSM(body)
        learned = Signal("2", "north", "charge-low")
        unmounted = fsm.handle(learned, DemoClock())
        built_in = fsm.handle(Signal("1", "north", "alarm"), DemoClock())
        fsm.register("charge-low", "north", prior)
        rejects = DemoClock(accepts=False)
        unconfirmed = fsm.handle(learned, rejects)
        duplicate = fsm.handle(learned, rejects)
        confirmed = fsm.handle(Signal("3", "north", "charge-low"), DemoClock())
        for chain, owner in (("meter", "reader"), ("gate", "scout"), ("crossing", "observer")):
            body.open_chain(chain, owner)
        for evidence, meter, gate in ((f1, "40/100", "visible"), (f2, "65/100", "not visible at gate C")):
            body.observe("meter", evidence, meter)
            body.observe("gate", evidence, gate)
        body.review("meter", "reader", 2)
        body.handoff("crossing", "observer", "relief")
    with closing(sqlite3.connect(path)) as db:
        body = Body(db)
        chains = {name: body.read_chain(name) for name in ("meter", "gate", "crossing")}
    missing = [name for name, chain in chains.items() if not chain["nodes"]]
    decision = ("unknown: no evidence of the " + ", ".join(missing)) if missing else "ready for human review"
    return {
        "1_memory": {"shared_keyword_hits": len(memory["matches"]), "distinct_ids": [x["id"] for x in memory["matches"]]},
        "2_fsm_query": retrieval,
        "3_reflex": {"built_in": built_in, "before_mount": unmounted, "after_mount": confirmed,
                     "ignored_input": unconfirmed, "repeat": duplicate, "ignored_clock_requests": rejects.requests},
        "4_logic_pool": {"chains_after_reopen": chains,
                         "cross_chain_decision": decision},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the full audit as JSON")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hongchenxian-") as directory:
        result = run(Path(directory) / "demo.sqlite")
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return
    print("Hongchenxian | four-stage public demo")
    print("1. Shared keyword, distinct originals:", result["1_memory"]["shared_keyword_hits"])
    print("2. Codebook query matched:", ", ".join(x["source"] for x in result["2_fsm_query"]["matches"]))
    reflex = result["3_reflex"]
    print("3. Reflex:", reflex["built_in"]["status"], "/", reflex["before_mount"]["status"],
          "/", reflex["after_mount"]["status"], "/", reflex["ignored_input"]["status"])
    for name, chain in result["4_logic_pool"]["chains_after_reopen"].items():
        print(f'4. {name} | owner={chain["owner"]} | observed={len(chain["nodes"])} | reviewed={chain["reviewed"]}')
    print("Decision:", result["4_logic_pool"]["cross_chain_decision"])


if __name__ == "__main__":
    main()
