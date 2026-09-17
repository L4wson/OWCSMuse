"""Pure ranking tests for the entity resolver (no database)."""

from owcsmuse.resolve import fold, rank_candidates, score_name

NAMES = [
    {"entity_type": "player", "entity_id": "p1", "name": "KSAA0", "name_kind": "current_nickname", "current_name": "KSAA0"},
    {"entity_type": "player", "entity_id": "p1", "name": "KSAA", "name_kind": "game_name", "current_name": "KSAA0"},
    {"entity_type": "player", "entity_id": "p2", "name": "kellemanden", "name_kind": "current_nickname", "current_name": "kellemanden"},
    {"entity_type": "player", "entity_id": "p3", "name": "Youbi1", "name_kind": "current_nickname", "current_name": "Youbi1"},
    {"entity_type": "player", "entity_id": "p3", "name": "Youbi_OW", "name_kind": "historical_nickname", "current_name": "Youbi1"},
    {"entity_type": "player", "entity_id": "p4", "name": "Skairipa00", "name_kind": "current_nickname", "current_name": "Skairipa00"},
    {"entity_type": "team", "entity_id": "t1", "name": "Twisted Minds", "name_kind": "current_name", "current_name": "Twisted Minds"},
    {"entity_type": "team", "entity_id": "t2", "name": "Ex Oblivione", "name_kind": "current_name", "current_name": "Ex Oblivione"},
    {"entity_type": "team", "entity_id": "t3", "name": "Café Ñandú", "name_kind": "current_name", "current_name": "Café Ñandú"},
    {"entity_type": "team", "entity_id": "t3", "name": "Old Café", "name_kind": "historical_name", "current_name": "Café Ñandú"},
]


def test_fold_is_case_and_accent_insensitive():
    assert fold("Café Ñandú") == "cafe nandu"
    assert fold("ESPERANÇA") == "esperanca"
    assert fold("  Twisted-Minds!! ") == "twisted minds"
    assert fold(None) == ""


def test_exact_then_prefix_then_substring_scores():
    assert score_name("ksaa", "ksaa") == 1.0
    assert score_name("ksaa", "ksaa0") == 0.9
    assert score_name("saa", "ksaa0") == 0.8
    assert score_name("twistedminds", "twisted minds") == 0.95
    assert score_name("zzz", "ksaa0") < 0.5


def test_player_resolves_via_game_name_and_current_nickname():
    cands = rank_candidates("KSAA", NAMES, limit=3)
    assert cands[0].entity_id == "p1" and cands[0].score == 1.0
    assert cands[0].current_name == "KSAA0"
    assert cands[0].matched_name in ("KSAA", "KSAA0")


def test_historical_nickname_still_resolves_to_current_entity():
    cands = rank_candidates("youbi_ow", NAMES)
    assert cands[0].entity_id == "p3" and cands[0].name_kind == "historical_nickname"
    assert cands[0].current_name == "Youbi1"


def test_team_accent_insensitive_and_history():
    cands = rank_candidates("cafe nandu", [n for n in NAMES if n["entity_type"] == "team"])
    assert cands[0].entity_id == "t3" and cands[0].score == 1.0
    cands = rank_candidates("old cafe", [n for n in NAMES if n["entity_type"] == "team"])
    assert cands[0].entity_id == "t3" and cands[0].name_kind == "historical_name"


def test_fuzzy_typo_and_threshold():
    cands = rank_candidates("kelemanden", NAMES)  # missing an l
    assert cands and cands[0].entity_id == "p2" and 0.5 <= cands[0].score < 1.0
    assert rank_candidates("completely unrelated", NAMES) == []


def test_one_candidate_per_entity_and_limit():
    cands = rank_candidates("a", NAMES, limit=50, min_score=0.0)
    ids = [(c.entity_type, c.entity_id) for c in cands]
    assert len(ids) == len(set(ids))
    assert len(rank_candidates("a", NAMES, limit=2, min_score=0.0)) == 2
