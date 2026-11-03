import random

import pytest

from app import draw


@pytest.mark.parametrize("n", [2, 3, 4, 19, 24, 40, 41])
def test_tickets(n):
    t = draw.make_tickets(n)
    assert len(t) == n
    nums = [x for x in t if x != "F"]
    assert sorted(set(nums)) == list(range(1, n // 2 + 1))
    assert all(nums.count(k) == 2 for k in set(nums))
    assert t.count("F") == n % 2


def test_19_players_9_tables_1_bye():
    ids = list(range(100, 119))
    a, v = draw.draw(ids)
    pairs, bye = draw.pairs_of(a)
    assert len(pairs) == 9 and bye in ids
    assert sorted(a) == ids


@pytest.mark.parametrize("n", [2, 3, 8, 19, 24, 31])
def test_assignment_valid(n):
    ids = random.sample(range(1, 500), n)
    a, _ = draw.draw(ids)
    assert set(a) == set(ids) and draw.validate_manual(a, ids) == []
    prs = draw.to_pairings(a, ids)
    flat = [x for p in prs for x in (p["a"], p["b"]) if x is not None]
    assert sorted(flat) == sorted(ids)
    assert sum(1 for p in prs if p["b"] is None) == n % 2


def test_even_count_never_has_bye():
    for _ in range(50):
        a, _ = draw.draw(list(range(24)))
        assert "F" not in a.values()


def test_soft_rules_are_respected():
    ids = [1, 2, 3, 4]
    prev = {frozenset((1, 2)), frozenset((3, 4))}
    for _ in range(30):
        a, v = draw.draw(ids, prev_pairs=prev)
        assert v == 0 and not (draw.pairs_of(a)[0] & prev)
    ids = [1, 2, 3]
    for _ in range(30):
        a, v = draw.draw(ids, prev_bye={1})
        assert v == 0 and draw.pairs_of(a)[1] != 1


def test_soft_rules_can_be_disabled_or_unavoidable():
    a, v = draw.draw([1, 2], prev_pairs={frozenset((1, 2))})
    assert v == 1
    a, v = draw.draw([1, 2], prev_pairs={frozenset((1, 2))}, avoid_repeat=False)
    assert v == 0


def test_manual_validation():
    ids = [1, 2, 3, 4, 5]
    ok = {1: 1, 2: 1, 3: 2, 4: 2, 5: "F"}
    assert draw.validate_manual(ok, ids) == []
    assert draw.validate_manual({1: 1, 2: 1, 3: 1, 4: 2, 5: "F"}, ids)           # ticket 1 used three times
    assert draw.validate_manual({1: 1, 2: 1, 3: 2, 4: 2, 5: 2}, ids)             # F missing
    assert draw.validate_manual({1: "F", 2: 1, 3: 2, 4: 2, 5: "F"}, ids)         # F used twice
    assert draw.validate_manual({1: 1, 2: 1, 3: 2, 4: 2}, ids)                   # one player without a ticket
    assert draw.validate_manual({1: 1, 2: 1, 3: 2, 4: 2, 9: "F"}, ids)           # unknown player
    assert draw.validate_manual({1: 3, 2: 3, 3: 2, 4: 2, 5: "F"}, ids)           # number too large
    assert draw.validate_manual({1: 1, 2: 1, 3: 2, 4: "F"}, [1, 2, 3, 4])        # F with an even player count
