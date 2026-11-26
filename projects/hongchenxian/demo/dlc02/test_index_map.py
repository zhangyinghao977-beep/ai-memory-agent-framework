from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from index_map import Gateway,PublishedView,publish,demo


class MapTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        a,b = root/"team.map",root/"finance.map"
        publish(a,"team",[PublishedView("Time","ten",("schedule",))])
        publish(b,"finance",[PublishedView("Payroll","secret",("schedule","payroll"))])
        self.grants={"team":a,"finance":b}
        self.gateway=Gateway(self.grants)

    def test_search_sees_only_its_visible_edges(self):
        team, = self.gateway.search("team","schedule")
        self.assertEqual(team["heading"],"Time")
        self.assertEqual(self.gateway.search("team","payroll"),[])

    def test_hidden_record_and_unknown_handle_same_response(self):
        secret,=self.gateway.search("finance","payroll")
        self.assertIsNone(self.gateway.read("team",secret["handle"]))
        self.assertIsNone(self.gateway.read("team","unknown"))

    def test_revocation_applies_to_existing_handle(self):
        visible,=self.gateway.search("team","schedule")
        self.assertEqual(self.gateway.read("team",visible["handle"])["excerpt"],"ten")
        del self.grants["team"]
        self.assertIsNone(self.gateway.read("team",visible["handle"]))

    def test_gateway_rejects_wrong_audience_map(self):
        self.grants["team"]=self.grants["finance"]
        self.assertEqual(self.gateway.search("team","payroll"),[])

    def test_graph_entry_uses_sqlite_key_search(self):
        with closing(sqlite3.connect(self.grants["team"])) as db:
            query=db.execute("EXPLAIN QUERY PLAN SELECT handle FROM edge WHERE term=?",("schedule",)).fetchall()
        self.assertIn("SEARCH",str(query))
        self.assertIn("term=?",str(query))

    def test_walkthrough(self):
        result=demo()
        self.assertEqual(result["approved_view"]["heading"],"Meeting time")
        self.assertIsNone(result["other_map_handle"])
        self.assertIsNone(result["after_revocation"])
