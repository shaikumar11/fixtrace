"""FIX message parsing, validation and construction (stdlib only)."""
SOH = "\x01"

TAGS = {
    7: "BeginSeqNo", 8: "BeginString", 9: "BodyLength", 10: "CheckSum", 11: "ClOrdID",
    14: "CumQty", 16: "EndSeqNo", 17: "ExecID", 31: "LastPx", 32: "LastQty",
    34: "MsgSeqNum", 35: "MsgType", 36: "NewSeqNo", 37: "OrderID", 38: "OrderQty",
    39: "OrdStatus", 40: "OrdType", 41: "OrigClOrdID", 43: "PossDupFlag", 44: "Price",
    45: "RefSeqNum", 49: "SenderCompID", 52: "SendingTime", 54: "Side", 55: "Symbol",
    56: "TargetCompID", 58: "Text", 98: "EncryptMethod", 103: "OrdRejReason",
    108: "HeartBtInt", 112: "TestReqID", 123: "GapFillFlag", 150: "ExecType",
    151: "LeavesQty", 371: "RefTagID", 373: "SessionRejectReason",
}
MSG_TYPES = {
    "0": "Heartbeat", "1": "TestRequest", "2": "ResendRequest", "3": "Reject",
    "4": "SequenceReset", "5": "Logout", "A": "Logon", "D": "NewOrderSingle",
    "8": "ExecutionReport", "9": "OrderCancelReject", "F": "OrderCancelRequest",
    "G": "OrderCancelReplaceRequest",
}
ORD_STATUS = {"0": "New", "1": "PartiallyFilled", "2": "Filled", "4": "Canceled",
              "5": "Replaced", "8": "Rejected", "A": "PendingNew", "E": "PendingReplace"}


class FixMessage:
    def __init__(self, fields, errors=None, line_no=0, raw=""):
        self.fields = fields          # ordered list of (int tag, str value)
        self.errors = errors or []
        self.line_no = line_no
        self.raw = raw

    def get(self, tag, default=None):
        for t, v in self.fields:
            if t == tag:
                return v
        return default

    def get_int(self, tag, default=None):
        v = self.get(tag)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    def get_float(self, tag, default=None):
        v = self.get(tag)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    @property
    def mtype(self):
        return self.get(35)

    @property
    def name(self):
        return MSG_TYPES.get(self.mtype, "Unknown(%s)" % self.mtype)

    @property
    def valid(self):
        return not self.errors


def checksum(text):
    return "%03d" % (sum(text.encode("latin-1")) % 256)


def build_message(pairs, begin="FIX.4.4"):
    """pairs: iterable of (tag, value) excluding 8, 9, 10. Returns a valid raw message."""
    body = "".join("%d=%s%s" % (t, v, SOH) for t, v in pairs)
    head = "8=%s%s9=%d%s" % (begin, SOH, len(body), SOH)
    msg = head + body
    return msg + "10=%s%s" % (checksum(msg), SOH)


def parse(raw, line_no=0):
    """Parse one FIX message. '|' is accepted as the delimiter (as in log files)."""
    text = raw.strip("\r\n")
    if SOH not in text:
        text = text.replace("|", SOH)
    if not text.endswith(SOH):
        text += SOH
    fields, errors = [], []
    for part in text.split(SOH):
        if not part:
            continue
        tag, eq, val = part.partition("=")
        if not eq or not tag.isdigit():
            errors.append("malformed field %r" % part)
            continue
        fields.append((int(tag), val))
    msg = FixMessage(fields, errors, line_no, text)
    _validate(msg, text)
    return msg


def _validate(msg, text):
    f = msg.fields
    if not f or f[0][0] != 8:
        msg.errors.append("first tag must be 8 BeginString")
    if len(f) < 2 or f[1][0] != 9:
        msg.errors.append("second tag must be 9 BodyLength")
    if not f or f[-1][0] != 10:
        msg.errors.append("last tag must be 10 CheckSum")
    if msg.get(35) is None:
        msg.errors.append("missing tag 35 MsgType")
    cs_pos = text.rfind(SOH + "10=")
    if cs_pos < 0 or len(f) < 2 or f[1][0] != 9:
        return
    body_start = text.find(SOH, text.find("9=")) + 1
    body = text[body_start:cs_pos + 1]
    declared = msg.get_int(9)
    if declared is not None and declared != len(body):
        msg.errors.append("BodyLength mismatch: declared %s, actual %d" % (declared, len(body)))
    expected = checksum(text[:cs_pos + 1])
    got = msg.get(10)
    if got != expected:
        msg.errors.append("CheckSum mismatch: declared %s, expected %s" % (got, expected))


def parse_log(lines):
    """Yield FixMessage for each log line that contains a FIX message."""
    for n, line in enumerate(lines, 1):
        i = line.find("8=FIX")
        if i >= 0:
            yield parse(line[i:], line_no=n)
