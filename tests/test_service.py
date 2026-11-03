import json
import random

import pytest

from app.service import ApiError
from app import simtools


def derived(svc):
    return svc.derive(svc.require_tid())


def setup_running(svc, n=4):
    simtools.fill_players(svc, n)
    svc.start_tournament()


def play_round_manual_results(svc, winners_first=True):
    svc.draw_digital()
    svc.publish()
    d = derived(svc)
    for pr in d["rounds"][-1]["pairings"]:
        if not pr["bye"]:
            svc.set_result(pr["id"], pr["a"] if winners_first else pr["b"])
    svc.close_round(d["rounds"][-1]["number"])
    return derived(svc)


def test_rebuy_only_after_first_bummerl_and_only_once(svc):
    setup_running(svc, 2)
    p = derived(svc)["players"]
    with pytest.raises(ApiError):
        svc.set_nk(p[0]["id"], "yes_paid")          # no bummerl yet
    d = play_round_manual_results(svc)
    loser = d["rounds"][-1]["pairings"][0]["loser"]
    svc.set_nk(loser, "yes_later")
    svc.set_nk(loser, "yes_paid")                    # only the payment status changes, no second rebuy
    d = derived(svc)
    assert d["cash"]["nk_count"] == 1
    # second bummerl: a rebuy can no longer be made afterwards
    svc.draw_digital(); svc.publish()
    d = derived(svc)
    pr = d["rounds"][-1]["pairings"][0]
    svc.set_result(pr["id"], pr["a"] if pr["a"] != loser else pr["b"])
    svc.close_round(d["current_round"])
    other = [p for p in derived(svc)["players"] if p["id"] != loser][0]["id"]
    with pytest.raises(ApiError):
        svc.set_nk(other, "yes_paid")                # has 0 bummerl


def test_no_draw_without_rebuy_decision(svc):
    setup_running(svc, 4)
    d = play_round_manual_results(svc)
    assert d["nk_pending"] and not d["can_draw"]
    with pytest.raises(ApiError):
        svc.draw_digital()
    for n in d["nk_pending"]:
        svc.set_nk(n["id"], "yes_paid")
    assert derived(svc)["can_draw"]
    svc.draw_digital()
    assert derived(svc)["draft"] is not None


def test_draft_hidden_on_dashboard_until_published(svc):
    setup_running(svc, 4)
    svc.draw_digital()
    pub = svc.public_state()
    assert pub["rounds"] == [] and pub["phase"] == "drawing"
    svc.publish()
    pub = svc.public_state()
    assert len(pub["rounds"]) == 1 and pub["rounds"][0]["total"] == 2
    assert "note" not in json.dumps(pub) and "audit" not in pub


def test_dashboard_cash_only_when_enabled(svc):
    setup_running(svc, 4)
    assert svc.public_state()["cash"] is None
    svc.update_tournament({"show_cashbox": True})
    c = svc.public_state()["cash"]
    assert c["total"] == 80


def test_withdrawal_mid_round_opponent_wins(svc):
    setup_running(svc, 4)
    svc.draw_digital(); svc.publish()
    d = derived(svc)
    pr = d["rounds"][-1]["pairings"][0]
    svc.withdraw_player(pr["a"])
    d = derived(svc)
    got = d["rounds"][-1]["pairings"][0]
    assert got["winner"] == pr["b"]
    a = next(p for p in d["players"] if p["id"] == pr["a"])
    assert a["status"] == "out" and a["withdrawn"] and a["elim_round"] == 1
    assert any("aufgegeben" in x["text"] and "kampflos" in x["text"] for x in svc.admin_state()["audit"])


def test_late_registration_and_delete(svc):
    simtools.fill_players(svc, 3)
    svc.start_tournament()
    with pytest.raises(ApiError) as e:
        svc.add_player({"name": "Neu"})
    assert e.value.code == "late_confirm"
    info = svc.add_player({"name": "Neu", "confirm_late": True})
    p = next(x for x in derived(svc)["players"] if x["id"] == info["id"])
    assert p["joined_round"] == 1
    play_round_manual_results(svc)
    info = svc.add_player({"name": "Spaet", "confirm_late": True})
    p = next(x for x in derived(svc)["players"] if x["id"] == info["id"])
    assert p["joined_round"] == 2
    svc.delete_player(p["id"])
    d = derived(svc)
    inpair = d["rounds"][0]["pairings"][0]["a"]
    with pytest.raises(ApiError):
        svc.delete_player(inpair)


def test_duplicate_name_warns_but_creates(svc):
    svc.add_player({"name": "Sepp"})
    info = svc.add_player({"name": "sepp"})
    assert "warning" in info and len(derived(svc)["players"]) == 2


