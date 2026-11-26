from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from demo import Body, DemoClock, ReflexFSM, Signal, run


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.body = Body(self.db)
        self.first = self.body.remember("  original\n", "test:1", "shift", "charge")
        self.second = self.body.remember("second", "test:2", "shift", "gate")

    def test_shared_keyword_returns_two_originals(self):
        hits = self.body.query("shift")["matches"]
        self.assertEqual([row["id"] for row in hits], [self.first, self.second])
        self.assertEqual(hits[0]["original"], "  original\n")

    def test_codebook_and_boolean(self):
        self.body.register_word("battery", "charge")
        hits = self.body.query("+shift |battery |gate !gate")
        self.assertEqual(hits["indices"]["|"], ["charge", "gate"])
        self.assertEqual([row["id"] for row in hits["matches"]], [self.first])

    def test_unknown_and_invalid_query_do_not_expand(self):
        self.assertEqual(self.body.query("shift typo")["matches"], [])
        for query in ("", "!gate", "+", "(gate)"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.body.query(query)

    def test_unmounted_or_wrong_scope_does_not_act(self):
        fsm = ReflexFSM(self.body)
        clock = DemoClock()
        obs = Signal("one", "north", "charge")
        self.assertEqual(fsm.handle(obs, clock)["status"], "not-mounted")
        fsm.register("charge", "south", self.first)
        self.assertEqual(fsm.handle(obs, clock)["status"], "not-mounted")
        self.assertEqual(clock.requests, 0)

    def test_unknown_clock_not_acted_on(self):
        clock = DemoClock(state="unknown")
        self.assertEqual(ReflexFSM(self.body).handle(Signal("1", "any", "alarm"), clock)["status"], "clock-unknown")
        self.assertEqual(clock.requests, 0)

    def test_ignored_pause_not_reported_as_success_or_retried(self):
        fsm = ReflexFSM(self.body)
        clock = DemoClock(accepts=False)
        obs = Signal("alarm-1", "north", "alarm")
        self.assertEqual(fsm.handle(obs, clock)["status"], "pause-unconfirmed")
        self.assertTrue(fsm.handle(obs, clock)["duplicate"])
        self.assertEqual(clock.requests, 1)

    def test_mount_requires_evidence(self):
        with self.assertRaises(KeyError):
            ReflexFSM(self.body).register("low", "north", 999)

    def test_handoff_checks_owner_and_retains_unknown(self):
        self.body.open_chain("crossing", "old")
        with self.assertRaises(ValueError):
            self.body.handoff("crossing", "wrong", "relief")
        self.body.handoff("crossing", "old", "relief")
        with self.assertRaises(ValueError):
            self.body.review("crossing", "relief", 1)
        self.assertEqual(self.body.read_chain("crossing"), {"owner": "relief", "reviewed": 0, "nodes": []})

    def test_full_walkthrough_uses_shared_evidence_and_independent_cursors(self):
        with TemporaryDirectory() as directory:
            report = run(Path(directory) / "demo.sqlite")
        chains = report["4_logic_pool"]["chains_after_reopen"]
        self.assertEqual(chains["meter"]["nodes"][0]["evidence"], chains["gate"]["nodes"][0]["evidence"])
        self.assertEqual([c["reviewed"] for c in chains.values()], [2, 0, 0])
        self.assertEqual(chains["crossing"]["owner"], "relief")
        self.assertEqual(chains["crossing"]["nodes"], [])
        self.assertEqual(report["3_reflex"]["after_mount"]["status"], "pause-confirmed")
        self.assertEqual(report["3_reflex"]["ignored_clock_requests"], 1)


if __name__ == "__main__":
    unittest.main()
