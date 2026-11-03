"""Helpers for the demo and simulation commands: play tournaments through the service layer."""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .service import ApiError, Service

DEMO_NAMES = [
    "Sepp Hinterhuber", "Resi Moosbauer", "Girgl Aschenbrenner", "Vroni Steinleitner", "Done Kaltenegger",
    "Bertl Hofreiter", "Zenzi Wimmer", "Lenz Gruber", "Moidl Pointner", "Xaver Obermaier", "Kathi Zwicknagl",
    "Hias Daxenberger", "Burgl Stiegler", "Wast Leitgeb", "Gretl Anzinger", "Done Mittermair", "Sixtus Kranzl",
    "Afra Lechner", "Done Brunnhuber", "Mare Schwaiger", "Korbinian Eder", "Walli Huber", "Natzi Reiter",
    "Poldi Aigner",
]
NICKS = {"Sepp Hinterhuber": "Hinterer", "Bertl Hofreiter": "Hofi", "Lenz Gruber": "Grubi"}


def derived(svc: Service) -> Dict[str, Any]:
    return svc.derive(svc.require_tid())


def decide_nk(svc: Service, rng: random.Random, p_yes: float = 0.7) -> None:
    for pend in list(derived(svc)["nk_pending"]):
        dec = rng.choice(["yes_paid", "yes_later"]) if rng.random() < p_yes else "no"
        svc.set_nk(pend["id"], dec)


def play_round(svc: Service, rng: random.Random, manual: bool = False, p_yes: float = 0.7,
               finish_results: bool = True, results_fraction: float = 1.0) -> Dict[str, Any]:
    d = derived(svc)
    if manual:
        ids = list(d["draw_ids"])
        tickets = [t for t in range(1, len(ids) // 2 + 1) for _ in (0, 1)] + (["F"] if len(ids) % 2 else [])
        rng.shuffle(tickets)
        svc.draw_manual({str(i): t for i, t in zip(ids, tickets)})
    else:
        svc.draw_digital()
    svc.publish()
    d = derived(svc)
    cur = d["rounds"][-1]
    prs = [p for p in cur["pairings"] if not p["bye"]]
    n_set = len(prs) if finish_results else int(len(prs) * results_fraction)
    for pr in prs[:n_set]:
        svc.set_result(pr["id"], rng.choice([pr["a"], pr["b"]]))
    if finish_results:
        svc.close_round(cur["number"])
        decide_nk(svc, rng, p_yes)
    return derived(svc)


def play_tournament(svc: Service, rng: random.Random, max_rounds: int = 80, p_yes: float = 0.7,
                    manual_prob: float = 0.2) -> Dict[str, Any]:
    d = derived(svc)
    for _ in range(max_rounds):
        if d["finished"]:
            break
        d = play_round(svc, rng, manual=rng.random() < manual_prob, p_yes=p_yes)
    return d


def fill_players(svc: Service, n: int, names: Optional[List[str]] = None) -> None:
    for i in range(n):
        nm = names[i] if names and i < len(names) else f"Spieler {i + 1:02d}"
        svc.add_player({"name": nm, "nickname": NICKS.get(nm, ""), "ng_paid": True, "confirm_late": True})


def check_invariants(svc: Service, expect_finished: bool = True) -> List[str]:
    """Check tournament invariants; return a list of error messages."""
    errs: List[str] = []
    d = derived(svc)
    players = {p["id"]: p for p in d["players"]}
    if d["warnings"]:
        errs.append("Warnungen: " + "; ".join(w["text"] for w in d["warnings"][:3]))
    for r in d["rounds"]:
        ids, tables, byes = [], [], 0
        for pr in r["pairings"]:
            if pr["bye"]:
                byes += 1
                ids.append(pr["a"])
            else:
                ids += [pr["a"], pr["b"]]
                tables.append(pr["table"])
        if len(ids) != len(set(ids)):
            errs.append(f"Runde {r['number']}: Spieler doppelt")
        if byes != len(ids) % 2:
            errs.append(f"Runde {r['number']}: Freilos-Anzahl falsch ({byes} bei {len(ids)} Spielern)")
        if sorted(tables) != list(range(1, len(ids) // 2 + 1)):
            errs.append(f"Runde {r['number']}: Tischnummern falsch")
        for pid in ids:
            p = players[pid]
            if p["elim_round"] is not None and p["elim_round"] < r["number"]:
                errs.append(f"Runde {r['number']}: ausgeschiedener Spieler {p['name']} gelost")
    for p in players.values():
        want = 3 if p["nk_bought"] else 1
        if p["status"] == "out" and not p["withdrawn"] and p["bummerl"] != want:
            errs.append(f"{p['name']}: ausgeschieden mit {p['bummerl']} Bummerl (erwartet {want})")
        if p["status"] != "out" and p["bummerl"] >= want and not p["nk_pending"]:
            errs.append(f"{p['name']}: sollte ausgeschieden sein")
    if expect_finished:
        if not d["finished"] or d["winner"] is None:
            errs.append("Turnier nicht beendet / kein Sieger")
        alive = [p for p in players.values() if p["status"] != "out"]
        if len(alive) != 1:
            errs.append(f"{len(alive)} Spieler uebrig")
    seen, cursor = [], 1
    for g in d["ranking"]["groups"]:
        if g["place_from"] != cursor:
            errs.append("Platzbereiche nicht lueckenlos")
        cursor = g["place_to"] + 1
        seen += g["players"]
    if sorted(seen) != sorted(players):
        errs.append("Rangliste enthaelt nicht alle Spieler genau einmal")
    c = d["cash"]
    if abs(c["total"] - (c["ng_sum"] + c["nk_sum"])) > 0.001:
        errs.append("Kassa-Summe stimmt nicht")
    return errs


def make_demo(svc: Service, seed: int = 7) -> int:
    """Demo tournament: 24 players, 3 rounds played, round 4 in progress."""
    rng = random.Random(seed)
    old = [t for t in svc.tournaments_list() if t["players"] == 0 and t["status"] == "signup"]
    tid = svc.create_tournament({"name": "Demo-Preisschnapsen", "date": "2026-11-14", "place": "Gasthaus Zur Linde",
                                 "ng_amount": 20, "nk_amount": 10, "prize_ranks": 11, "tables_available": 14})
    for t in old:
        try:
            svc.delete_tournament(t["id"])
        except ApiError:
            pass
    svc.update_tournament({"prizes": ["Schinken", "Schnapskorb", "Bierträger", "Speckbrett", "Kasbrettl",
                                      "Wurstpaket", "Brotzeit-Gutschein", "Schnaps", "Bier-Gutschein",
                                      "Kaffee-Gutschein", "Trostpreis"]})
    for nm in DEMO_NAMES:
        svc.add_player({"name": nm, "nickname": NICKS.get(nm, ""), "ng_paid": rng.random() < 0.9})
    svc.start_tournament()
    for _ in range(3):
        play_round(svc, rng, manual=False, p_yes=0.7)
    play_round(svc, rng, finish_results=False, results_fraction=0.55)
    return tid
