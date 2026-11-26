"""A detached short-term memory built from selected, reconstructed fragments."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4

from rebuild import Rebuilder, setup


class ShortMemory:
    def __init__(self, db):
        self.db = db
        db.executescript("""
            CREATE TABLE IF NOT EXISTS info (id TEXT PRIMARY KEY, source TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS base (anchor INTEGER PRIMARY KEY, head INTEGER, view TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS edit (id INTEGER PRIMARY KEY, anchor INTEGER, mode TEXT, text TEXT,
                evidence TEXT, source TEXT, keywords TEXT);
        """)

    @classmethod
    def fork(cls, db, long, anchors):
        local = cls(db)
        if local.db.execute("SELECT 1 FROM info").fetchone():
            raise ValueError("Workspace already exists")
        ensure_identity(long)
        long.db.execute("BEGIN")
        with long.db:
            source = identity(long)
            snapshots = [(key, long.head(key), json.dumps(long.show(key), ensure_ascii=False))
                         for key in dict.fromkeys(anchors)]
        if not snapshots:
            raise ValueError("Select at least one fragment")
        with db:
            db.execute("INSERT INTO info VALUES (?,?)", (uuid4().hex, source))
            db.executemany("INSERT INTO base VALUES (?,?,?)", snapshots)
        return local

    def _base(self, anchor):
        row = self.db.execute("SELECT head,view FROM base WHERE anchor=?", (anchor,)).fetchone()
        if row is None:
            raise KeyError(anchor)
        return row[0], json.loads(row[1])

    def read(self, anchor):
        head, start = self._base(anchor)
        edits = [dict(zip(("id","mode","text","evidence","source","keywords"),
                          (*row[:-1], json.loads(row[-1]))))
                 for row in self.db.execute(
                     "SELECT id,mode,text,evidence,source,keywords FROM edit WHERE anchor=? ORDER BY id", (anchor,))]
        current = next((e["text"] for e in reversed(edits) if e["mode"] == "update"), start["current_fragment"])
        return {"base_head": head, "base": start, "current_fragment": current, "edits": edits}

    def edit(self, anchor, text, *, mode, evidence, source, keywords):
        self._base(anchor)
        if mode not in {"note","update"} or not text.strip() or not evidence.strip() or not source.strip():
            raise ValueError("An edit needs a mode, text and a separate evidence record")
        with self.db:
            return self.db.execute("INSERT INTO edit(anchor,mode,text,evidence,source,keywords) VALUES (?,?,?,?,?,?)",
                        (anchor,mode,text,evidence,source,json.dumps(list(keywords),ensure_ascii=False))).lastrowid


def ensure_identity(long):
    long.db.executescript("""
        CREATE TABLE IF NOT EXISTS merge_origin (singleton INTEGER PRIMARY KEY CHECK(singleton=1), uid TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS merge_receipt (workspace TEXT PRIMARY KEY, edits TEXT NOT NULL, patches TEXT NOT NULL);
    """)
    with long.db:
        long.db.execute("INSERT OR IGNORE INTO merge_origin VALUES (1,?)", (uuid4().hex,))


def identity(long):
    return long.db.execute("SELECT uid FROM merge_origin WHERE singleton=1").fetchone()[0]


def merge(long, local):
    """Explicit merge request. Compare each touched fragment; append all or append nothing."""
    ensure_identity(long)
    # Pin the branch contents, then release the branch read transaction before taking the writer lock.
    local.db.execute("BEGIN")
    with local.db:
        workspace, origin = local.db.execute("SELECT id,source FROM info").fetchone()
        changes = [(a, local.read(a)) for (a,) in local.db.execute("SELECT DISTINCT anchor FROM edit ORDER BY anchor")]
    encoded = json.dumps(changes, ensure_ascii=False, sort_keys=True)
    long.db.execute("BEGIN IMMEDIATE")
    with long.db:
        if identity(long) != origin:
            raise ValueError("This workspace was built from a different long-term store")
        done = long.db.execute("SELECT edits,patches FROM merge_receipt WHERE workspace=?", (workspace,)).fetchone()
        if done:
            if encoded != done[0]:
                raise ValueError("Already merged; fork a fresh workspace for more edits")
            return {"status":"merged", "patch_ids":json.loads(done[1]), "replayed":True}
        if not changes:
            return {"status":"no-changes", "patch_ids":[]}
        conflicts = []
        for anchor, short in changes:
            if long.head(anchor) != short["base_head"]:
                live = long.show(anchor)
                conflicts.append({"anchor":anchor, "base_head":short["base_head"], "long_head":long.head(anchor),
                                  "base":short["base"]["current_fragment"], "short":short["current_fragment"],
                                  "long":live["current_fragment"], "short_edits":short["edits"]})
        if conflicts:
            return {"status":"conflict", "conflicts":conflicts, "patch_ids":[]}
        patches = []
        for anchor, short in changes:
            previous = short["base_head"]
            for edit in short["edits"]:
                witness = long._save(edit["evidence"], edit["source"], ())
                pid = long._save(edit["text"], edit["source"], edit["keywords"])
                long.db.execute("INSERT INTO patches VALUES (?,?,?,?,?)",
                                (pid, anchor, previous, witness, edit["mode"]))
                previous = pid
                patches.append(pid)
        long.db.execute("INSERT INTO merge_receipt VALUES (?,?,?)",
                        (workspace, encoded, json.dumps(patches)))
        return {"status":"merged", "patch_ids":patches, "replayed":False}


def demo():
    with TemporaryDirectory() as root:
        root = Path(root)
        with (closing(sqlite3.connect(root/"long.sqlite")) as long_db,
              closing(sqlite3.connect(root/"short.sqlite")) as short_db,
              closing(sqlite3.connect(root/"parallel.sqlite")) as parallel_db):
            long = Rebuilder(long_db)
            original, doc, anchors = setup(long)
            time = anchors["time"]
            current = ShortMemory.fork(short_db, long, [time])
            parallel = ShortMemory.fork(parallel_db, long, [time])
            current.edit(time, "例会时间：周四 10:00。", mode="update",
                         evidence="办公室通知：例会改到周四。", source="fixture:time-2", keywords=["例会","周四"])
            parallel.edit(time, "例会时间：周五 10:00。", mode="update",
                          evidence="暂定周五，待对照。", source="fixture:other-shift", keywords=["例会","周五"])
            before = {"short":current.read(time)["current_fragment"], "long":long.show(time)["current_fragment"]}
            first = merge(long,current)
            conflict = merge(long,parallel)
            return {"before_merge":before,"merge":first,"conflict":conflict,
                    "long_after_merge":long.show(time),"original_unchanged":long.body.original(doc)["original"]==original}


if __name__ == "__main__":
    print(json.dumps(demo(), ensure_ascii=False, indent=2))
