"""Draw logic modelled on a pot of paper tickets."""
from __future__ import annotations

import secrets
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

Ticket = Union[int, str]
_RNG = secrets.SystemRandom()


def make_tickets(n_players: int) -> List[Ticket]:
    """Return [1,1,2,2,...,N,N] plus 'F' for an odd number of players."""
    tickets: List[Ticket] = []
    for t in range(1, n_players // 2 + 1):
        tickets += [t, t]
    if n_players % 2:
        tickets.append("F")
    return tickets


def pairs_of(assign: Dict[int, Ticket]) -> Tuple[Set[frozenset], Optional[int]]:
    by: Dict[Ticket, List[int]] = {}
    for pid, tk in assign.items():
        by.setdefault(tk, []).append(pid)
    pairs = {frozenset(v) for k, v in by.items() if k != "F" and len(v) == 2}
    bye = by.get("F", [None])[0]
    return pairs, bye


def violations(assign: Dict[int, Ticket], prev_pairs: Iterable[frozenset] = (), prev_bye: Iterable[int] = (),
               avoid_repeat: bool = True, avoid_bye_repeat: bool = True) -> int:
    pairs, bye = pairs_of(assign)
    v = 0
    if avoid_repeat:
        v += len(pairs & set(prev_pairs))
    if avoid_bye_repeat and bye is not None and bye in set(prev_bye):
        v += 1
    return v


def draw(ids: Sequence[int], prev_pairs: Iterable[frozenset] = (), prev_bye: Iterable[int] = (),
         avoid_repeat: bool = True, avoid_bye_repeat: bool = True, tries: int = 300,
         rng: Optional[Any] = None) -> Tuple[Dict[int, Ticket], int]:
    """Shuffle the tickets repeatedly and keep the variant with the fewest soft-rule violations."""
    rng = rng or _RNG
    prev_pairs = set(prev_pairs)
    prev_bye = set(prev_bye)
    best: Optional[Dict[int, Ticket]] = None
    best_v = 10 ** 9
    for _ in range(max(1, tries)):
        tickets = make_tickets(len(ids))
        rng.shuffle(tickets)
        assign = dict(zip(ids, tickets))
        v = violations(assign, prev_pairs, prev_bye, avoid_repeat, avoid_bye_repeat)
        if v < best_v:
            best, best_v = assign, v
            if v == 0:
                break
    assert best is not None
    return best, best_v


def validate_manual(assign: Dict[int, Any], ids: Sequence[int]) -> List[str]:
    """Validate a manual assignment; return error messages (empty list = valid)."""
    errors: List[str] = []
    idset = set(ids)
    for pid in assign:
        if pid not in idset:
            errors.append(f"Spieler {pid} ist nicht aktiv.")
    missing = [p for p in ids if p not in assign or assign[p] in (None, "")]
    if missing:
        errors.append(f"{len(missing)} Spieler ohne Zettel.")
    n = len(ids)
    tables = n // 2
    counts: Dict[Any, int] = {}
    for pid, tk in assign.items():
        if tk in (None, ""):
            continue
        if tk != "F" and not (isinstance(tk, int) and 1 <= tk <= tables):
            errors.append(f"Ungültiger Zettel: {tk}")
            continue
        counts[tk] = counts.get(tk, 0) + 1
    for t in range(1, tables + 1):
        c = counts.get(t, 0)
        if c > 2:
            errors.append(f"Zettel {t} wurde {c}× vergeben (erlaubt: 2×).")
        elif c != 2 and not missing:
            errors.append(f"Zettel {t} wurde {c}× vergeben (erwartet: 2×).")
    f = counts.get("F", 0)
    if n % 2 == 1 and f > 1:
        errors.append("Der Freilos-Zettel F darf nur 1× vergeben werden.")
    if n % 2 == 1 and f == 0 and not missing:
        errors.append("Der Freilos-Zettel F fehlt.")
    if n % 2 == 0 and f > 0:
        errors.append("Bei gerader Spielerzahl gibt es kein Freilos (F).")
    return errors


def to_pairings(assign: Dict[int, Ticket], order: Sequence[int]) -> List[Dict[str, Any]]:
    """Convert an assignment into pairings (tables ascending, bye last)."""
    pos = {pid: i for i, pid in enumerate(order)}
    by: Dict[Ticket, List[int]] = {}
    for pid, tk in assign.items():
        by.setdefault(tk, []).append(pid)
    out: List[Dict[str, Any]] = []
    for tk in sorted((k for k in by if k != "F")):
        a, b = sorted(by[tk], key=lambda p: pos.get(p, 0))
        out.append({"table": tk, "a": a, "b": b})
    for pid in by.get("F", []):
        out.append({"table": None, "a": pid, "b": None})
    return out
