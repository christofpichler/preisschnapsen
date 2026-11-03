"""Persistence (SQLite) and business logic. All writes are serialised by a global lock."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from . import draw as drawmod
from . import engine
from .config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS tournaments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, date TEXT DEFAULT '', place TEXT DEFAULT '',
  ng_amount REAL DEFAULT 20, nk_amount REAL DEFAULT 10, prize_ranks INTEGER DEFAULT 3,
  tables_available INTEGER DEFAULT 0, prizes_json TEXT DEFAULT '[]', status TEXT DEFAULT 'signup',
  show_cashbox INTEGER DEFAULT 0, beamer_json TEXT DEFAULT '{}', draw_json TEXT DEFAULT '{}',
  active INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS players(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL, number INTEGER NOT NULL,
  name TEXT NOT NULL, nickname TEXT DEFAULT '', ng_paid INTEGER DEFAULT 0, nk_bought INTEGER,
  nk_paid INTEGER DEFAULT 0, withdrawn_round INTEGER, joined_round INTEGER DEFAULT 1, note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS rounds(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL, number INTEGER NOT NULL,
  status TEXT NOT NULL, mode TEXT DEFAULT 'digital', created_at TEXT, published_at TEXT, closed_at TEXT);
CREATE TABLE IF NOT EXISTS pairings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER NOT NULL, table_no INTEGER,
  player_a INTEGER NOT NULL, player_b INTEGER, winner_id INTEGER, updated_at TEXT);
CREATE TABLE IF NOT EXISTS placement_order(
  tournament_id INTEGER NOT NULL, elim_round INTEGER NOT NULL, order_json TEXT NOT NULL,
  PRIMARY KEY(tournament_id, elim_round));
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER, ts TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS undo(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL, ts TEXT, label TEXT, snapshot_json TEXT);
CREATE INDEX IF NOT EXISTS ix_players_t ON players(tournament_id);
CREATE INDEX IF NOT EXISTS ix_rounds_t ON rounds(tournament_id);
CREATE INDEX IF NOT EXISTS ix_pair_r ON pairings(round_id);
"""

DEFAULT_DASHBOARD = {"rotate_seconds": 20, "pinned": "", "views": ["tables", "players", "matrix", "ranking"],
                  "ceremony_auto": True, "show_ceremony": False, "animation": True}
DEFAULT_DRAW = {"avoid_repeat": True, "avoid_bye_repeat": True}
VIEW_KEYS = ["tables", "players", "matrix", "ranking", "cash"]
UNDO_KEEP = 50


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "error") -> None:
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _int(v: Any, name: str, lo: int = 0, hi: int = 100000) -> int:
    try:
        i = int(v)
    except (TypeError, ValueError):
        raise ApiError(f"{name}: ungültige Zahl.", 422)
    if i < lo or i > hi:
        raise ApiError(f"{name}: Wert außerhalb des erlaubten Bereichs.", 422)
    return i


def _money(v: Any, name: str) -> float:
    try:
        f = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        raise ApiError(f"{name}: ungültiger Betrag.", 422)
    if f < 0 or f > 100000:
        raise ApiError(f"{name}: ungültiger Betrag.", 422)
    return round(f, 2)


def _clean(v: Any, name: str, maxlen: int = 80, required: bool = False) -> str:
    s = " ".join(str(v or "").split())
    if required and not s:
        raise ApiError(f"{name} darf nicht leer sein.", 422)
    if len(s) > maxlen:
        raise ApiError(f"{name} ist zu lang (max. {maxlen} Zeichen).", 422)
    return s


