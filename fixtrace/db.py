"""Load parsed messages and analysis into SQLite so issues can be triaged with SQL."""
import sqlite3

SCHEMA = """
CREATE TABLE messages(
  id INTEGER PRIMARY KEY, line_no INTEGER, sender TEXT, target TEXT, msg_type TEXT, msg_name TEXT,
  seq_num INTEGER, sending_time TEXT, clordid TEXT, symbol TEXT, side TEXT, qty REAL, price REAL,
  ord_status TEXT, last_qty REAL, cum_qty REAL, text TEXT, valid INTEGER, errors TEXT);
CREATE TABLE orders(
  clordid TEXT PRIMARY KEY, client TEXT, symbol TEXT, side TEXT, qty REAL, cum_qty REAL,
  status TEXT, acked INTEGER, text TEXT, anomalies TEXT);
CREATE TABLE session_issues(line_no INTEGER, kind TEXT, sender TEXT, target TEXT, detail TEXT);
CREATE INDEX ix_messages_clordid ON messages(clordid);
CREATE INDEX ix_messages_type ON messages(msg_type);
"""


def load(messages, orders, issues, path=":memory:"):
    con = sqlite3.connect(path)
    con.executescript("DROP TABLE IF EXISTS messages; DROP TABLE IF EXISTS orders; "
                      "DROP TABLE IF EXISTS session_issues;" + SCHEMA)
    con.executemany("INSERT INTO messages(line_no,sender,target,msg_type,msg_name,seq_num,sending_time,"
                    "clordid,symbol,side,qty,price,ord_status,last_qty,cum_qty,text,valid,errors) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(m.line_no, m.get(49), m.get(56), m.mtype, m.name, m.get_int(34), m.get(52),
                      m.get(11), m.get(55), m.get(54), m.get_float(38), m.get_float(44), m.get(39),
                      m.get_float(32), m.get_float(14), m.get(58), int(m.valid), "; ".join(m.errors))
                     for m in messages])
    con.executemany("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?)",
                    [(o["root"], o["client"], o["symbol"], o["side"], o["qty"], o["cum_qty"], o["status"],
                      int(o["acked"]), o["text"], ",".join(o["anomalies"])) for o in orders])
    con.executemany("INSERT INTO session_issues VALUES(?,?,?,?,?)",
                    [(i["line_no"], i["kind"], i["sender"], i["target"], i["detail"]) for i in issues])
    con.commit()
    return con


# Triage queries a support analyst would run first.
QUERIES = {
    "orders_needing_attention": "SELECT clordid, client, symbol, qty, cum_qty, status, anomalies FROM orders "
                                "WHERE anomalies <> '' ORDER BY anomalies, clordid",
    "reject_reasons": "SELECT text, COUNT(*) AS n FROM messages WHERE ord_status='8' GROUP BY text ORDER BY n DESC",
    "invalid_messages": "SELECT line_no, msg_name, errors FROM messages WHERE valid=0 ORDER BY line_no",
    "message_mix": "SELECT msg_name, COUNT(*) AS n FROM messages GROUP BY msg_name ORDER BY n DESC",
    "fill_rate_by_symbol": "SELECT symbol, SUM(qty) AS ordered, SUM(cum_qty) AS filled, "
                           "ROUND(100.0*SUM(cum_qty)/SUM(qty),1) AS fill_pct FROM orders GROUP BY symbol "
                           "ORDER BY fill_pct",
    "session_issues": "SELECT line_no, kind, sender, target, detail FROM session_issues ORDER BY line_no",
}
