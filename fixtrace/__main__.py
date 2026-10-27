import argparse
import sys
from .fixparse import parse_log
from .session import analyze_session
from .orders import reconstruct
from . import db, sample


def analyze(lines):
    msgs = list(parse_log(lines))
    return msgs, reconstruct(msgs), analyze_session(msgs)


def main(argv=None):
    p = argparse.ArgumentParser(prog="fixtrace", description="FIX log triage toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("sample", help="write a synthetic FIX log with injected faults")
    g.add_argument("out")
    r = sub.add_parser("report", help="analyze a FIX log and print findings")
    r.add_argument("log")
    r.add_argument("--db", help="also save SQLite database to this path")
    q = sub.add_parser("sql", help="run a SQL query (or a named triage query) against a log")
    q.add_argument("log")
    q.add_argument("query", help="SQL text or one of: " + ", ".join(db.QUERIES))
    a = p.parse_args(argv)

    if a.cmd == "sample":
        with open(a.out, "w") as f:
            f.write("\n".join(sample.generate()) + "\n")
        print("wrote", a.out)
        return 0
    with open(a.log) as f:
        msgs, orders, issues = analyze(f.readlines())
    con = db.load(msgs, orders, issues, getattr(a, "db", None) or ":memory:")
    if a.cmd == "sql":
        for row in con.execute(db.QUERIES.get(a.query, a.query)):
            print(" | ".join(str(c) for c in row))
        return 0
    print("messages: %d  invalid: %d  orders: %d" % (len(msgs), sum(not m.valid for m in msgs), len(orders)))
    for title, key in (("INVALID MESSAGES", "invalid_messages"), ("SESSION ISSUES", "session_issues"),
                       ("ORDERS NEEDING ATTENTION", "orders_needing_attention")):
        print("\n== %s ==" % title)
        for row in con.execute(db.QUERIES[key]):
            print(" | ".join(str(c) for c in row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
