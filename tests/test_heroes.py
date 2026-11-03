"""The hero list (049) and how a Liquipedia game's bans are read: offline, no database."""

from __future__ import annotations

import json

import pytest

from owcsmuse import heroes
from owcsmuse.liquipedia.matches import bans_of, parse_row


def test_every_known_spelling_reaches_one_canonical_name():
    hl = heroes.load_file()
    # FACEIT's spellings, Liquipedia's, and what people type
    for typed, canon in [("DVa", "D.Va"), ("d.va", "D.Va"), ("d va", "D.Va"), ("LifeWeaver", "Lifeweaver"),
                         ("Lucio", "Lúcio"), ("Torbjorn", "Torbjörn"), ("Soldier 76", "Soldier: 76"),
                         ("Soldier: 76", "Soldier: 76"), ("JETPACK CAT", "Jetpack Cat"), ("D.Mon", "D.Mon")]:
        assert hl.canonical(typed) == canon, typed
    # a name the list does not hold is kept as given, for the consistency check to name
    assert hl.canonical("Not A Hero") == "Not A Hero"


def test_the_reviewed_file_is_internally_consistent():
    doc = json.loads(open(heroes.ROOT / heroes.HEROES_PATH, encoding="utf-8").read())
    hl = heroes.load_file()
    assert doc["bans_introduced_season"] == 2025 == hl.bans_introduced_season
    assert len({h.name for h in hl.heroes}) == len(hl.heroes)
    for h in doc["heroes"]:
        if h["basis"] == "owner":
            # an owner-accepted date is the first evidence of the hero, inside the bracket the stored data allows
            lo, hi = h["window"]
            assert lo < h["available_from"] <= hi, h["name"]
            assert h["evidence"]
        else:
            assert h["available_from"] is None, h["name"]


def test_two_heroes_answering_to_one_spelling_is_an_error(tmp_path):
    p = tmp_path / "heroes.json"
    p.write_text(json.dumps({"heroes": [{"name": "D.Va", "aliases": []}, {"name": "DVa", "aliases": []}]}))
    with pytest.raises(ValueError, match="names both"):
        heroes.load_file(p)


def test_a_missing_file_is_an_error_not_an_empty_list(tmp_path):
    # `migrate` loads the list on every deploy: run from a directory without scope/, it must not delete every hero
    with pytest.raises(FileNotFoundError):
        heroes.load(None, tmp_path / "absent.json")


def test_a_games_bans_are_read_from_extradata_by_team():
    game = {"map": "Ilios", "extradata": {"banstart": 2, "team1ban1": "Freja", "team2ban1": "Jetpack Cat",
                                          "team1ban2": "", "dateexact": True, "timestamp": 1}}
    assert bans_of(game) == ((1, "Freja"), (2, "Jetpack Cat"))
    assert bans_of({"map": "Ilios"}) == ()
    assert bans_of({"extradata": {"team1ban1": "  "}}) == ()


def test_a_parsed_record_carries_each_played_games_bans_and_who_banned_first():
    row = {"match2opponents": [{"name": "A", "type": "team", "score": 2}, {"name": "B", "type": "team", "score": 0}],
           "winner": "1", "pagename": "P", "objectname": "1_x", "match2id": "x", "match2bracketid": "b",
           "date": "2025-05-10 12:00:00", "finished": 1, "bestof": 3,
           "match2games": [
               {"map": "Ilios", "scores": [2, 0], "winner": "1",
                "extradata": {"banstart": 1, "team1ban1": "Kiriko", "team2ban1": "D.Va"}},
               {"map": "Dorado", "scores": [3, 2], "winner": "1",
                "extradata": {"banstart": 2, "team1ban1": "Tracer", "team2ban1": "Sigma"}},
               {"map": "", "scores": [], "status": "notplayed", "resulttype": "np",
                "extradata": {"team1ban1": "Mercy", "team2ban1": "Ana"}}]}
    m = parse_row(row, raw_id=1)
    assert [g.bans for g in m.games] == [((1, "Kiriko"), (2, "D.Va")), ((1, "Tracer"), (2, "Sigma"))]
    assert [g.banstart for g in m.games] == [1, 2]
