"""Order lifecycle reconstruction from NewOrderSingle / ExecutionReport / cancel / replace."""
from .fixparse import ORD_STATUS

FINAL = {"2", "4", "8"}


def reconstruct(messages):
    orders, alias = {}, {}          # alias: any ClOrdID -> root ClOrdID
    for m in messages:
        if not m.valid:
            continue
        mt = m.mtype
        if mt == "D":
            cid = m.get(11)
            orders[cid] = dict(root=cid, client=m.get(49), symbol=m.get(55), side=m.get(54),
                               qty=m.get_float(38), price=m.get_float(44), status=None,
                               cum_qty=0.0, fill_sum=0.0, events=["NewOrderSingle"],
                               text="", cancel_rejected=False, line_no=m.line_no, acked=False,
                               fill_ids=set())
            alias[cid] = cid
        elif mt in ("F", "G"):
            root = alias.get(m.get(41))
            if root:
                alias[m.get(11)] = root
                orders[root]["events"].append(m.name)
                if mt == "G" and m.get_float(38):
                    orders[root]["qty"] = m.get_float(38)
        elif mt == "8":
            root = alias.get(m.get(11)) or alias.get(m.get(41))
            if not root:
                continue
            o = orders[root]
            o["acked"] = True
            status = m.get(39)
            o["status"] = status
            o["text"] = m.get(58, o["text"])
            o["events"].append("ExecutionReport:" + ORD_STATUS.get(status, str(status)))
            if m.get(150) in ("F", "1", "2"):          # trade / partial / fill
                exec_id = m.get(17)
                if exec_id not in o["fill_ids"]:       # ignore PossDup replays of the same fill
                    o["fill_ids"].add(exec_id)
                    o["fill_sum"] += m.get_float(32, 0.0)
            if m.get_float(14) is not None:
                o["cum_qty"] = m.get_float(14)
            if status == "5":
                alias[m.get(11)] = root
        elif mt == "9":
            root = alias.get(m.get(41)) or alias.get(m.get(11))
            if root:
                orders[root]["cancel_rejected"] = True
                orders[root]["events"].append("OrderCancelReject")
                orders[root]["text"] = m.get(58, orders[root]["text"])
    for o in orders.values():
        o["anomalies"] = _anomalies(o)
        o["fill_ids"] = len(o["fill_ids"])
    return list(orders.values())


def _anomalies(o):
    a = []
    if not o["acked"]:
        a.append("NO_ACK")
    if o["status"] == "8":
        a.append("REJECTED")
    if o["qty"] is not None and o["cum_qty"] > o["qty"]:
        a.append("OVERFILL")
    if o["acked"] and abs(o["fill_sum"] - o["cum_qty"]) > 1e-9:
        a.append("QTY_MISMATCH")
    if o["status"] == "1":
        a.append("OPEN_PARTIAL")
    if o["cancel_rejected"]:
        a.append("CANCEL_REJECTED")
    return a