def test_correcting_past_round_warns_without_changing_data(svc):
    simtools.fill_players(svc, 4)
    svc.start_tournament()
    rng = random.Random(3)
    simtools.play_round(svc, rng, p_yes=0.0)       # every loser is eliminated
    simtools.play_round(svc, rng, p_yes=0.0)       # final
    d = derived(svc)
    assert d["finished"] and d["warnings"] == []
    r1 = d["rounds"][0]["pairings"][0]
    with pytest.raises(ApiError) as e:
        svc.set_result(r1["id"], r1["loser"])
    assert e.value.code == "confirm_needed"
    svc.set_result(r1["id"], r1["loser"], confirm=True)
    d = derived(svc)
    assert d["warnings"]                           # data is kept, but a warning is raised
    assert len(d["rounds"]) == 2


def test_undo_restores_state(svc):
    setup_running(svc, 4)
    before = derived(svc)
    svc.draw_digital(); svc.publish()
    assert derived(svc)["rounds"]
    svc.undo()                                      # undo publish
    d = derived(svc)
    assert d["rounds"] == [] and d["draft"] is not None
    svc.undo()                                      # undo draw
    d = derived(svc)
    assert d["draft"] is None and d["phase"] == "ready"
    assert [p["id"] for p in d["players"]] == [p["id"] for p in before["players"]]
    svc.undo()                                      # undo start
    assert derived(svc)["phase"] == "signup"


def test_undo_keeps_only_50(svc):
    for i in range(60):
        svc.add_player({"name": f"S{i}"})
    n = svc.db.execute("SELECT COUNT(*) c FROM undo").fetchone()["c"]
    assert n == 50
    with pytest.raises(ApiError):
        for _ in range(51):
            svc.undo()


def test_export_import_new_tournament_new_ids(svc):
    simtools.fill_players(svc, 6)
    svc.start_tournament()
    simtools.play_round(svc, random.Random(1), p_yes=1.0)
    tid = svc.require_tid()
    snap = svc.export_snapshot(tid)
    new = svc.import_snapshot(json.loads(json.dumps(snap)))
    assert new != tid and svc.active_tid() == tid
    a = svc.derive(tid)
    b = svc.derive(new)
    assert {p["id"] for p in a["players"]}.isdisjoint({p["id"] for p in b["players"]})
    assert [(p["name"], p["bummerl"], p["status"]) for p in a["players"]] == [(p["name"], p["bummerl"], p["status"]) for p in b["players"]]
    assert a["current_round"] == b["current_round"]
    with pytest.raises(ApiError):
        svc.import_snapshot({"format": "nope"})


def test_closing_round_creates_backup(svc, cfg):
    import os
    setup_running(svc, 4)
    play_round_manual_results(svc)
    files = os.listdir(cfg.backup_dir)
    assert len(files) == 1 and files[0].endswith("-runde1.db")


def test_tournament_archive_activate_and_delete(svc):
    first = svc.require_tid()
    second = svc.create_tournament({"name": "Zweites"})
    assert svc.active_tid() == second
    with pytest.raises(ApiError):
        svc.delete_tournament(second)
    svc.activate_tournament(first)
    svc.delete_tournament(second)
    assert [t["id"] for t in svc.tournaments_list()] == [first]


def test_placement_two_players_audit_log(svc):
    simtools.fill_players(svc, 4)
    svc.start_tournament()
    svc.update_tournament({"prize_ranks": 4})
    d = simtools.play_tournament(svc, random.Random(5), p_yes=0.0)
    assert any(len(g["players"]) == 2 and g["needs_playoff"] for g in d["ranking"]["groups"])
    for g in d["ranking"]["groups"]:
        if g["needs_playoff"]:
            svc.set_placement(g["key"], list(reversed(g["players"])))
    d = derived(svc)
    assert d["ranking"]["open_playoffs"] == []
    log = " ".join(a["text"] for a in svc.admin_state()["audit"])
    assert "Platzierungsspiel Pl." in log and "schlägt" in log
    with pytest.raises(ApiError):
        svc.set_placement(1, [999, 998])


def test_regularly_finished_tournament_cannot_be_reopened(svc):
    simtools.fill_players(svc, 2)
    svc.start_tournament()
    d = simtools.play_tournament(svc, random.Random(2), p_yes=0.0)
    assert d["finished"]
    with pytest.raises(ApiError):
        svc.reopen_tournament()
    n = d["current_round"]
    svc.reopen_round(n)                       # proper way to correct
    d = derived(svc)
    assert not d["finished"] and d["phase"] == "running"


def test_legacy_snapshots_with_old_settings_key(svc):
    simtools.fill_players(svc, 2)
    snap = svc.export_snapshot(svc.require_tid())
    snap["tournament"]["beamer"] = snap["tournament"].pop("dashboard")
    snap["tournament"]["beamer"]["rotate_seconds"] = 33
    new = svc.import_snapshot(snap)
    assert svc.load_raw(new)["tournament"]["dashboard"]["rotate_seconds"] == 33
