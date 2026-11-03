"""Rules engine: a pure function that derives the complete state from raw data.

Input (raw):
  tournament: {name, ng_amount, nk_amount, prize_ranks, tables_available, prizes[], status, ...}
  players:    [{id, number, name, nickname, ng_paid, nk_bought (None/True/False), nk_paid,
                withdrawn_round (None/int), joined_round, note}]
  rounds:     [{id, number, status ('draft'|'published'|'closed'), mode, published_at, closed_at,
                pairings: [{id, table, a, b, winner}]}]      (b None = Freilos)
  placements: {elim_round: [player ids]}
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ACTIVE_KEY = 9999  # placement-order key for the "still in the game" group
LIFE_CAP = 3

SYM = {"win": "+", "loss1": "–", "loss2": "⊖", "bye": "F", "open": "…"}


def fmt_range(a: int, b: int) -> str:
    return f"{a}." if a == b else f"{a}.–{b}."


def pl_label(a: int, b: int) -> str:
    if a == b:
        return f"Pl. {a}"
    return f"Pl. {a}/{b}" if b == a + 1 else f"Pl. {a}–{b}"


def ticket_text(round_no: int, n: int) -> str:
    tables = n // 2
    bye = n % 2 == 1
    if tables == 0:
        return f"Runde {round_no} – {n} Spieler"
    rng = "1" if tables == 1 else f"1–{tables}"
    txt = f"Runde {round_no} – {n} Spieler: Zettel {rng} je doppelt"
    if bye:
        txt += " + 1× F"
    return f"{txt} = {n} Zettel"


def compute(raw: Dict[str, Any]) -> Dict[str, Any]:
    t = raw["tournament"]
    status = t.get("status", "signup")
    prize_ranks = int(t.get("prize_ranks") or 0)
    prizes = list(t.get("prizes") or [])
    players = sorted(raw["players"], key=lambda p: (p["number"], p["id"]))
    rounds = sorted(raw["rounds"], key=lambda r: r["number"])
    placements = {int(k): list(v) for k, v in (raw.get("placements") or {}).items()}
    counted = [r for r in rounds if r["status"] in ("published", "closed")]
    draft = next((r for r in rounds if r["status"] == "draft"), None)

    P: Dict[int, Dict[str, Any]] = {}
    for p in players:
        P[p["id"]] = {
            "id": p["id"], "number": p["number"], "name": p["name"], "nickname": p.get("nickname") or "",
            "label": p.get("nickname") or p["name"],
            "ng_paid": bool(p.get("ng_paid")), "nk_bought": p.get("nk_bought"), "nk_paid": bool(p.get("nk_paid")),
            "note": p.get("note") or "", "joined_round": p.get("joined_round") or 1,
            "withdrawn_round": p.get("withdrawn_round"),
            "bummerl": 0, "cells": {}, "loss_rounds": [],
        }
        if P[p["id"]]["nk_bought"] is not None:
            P[p["id"]]["nk_bought"] = bool(P[p["id"]]["nk_bought"])

    warnings: List[Dict[str, Any]] = []
    notices: List[Dict[str, Any]] = []

    def warn(code: str, text: str, **kw: Any) -> None:
        warnings.append({"code": code, "text": text, **kw})

    round_out: List[Dict[str, Any]] = []
    round_members: Dict[int, set] = {}

    def pairing_out(pr: Dict[str, Any]) -> Dict[str, Any]:
        a, b, w = pr["a"], pr.get("b"), pr.get("winner")
        loser = None
        if b is not None and w is not None:
            loser = b if w == a else a
        return {"id": pr["id"], "table": pr.get("table"), "a": a, "b": b, "winner": w, "loser": loser,
                "bye": b is None}

    for r in rounds:
        pairs = sorted(r["pairings"], key=lambda x: (x.get("table") is None, x.get("table") or 0, x["id"]))
        if r["status"] == "draft":
            continue
        seen: set = set()
        total = done = 0
        open_tables: List[int] = []
        bye = None
        for pr in pairs:
            a, b, w = pr["a"], pr.get("b"), pr.get("winner")
            if a not in P:
                continue
            if b is None:
                bye = a
                if a in seen:
                    warn("double", f"{P[a]['name']} steht in Runde {r['number']} mehrfach.", round=r["number"])
                seen.add(a)
                P[a]["cells"][r["number"]] = {"round": r["number"], "table": None, "kind": "bye", "text": "F",
                                              "pairing_id": pr["id"], "opponent": None, "loss_no": 0}
                continue
            total += 1
            if w is None:
                open_tables.append(pr.get("table"))
            else:
                done += 1
            for x, o in ((a, b), (b, a)):
                if x not in P:
                    continue
                if x in seen:
                    warn("double", f"{P[x]['name']} steht in Runde {r['number']} mehrfach.", round=r["number"])
                seen.add(x)
                loss_no = 0
                if w is None:
                    kind = "open"
                elif w == x:
                    kind = "win"
                else:
                    P[x]["bummerl"] += 1
                    P[x]["loss_rounds"].append(r["number"])
                    loss_no = P[x]["bummerl"]
                    kind = "loss1" if loss_no == 1 else "loss2"
                P[x]["cells"][r["number"]] = {
                    "round": r["number"], "table": pr.get("table"), "kind": kind, "loss_no": loss_no,
                    "text": f"{pr.get('table')}{SYM[kind]}", "pairing_id": pr["id"], "opponent": o}
        round_members[r["number"]] = seen
        if r["status"] == "closed" and open_tables:
            warn("closed_open", f"Runde {r['number']} ist abgeschlossen, aber Tisch "
                 f"{', '.join(str(x) for x in open_tables)} hat kein Ergebnis.", round=r["number"])
        round_out.append({
            "id": r["id"], "number": r["number"], "status": r["status"], "mode": r.get("mode"),
            "published_at": r.get("published_at"), "closed_at": r.get("closed_at"),
            "total": total, "done": done, "open_tables": open_tables, "bye": bye,
            "pairings": [pairing_out(x) for x in pairs],
        })

    # ---- elimination, status, hearts ----
    for p in P.values():
        b = p["bummerl"]
        nk = p["nk_bought"]
        cap = 1 if nk is False else LIFE_CAP
        elim = None
        if b >= cap:
            elim = p["loss_rounds"][cap - 1]
        by_withdraw = False
        w = p["withdrawn_round"]
        if w is not None and (elim is None or w <= elim):
            if elim is None or w < elim:
                by_withdraw = True
            elim = w
        p["elim_round"] = elim
        p["withdrawn"] = w is not None
        p["by_withdraw"] = by_withdraw
        p["nk_pending"] = elim is None and b >= 1 and nk is None
        p["status"] = "out" if elim is not None else ("nk_open" if p["nk_pending"] else "active")
        if nk:
            hearts = ["full" if b < i + 1 else "lost" for i in range(3)]
            p["lives"] = max(0, 3 - b)
        else:
            hearts = ["full" if b < 1 else "lost", "none", "none"]
            p["lives"] = 0 if b >= 1 else 1
        p["hearts"] = hearts
        p["first_loss_round"] = p["loss_rounds"][0] if p["loss_rounds"] else None
        if nk and b == 0:
            notices.append({"code": "nk_no_loss", "text": f"{p['name']} hat nachgekauft, aber kein Bummerl.", "player": p["id"]})
        if nk is None and b >= 2:
            warn("nk_missing", f"{p['name']} hat {b} Bummerl, aber keine Nachkauf-Entscheidung.", player=p["id"])
        if nk is False and b >= 2:
            warn("after_out", f"{p['name']} hat ohne Nachkauf mehr als ein Bummerl.", player=p["id"])
        if elim is not None:
            late = sorted(r for r in p["cells"] if r > elim)
            if late:
                warn("after_out", f"{p['name']} ist seit Runde {elim} ausgeschieden, hat aber noch Spiele in "
                     f"Runde {', '.join(str(x) for x in late)}.", player=p["id"], round=late[0])

    for rn, members in round_members.items():
        for p in P.values():
            if p["joined_round"] <= rn and (p["elim_round"] is None or p["elim_round"] >= rn) \
                    and p["id"] not in members:
                warn("missing", f"{p['name']} wäre in Runde {rn} noch im Spiel, ist aber nicht ausgelost.",
                     player=p["id"], round=rn)

    # ---- progress, phase ----
    cur = round_out[-1] if round_out else None
    next_round = (cur["number"] + 1) if cur else 1
    alive = [p for p in P.values() if p["elim_round"] is None]
    pending = [p for p in P.values() if p["nk_pending"]]
    last_closed = bool(cur and cur["status"] == "closed")
    finished_by_rules = bool(cur and last_closed and not pending and len(alive) <= 1)
    finished = status == "finished" or (status == "running" and finished_by_rules)
    winner = alive[0]["id"] if finished and len(alive) == 1 else None

    draw_ids = [p["id"] for p in alive if p["status"] == "active" and p["joined_round"] <= next_round]
    can_draw, reason = True, ""
    if status == "signup":
        can_draw, reason = False, "Das Turnier ist noch nicht gestartet."
    elif finished:
        can_draw, reason = False, "Das Turnier ist beendet."
    elif draft:
        can_draw, reason = False, "Es gibt bereits einen Entwurf."
    elif cur and cur["status"] != "closed":
        can_draw, reason = False, f"Runde {cur['number']} ist noch nicht abgeschlossen."
    elif pending:
        can_draw, reason = False, "Nachkauf-Entscheidung offen: " + ", ".join(p["name"] for p in pending)
    elif len(draw_ids) < 2:
        can_draw, reason = False, "Es sind weniger als 2 Spieler im Spiel."

    if status == "signup":
        phase = "signup"
    elif finished:
        phase = "finished"
    elif draft:
        phase = "drawing"
    elif not cur:
        phase = "ready"
    elif cur["status"] == "published":
        phase = "running"
    else:
        phase = "closed"

    draw_info = None
    if status == "running" and len(draw_ids) >= 2 and not finished:
        n = len(draw_ids)
        draw_info = {"round": next_round, "n": n, "tables": n // 2, "bye": n % 2 == 1,
                     "text": ticket_text(next_round, n)}

    tables_avail = int(t.get("tables_available") or 0)
    shown = draft if draft else (cur and next((r for r in rounds if r["number"] == cur["number"]), None))
    if shown and tables_avail:
        need = len([x for x in shown["pairings"] if x.get("b") is not None])
        if need > tables_avail:
            notices.append({"code": "tables", "text": f"Für Runde {shown['number']} werden {need} Tische gebraucht, "
                            f"verfügbar sind {tables_avail}."})
    if draw_info and tables_avail and draw_info["tables"] > tables_avail and not draft:
        notices.append({"code": "tables", "text": f"Die nächste Runde braucht {draw_info['tables']} Tische, "
                        f"verfügbar sind {tables_avail}."})

    draft_out = None
    if draft:
        dp = sorted(draft["pairings"], key=lambda x: (x.get("table") is None, x.get("table") or 0, x["id"]))
        draft_out = {"id": draft["id"], "number": draft["number"], "mode": draft.get("mode"),
                     "pairings": [pairing_out(x) for x in dp]}

    # ---- ranking ----
    groups_by_key: Dict[int, List[int]] = {}
    for p in P.values():
        key = ACTIVE_KEY if p["elim_round"] is None else p["elim_round"]
        groups_by_key.setdefault(key, []).append(p["id"])
    closed_nums = {r["number"] for r in round_out if r["status"] == "closed"}
    groups: List[Dict[str, Any]] = []
    entries: List[Dict[str, Any]] = []
    cursor = 1
    for key in sorted(groups_by_key, reverse=True):
        ids = sorted(groups_by_key[key], key=lambda i: (P[i]["number"], i))
        n = len(ids)
        frm, to = cursor, cursor + n - 1
        saved = placements.get(key)
        decided = n == 1
        if saved and set(saved) == set(ids) and len(saved) == n:
            ids = list(saved)
            decided = True
        is_active = key == ACTIVE_KEY
        relevant = frm <= prize_ranks
        needs = (n > 1 and not decided and relevant
                 and ((is_active and finished) or (not is_active and key in closed_nums)))
        groups.append({"key": key, "elim_round": None if is_active else key, "active": is_active,
                       "place_from": frm, "place_to": to, "label": fmt_range(frm, to),
                       "pl_label": pl_label(frm, to), "players": ids, "decided": decided,
                       "needs_playoff": needs, "in_prizes": relevant})
        if decided and n > 1:
            for i, pid in enumerate(ids):
                P[pid]["place_from"] = P[pid]["place_to"] = frm + i
                entries.append({"place_from": frm + i, "place_to": frm + i, "label": fmt_range(frm + i, frm + i),
                                "players": [pid], "active": is_active, "needs_playoff": False})
        else:
            for pid in ids:
                P[pid]["place_from"], P[pid]["place_to"] = frm, to
            entries.append({"place_from": frm, "place_to": to, "label": fmt_range(frm, to), "players": ids,
                            "active": is_active and not (finished and n == 1), "needs_playoff": needs})
        cursor += n
    for e in entries:
        pr = prizes[e["place_from"] - 1] if 0 < e["place_from"] <= len(prizes) else ""
        e["prize"] = pr if (e["place_from"] <= prize_ranks or pr) else ""
        e["in_prizes"] = e["place_from"] <= prize_ranks
    open_playoffs = [g for g in groups if g["needs_playoff"]]

    # ---- cash ----
    ng_amt = float(t.get("ng_amount") or 0)
    nk_amt = float(t.get("nk_amount") or 0)
    plist = list(P.values())
    nk_list = [p for p in plist if p["nk_bought"]]
    ng_paid_n = sum(1 for p in plist if p["ng_paid"])
    nk_paid_n = sum(1 for p in nk_list if p["nk_paid"])
    total = len(plist) * ng_amt + len(nk_list) * nk_amt
    paid = ng_paid_n * ng_amt + nk_paid_n * nk_amt
    cash = {
        "ng_amount": ng_amt, "nk_amount": nk_amt,
        "ng_count": len(plist), "ng_sum": round(len(plist) * ng_amt, 2), "ng_paid_count": ng_paid_n,
        "nk_count": len(nk_list), "nk_sum": round(len(nk_list) * nk_amt, 2), "nk_paid_count": nk_paid_n,
        "total": round(total, 2), "paid": round(paid, 2), "open": round(total - paid, 2),
        "open_ng": [p["id"] for p in plist if not p["ng_paid"]],
        "open_nk": [p["id"] for p in nk_list if not p["nk_paid"]],
    }

    counts = {"total": len(plist), "alive": len(alive), "out": len(plist) - len(alive),
              "nk_open": len(pending)}

    return {
        "phase": phase, "status": status, "finished": finished, "finished_by_rules": finished_by_rules,
        "winner": winner, "players": plist, "rounds": round_out, "current_round": cur["number"] if cur else 0,
        "round_progress": ({k: cur[k] for k in ("number", "status", "total", "done", "open_tables", "bye")}
                           if cur else None),
        "next_round": next_round, "draft": draft_out, "can_draw": can_draw, "can_draw_reason": reason,
        "draw_ids": draw_ids, "draw_info": draw_info,
        "nk_pending": [{"id": p["id"], "label": p["name"], "round": p["first_loss_round"]} for p in pending],
        "ranking": {"groups": groups, "entries": entries, "open_playoffs": [g["key"] for g in open_playoffs]},
        "cash": cash, "counts": counts, "warnings": warnings, "notices": notices,
    }
