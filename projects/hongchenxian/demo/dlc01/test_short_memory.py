from contextlib import ExitStack, closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from rebuild import Rebuilder, setup
from short_memory import ShortMemory, merge


class ShortMemoryTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(TemporaryDirectory()))
        self.connect = lambda name: stack.enter_context(closing(sqlite3.connect(self.root/name)))
        self.long = Rebuilder(self.connect("long"))
        self.original, self.doc, self.anchors = setup(self.long)
        self.time, self.place = (self.anchors[k] for k in ("time","place"))

    def fork(self, name, *anchors):
        return ShortMemory.fork(self.connect(name), self.long, anchors)

    def edit(self, workspace, anchor, value):
        return workspace.edit(anchor, value, mode="update", evidence="witness " + value,
                              source="fixture:edit", keywords=["updated"])

    def test_detached_contains_only_selected_and_persists(self):
        short = self.fork("short", self.time)
        self.edit(short, self.time, "Thursday")
        reopened = ShortMemory(self.connect("short"))
        self.assertEqual(reopened.read(self.time)["current_fragment"], "Thursday")
        with self.assertRaises(KeyError):
            reopened.read(self.place)
        self.assertIn("周二", self.long.show(self.time)["current_fragment"])
        self.assertFalse(self.long.query("updated"))

    def test_merge_atomic_and_idempotent(self):
        short = self.fork("short", self.time)
        self.edit(short, self.time, "Thursday")
        first = merge(self.long, short)
        second = merge(self.long, short)
        self.assertEqual(first["patch_ids"], second["patch_ids"])
        self.assertTrue(second["replayed"])
        self.assertEqual(self.long.body.original(self.doc)["original"], self.original)
        self.assertEqual(self.long.query("updated")[0]["current_fragment"], "Thursday")

    def test_same_anchor_conflict_blocks_batch_without_partial_write(self):
        a = self.fork("a",self.time)
        b = self.fork("b",self.time,self.place)
        self.edit(a,self.time,"Thursday")
        self.edit(b,self.time,"Friday")
        self.edit(b,self.place,"South building")
        merge(self.long,a)
        result = merge(self.long,b)
        self.assertEqual(result["status"],"conflict")
        self.assertEqual((result["conflicts"][0]["short"], result["conflicts"][0]["long"]),("Friday","Thursday"))
        self.assertIsNone(self.long.head(self.place))
        self.assertEqual(b.read(self.place)["current_fragment"],"South building")

    def test_unrelated_head_change_does_not_block_merge(self):
        a = self.fork("a",self.time)
        b = self.fork("b",self.place)
        self.edit(a,self.time,"Thursday")
        self.edit(b,self.place,"South building")
        merge(self.long,a)
        self.assertEqual(merge(self.long,b)["status"],"merged")

    def test_wrong_store_rejected_even_with_same_anchor_numbers(self):
        a = self.fork("a",self.time)
        self.edit(a,self.time,"Thursday")
        wrong = Rebuilder(self.connect("wrong"))
        setup(wrong)
        with self.assertRaisesRegex(ValueError,"different"):
            merge(wrong,a)
        self.assertIsNone(wrong.head(self.time))
