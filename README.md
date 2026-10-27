# FixTrace

![CI](https://github.com/shaikumar11/fixtrace/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

A FIX protocol log triage toolkit for client support work. Give it a FIX 4.x log and it answers the three questions a support analyst asks first:

1. Are the messages valid?
2. Is the session healthy?
3. Which orders need attention, and why?

Built with the Python standard library only. No installs required.

## Why this exists

Buy-side clients report problems like "my order never got an acknowledgement" or "I was filled more than I sent". Finding the cause means reading raw FIX logs line by line, which is slow and error prone. FixTrace automates the first pass of that triage and loads the results into SQLite so the rest can be done with SQL.

## Features

**Message validation**
- Parses FIX messages with `|` or SOH delimiters
- Verifies `BodyLength (9)` and `CheckSum (10)`
- Reports malformed fields and missing required tags

**Session checks**
- Sequence gaps and sequence numbers too low
- `PossDupFlag` and `SequenceReset` gap-fill handling
- `ResendRequest` and session `Reject` detection
- `TestRequest` with no matching `Heartbeat`

**Order lifecycle reconstruction**
- Follows New, Cancel and Replace chains by `ClOrdID` and `OrigClOrdID`
- Tracks fills, ignoring duplicate replays of the same `ExecID`
- Flags problem orders:

| Flag | Meaning |
|---|---|
| `NO_ACK` | Order sent, no ExecutionReport received |
| `REJECTED` | Order rejected, reason text captured |
| `OVERFILL` | Cumulative filled quantity exceeds order quantity |
| `QTY_MISMATCH` | Sum of last fills differs from reported `CumQty` |
| `OPEN_PARTIAL` | Order left partially filled |
| `CANCEL_REJECTED` | Cancel request refused |

**SQL triage**
- All results load into SQLite (in memory or a `.db` file)
- Ready-made queries, or run your own

## Quick start

```bash
git clone https://github.com/shaikumar11/fixtrace.git
cd fixtrace

python -m fixtrace sample sample.log      # generate a synthetic log with injected faults
python -m fixtrace report sample.log      # analyze it
```

Example output:

```
messages: 90  invalid: 1  orders: 30

== INVALID MESSAGES ==
74 | ExecutionReport | CheckSum mismatch: declared 091, expected 084

== SESSION ISSUES ==
33 | SEQ_GAP | BUYSIDE1 | BROKER1 | expected 13, received 14, missing 13-13
76 | SEQ_GAP | BROKER1 | BUYSIDE1 | expected 48, received 49, missing 48-48
90 | TESTREQ_UNANSWERED | BUYSIDE1 | BROKER1 | TestReqID PING1 got no Heartbeat reply

== ORDERS NEEDING ATTENTION ==
ORD0005 | BUYSIDE1 | AAPL | 200.0 | 0.0 | None | NO_ACK
ORD0014 | BUYSIDE1 | JPM | 1000.0 | 500.0 | 1 | OPEN_PARTIAL
ORD0020 | BUYSIDE1 | AAPL | 200.0 | 300.0 | 2 | OVERFILL
ORD0009 | BUYSIDE1 | AAPL | 200.0 | 0.0 | 8 | REJECTED
```

Line 76 is a knock-on effect: the corrupted message on line 74 is dropped, so the next broker message looks like a gap. This mirrors what a real engine would see.

## Usage

```bash
# Full report, and save the database for a SQLite viewer
python -m fixtrace report my.log --db triage.db

# Named triage query
python -m fixtrace sql my.log reject_reasons

# Your own SQL
python -m fixtrace sql my.log "SELECT clordid, qty, cum_qty FROM orders WHERE symbol='IBM'"
```

Log lines may carry any prefix (timestamps, direction). FixTrace starts reading each line at `8=FIX`.

### Built-in queries

| Name | Answers |
|---|---|
| `orders_needing_attention` | Which orders have anomalies |
| `reject_reasons` | Reject text counts |
| `invalid_messages` | Messages failing validation, with the reason |
| `message_mix` | Count of each message type |
| `fill_rate_by_symbol` | Ordered vs filled quantity per symbol |
| `session_issues` | Gaps, resends, rejects, unanswered test requests |

### Database tables

- `messages`: one row per message (type, sequence, ClOrdID, symbol, side, quantities, status, validity, errors)
- `orders`: one row per order chain with final status and anomaly flags
- `session_issues`: one row per session finding

Example: find every order that was rejected, with the raw reason.

```sql
SELECT m.line_no, m.clordid, m.symbol, m.text
FROM messages m
WHERE m.ord_status = '8';
```

## Project layout

```
fixtrace/
  fixparse.py   parse, validate, build FIX messages
  session.py    sequence and heartbeat analysis
  orders.py     order lifecycle and anomaly flags
  db.py         SQLite schema and triage queries
  sample.py     synthetic log generator with known faults
  __main__.py   command line interface
tests/
  test_fixtrace.py
.github/workflows/ci.yml
```

## Tests

```bash
python -m unittest discover -s tests -v
```

19 tests cover parsing and checksum validation, sequence gap and gap-fill handling, order lifecycle cases (clean fill, reject, overfill, partial, quantity mismatch, duplicate replay, replace chains), and an end-to-end test that checks the generated log's injected faults are all found. CI runs the suite on every push.

## Limitations

- Targets FIX 4.x style messages and a core set of session and order message types
- Repeating groups are not interpreted
- Sequence tracking assumes one session per log
- Sample data is synthetic and not connected to any real venue

## Roadmap

- More message types (allocations, quotes)
- Repeating group support
- CSV and HTML report export
- Multi-session logs

## License

MIT
