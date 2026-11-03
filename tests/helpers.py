"""Helpers for building raw input data for the engine tests."""
from app import engine


def players(n, nk=None, **over):
    out = []
    for i in range(1, n + 1):
        p = {"id": i, "number": i, "name": f"P{i}", "nickname": "", "ng_paid": True, "nk_bought": None,
             "nk_paid": False, "withdrawn_round": None, "joined_round": 1, "note": ""}
        if nk and i in nk:
            p["nk_bought"] = nk[i]
        out.append(p)
    return out


_pid = [1000]


def rnd(number, pairs, status="closed"):
    """pairs: [(table, a, b, winner)] ; b=None => bye."""
    prs = []
    for t, a, b, w in pairs:
        _pid[0] += 1
        prs.append({"id": _pid[0], "table": t, "a": a, "b": b, "winner": w})
    return {"id": 100 + number, "number": number, "status": status, "mode": "digital",
            "published_at": None, "closed_at": None, "pairings": prs}


def raw(pls, rounds=(), status="running", placements=None, **t):
    tt = {"name": "T", "ng_amount": 20, "nk_amount": 10, "prize_ranks": 3, "tables_available": 0,
          "prizes": [], "status": status}
    tt.update(t)
    return {"tournament": tt, "players": pls, "rounds": list(rounds), "placements": placements or {}}


def compute(*a, **k):
    return engine.compute(raw(*a, **k))


def P(d, pid):
    return next(p for p in d["players"] if p["id"] == pid)
