from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from rebuild import Rebuilder, setup, example


class RebuildTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/"test.sqlite"
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.view = Rebuilder(self.db)
        self.raw, self.doc, self.anchors = setup(self.view)
        self.time = self.anchors["time"]
        self.evidence = self.view.body.remember("confirmed change", "fixture:new")

    def patch(self, expected=None, text="例会时间：周四 10:00。", mode="update"):
        return self.view.append_patch(self.time, expected, text, mode=mode,
                                      evidence=self.evidence, keywords=["例会", "周四"])

    def test_original_verbatim(self):
        self.patch()
        self.assertEqual(self.view.body.original(self.doc)["original"], self.raw)

    def test_new_and_old_keywords_find_same_updated_fragment(self):
        pid = self.patch()
        current, = self.view.query("周四")
        older, = self.view.query("周二")
        self.assertEqual(current["current_fragment"], older["current_fragment"])
        self.assertEqual(current["matched_record_ids"], [pid])
        self.assertEqual(older["matched_record_ids"], [self.time])
        self.assertTrue(older["original_is_historical"])

    def test_query_does_not_pull_unrelated_sections_by_default(self):
        self.patch()
        item, = self.view.query("周四")
        self.assertNotIn("neighbors", item)
        self.assertNotIn("北楼", item["current_fragment"])

    def test_bounded_adjacent_context(self):
        self.patch()
        item, = self.view.query("周四", neighbors=True)
        self.assertEqual([n["name"] for n in item["neighbors"]], ["place"])

    def test_notes_do_not_override_update(self):
        p1 = self.patch()
        p2 = self.patch(p1, "只改时间", "note")
        item = self.view.show(self.time)
        self.assertEqual(item["current_fragment"], "例会时间：周四 10:00。")
        self.assertEqual([(r["id"], r["previous"]) for r in item["history"]], [(p1,None),(p2,p1)])
        self.assertEqual(item["history"][0]["evidence"]["source"], "fixture:new")

    def test_as_of_does_not_leak_future_patch_or_keyword(self):
        v1 = self.patch()
        v2 = self.patch(v1, "例会时间：周五。")
        self.assertEqual(self.view.query("周四", as_of=v1-1), [])
        self.assertIn("周二", self.view.show(self.time, as_of=v1-1)["current_fragment"])
        self.assertIn("周四", self.view.show(self.time, as_of=v1)["current_fragment"])
        self.assertIn("周五", self.view.show(self.time, as_of=v2)["current_fragment"])

    def test_stale_revision_does_not_write_or_reorder(self):
        self.patch()
        count = self.db.execute("SELECT count(*) FROM memory").fetchone()[0]
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.patch()
        self.assertEqual(self.db.execute("SELECT count(*) FROM memory").fetchone()[0], count)

    def test_unknown_evidence_and_empty_address_rejected(self):
        for evidence in (999, self.time):
            with self.subTest(evidence=evidence), self.assertRaises((ValueError, KeyError)):
                self.view.append_patch(self.time, None, "new", mode="update", evidence=evidence, keywords=["test"])
        self.assertIsNone(self.view.head(self.time))

    def test_ambiguity_retained_and_same_anchor_deduplicated(self):
        self.patch()
        matches = self.view.query("例会")
        self.assertEqual({item["name"] for item in matches}, {"time", "place", "access"})
        self.assertEqual(len(matches), 3)

    def test_reopen_preserves_patch_links(self):
        p1 = self.patch()
        with closing(sqlite3.connect(self.path)) as reopened:
            self.assertEqual(Rebuilder(reopened).head(self.time), p1)

    def test_end_to_end_entry(self):
        result = example("周四", False)
        self.assertTrue(result["original_unchanged"])
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(len(result["matches"][0]["history"]), 2)


if __name__ == "__main__":
    unittest.main()
