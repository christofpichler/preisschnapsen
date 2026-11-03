from app.engine import ACTIVE_KEY
from tests.helpers import P, compute, players, raw, rnd


def test_without_rebuy_out_after_first_bummerl():
    d = compute(players(2, nk={2: False}), [rnd(1, [(1, 1, 2, 1)])])
    p2 = P(d, 2)
    assert p2["bummerl"] == 1 and p2["status"] == "out" and p2["elim_round"] == 1
    assert p2["lives"] == 0 and P(d, 1)["status"] == "active"


def test_first_bummerl_without_decision_is_rebuy_open():
    d = compute(players(2), [rnd(1, [(1, 1, 2, 1)])])
    assert P(d, 2)["status"] == "nk_open"
    assert d["nk_pending"] == [{"id": 2, "label": "P2", "round": 1}]
    assert d["can_draw"] is False and "Nachkauf" in d["can_draw_reason"]


def test_with_rebuy_out_only_after_third_bummerl():
    rounds = [rnd(1, [(1, 1, 2, 1)]), rnd(2, [(1, 1, 2, 1)]), rnd(3, [(1, 1, 2, 1)])]
    d = compute(players(2, nk={2: True}), rounds[:1])
    assert P(d, 2)["status"] == "active" and P(d, 2)["lives"] == 2
    d = compute(players(2, nk={2: True}), rounds[:2])
    assert P(d, 2)["status"] == "active" and P(d, 2)["lives"] == 1 and P(d, 2)["bummerl"] == 2
    d = compute(players(2, nk={2: True}), rounds)
    p2 = P(d, 2)
    assert p2["status"] == "out" and p2["elim_round"] == 3 and p2["bummerl"] == 3 and p2["lives"] == 0


def test_hearts_and_cells():
    d = compute(players(2, nk={2: True}), [rnd(1, [(3, 1, 2, 1)]), rnd(2, [(5, 1, 2, 1)])])
    p2 = P(d, 2)
    assert p2["hearts"] == ["lost", "lost", "full"]
    assert p2["cells"][1]["text"] == "3–" and p2["cells"][2]["text"] == "5⊖"
    assert P(d, 1)["cells"][1]["text"] == "3+"
    assert P(d, 1)["hearts"] == ["full", "none", "none"]


def test_bye_is_not_a_loss():
    d = compute(players(3), [rnd(1, [(1, 1, 2, 1), (None, 3, None, None)])])
    p3 = P(d, 3)
    assert p3["bummerl"] == 0 and p3["status"] == "active" and p3["cells"][1]["text"] == "F"


def test_no_draw_without_rebuy_decision_then_allowed():
    rounds = [rnd(1, [(1, 1, 2, 1), (2, 3, 4, 3)])]
    d = compute(players(4), rounds)
    assert not d["can_draw"] and len(d["nk_pending"]) == 2
    d = compute(players(4, nk={2: True, 4: False}), rounds)
    assert d["can_draw"] and sorted(d["draw_ids"]) == [1, 2, 3]
    assert d["draw_info"]["tables"] == 1 and d["draw_info"]["bye"] is True
    assert "Zettel 1 je doppelt + 1× F = 3 Zettel" in d["draw_info"]["text"]


def test_ticket_text_19_and_24():
    d = compute(players(19), [], status="running")
    assert d["draw_info"]["text"] == "Runde 1 – 19 Spieler: Zettel 1–9 je doppelt + 1× F = 19 Zettel"
    d = compute(players(24), [], status="running")
    assert d["draw_info"]["text"] == "Runde 1 – 24 Spieler: Zettel 1–12 je doppelt = 24 Zettel"


def test_draw_only_after_round_closed():
    d = compute(players(2), [rnd(1, [(1, 1, 2, 1)], status="published")])
    assert d["phase"] == "running" and not d["can_draw"]
    assert "noch nicht abgeschlossen" in d["can_draw_reason"]


def test_tournament_ends_with_one_player_final_loser_with_lives_continues():
    # final 1 vs 2: loser has the rebuy, still has lives, tournament continues
    d = compute(players(2, nk={2: True}), [rnd(1, [(1, 1, 2, 1)])])
    assert d["finished"] is False and d["can_draw"] and len(d["draw_ids"]) == 2
    rounds = [rnd(1, [(1, 1, 2, 1)]), rnd(2, [(1, 1, 2, 1)]), rnd(3, [(1, 1, 2, 1)])]
    d = compute(players(2, nk={2: True}), rounds)
    assert d["finished"] and d["winner"] == 1 and d["phase"] == "finished"
    # loser without rebuy: tournament ends immediately
    d = compute(players(2, nk={1: False}), [rnd(1, [(1, 1, 2, 2)])])
    assert d["finished"] and d["winner"] == 2


def test_end_waits_for_rebuy_decision():
    d = compute(players(2), [rnd(1, [(1, 1, 2, 1)])])
    assert not d["finished"]


