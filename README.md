# fixtrace

FIX protocol log triage toolkit for client support work. Python standard library only.

Given a FIX 4.x log, it answers the first questions a support analyst asks:
is the message valid, is the session healthy, and which orders need attention.

- Parses FIX messages and validates BodyLength and CheckSum
- Session checks: sequence gaps, sequence too low, ResendRequest, session Reject, unanswered TestRequest, PossDup and gap-fill handling
- Order lifecycle: New, Replace and Cancel chains, fills, rejects, with flags NO_ACK, REJECTED, OVERFILL, QTY_MISMATCH, OPEN_PARTIAL, CANCEL_REJECTED
- Loads everything into SQLite with ready triage queries

## Run
    python -m fixtrace sample sample.log
    python -m fixtrace report sample.log --db triage.db
    python -m fixtrace sql sample.log reject_reasons
    python -m fixtrace sql sample.log "SELECT * FROM orders WHERE symbol='IBM'"
    python -m unittest discover -s tests -v

## Triage queries
orders_needing_attention, reject_reasons, invalid_messages, message_mix, fill_rate_by_symbol, session_issues.

Sample data is synthetic with injected faults. Not connected to any real venue.
