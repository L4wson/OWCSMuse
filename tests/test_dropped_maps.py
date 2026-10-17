"""Maps FACEIT's /stats dropped: recovered only where Liquipedia's record of the series has the same game (045).

The entries are copied from real detailed_results payloads. Two of them look like maps and are not on Liquipedia's
record of their series: a 0-0 "win", and the phantom 1-0 "Dorado" of a 2024 grand final - which a rule on the score
alone would have recovered.
"""

from owcsmuse.liquipedia.enrich import dropped_positions, judge
from owcsmuse.liquipedia.matches import LPGame


def entry(winner, s1, s2):
    return {"winner": winner, "factions": {"faction1": {"score": s1}, "faction2": {"score": s2}}, "asc_score": False}


# 1-1d2eaf73 (Team Liquid 3-1 SpaceStation, 2025-05-10): /stats returned rounds 2-4 only
LIQUID_SSG = [entry("faction2", 1, 2), entry("faction1", 2, 1), entry("faction1", 2, 1), entry("faction1", 3, 0)]
# 1-172bc582 (Extinction 1-3 SpaceStation): four maps and an empty fifth slot
EXTINCTION_SSG = [entry("faction2", 0, 2), entry("faction2", 0, 1), entry("faction1", 1, 0), entry("faction2", 1, 3),
                  {"winner": "", "factions": {}, "asc_score": False}]


def test_only_positions_stats_did_not_return_and_that_have_a_winner():
    assert [n for n, _ in dropped_positions(LIQUID_SSG, {2, 3, 4})] == [1]
    assert [n for n, _ in dropped_positions(EXTINCTION_SSG, {1, 2, 3})] == [4]   # the empty slot is no map
    assert dropped_positions(LIQUID_SSG, {1, 2, 3, 4}) == []
    assert dropped_positions(None, set()) == []


def test_corroborated_map_is_recovered_with_sides_flipped():
    # Liquipedia lists SpaceStation first (side 1 = FACEIT faction2): its winner 1 is FACEIT's faction2
    ilios = LPGame(map="Ilios", mode="Control", winner=1, scores=(2, 1))
    assert judge(1, LIQUID_SSG[0], "Ilios", aligned=True, flip=True, game=ilios) == "recovered"
    assert judge(1, LIQUID_SSG[0], "Ilios", aligned=True, flip=False, game=ilios) == "winner_differs"


def test_entries_liquipedia_does_not_list_are_not_maps():
    # 1-c5823143 Twisted Minds 5-1 ENCE: entry 6 is a 0-0 "win"; Liquipedia has 5 games
    assert judge(6, entry("faction1", 0, 0), "Ilios", aligned=True, flip=False, game=None) == "not_on_liquipedia"
    # 1-70cff415 Toronto Defiant v Timeless: FACEIT 5-0 with a phantom 1-0 "Dorado"; Liquipedia has 4 games (4-0)
    assert judge(5, entry("faction1", 1, 0), "Dorado", aligned=True, flip=False, game=None) == "not_on_liquipedia"


def test_a_different_map_or_unknown_order_is_not_recovered():
    game = LPGame(map="Busan", mode="Control", winner=1, scores=(2, 0))
    assert judge(1, entry("faction1", 2, 0), "Nepal", aligned=True, flip=False, game=game) == "map_differs"
    assert judge(1, entry("faction1", 2, 0), None, aligned=False, flip=False, game=game) == "picks_unaligned"
    assert judge(1, entry("faction1", 2, 0), "Busan", aligned=True, flip=None, game=game) == "cannot_orient"
    assert judge(1, entry("faction1", 2, 0), "Busan", aligned=True, flip=False, game=game) == "recovered"


def test_map_names_fold():
    game = LPGame(map="Paraíso", mode="Hybrid", winner=2, scores=(1, 2))
    assert judge(2, entry("faction2", 1, 2), "Paraiso", aligned=True, flip=False, game=game) == "recovered"


def test_a_drawn_liquipedia_game_never_confirms_a_winner():
    game = LPGame(map="Busan", mode="Control", winner=0, scores=(1, 1))
    assert judge(1, entry("faction1", 2, 0), "Busan", aligned=True, flip=False, game=game) == "winner_differs"
