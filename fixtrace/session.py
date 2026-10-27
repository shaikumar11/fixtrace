"""Session-level analysis: sequence gaps, resends, unanswered test requests."""


def analyze_session(messages):
    issues = []
    expected = {}           # (sender, target) -> next expected MsgSeqNum
    pending_tests = {}      # (sender, target, TestReqID) -> line_no
    for m in messages:
        if not m.valid or m.get(34) is None:
            continue
        key = (m.get(49), m.get(56))
        seq = m.get_int(34)
        poss_dup = m.get(43) == "Y"
        mt = m.mtype
        if mt == "A" and seq == 1:
            expected[key] = 1
        exp = expected.get(key)
        if exp is not None and not poss_dup:
            if seq > exp:
                issues.append(dict(kind="SEQ_GAP", line_no=m.line_no, sender=key[0], target=key[1],
                                   detail="expected %d, received %d, missing %d-%d" % (exp, seq, exp, seq - 1)))
            elif seq < exp:
                issues.append(dict(kind="SEQ_TOO_LOW", line_no=m.line_no, sender=key[0], target=key[1],
                                   detail="expected %d, received %d without PossDupFlag" % (exp, seq)))
        if mt == "4":                       # SequenceReset
            new_seq = m.get_int(36)
            if new_seq:
                expected[key] = new_seq
                continue
        if not poss_dup or exp is None:
            expected[key] = max(seq + 1, expected.get(key, 0)) if poss_dup else seq + 1
        if mt == "2":
            issues.append(dict(kind="RESEND_REQUEST", line_no=m.line_no, sender=key[0], target=key[1],
                               detail="requested %s-%s" % (m.get(7), m.get(16))))
        elif mt == "3":
            issues.append(dict(kind="SESSION_REJECT", line_no=m.line_no, sender=key[0], target=key[1],
                               detail="ref seq %s tag %s: %s" % (m.get(45), m.get(371), m.get(58, ""))))
        elif mt == "1":
            pending_tests[(key[1], key[0], m.get(112))] = m.line_no   # reply comes from the other side
        elif mt == "0" and m.get(112):
            pending_tests.pop((key[0], key[1], m.get(112)), None)
    for (snd, tgt, rid), line_no in pending_tests.items():
        issues.append(dict(kind="TESTREQ_UNANSWERED", line_no=line_no, sender=tgt, target=snd,
                           detail="TestReqID %s got no Heartbeat reply" % rid))
    return sorted(issues, key=lambda i: i["line_no"])
