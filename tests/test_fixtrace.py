import unittest
from fixtrace.fixparse import build_message, parse
from fixtrace.session import analyze_session
from fixtrace.orders import reconstruct
from fixtrace import sample, db
from fixtrace.__main__ import analyze

S = "BUYSIDE1"; B = "BROKER1"


def msg(mt, snd, tgt, seq, body=()):
    return parse(build_message([(35, mt), (49, snd), (56, tgt), (34, seq), (52, "20261020-14:00:00.000")] + list(body)))


class ParseTests(unittest.TestCase):
    def test_roundtrip_valid(self):
        m = msg("D", S, B, 2, [(11, "A1"), (55, "IBM"), (38, 100)])
        self.assertTrue(m.valid)
        self.assertEqual(m.get(55), "IBM")
        self.assertEqual(m.name, "NewOrderSingle")

    def test_pipe_delimiter(self):
        raw = build_message([(35, "0"), (34, 1)]).replace("\x01", "|")
        self.assertTrue(parse(raw).valid)

    def test_bad_checksum(self):
        raw = build_message([(35, "0"), (34, 1)])
        bad = raw[:-4] + "999\x01"
        self.assertTrue(any("CheckSum" in e for e in parse(bad).errors))

    def test_bad_body_length(self):
        raw = build_message([(35, "0"), (34, 1)]).replace("9=", "9=1", 1)
        self.assertTrue(any("BodyLength" in e for e in parse(raw).errors))

    def test_malformed_field(self):
        self.assertTrue(any("malformed" in e for e in parse("8=FIX.4.4|9=5|35=0|abc|10=000|").errors))


class SessionTests(unittest.TestCase):
    def test_gap_detected(self):
        ms = [msg("A", S, B, 1), msg("0", S, B, 2), msg("0", S, B, 5)]
        issues = analyze_session(ms)
        self.assertEqual([i["kind"] for i in issues], ["SEQ_GAP"])
        self.assertIn("missing 3-4", issues[0]["detail"])

    def test_possdup_not_flagged(self):
        dup = parse(build_message([(35, "0"), (49, S), (56, B), (34, 2), (43, "Y"), (52, "x")]))
        self.assertEqual(analyze_session([msg("A", S, B, 1), msg("0", S, B, 2), msg("0", S, B, 3), dup]), [])

    def test_sequence_reset_moves_expectation(self):
        ms = [msg("A", S, B, 1), msg("4", S, B, 2, [(36, 10), (123, "Y")]), msg("0", S, B, 10)]
        self.assertEqual(analyze_session(ms), [])

    def test_unanswered_test_request(self):
        ms = [msg("1", S, B, 1, [(112, "T1")])]
        self.assertEqual(analyze_session(ms)[0]["kind"], "TESTREQ_UNANSWERED")

    def test_answered_test_request(self):
        ms = [msg("1", S, B, 1, [(112, "T1")]), msg("0", B, S, 1, [(112, "T1")])]
        self.assertEqual(analyze_session(ms), [])


def er(seq, cid, status, et, **kw):
    body = [(37, "X"), (17, "E%d" % seq), (11, cid), (39, status), (150, et), (55, "IBM")]
    body += [(k, v) for k, v in kw.items() if False]
    return msg("8", B, S, seq, body + kw.get("extra", []))


class OrderTests(unittest.TestCase):
    def new(self, cid="O1", qty=100):
        return msg("D", S, B, 2, [(11, cid), (55, "IBM"), (54, 1), (38, qty), (40, 2), (44, 10)])

    def test_filled_clean(self):
        o = reconstruct([self.new(), er(2, "O1", 0, 0, extra=[(14, 0)]),
                         er(3, "O1", 2, 2, extra=[(32, 100), (14, 100)])])[0]
        self.assertEqual(o["anomalies"], [])

    def test_no_ack(self):
        self.assertEqual(reconstruct([self.new()])[0]["anomalies"], ["NO_ACK"])

    def test_reject(self):
        o = reconstruct([self.new(), er(2, "O1", 8, 8, extra=[(14, 0), (58, "bad")])])[0]
        self.assertIn("REJECTED", o["anomalies"])
        self.assertEqual(o["text"], "bad")

    def test_overfill_and_partial(self):
        o = reconstruct([self.new(), er(2, "O1", 2, 2, extra=[(32, 150), (14, 150)])])[0]
        self.assertIn("OVERFILL", o["anomalies"])
        p = reconstruct([self.new(), er(2, "O1", 1, 1, extra=[(32, 40), (14, 40)])])[0]
        self.assertIn("OPEN_PARTIAL", p["anomalies"])

    def test_qty_mismatch(self):
        o = reconstruct([self.new(), er(2, "O1", 1, 1, extra=[(32, 40), (14, 60)])])[0]
        self.assertIn("QTY_MISMATCH", o["anomalies"])

    def test_duplicate_fill_replay_not_double_counted(self):
        f = er(2, "O1", 1, 1, extra=[(32, 40), (14, 40)])
        o = reconstruct([self.new(), f, f])[0]
        self.assertNotIn("QTY_MISMATCH", o["anomalies"])

    def test_replace_chain(self):
        rep = msg("G", S, B, 3, [(11, "O2"), (41, "O1"), (55, "IBM"), (38, 200)])
        ack = msg("8", B, S, 3, [(37, "X"), (17, "E9"), (11, "O2"), (41, "O1"), (39, 5), (150, 5), (14, 0)])
        orders = reconstruct([self.new(), er(2, "O1", 0, 0, extra=[(14, 0)]), rep, ack])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["qty"], 200)


class EndToEnd(unittest.TestCase):
    def test_injected_faults_found_exactly(self):
        msgs, orders, issues = analyze(sample.generate())
        found = {o["root"]: set(o["anomalies"]) for o in orders if o["anomalies"]}
        self.assertEqual(found["ORD0005"], {"NO_ACK"})
        self.assertEqual(found["ORD0009"], {"REJECTED"})
        self.assertEqual(found["ORD0014"], {"OPEN_PARTIAL"})
        self.assertEqual(found["ORD0020"], {"OVERFILL"})
        self.assertEqual(len([m for m in msgs if not m.valid]), 1)
        kinds = [i["kind"] for i in issues]
        self.assertIn("SEQ_GAP", kinds)
        self.assertIn("TESTREQ_UNANSWERED", kinds)

    def test_sql_triage(self):
        msgs, orders, issues = analyze(sample.generate())
        con = db.load(msgs, orders, issues)
        n = con.execute(db.QUERIES["invalid_messages"]).fetchall()
        self.assertEqual(len(n), 1)
        rows = con.execute(db.QUERIES["reject_reasons"]).fetchall()
        self.assertEqual(rows, [("Unknown symbol for venue", 1)])


if __name__ == "__main__":
    unittest.main()
