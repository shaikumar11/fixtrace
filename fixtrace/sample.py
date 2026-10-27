"""Generate a synthetic FIX log with known injected faults."""
import random
from .fixparse import build_message

CLIENT, BROKER = "BUYSIDE1", "BROKER1"
SYMS = [("AAPL", 190.5), ("MSFT", 410.2), ("IBM", 172.8), ("JPM", 195.4)]


def _hdr(mt, snd, tgt, seq, t):
    return [(35, mt), (49, snd), (56, tgt), (34, seq), (52, "20261020-14:%02d:%02d.000" % (t // 60 % 60, t % 60))]


def generate(n_orders=30, seed=7):
    rnd = random.Random(seed)
    out, seq = [], {CLIENT: 1, BROKER: 1}
    t = [0]

    def send(snd, tgt, mt, body, corrupt=None, skip=0):
        seq[snd] += skip
        t[0] += rnd.randint(1, 3)
        raw = build_message(_hdr(mt, snd, tgt, seq[snd], t[0]) + body)
        seq[snd] += 1
        if corrupt == "checksum":
            raw = raw[:-4] + "%03d\x01" % ((int(raw[-4:-1]) + 7) % 256)
        out.append(raw.replace("\x01", "|"))

    send(CLIENT, BROKER, "A", [(98, 0), (108, 30)])
    send(BROKER, CLIENT, "A", [(98, 0), (108, 30)])
    for i in range(1, n_orders + 1):
        sym, px = rnd.choice(SYMS)
        qty = rnd.choice([100, 200, 500, 1000])
        cid = "ORD%04d" % i
        new = [(11, cid), (55, sym), (54, rnd.choice([1, 2])), (38, qty), (40, 2), (44, px)]
        send(CLIENT, BROKER, "D", new, skip=1 if i == 12 else 0)           # fault: client seq gap
        if i == 5:
            continue                                                      # fault: no ack
        if i == 9:                                                        # fault: reject
            send(BROKER, CLIENT, "8", [(37, "X%d" % i), (17, "E%da" % i), (11, cid), (39, 8), (150, 8), (55, sym),
                                        (14, 0), (151, 0), (103, 3), (58, "Unknown symbol for venue")])
            continue
        send(BROKER, CLIENT, "8", [(37, "X%d" % i), (17, "E%da" % i), (11, cid), (39, 0), (150, 0), (55, sym),
                                    (14, 0), (151, qty)])
        if i == 14:
            half = qty // 2                                               # fault: stuck partial
            send(BROKER, CLIENT, "8", [(37, "X%d" % i), (17, "E%db" % i), (11, cid), (39, 1), (150, 1), (55, sym),
                                        (32, half), (31, px), (14, half), (151, qty - half)])
            continue
        qty_fill = qty + 100 if i == 20 else qty                           # fault: overfill
        send(BROKER, CLIENT, "8", [(37, "X%d" % i), (17, "E%db" % i), (11, cid), (39, 2), (150, 2), (55, sym),
                                    (32, qty_fill), (31, px), (14, qty_fill), (151, 0)],
             corrupt="checksum" if i == 25 else None)                      # fault: bad checksum on a fill
    send(CLIENT, BROKER, "1", [(112, "PING1")])                           # fault: unanswered TestRequest
    return out