def test_ranking_groups_and_place_ranges():
    # 6 players without rebuy: R1: 1,3,5 win; 2,4,6 out (places 4-6). R2: 1 beats 3, 5 gets a bye -> 3 out
    pls = players(6, nk={2: False, 4: False, 6: False, 3: False, 5: False, 1: False})
    rounds = [rnd(1, [(1, 1, 2, 1), (2, 3, 4, 3), (3, 5, 6, 5)]),
              rnd(2, [(1, 1, 3, 1), (None, 5, None, None)]),
              rnd(3, [(1, 1, 5, 1)])]
    d = compute(pls, rounds, prize_ranks=6)
    g = {x["key"]: x for x in d["ranking"]["groups"]}
    assert d["winner"] == 1 and d["finished"]
    assert (g[ACTIVE_KEY]["place_from"], g[ACTIVE_KEY]["place_to"]) == (1, 1)
    assert (g[3]["place_from"], g[3]["place_to"]) == (2, 2)      # P5 (out in R3)
    assert (g[2]["place_from"], g[2]["place_to"]) == (3, 3)      # P3
    assert (g[1]["place_from"], g[1]["place_to"]) == (4, 6) and g[1]["needs_playoff"]
    assert P(d, 2)["place_from"] == 4 and P(d, 2)["place_to"] == 6
    assert d["ranking"]["open_playoffs"] == [1]
    # set a placement order
    d = compute(pls, rounds, prize_ranks=6, placements={1: [6, 2, 4]})
    assert [P(d, i)["place_from"] for i in (6, 2, 4)] == [4, 5, 6]
    assert d["ranking"]["open_playoffs"] == []
    # no placement game outside the prize ranks
    d = compute(pls, rounds, prize_ranks=3)
    assert d["ranking"]["open_playoffs"] == []


def test_cash():
    pls = players(4, nk={1: True, 2: True})
    pls[0]["nk_paid"] = True
    pls[3]["ng_paid"] = False
    d = compute(pls, [])
    c = d["cash"]
    assert c["ng_count"] == 4 and c["ng_sum"] == 80 and c["nk_count"] == 2 and c["nk_sum"] == 20
    assert c["total"] == 100 and c["paid"] == 70 and c["open"] == 30
    assert c["open_ng"] == [4] and c["open_nk"] == [2]


def test_correcting_old_round_creates_warning():
    # R1: 1 beats 2 (2 has no rebuy, out); correction: 2 wins instead
    pls = players(4, nk={2: False, 4: False})
    r1 = rnd(1, [(1, 1, 2, 1), (2, 3, 4, 3)])
    r2 = rnd(2, [(1, 1, 3, 1), (None, 3, None, None)][:1])
    d = compute(pls, [r1, r2])
    assert d["warnings"] == []
    # correction: 2 beats 1 in R1, so 2 should still be in the game but is missing from R2
    r1b = rnd(1, [(1, 1, 2, 2), (2, 3, 4, 3)])
    d = compute(pls, [r1b, r2])
    texts = " ".join(w["text"] for w in d["warnings"])
    assert d["warnings"] and "P2" in texts and "nicht ausgelost" in texts
    # correction eliminates a player who still plays later
    r1c = rnd(1, [(1, 1, 2, 2), (2, 3, 4, 3)])
    d = compute(players(4, nk={1: False, 4: False}), [r1c, r2])
    assert any(w["code"] == "after_out" for w in d["warnings"])


def test_rebuy_revoked_after_second_bummerl_warns():
    rounds = [rnd(1, [(1, 1, 2, 1)]), rnd(2, [(1, 1, 2, 1)])]
    d = compute(players(2, nk={2: False}), rounds)
    assert any(w["code"] in ("after_out", "nk_missing") for w in d["warnings"])


def test_withdrawal_eliminates_player():
    pls = players(4, nk={1: True, 2: True, 3: True, 4: True})
    pls[0]["withdrawn_round"] = 1
    d = compute(pls, [rnd(1, [(1, 1, 2, 2), (2, 3, 4, 3)])])
    p1 = P(d, 1)
    assert p1["status"] == "out" and p1["elim_round"] == 1 and p1["withdrawn"] and p1["by_withdraw"]
    assert d["counts"]["alive"] == 3


def test_late_registration_joined_round():
    pls = players(5)
    pls[4]["joined_round"] = 2
    pls[4]["nk_bought"] = False
    d = compute(pls, [rnd(1, [(1, 1, 2, 1), (2, 3, 4, 3)], status="closed")])
    assert d["warnings"] == []          # player 5 is rightly absent from R1
    assert 5 in d["draw_ids"]
    d1 = compute(players(5), [rnd(1, [(1, 1, 2, 1), (2, 3, 4, 3)])], status="running")
    assert any(w["code"] == "missing" for w in d1["warnings"])


def test_table_notice():
    d = compute(players(6), [], tables_available=2)
    assert any(n["code"] == "tables" for n in d["notices"])
