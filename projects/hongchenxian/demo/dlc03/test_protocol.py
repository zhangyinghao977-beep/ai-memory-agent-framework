from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from protocol import Catalog, FSM, Reflexes, fixtures, run, witness


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        self.cat = fixtures(db)
        self.machine = self.new()

    def new(self, key="shift-a-v1-pause"):
        return FSM(self.cat.one(key), "run", "gate", 10)

    def preconditions(self):
        for fact in ("target-matched","clock-running"):
            self.machine.accept(witness("run","gate",fact,10))

    def test_concrete_slice_retains_version_and_origin(self):
        part = self.cat.one("shift-a-v1-pause")
        entire = self.cat.one("shift-a-v1-full")
        self.assertEqual((part.chain,part.version,part.start),("shift-a",1,1))
        self.assertEqual(part.steps, entire.steps[1:2])

    def test_abstract_returns_candidates_not_an_executable_decision(self):
        self.assertEqual(len(self.cat.find("先停再查")),2)
        self.machine = self.new("shift-b-v2-pause")
        self.preconditions()
        self.assertEqual(self.machine.advance()["missing"], ["sensor-ready"])

    def test_arbitrary_slice_can_be_registered(self):
        p = self.cat.cut("shift-a-v1-full", 1, 3, "pause-review", "交流前保护")
        self.assertEqual(len(p.steps),2)
        self.assertEqual(self.cat.find("交流前保护"), [p])

    def test_old_and_other_target_evidence_do_not_bind(self):
        for old in (witness("run","gate","clock-running",9),
                    witness("old","gate","clock-running",10),
                    witness("run","other","clock-running",10)):
            with self.assertRaises(ValueError):
                self.machine.accept(old)
        self.assertEqual(self.machine.advance()["status"],"blocked")

    def test_older_reading_expires_at_new_frame(self):
        self.preconditions()
        self.machine.accept(witness("run","gate","target-matched",11))
        self.assertEqual(self.machine.advance()["missing"],["clock-running"])

    def test_request_is_not_completion_and_is_not_issued_twice(self):
        self.preconditions()
        req = self.machine.advance()
        self.assertEqual(req["status"],"requested")
        self.assertEqual(self.machine.advance()["status"],"awaiting-readback")
        self.assertEqual(len(self.machine.receipts),1)
        with self.assertRaises(ValueError):
            self.machine.readback(req["intent"], witness("run","gate","clock-paused",10))
        with self.assertRaises(ValueError):
            self.machine.accept(witness("run","gate","clock-paused",11))
        self.machine.readback(req["intent"],witness("run","gate","clock-paused",11))
        self.assertEqual(self.machine.advance()["status"],"complete")

    def test_builtin_and_learned_use_same_gate(self):
        r = Reflexes(self.cat, {"alarm":"shift-a-v1-pause"})
        f = lambda sig, scope: r.trigger(sig,scope,"e","run","gate",10)
        self.assertEqual(f("alarm","north").advance()["status"],"blocked")
        self.assertIsNone(f("low","north"))
        e = self.cat.body.remember("previous experience","fixture")
        r.mount("low","north","shift-a-v1-pause",e)
        self.assertIsNone(f("low","other"))
        self.assertIs(f("low","north"),f("low","north"))
        self.assertEqual(f("low","north").advance()["status"],"blocked")

    def test_catalog_reopens(self):
        with TemporaryDirectory() as folder:
            file=Path(folder)/"catalog.sqlite"
            with closing(sqlite3.connect(file)) as db:
                fixtures(db)
            with closing(sqlite3.connect(file)) as db:
                self.assertEqual(Catalog(db).one("shift-a-v1-pause").start,1)

    def test_walkthrough(self):
        r = run()
        self.assertEqual(r["complete_chain"]["state"]["status"],"complete")
        self.assertEqual(r["after_readback"]["status"],"complete")
        self.assertEqual(r["without_readback"]["status"],"awaiting-readback")
