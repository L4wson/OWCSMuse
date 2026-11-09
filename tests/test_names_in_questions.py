"""Names in questions (2026-11-05): one closed list of words that are never names, one extractor, filters read around
names. Offline: the warehouse's names are given as a KnownNames, as the pipeline passes them."""

from __future__ import annotations

import pytest

from owcsmuse.nlq.parser import parse_question
from owcsmuse.nlq.schema import StructuredQuery
from owcsmuse.nlq.words import KnownNames, name_in, only_listed

# real names from the warehouse (2026-11-05) that begin, end or consist of a listed word, and two aliases
KNOWN = KnownNames(["All Gamers Global", "All Gamers", "The Kafe", "Students of the Game", "A One Man Army", "Once Again",
                    "Anyone's Legend", "Anyones Legend", "Who Is Goldfish", "nah id win", "Someone", "One",
                    "Team Liquid", "Wasp X Ohhhh No", "The Ultimates", "Piece of Cake", "Fries In The Bag",
                    "Peace and Love", "Pirates in Pyjamas", "Dallas Fuel", "Twisted Minds", "SpaceStation Gaming",
                    "gk emea", "ssg"])


def _name(q, known=KNOWN):
    r = parse_question(q, known)
    assert isinstance(r, StructuredQuery), getattr(r, "reason", r)
    f = r.filters
    return f.subject or f.team or f.player


@pytest.mark.parametrize("name", ["All Gamers Global", "The Kafe", "Students of the Game", "A One Man Army", "Once Again",
                                  "Anyone's Legend", "Who Is Goldfish", "nah id win", "Someone", "Team Liquid",
                                  "Wasp X Ohhhh No", "Piece of Cake", "Fries In The Bag", "GK EMEA"])
@pytest.mark.parametrize("shape", ["{} record", "{} record in 2025 NA", "NA 2025 {} record", "{} record in 2026 EMEA stage 3"])
def test_a_real_name_with_a_listed_word_is_read_whole(name, shape):
    assert _name(shape.format(name)).lower() == name.lower()


@pytest.mark.parametrize("q", ["highest kd of any player", "highest kd of all players", "best kd among players",
                               "best kd among all players in 2026", "kd of every player in 2026",
                               "most healing of any support in 2026", "highest kd of anyone",
                               "which team has the best win rate of any team"])
def test_a_quantifier_or_filler_word_is_never_a_name(q):
    assert _name(q) is None


@pytest.mark.parametrize("q,name", [
    ("Dallas Fuel record in 2026 NA stage 3", "dallas fuel"),
    ("NA 2026 Dallas Fuel record", "dallas fuel"),
    ("Dallas Fuel 2026 NA record", "dallas fuel"),
    ("sugarfree kd in 2025 NA", "sugarfree"),
    ("Dallas Fuel record for north america in 2025", "dallas fuel"),
])
def test_a_region_or_year_beside_a_name_is_a_filter_wherever_it_stands(q, name):
    assert _name(q) == name


def test_a_region_or_year_after_the_opponent_is_a_filter():
    r = parse_question("Dallas Fuel vs Twisted Minds in 2025 NA", KNOWN)
    assert (r.filters.subject, r.filters.opponent, r.filters.season, r.filters.region) == \
        ("dallas fuel", "twisted minds", 2025, "na")


def test_without_the_warehouses_names_a_listed_word_is_trimmed_but_never_a_name_alone():
    # the parser alone, as offline tests and the LLM fallback see it: the edges go, the middle stays
    assert name_in("the kafe".split()) == "kafe"
    assert name_in("students of the game".split()) == "students of the game"
    assert name_in("among all".split()) is None
    assert only_listed("any") and only_listed("among all") and not only_listed("anyones legend")
    # a known name made only of listed words is kept when the question says exactly that, never inside a longer piece
    assert name_in(["someone"], KNOWN) == "someone"
    assert name_in("highest of someone".split(), KNOWN) is None
