"""Visible index map: curated views, not direct access to trusted memory."""
from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4


@dataclass(frozen=True)
class PublishedView:
    heading: str
    excerpt: str
    terms: tuple[str, ...]


def publish(path, audience, approved):
    """Trusted publisher materializes approved text, never backend IDs or raw paths."""
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE audience(name TEXT NOT NULL)")
        db.execute("CREATE TABLE view(handle TEXT PRIMARY KEY, heading TEXT, excerpt TEXT)")
        db.execute("CREATE TABLE edge(term TEXT, handle TEXT, PRIMARY KEY(term,handle)) WITHOUT ROWID")
        db.execute("INSERT INTO audience VALUES (?)", (audience,))
        for item in approved:
            key = uuid4().hex
            db.execute("INSERT INTO view VALUES (?,?,?)", (key, item.heading, item.excerpt))
            db.executemany("INSERT INTO edge VALUES (?,?)",
                           [(t, key) for t in {word.casefold() for word in item.terms}])


class Gateway:
    """Service-side binding receives a current path from the operator, not from the caller."""
    def __init__(self, grants):
        self.grants = grants

    def _read(self, audience, sql, args):
        path = self.grants.get(audience)
        if path is None:
            return []
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT name FROM audience").fetchone()
            if not row or row[0] != audience:
                return []
            return db.execute(sql, args).fetchall()

    def search(self, audience, term):
        return [{"handle":h, "heading":title} for h,title in self._read(audience,
            """SELECT v.handle,v.heading FROM edge e JOIN view v ON e.handle=v.handle
               WHERE e.term=? ORDER BY v.heading,v.handle""", (term.casefold(),))]

    def read(self, audience, handle):
        rows = self._read(audience, "SELECT heading,excerpt FROM view WHERE handle=?", (handle,))
        if rows:
            heading, excerpt = rows[0]
            return {"heading":heading,"excerpt":excerpt}
        return None


def demo():
    with TemporaryDirectory() as folder:
        root = Path(folder)
        # Only the trusted side can see the full fixture tree.
        trusted = {"meeting": "Meeting starts at ten.", "payroll": "Payroll forecast is private."}
        meeting = PublishedView("Meeting time",trusted["meeting"],("meeting","schedule"))
        payroll = PublishedView("Payroll forecast",trusted["payroll"],("payroll","schedule"))
        publish(root/"team.map", "team", [meeting])
        publish(root/"finance.map", "finance", [meeting,payroll])
        grants = {"team":root/"team.map", "finance":root/"finance.map"}
        access = Gateway(grants)
        visible = access.search("team","schedule")
        secret = access.search("finance","payroll")[0]
        denied = access.read("team",secret["handle"])
        approved = access.read("team",visible[0]["handle"])
        del grants["team"]
        revoked = access.read("team",visible[0]["handle"])
        return {"team_search":visible,"approved_view":approved,"other_map_handle":denied,
                "after_revocation":revoked,"trusted_records_unchanged":trusted["meeting"]=="Meeting starts at ten."}


if __name__ == "__main__":
    print(json.dumps(demo(),indent=2))
