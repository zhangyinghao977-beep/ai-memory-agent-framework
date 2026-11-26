"""Patch-led local reconstruction on the Hongchenxian demo's original-text store."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from demo import Body


class Rebuilder:
    def __init__(self, db):
        self.db = db
        self.body = Body(db)
        db.executescript("""
        CREATE TABLE IF NOT EXISTS anchors (
            id INTEGER PRIMARY KEY,
            doc INTEGER NOT NULL REFERENCES memory(id),
            name TEXT NOT NULL,
            start INTEGER NOT NULL,
            end INTEGER NOT NULL,
            UNIQUE(doc, name), CHECK(start >= 0 AND end > start));
        CREATE TABLE IF NOT EXISTS patches (
            id INTEGER PRIMARY KEY REFERENCES memory(id),
            anchor INTEGER NOT NULL REFERENCES anchors(id),
            previous INTEGER REFERENCES patches(id),
            evidence INTEGER NOT NULL REFERENCES memory(id),
            mode TEXT NOT NULL CHECK(mode IN ('note','update')));
        """)

    def _save(self, text, source, keywords):
        """Insert without an inner commit so patch text, indices and links are atomic."""
        key = self.db.execute("INSERT INTO memory(original,source) VALUES (?,?)",
                              (text, source)).lastrowid
        self.db.executemany("INSERT INTO tag VALUES (?,?)",
                            ((key, word) for word in {k.casefold().strip() for k in keywords if k.strip()}))
        return key

    def add_document(self, original, source, sections):
        """Register one verbatim document; sections are exact non-overlapping spans."""
        prepared = []
        for name, start, end, words in sections:
            if not name or not (0 <= start < end <= len(original)):
                raise ValueError("Invalid anchor")
            prepared.append((start, end, name, tuple(words)))
        prepared.sort()
        if not prepared or any(a[1] > b[0] for a, b in zip(prepared, prepared[1:])):
            raise ValueError("Anchors must exist and must not overlap")
        with self.db:
            doc = self._save(original, source, ())
            result = {}
            for start, end, name, words in prepared:
                # Store only offsets for the original. An index address is not a copy of the text.
                address = self._save("", source + "#" + name, words)
                self.db.execute("INSERT INTO anchors VALUES (?,?,?,?,?)",
                                (address, doc, name, start, end))
                result[name] = address
        return doc, result

    def head(self, anchor):
        return self.db.execute("SELECT MAX(id) FROM patches WHERE anchor=?", (anchor,)).fetchone()[0]

    def append_patch(self, anchor, expected_head, text, *, mode, evidence, keywords):
        """Register a reviewed patch; reject a stale writer instead of selecting a winner."""
        if mode not in {"note", "update"} or not text.strip() or not evidence:
            raise ValueError("A patch requires a mode, text and a source record")
        # Hold the writer lock across the head check and append. A failed patch leaves no orphan.
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            if not self.db.execute("SELECT id FROM anchors WHERE id=?", (anchor,)).fetchone():
                raise KeyError(anchor)
            if self.head(anchor) != expected_head:
                raise ValueError("Stale base: reread current patches before deciding")
            record = self.body.original(evidence)
            if not record["original"].strip():
                raise ValueError("Evidence must be an original record, not an empty index address")
            pid = self._save(text, record["source"], keywords)
            self.db.execute("INSERT INTO patches VALUES (?,?,?,?,?)",
                            (pid, anchor, expected_head, evidence, mode))
            return pid

    def show(self, anchor, as_of=None):
        row = self.db.execute("SELECT doc,name,start,end FROM anchors WHERE id=?", (anchor,)).fetchone()
        if row is None:
            raise KeyError(anchor)
        doc, name, start, end = row
        source = self.body.original(doc)
        args = (anchor,) if as_of is None else (anchor, as_of)
        patch_rows = self.db.execute(
            "SELECT id,previous,evidence,mode FROM patches WHERE anchor=?"
            + ("" if as_of is None else " AND id<=?")
            + " ORDER BY id", args)
        original = source["original"][start:end]
        current = original
        history = []
        for pid, previous, evidence, mode in patch_rows:
            value = self.body.original(pid)["original"]
            history.append({"id": pid, "previous": previous, "mode": mode, "text": value,
                            "evidence": self.body.original(evidence)})
            if mode == "update":
                current = value
        return {"anchor": anchor, "name": name, "doc": doc, "source": source["source"],
                "span": [start, end], "original_fragment": original,
                "current_fragment": current, "history": history,
                "original_is_historical": any(x["mode"] == "update" for x in history)}

    def query(self, expression, *, as_of=None, neighbors=False):
        """Decode hits into anchor IDs; combine only the requested section and bounded context."""
        if as_of is None:
            as_of = self.db.execute("SELECT COALESCE(MAX(id), 0) FROM memory").fetchone()[0]
        hits = self.body.query(expression)["matches"]
        decoded = {}
        for hit in hits:
            key = hit["id"]
            active = self.db.execute("SELECT id,doc,start FROM anchors WHERE id=?", (key,)).fetchone()
            if active is None:
                active = self.db.execute(
                    "SELECT a.id,a.doc,a.start FROM patches p JOIN anchors a ON a.id=p.anchor WHERE p.id=?",
                    (key,)).fetchone()
            if active is None or (as_of is not None and key > as_of):
                continue
            decoded.setdefault(active, []).append(key)
        result = []
        for (anchor, doc, start), ids in sorted(decoded.items()):
            item = self.show(anchor, as_of)
            item["matched_record_ids"] = ids
            if neighbors:
                item["neighbors"] = [
                    self.show(row[0], as_of) for row in (
                        self.db.execute("SELECT id FROM anchors WHERE doc=? AND start<? AND id<=? ORDER BY start DESC LIMIT 1",
                                        (doc, start, as_of)).fetchone(),
                        self.db.execute("SELECT id FROM anchors WHERE doc=? AND start>? AND id<=? ORDER BY start LIMIT 1",
                                        (doc, start, as_of)).fetchone(),
                    ) if row is not None
                ]
            result.append(item)
        return result


def setup(rebuild):
    fragments = ["例会时间：周二 10:00。", "地点：北楼 203。", "门禁：进楼时刷卡。"]
    original = "\n".join(fragments) + "\n"
    labels = [("time", ["例会", "周二"]), ("place", ["例会", "地点"]), ("access", ["例会", "门禁"])]
    sections = []
    start = 0
    for s, (name, tags) in zip(fragments, labels):
        sections.append((name, start, start + len(s), tags))
        start += len(s) + 1
    doc, anchors = rebuild.add_document(original, "fixture:original-notice", sections)
    return original, doc, anchors


def example(query, neighbors):
    with TemporaryDirectory(prefix="hongchenxian-rebuild-") as temp:
        db_path = Path(temp) / "memory.sqlite"
        with closing(sqlite3.connect(db_path)) as db:
            rebuild = Rebuilder(db)
            original, doc, anchors = setup(rebuild)
            time = anchors["time"]
            before = rebuild.body.remember("办公室通知：本周例会改为周四上午十点。", "fixture:notice-2")
            p1 = rebuild.append_patch(time, None, "例会时间：周四 10:00。", mode="update",
                                      evidence=before, keywords=["例会", "周四"])
            after = rebuild.body.remember("补充通知：其他安排不变。", "fixture:notice-3")
            p2 = rebuild.append_patch(time, p1, "此补丁仅调整时间，不涉及地点。", mode="note",
                                      evidence=after, keywords=["例会", "改期说明"])
        with closing(sqlite3.connect(db_path)) as db:
            rebuild = Rebuilder(db)
            return {"query": query, "original_unchanged": rebuild.body.original(doc)["original"] == original,
                    "before_patches": rebuild.show(time, as_of=p1 - 1),
                    "after_update": rebuild.show(time, as_of=p1),
                    "patch_ids": [p1, p2], "matches": rebuild.query(query, neighbors=neighbors)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="周四")
    parser.add_argument("--neighbors", action="store_true")
    args = parser.parse_args()
    print(json.dumps(example(args.query, args.neighbors), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