class Service:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.lock = threading.RLock()
        d = os.path.dirname(os.path.abspath(cfg.db))
        if d:
            os.makedirs(d, exist_ok=True)
        self.db = sqlite3.connect(cfg.db, check_same_thread=False, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.version = int(time.time()) * 1000
        self.anim_event = 0  # bumped by the admin to replay the draw animation on dashboards
        with self.lock:
            if not self.db.execute("SELECT 1 FROM tournaments LIMIT 1").fetchone():
                self._create_tournament_row({"name": "Preisschnapsen", "date": datetime.now().strftime("%Y-%m-%d")},
                                            active=True)
            elif not self.db.execute("SELECT 1 FROM tournaments WHERE active=1").fetchone():
                self.db.execute("UPDATE tournaments SET active=1 WHERE id=(SELECT MAX(id) FROM tournaments)")

    # ------------------------------------------------------------------ reads
    def q(self, sql: str, args: tuple = ()) -> List[sqlite3.Row]:
        return self.db.execute(sql, args).fetchall()

    def active_tid(self) -> Optional[int]:
        r = self.db.execute("SELECT id FROM tournaments WHERE active=1").fetchone()
        return r["id"] if r else None

    def require_tid(self) -> int:
        tid = self.active_tid()
        if tid is None:
            raise ApiError("Kein aktives Turnier.", 409)
        return tid

    def _t_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        dash = dict(DEFAULT_DASHBOARD)
        dash.update(json.loads(row["beamer_json"] or "{}"))
        dr = dict(DEFAULT_DRAW)
        dr.update(json.loads(row["draw_json"] or "{}"))
        return {"id": row["id"], "name": row["name"], "date": row["date"] or "", "place": row["place"] or "",
                "ng_amount": row["ng_amount"], "nk_amount": row["nk_amount"], "prize_ranks": row["prize_ranks"],
                "tables_available": row["tables_available"], "prizes": json.loads(row["prizes_json"] or "[]"),
                "status": row["status"], "show_cashbox": bool(row["show_cashbox"]), "dashboard": dash,
                "draw": dr, "active": bool(row["active"])}

    def load_raw(self, tid: int) -> Dict[str, Any]:
        trow = self.db.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
        if not trow:
            raise ApiError("Turnier nicht gefunden.", 404)
        players = [{"id": r["id"], "number": r["number"], "name": r["name"], "nickname": r["nickname"],
                    "ng_paid": bool(r["ng_paid"]), "nk_bought": None if r["nk_bought"] is None else bool(r["nk_bought"]),
                    "nk_paid": bool(r["nk_paid"]), "withdrawn_round": r["withdrawn_round"],
                    "joined_round": r["joined_round"], "note": r["note"]}
                   for r in self.q("SELECT * FROM players WHERE tournament_id=? ORDER BY number, id", (tid,))]
        rounds = []
        for r in self.q("SELECT * FROM rounds WHERE tournament_id=? ORDER BY number", (tid,)):
            prs = [{"id": p["id"], "table": p["table_no"], "a": p["player_a"], "b": p["player_b"],
                    "winner": p["winner_id"]} for p in self.q("SELECT * FROM pairings WHERE round_id=?", (r["id"],))]
            rounds.append({"id": r["id"], "number": r["number"], "status": r["status"], "mode": r["mode"],
                           "published_at": r["published_at"], "closed_at": r["closed_at"], "pairings": prs})
        placements = {r["elim_round"]: json.loads(r["order_json"])
                      for r in self.q("SELECT * FROM placement_order WHERE tournament_id=?", (tid,))}
        return {"tournament": self._t_dict(trow), "players": players, "rounds": rounds, "placements": placements}

    def derive(self, tid: int) -> Dict[str, Any]:
        return engine.compute(self.load_raw(tid))

    def tournaments_list(self) -> List[Dict[str, Any]]:
        out = []
        for r in self.q("SELECT t.*, (SELECT COUNT(*) FROM players p WHERE p.tournament_id=t.id) AS pc "
                        "FROM tournaments t ORDER BY id DESC"):
            out.append({"id": r["id"], "name": r["name"], "date": r["date"], "status": r["status"],
                        "active": bool(r["active"]), "players": r["pc"]})
        return out

    def _draft_violations(self, raw: Dict[str, Any], d: Dict[str, Any]) -> int:
        if not d["draft"]:
            return 0
        assign = {}
        for pr in d["draft"]["pairings"]:
            if pr["bye"]:
                assign[pr["a"]] = "F"
            else:
                assign[pr["a"]] = assign[pr["b"]] = pr["table"]
        pp, pb = self._prev_info(d)
        t = raw["tournament"]
        return drawmod.violations(assign, pp, pb, t["draw"]["avoid_repeat"], t["draw"]["avoid_bye_repeat"])

    @staticmethod
    def _prev_info(d: Dict[str, Any]):
        pairs, byes = set(), set()
        if d["rounds"]:
            last = d["rounds"][-1]
            for pr in last["pairings"]:
                if pr["bye"]:
                    byes.add(pr["a"])
                else:
                    pairs.add(frozenset((pr["a"], pr["b"])))
        return pairs, byes

    def admin_state(self) -> Dict[str, Any]:
        with self.lock:
            tid = self.active_tid()
            base = {"version": self.version, "server_time": now_iso(), "tournaments": self.tournaments_list()}
            if tid is None:
                return {**base, "tournament": None}
            raw = self.load_raw(tid)
            d = engine.compute(raw)
            d["draft_violations"] = self._draft_violations(raw, d)
            audit = [{"id": r["id"], "ts": r["ts"], "text": r["text"]} for r in
                     self.q("SELECT * FROM audit WHERE tournament_id=? ORDER BY id DESC LIMIT 60", (tid,))]
            u = self.db.execute("SELECT label FROM undo WHERE tournament_id=? ORDER BY id DESC LIMIT 1",
                                (tid,)).fetchone()
            return {**base, "tournament": raw["tournament"], "derived": d, "audit": audit,
                    "undo": {"available": bool(u), "label": u["label"] if u else ""}}

    def trigger_animation(self) -> int:
        """Ask all dashboards to play the draw animation once (not persisted, no undo)."""
        with self.lock:
            self.anim_event += 1
            self.version += 1
            return self.anim_event

    def public_state(self) -> Dict[str, Any]:
        """Reduced view for the dashboard."""
        with self.lock:
            tid = self.active_tid()
            base = {"version": self.version, "server_time": now_iso(), "anim_event": self.anim_event}
            if tid is None:
                return {**base, "tournament": None}
            raw = self.load_raw(tid)
            d = engine.compute(raw)
        t = raw["tournament"]
        players = []
        for p in d["players"]:
            players.append({k: p[k] for k in ("id", "number", "label", "bummerl", "lives", "hearts", "status",
                                              "elim_round", "withdrawn", "nk_bought", "place_from", "place_to")}
                           | {"cells": [{"round": c["round"], "table": c["table"], "kind": c["kind"],
                                         "loss_no": c["loss_no"], "text": c["text"]}
                                        for c in p["cells"].values()]})
        rounds = [{k: r[k] for k in ("number", "status", "total", "done", "open_tables", "published_at")}
                  | {"pairings": r["pairings"]} for r in d["rounds"]]
        cash = None
        if t["show_cashbox"]:
            c = d["cash"]
            cash = {k: c[k] for k in ("ng_amount", "nk_amount", "ng_count", "ng_sum", "nk_count", "nk_sum",
                                      "total")}
        cur = d["rounds"][-1] if d["rounds"] else None
        return {**base,
                "tournament": {"name": t["name"], "date": t["date"], "place": t["place"], "status": t["status"],
                               "prize_ranks": t["prize_ranks"], "prizes": t["prizes"],
                               "show_cashbox": t["show_cashbox"], "dashboard": t["dashboard"]},
                "phase": d["phase"], "finished": d["finished"], "winner": d["winner"], "players": players,
                "rounds": rounds, "current_round": d["current_round"],
                "round_progress": d["round_progress"], "counts": d["counts"],
                "ranking": d["ranking"], "cash": cash,
                "draw_event": ({"round": cur["number"], "published_at": cur["published_at"]} if cur else None)}

    # ------------------------------------------------------- snapshots / export
    def export_snapshot(self, tid: int) -> Dict[str, Any]:
        raw = self.load_raw(tid)
        t = raw["tournament"]
        return {"format": "schnapsen-backup", "version": 1, "exported_at": now_iso(),
                "tournament": {k: t[k] for k in ("name", "date", "place", "ng_amount", "nk_amount", "prize_ranks",
                                                 "tables_available", "prizes", "status", "show_cashbox", "dashboard",
                                                 "draw")},
                "players": raw["players"],
                "rounds": [{"id": r["id"], "number": r["number"], "status": r["status"], "mode": r["mode"],
                            "published_at": r["published_at"], "closed_at": r["closed_at"],
                            "pairings": r["pairings"]} for r in raw["rounds"]],
                "placements": {str(k): v for k, v in raw["placements"].items()}}

    def _apply_tournament_fields(self, tid: int, t: Dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE tournaments SET name=?, date=?, place=?, ng_amount=?, nk_amount=?, prize_ranks=?, "
            "tables_available=?, prizes_json=?, status=?, show_cashbox=?, beamer_json=?, draw_json=? WHERE id=?",
            (t["name"], t.get("date", ""), t.get("place", ""), t.get("ng_amount", 20), t.get("nk_amount", 10),
             t.get("prize_ranks", 3), t.get("tables_available", 0), json.dumps(t.get("prizes", [])),
             t.get("status", "signup"), 1 if t.get("show_cashbox") else 0,
             json.dumps((t.get("dashboard") or t.get("beamer") or {})), json.dumps(t.get("draw", {})), tid))

    def _insert_content(self, tid: int, snap: Dict[str, Any], keep_ids: bool) -> None:
        pmap: Dict[int, int] = {}
        for p in snap["players"]:
            vals = (tid, p["number"], p["name"], p.get("nickname", ""), int(bool(p.get("ng_paid"))),
                    None if p.get("nk_bought") is None else int(bool(p["nk_bought"])), int(bool(p.get("nk_paid"))),
                    p.get("withdrawn_round"), p.get("joined_round", 1), p.get("note", ""))
            if keep_ids:
                self.db.execute("INSERT INTO players(id,tournament_id,number,name,nickname,ng_paid,nk_bought,nk_paid,"
                                "withdrawn_round,joined_round,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (p["id"],) + vals)
                pmap[p["id"]] = p["id"]
            else:
                cur = self.db.execute("INSERT INTO players(tournament_id,number,name,nickname,ng_paid,nk_bought,"
                                      "nk_paid,withdrawn_round,joined_round,note) VALUES(?,?,?,?,?,?,?,?,?,?)", vals)
                pmap[p["id"]] = cur.lastrowid
        for r in snap["rounds"]:
            args = (tid, r["number"], r["status"], r.get("mode", "digital"), now_iso(), r.get("published_at"),
                    r.get("closed_at"))
            if keep_ids and r.get("id"):
                self.db.execute("INSERT INTO rounds(id,tournament_id,number,status,mode,created_at,published_at,"
                                "closed_at) VALUES(?,?,?,?,?,?,?,?)", (r["id"],) + args)
                rid = r["id"]
            else:
                rid = self.db.execute("INSERT INTO rounds(tournament_id,number,status,mode,created_at,published_at,"
                                      "closed_at) VALUES(?,?,?,?,?,?,?)", args).lastrowid
            for pr in r["pairings"]:
                a = pmap[pr["a"]]
                b = pmap[pr["b"]] if pr.get("b") is not None else None
                w = pmap[pr["winner"]] if pr.get("winner") is not None else None
                vals = (rid, pr.get("table"), a, b, w, now_iso())
                if keep_ids and pr.get("id"):
                    self.db.execute("INSERT INTO pairings(id,round_id,table_no,player_a,player_b,winner_id,"
                                    "updated_at) VALUES(?,?,?,?,?,?,?)", (pr["id"],) + vals)
                else:
                    self.db.execute("INSERT INTO pairings(round_id,table_no,player_a,player_b,winner_id,updated_at)"
                                    " VALUES(?,?,?,?,?,?)", vals)
        for k, order in (snap.get("placements") or {}).items():
            self.db.execute("INSERT INTO placement_order VALUES(?,?,?)",
                            (tid, int(k), json.dumps([pmap[i] for i in order if i in pmap])))

    def _wipe_content(self, tid: int) -> None:
        self.db.execute("DELETE FROM pairings WHERE round_id IN (SELECT id FROM rounds WHERE tournament_id=?)", (tid,))
        self.db.execute("DELETE FROM rounds WHERE tournament_id=?", (tid,))
        self.db.execute("DELETE FROM players WHERE tournament_id=?", (tid,))
        self.db.execute("DELETE FROM placement_order WHERE tournament_id=?", (tid,))

    @staticmethod
    def validate_snapshot(snap: Any) -> None:
        try:
            if not isinstance(snap, dict) or snap.get("format") != "schnapsen-backup":
                raise ValueError("kein Schnapsen-Backup")
            t = snap["tournament"]
            if not isinstance(t.get("name"), str):
                raise ValueError("Turniername fehlt")
            ids = set()
            for p in snap["players"]:
                if not isinstance(p["id"], int) or not isinstance(p["name"], str) or not isinstance(p["number"], int):
                    raise ValueError("Spieler ungültig")
                ids.add(p["id"])
            for r in snap["rounds"]:
                if r["status"] not in ("draft", "published", "closed"):
                    raise ValueError("Rundenstatus ungültig")
                for pr in r["pairings"]:
                    for k in ("a", "b", "winner"):
                        if pr.get(k) is not None and pr[k] not in ids:
                            raise ValueError("Paarung verweist auf unbekannten Spieler")
        except (KeyError, TypeError, ValueError) as e:
            raise ApiError(f"Ungültige Backup-Datei: {e}", 422)

    # ------------------------------------------------------------- mutations
    def _log(self, tid: Optional[int], text: str) -> None:
        self.db.execute("INSERT INTO audit(tournament_id,ts,text) VALUES(?,?,?)", (tid, now_iso(), text))

    def _push_undo(self, tid: int, label: str) -> None:
        snap = json.dumps(self.export_snapshot(tid), ensure_ascii=False)
        self.db.execute("INSERT INTO undo(tournament_id,ts,label,snapshot_json) VALUES(?,?,?,?)",
                        (tid, now_iso(), label, snap))
        self.db.execute("DELETE FROM undo WHERE tournament_id=? AND id NOT IN "
                        "(SELECT id FROM undo WHERE tournament_id=? ORDER BY id DESC LIMIT ?)", (tid, tid, UNDO_KEEP))

    def _mut(self, label: str, fn: Callable[[int], Any], undo: bool = True, tid: Optional[int] = None) -> Any:
        with self.lock:
            tid = tid if tid is not None else self.require_tid()
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if undo:
                    self._push_undo(tid, label)
                res = fn(tid)
                self._sync_status(tid)
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.version += 1
            return res

    def _sync_status(self, tid: int) -> None:
        row = self.db.execute("SELECT status FROM tournaments WHERE id=?", (tid,)).fetchone()
        if row and row["status"] == "running":
            d = self.derive(tid)
            if d["finished_by_rules"]:
                self.db.execute("UPDATE tournaments SET status='finished' WHERE id=?", (tid,))
                w = next((p["name"] for p in d["players"] if p["id"] == d["winner"]), None)
                self._log(tid, "Turnier beendet." + (f" Sieger: {w}." if w else ""))

    def _pname(self, pid: Optional[int]) -> str:
        r = self.db.execute("SELECT name FROM players WHERE id=?", (pid,)).fetchone()
        return r["name"] if r else "?"

    def _player(self, tid: int, pid: Any) -> sqlite3.Row:
        r = self.db.execute("SELECT * FROM players WHERE id=? AND tournament_id=?", (pid, tid)).fetchone()
        if not r:
            raise ApiError("Spieler nicht gefunden.", 404)
        return r

    def _tstatus(self, tid: int) -> str:
        return self.db.execute("SELECT status FROM tournaments WHERE id=?", (tid,)).fetchone()["status"]

    # ---- players
    def add_player(self, p: Dict[str, Any]) -> Dict[str, Any]:
        name = _clean(p.get("name"), "Name", 80, True)
        nick = _clean(p.get("nickname"), "Spitzname", 40)
        ng_paid = bool(p.get("ng_paid", True))
        info: Dict[str, Any] = {}

        def fn(tid: int) -> None:
            st = self._tstatus(tid)
            if st == "finished":
                raise ApiError("Das Turnier ist beendet.", 409)
            joined = 1
            if st == "running":
                if self.db.execute("SELECT 1 FROM rounds WHERE tournament_id=? AND status='draft'", (tid,)).fetchone():
                    raise ApiError("Es gibt einen Auslosungs-Entwurf. Bitte zuerst verwerfen oder veröffentlichen.",
                                   409, "draft_exists")
                if not p.get("confirm_late"):
                    raise ApiError("Das Turnier läuft bereits. Nachmeldung bestätigen?", 409, "late_confirm")
                m = self.db.execute("SELECT MAX(number) m FROM rounds WHERE tournament_id=?", (tid,)).fetchone()["m"]
                joined = (m or 0) + 1
            num = (self.db.execute("SELECT MAX(number) m FROM players WHERE tournament_id=?", (tid,)).fetchone()["m"]
                   or 0) + 1
            dup = self.db.execute("SELECT 1 FROM players WHERE tournament_id=? AND lower(name)=lower(?)",
                                  (tid, name)).fetchone()
            cur = self.db.execute("INSERT INTO players(tournament_id,number,name,nickname,ng_paid,joined_round) "
                                  "VALUES(?,?,?,?,?,?)", (tid, num, name, nick, int(ng_paid), joined))
            info["id"] = cur.lastrowid
            if dup:
                info["warning"] = f"Achtung: Der Name „{name}“ ist schon vergeben."
            self._log(tid, f"Spieler angelegt: Nr. {num} {name}" + (f" (ab Runde {joined})" if joined > 1 else ""))

        self._mut(f"Spieler {name} anlegen", fn)
        return info

    def update_player(self, pid: int, p: Dict[str, Any]) -> Dict[str, Any]:
        info: Dict[str, Any] = {}

        def fn(tid: int) -> None:
            row = self._player(tid, pid)
            sets, vals, notes = [], [], []
            if "name" in p:
                nm = _clean(p["name"], "Name", 80, True)
                sets.append("name=?"); vals.append(nm)
                if nm != row["name"]:
                    notes.append(f"Name {row['name']} -> {nm}")
                    if self.db.execute("SELECT 1 FROM players WHERE tournament_id=? AND id!=? AND lower(name)=lower(?)",
                                       (tid, pid, nm)).fetchone():
                        info["warning"] = f"Achtung: Der Name „{nm}“ ist schon vergeben."
            if "nickname" in p:
                sets.append("nickname=?"); vals.append(_clean(p["nickname"], "Spitzname", 40))
            if "note" in p:
                sets.append("note=?"); vals.append(_clean(p["note"], "Notiz", 300))
            if "ng_paid" in p:
                sets.append("ng_paid=?"); vals.append(int(bool(p["ng_paid"])))
                notes.append("NG " + ("bezahlt" if p["ng_paid"] else "nicht bezahlt"))
            if "nk_paid" in p:
                if row["nk_bought"] != 1:
                    raise ApiError("Es wurde kein Nachkauf eingetragen.", 409)
                sets.append("nk_paid=?"); vals.append(int(bool(p["nk_paid"])))
                notes.append("NK " + ("bezahlt" if p["nk_paid"] else "nicht bezahlt"))
            if sets:
                self.db.execute(f"UPDATE players SET {', '.join(sets)} WHERE id=?", vals + [pid])
                self._log(tid, f"Spieler {row['name']}: " + (", ".join(notes) or "geändert"))

        self._mut("Spieler ändern", fn)
        return info

    def delete_player(self, pid: int) -> None:
        def fn(tid: int) -> None:
            row = self._player(tid, pid)
            if self.db.execute("SELECT 1 FROM pairings WHERE player_a=? OR player_b=?", (pid, pid)).fetchone():
                raise ApiError("Der Spieler kommt in einer Paarung vor und kann nicht gelöscht werden.", 409)
            self.db.execute("DELETE FROM players WHERE id=?", (pid,))
            self._log(tid, f"Spieler gelöscht: {row['name']}")

        self._mut("Spieler löschen", fn)

    def remove_all_players(self) -> int:
        """Delete every player of the active tournament together with its rounds,
        pairings and placement orders. Settings are kept, status returns to signup.
        Undoable via the regular undo snapshot."""
        def fn(tid: int) -> int:
            n = self.db.execute("SELECT COUNT(*) c FROM players WHERE tournament_id=?", (tid,)).fetchone()["c"]
            self.db.execute("DELETE FROM pairings WHERE round_id IN (SELECT id FROM rounds WHERE tournament_id=?)", (tid,))
            self.db.execute("DELETE FROM rounds WHERE tournament_id=?", (tid,))
            self.db.execute("DELETE FROM placement_order WHERE tournament_id=?", (tid,))
            self.db.execute("DELETE FROM players WHERE tournament_id=?", (tid,))
            self.db.execute("UPDATE tournaments SET status='signup' WHERE id=?", (tid,))
            self._log(tid, f"Alle Spieler entfernt ({n})")
            return n

        return self._mut("Alle Spieler entfernen", fn)

    def withdraw_player(self, pid: int) -> None:
        def fn(tid: int) -> None:
            row = self._player(tid, pid)
            if self._tstatus(tid) != "running":
                raise ApiError("Aufgeben ist nur bei laufendem Turnier möglich.", 409)
            d = self.derive(tid)
            pl = next(p for p in d["players"] if p["id"] == pid)
            if pl["status"] == "out":
                raise ApiError("Der Spieler ist bereits ausgeschieden.", 409)
            if d["draft"] and any(pid in (x["a"], x["b"]) for x in d["draft"]["pairings"]):
                raise ApiError("Der Spieler steht im Auslosungs-Entwurf. Bitte erst Entwurf verwerfen.", 409)
            cur = d["rounds"][-1] if d["rounds"] else None
            if not cur:
                raise ApiError("Es wurde noch keine Runde gespielt – Spieler bitte einfach löschen.", 409)
            w = cur["number"]
            msg = f"Spieler {row['name']} hat aufgegeben (Runde {w})"
            if cur["status"] == "published":
                pr = next((x for x in cur["pairings"] if pid in (x["a"], x["b"])), None)
                if pr and not pr["bye"] and pr["winner"] is None:
                    opp = pr["b"] if pr["a"] == pid else pr["a"]
                    self.db.execute("UPDATE pairings SET winner_id=?, updated_at=? WHERE id=?",
                                    (opp, now_iso(), pr["id"]))
                    msg += f"; {self._pname(opp)} gewinnt kampflos"
            self.db.execute("UPDATE players SET withdrawn_round=? WHERE id=?", (w, pid))
            self._log(tid, msg)

        self._mut("Aufgabe", fn)

    def set_nk(self, pid: int, decision: str) -> None:
        def fn(tid: int) -> None:
            row = self._player(tid, pid)
            d = self.derive(tid)
            pl = next(p for p in d["players"] if p["id"] == pid)
            if decision not in ("yes_paid", "yes_later", "no", "reset"):
                raise ApiError("Unbekannte Entscheidung.", 422)
            if decision.startswith("yes") and pl["bummerl"] == 0:
                raise ApiError("Ein Nachkauf ist erst nach dem ersten Bummerl möglich.", 409)
            if decision.startswith("yes") and pl["bummerl"] >= 2 and row["nk_bought"] != 1:
                raise ApiError("Ein Nachkauf ist nur unmittelbar nach dem ersten Bummerl möglich.", 409)
            if decision == "no" and pl["bummerl"] == 0:
                raise ApiError("Es gibt noch kein Bummerl.", 409)
            vals = {"yes_paid": (1, 1), "yes_later": (1, 0), "no": (0, 0), "reset": (None, 0)}[decision]
            self.db.execute("UPDATE players SET nk_bought=?, nk_paid=? WHERE id=?", (vals[0], vals[1], pid))
            txt = {"yes_paid": "Nachkauf (bezahlt)", "yes_later": "Nachkauf (zahlt später)",
                   "no": "kein Nachkauf, scheidet aus", "reset": "Nachkauf-Entscheidung zurückgesetzt"}[decision]
            self._log(tid, f"{row['name']}: {txt}")

        self._mut("Nachkauf", fn)

    # ---- rounds
    def _prev_for_draw(self, d: Dict[str, Any]):
        return self._prev_info(d)

    def _make_draft(self, tid: int, assign: Dict[int, Any], order: List[int], mode: str, d: Dict[str, Any]) -> None:
        self.db.execute("DELETE FROM pairings WHERE round_id IN (SELECT id FROM rounds WHERE tournament_id=? "
                        "AND status='draft')", (tid,))
        self.db.execute("DELETE FROM rounds WHERE tournament_id=? AND status='draft'", (tid,))
        rid = self.db.execute("INSERT INTO rounds(tournament_id,number,status,mode,created_at) VALUES(?,?,?,?,?)",
                              (tid, d["next_round"], "draft", mode, now_iso())).lastrowid
        for pr in drawmod.to_pairings(assign, order):
            self.db.execute("INSERT INTO pairings(round_id,table_no,player_a,player_b,updated_at) VALUES(?,?,?,?,?)",
                            (rid, pr["table"], pr["a"], pr["b"], now_iso()))

    def draw_digital(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {}

        def fn(tid: int) -> None:
            raw = self.load_raw(tid)
            d = engine.compute(raw)
            had = d["draft"] is not None
            if had:
                # redraw: replace the draft
                self.db.execute("DELETE FROM pairings WHERE round_id IN (SELECT id FROM rounds WHERE "
                                "tournament_id=? AND status='draft')", (tid,))
                self.db.execute("DELETE FROM rounds WHERE tournament_id=? AND status='draft'", (tid,))
                raw = self.load_raw(tid)
                d = engine.compute(raw)
            if not d["can_draw"]:
                raise ApiError(d["can_draw_reason"], 409, "cannot_draw")
            pp, pb = self._prev_for_draw(d)
            opt = raw["tournament"]["draw"]
            assign, viol = drawmod.draw(d["draw_ids"], pp, pb, opt["avoid_repeat"], opt["avoid_bye_repeat"])
            self._make_draft(tid, assign, d["draw_ids"], "digital", d)
            info["violations"] = viol
            self._log(tid, f"Runde {d['next_round']} ausgelost (digital, Entwurf" + (", neu" if had else "") + ")")

        self._mut("Auslosung", fn)
        return info

    def draw_manual(self, assignment: Dict[Any, Any]) -> None:
        def fn(tid: int) -> None:
            d = self.derive(tid)
            if d["draft"]:
                self.db.execute("DELETE FROM pairings WHERE round_id IN (SELECT id FROM rounds WHERE "
                                "tournament_id=? AND status='draft')", (tid,))
                self.db.execute("DELETE FROM rounds WHERE tournament_id=? AND status='draft'", (tid,))
                d = self.derive(tid)
            if not d["can_draw"]:
                raise ApiError(d["can_draw_reason"], 409, "cannot_draw")
            assign: Dict[int, Any] = {}
            try:
                for k, v in (assignment or {}).items():
                    if v in (None, ""):
                        continue
                    assign[int(k)] = "F" if str(v).upper() == "F" else int(v)
            except (TypeError, ValueError):
                raise ApiError("Ungültige Zuordnung.", 422)
            errs = drawmod.validate_manual(assign, d["draw_ids"])
            if errs:
                raise ApiError(" ".join(errs), 422, "invalid_draw")
            self._make_draft(tid, assign, d["draw_ids"], "manual", d)
            self._log(tid, f"Runde {d['next_round']} manuell ausgelost (Entwurf)")

        self._mut("Manuelle Auslosung", fn)

    def discard_draft(self) -> None:
        def fn(tid: int) -> None:
            r = self.db.execute("SELECT number FROM rounds WHERE tournament_id=? AND status='draft'", (tid,)).fetchone()
            if not r:
                raise ApiError("Kein Entwurf vorhanden.", 409)
            self.db.execute("DELETE FROM pairings WHERE round_id IN (SELECT id FROM rounds WHERE tournament_id=? "
                            "AND status='draft')", (tid,))
            self.db.execute("DELETE FROM rounds WHERE tournament_id=? AND status='draft'", (tid,))
            self._log(tid, f"Entwurf Runde {r['number']} verworfen")

        self._mut("Entwurf verwerfen", fn)

    def publish(self) -> None:
        def fn(tid: int) -> None:
            r = self.db.execute("SELECT * FROM rounds WHERE tournament_id=? AND status='draft'", (tid,)).fetchone()
            if not r:
                raise ApiError("Kein Entwurf vorhanden.", 409)
            self.db.execute("UPDATE rounds SET status='published', published_at=? WHERE id=?",
                            (datetime.now().isoformat(timespec="milliseconds"), r["id"]))
            self._log(tid, f"Runde {r['number']} veröffentlicht")

        self._mut("Auslosung veröffentlichen", fn)

    def _pairing(self, tid: int, pairing_id: Any) -> sqlite3.Row:
        r = self.db.execute("SELECT p.*, r.status AS rstatus, r.number AS rnum FROM pairings p JOIN rounds r ON "
                            "r.id=p.round_id WHERE p.id=? AND r.tournament_id=?", (pairing_id, tid)).fetchone()
        if not r:
            raise ApiError("Paarung nicht gefunden.", 404)
        return r

    def set_result(self, pairing_id: int, winner_id: Optional[int], confirm: bool = False) -> None:
        def fn(tid: int) -> None:
            pr = self._pairing(tid, pairing_id)
            if pr["rstatus"] == "draft":
                raise ApiError("Die Auslosung ist noch ein Entwurf.", 409)
            if pr["player_b"] is None:
                raise ApiError("Freilos hat kein Ergebnis.", 409)
            if pr["rstatus"] == "closed" and not confirm:
                raise ApiError("Runde ist abgeschlossen – Korrektur bestätigen.", 409, "confirm_needed")
            if winner_id is not None and winner_id not in (pr["player_a"], pr["player_b"]):
                raise ApiError("Der Sieger muss einer der beiden Spieler sein.", 422)
            if winner_id == pr["winner_id"]:
                return
            self.db.execute("UPDATE pairings SET winner_id=?, updated_at=? WHERE id=?",
                            (winner_id, now_iso(), pairing_id))
            a, b = self._pname(pr["player_a"]), self._pname(pr["player_b"])
            corr = " (Korrektur)" if (pr["winner_id"] is not None or pr["rstatus"] == "closed") else ""
            if winner_id is None:
                self._log(tid, f"Runde {pr['rnum']} Tisch {pr['table_no']}: Ergebnis zurückgesetzt ({a} – {b}){corr}")
            else:
                loser = pr["player_b"] if winner_id == pr["player_a"] else pr["player_a"]
                self._log(tid, f"Runde {pr['rnum']} Tisch {pr['table_no']}: {self._pname(winner_id)} schlägt "
                          f"{self._pname(loser)}{corr}")

        self._mut("Ergebnis" if winner_id else "Ergebnis zurücksetzen", fn)

    def close_round(self, number: int) -> None:
        def fn(tid: int) -> None:
            r = self.db.execute("SELECT * FROM rounds WHERE tournament_id=? AND number=? AND status!='draft'",
                                (tid, number)).fetchone()
            if not r:
                raise ApiError("Runde nicht gefunden.", 404)
            if r["status"] != "published":
                raise ApiError("Die Runde ist bereits abgeschlossen.", 409)
            open_t = [str(x["table_no"]) for x in self.q(
                "SELECT table_no FROM pairings WHERE round_id=? AND player_b IS NOT NULL AND winner_id IS NULL "
                "ORDER BY table_no", (r["id"],))]
            if open_t:
                raise ApiError("Es fehlen noch Ergebnisse: Tisch " + ", ".join(open_t), 409)
            self.db.execute("UPDATE rounds SET status='closed', closed_at=? WHERE id=?", (now_iso(), r["id"]))
            self._log(tid, f"Runde {number} abgeschlossen")

        self._mut(f"Runde {number} abschließen", fn)
        self.backup(f"runde{number}")

    def reopen_round(self, number: int) -> None:
        def fn(tid: int) -> None:
            r = self.db.execute("SELECT * FROM rounds WHERE tournament_id=? AND number=? AND status='closed'",
                                (tid, number)).fetchone()
            if not r:
                raise ApiError("Runde nicht gefunden oder nicht abgeschlossen.", 404)
            if self.db.execute("SELECT 1 FROM rounds WHERE tournament_id=? AND number>?", (tid, number)).fetchone():
                raise ApiError("Es gibt bereits eine spätere Runde.", 409)
            self.db.execute("UPDATE rounds SET status='published', closed_at=NULL WHERE id=?", (r["id"],))
            if self._tstatus(tid) == "finished":
                self.db.execute("UPDATE tournaments SET status='running' WHERE id=?", (tid,))
            self._log(tid, f"Runde {number} wieder geöffnet")

        self._mut(f"Runde {number} öffnen", fn)

    # ---- placements
    def set_placement(self, elim_round: int, order: List[int]) -> None:
        def fn(tid: int) -> None:
            d = self.derive(tid)
            g = next((x for x in d["ranking"]["groups"]
                      if (x["key"] == elim_round)), None)
            if not g:
                raise ApiError("Keine solche Platzierungsgruppe.", 404)
            if len(order) != len(set(order)) or set(order) != set(g["players"]):
                raise ApiError("Die Reihenfolge muss genau die Spieler der Gruppe enthalten.", 422)
            self.db.execute("INSERT OR REPLACE INTO placement_order VALUES(?,?,?)",
                            (tid, elim_round, json.dumps(order)))
            names = [self._pname(i) for i in order]
            lab = g["pl_label"]
            if len(order) == 2:
                self._log(tid, f"Platzierungsspiel {lab}: {names[0]} schlägt {names[1]}")
            else:
                self._log(tid, f"Platzierung {lab} festgelegt: " + ", ".join(f"{i+1}. {n}" for i, n in enumerate(names)))

        self._mut("Platzierung", fn)

    def clear_placement(self, elim_round: int) -> None:
        def fn(tid: int) -> None:
            self.db.execute("DELETE FROM placement_order WHERE tournament_id=? AND elim_round=?", (tid, elim_round))
            self._log(tid, f"Platzierung (ausgeschieden in Runde {elim_round}) zurückgesetzt")

        self._mut("Platzierung zurücksetzen", fn)

    # ---- tournament
    def update_tournament(self, p: Dict[str, Any]) -> None:
        def fn(tid: int) -> None:
            t = self._t_dict(self.db.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone())
            if "name" in p:
                t["name"] = _clean(p["name"], "Name", 100, True)
            if "date" in p:
                t["date"] = _clean(p["date"], "Datum", 20)
            if "place" in p:
                t["place"] = _clean(p["place"], "Ort", 100)
            if "ng_amount" in p:
                t["ng_amount"] = _money(p["ng_amount"], "Nenngeld")
            if "nk_amount" in p:
                t["nk_amount"] = _money(p["nk_amount"], "Nachkauf")
            if "prize_ranks" in p:
                t["prize_ranks"] = _int(p["prize_ranks"], "Preisränge", 0, 200)
            if "tables_available" in p:
                t["tables_available"] = _int(p["tables_available"], "Tische", 0, 500)
            if "prizes" in p:
                pr = p["prizes"]
                if not isinstance(pr, list) or len(pr) > 200:
                    raise ApiError("Preise ungültig.", 422)
                t["prizes"] = [_clean(x, "Preis", 80) for x in pr]
            if "show_cashbox" in p:
                t["show_cashbox"] = bool(p["show_cashbox"])
            if "draw" in p and isinstance(p["draw"], dict):
                t["draw"] = {"avoid_repeat": bool(p["draw"].get("avoid_repeat", True)),
                             "avoid_bye_repeat": bool(p["draw"].get("avoid_bye_repeat", True))}
            self._apply_tournament_fields(tid, t)
            self._log(tid, "Turniereinstellungen geändert")

        self._mut("Einstellungen", fn)

    def update_dashboard(self, p: Dict[str, Any]) -> None:
        def fn(tid: int) -> None:
            t = self._t_dict(self.db.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone())
            b = t["dashboard"]
            if "rotate_seconds" in p:
                b["rotate_seconds"] = _int(p["rotate_seconds"], "Wechseldauer", 3, 600)
            if "pinned" in p:
                if p["pinned"] not in ("", "signup") + tuple(VIEW_KEYS) + ("ceremony",):
                    raise ApiError("Unbekannte Ansicht.", 422)
                b["pinned"] = p["pinned"]
            if "views" in p:
                if not isinstance(p["views"], list) or any(v not in VIEW_KEYS for v in p["views"]):
                    raise ApiError("Ansichten ungültig.", 422)
                b["views"] = [v for v in VIEW_KEYS if v in p["views"]]
            for k in ("ceremony_auto", "show_ceremony", "animation"):
                if k in p:
                    b[k] = bool(p[k])
            t["dashboard"] = b
            if "show_cashbox" in p:
                t["show_cashbox"] = bool(p["show_cashbox"])
            self._apply_tournament_fields(tid, t)
            self._log(tid, "Dashboard-Einstellungen geändert")

        self._mut("Dashboard", fn, undo=False)

    def start_tournament(self) -> None:
        def fn(tid: int) -> None:
            if self._tstatus(tid) != "signup":
                raise ApiError("Das Turnier wurde bereits gestartet.", 409)
            n = self.db.execute("SELECT COUNT(*) c FROM players WHERE tournament_id=?", (tid,)).fetchone()["c"]
            if n < 2:
                raise ApiError("Zum Start braucht es mindestens 2 Spieler.", 409)
            self.db.execute("UPDATE tournaments SET status='running' WHERE id=?", (tid,))
            self._log(tid, f"Turnier gestartet ({n} Spieler)")

        self._mut("Turnier starten", fn)

    def finish_tournament(self) -> None:
        def fn(tid: int) -> None:
            if self._tstatus(tid) != "running":
                raise ApiError("Das Turnier läuft nicht.", 409)
            self.db.execute("UPDATE tournaments SET status='finished' WHERE id=?", (tid,))
            self._log(tid, "Turnier manuell beendet")

        self._mut("Turnier beenden", fn)

    def reopen_tournament(self) -> None:
        def fn(tid: int) -> None:
            if self._tstatus(tid) != "finished":
                raise ApiError("Das Turnier ist nicht beendet.", 409)
            if self.derive(tid)["finished_by_rules"]:
                raise ApiError("Das Turnier ist regulär beendet (nur noch ein Spieler). Zum Korrigieren im Tab "
                               "„Runde“ die letzte Runde wieder öffnen.", 409)
            self.db.execute("UPDATE tournaments SET status='running' WHERE id=?", (tid,))
            self._log(tid, "Turnier wieder geöffnet")

        self._mut("Turnier öffnen", fn)

    def reset_tournament(self) -> None:
        def fn(tid: int) -> None:
            self.db.execute("DELETE FROM pairings WHERE round_id IN (SELECT id FROM rounds WHERE tournament_id=?)", (tid,))
            self.db.execute("DELETE FROM rounds WHERE tournament_id=?", (tid,))
            self.db.execute("DELETE FROM placement_order WHERE tournament_id=?", (tid,))
            self.db.execute("UPDATE players SET nk_bought=NULL, nk_paid=0, withdrawn_round=NULL, joined_round=1 "
                            "WHERE tournament_id=?", (tid,))
            self.db.execute("UPDATE tournaments SET status='signup' WHERE id=?", (tid,))
            self._log(tid, "Turnier zurückgesetzt (Spieler bleiben, Runden gelöscht)")

        self._mut("Turnier zurücksetzen", fn)

    def _create_tournament_row(self, p: Dict[str, Any], active: bool) -> int:
        b = dict(DEFAULT_DASHBOARD)
        cur = self.db.execute(
            "INSERT INTO tournaments(name,date,place,ng_amount,nk_amount,prize_ranks,tables_available,prizes_json,"
            "status,show_cashbox,beamer_json,draw_json,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_clean(p.get("name"), "Name", 100, True), _clean(p.get("date"), "Datum", 20),
             _clean(p.get("place"), "Ort", 100), _money(p.get("ng_amount", 20), "Nenngeld"),
             _money(p.get("nk_amount", 10), "Nachkauf"), _int(p.get("prize_ranks", 3), "Preisränge", 0, 200),
             _int(p.get("tables_available", 0), "Tische", 0, 500), "[]", "signup", 0, json.dumps(b),
             json.dumps(DEFAULT_DRAW), 0, now_iso()))
        tid = cur.lastrowid
        if active:
            self.db.execute("UPDATE tournaments SET active=0")
            self.db.execute("UPDATE tournaments SET active=1 WHERE id=?", (tid,))
        return tid

    def create_tournament(self, p: Dict[str, Any]) -> int:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                tid = self._create_tournament_row(p, True)
                self._log(tid, f"Turnier angelegt: {p.get('name')}")
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.version += 1
            return tid

    def activate_tournament(self, tid: int) -> None:
        with self.lock:
            if not self.db.execute("SELECT 1 FROM tournaments WHERE id=?", (tid,)).fetchone():
                raise ApiError("Turnier nicht gefunden.", 404)
            self.db.execute("UPDATE tournaments SET active=0")
            self.db.execute("UPDATE tournaments SET active=1 WHERE id=?", (tid,))
            self._log(tid, "Turnier aktiviert")
            self.version += 1

    def delete_tournament(self, tid: int) -> None:
        with self.lock:
            row = self.db.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
            if not row:
                raise ApiError("Turnier nicht gefunden.", 404)
            if row["active"]:
                raise ApiError("Das aktive Turnier kann nicht gelöscht werden. Erst ein anderes aktivieren.", 409)
            self.db.execute("BEGIN IMMEDIATE")
            self._wipe_content(tid)
            self.db.execute("DELETE FROM undo WHERE tournament_id=?", (tid,))
            self.db.execute("DELETE FROM audit WHERE tournament_id=?", (tid,))
            self.db.execute("DELETE FROM tournaments WHERE id=?", (tid,))
            self.db.execute("COMMIT")
            self.version += 1

    def import_snapshot(self, snap: Dict[str, Any]) -> int:
        self.validate_snapshot(snap)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                t = dict(snap["tournament"])
                t["name"] = _clean(t["name"], "Name", 100, True) + " (Import)"
                tid = self._create_tournament_row(t, False)
                tt = dict(DEFAULT_DASHBOARD); tt.update(t.get("dashboard") or t.get("beamer") or {})
                dd = dict(DEFAULT_DRAW); dd.update(t.get("draw") or {})
                self._apply_tournament_fields(tid, {**t, "dashboard": tt, "draw": dd,
                                                    "status": t.get("status", "signup")})
                self._insert_content(tid, snap, keep_ids=False)
                self._log(tid, "Aus Backup importiert")
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.version += 1
            return tid

    def undo(self) -> str:
        with self.lock:
            tid = self.require_tid()
            row = self.db.execute("SELECT * FROM undo WHERE tournament_id=? ORDER BY id DESC LIMIT 1", (tid,)).fetchone()
            if not row:
                raise ApiError("Nichts zum Rückgängigmachen.", 409)
            snap = json.loads(row["snapshot_json"])
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self._wipe_content(tid)
                t = dict(snap["tournament"])
                self._apply_tournament_fields(tid, t)
                self._insert_content(tid, snap, keep_ids=True)
                self.db.execute("DELETE FROM undo WHERE id=?", (row["id"],))
                self._log(tid, f"Rückgängig: {row['label']}")
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.version += 1
            return row["label"]

    # ---- Backup
    def backup(self, tag: str = "") -> Optional[str]:
        try:
            os.makedirs(self.cfg.backup_dir, exist_ok=True)
            name = "schnapsen-" + datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{tag}" if tag else "") + ".db"
            path = os.path.join(self.cfg.backup_dir, name)
            n = 1
            while os.path.exists(path):
                n += 1
                path = path[:-3] + f"-{n}.db"
            with self.lock:
                dst = sqlite3.connect(path)
                try:
                    self.db.backup(dst)
                finally:
                    dst.close()
            files = sorted(f for f in os.listdir(self.cfg.backup_dir) if f.startswith("schnapsen-") and f.endswith(".db"))
            for old in files[:-300]:
                os.remove(os.path.join(self.cfg.backup_dir, old))
            return path
        except Exception as e:  # a failed backup must never abort the triggering action
            print("Backup failed:", e)
            return None
