"""Answer sentences: fixed templates, reproducible text, and no number that is not in the rows."""

import re
from decimal import Decimal

from owcsmuse.nlq.sentence import num, pct, render_sentence, render_unanswerable, seasons_phrase

VERSUS_Q = {"intent": "versus", "entity": "player", "metric": "map_win_rate", "filters": {}}
VERSUS_ROW = {"subject": "sug2rfree", "opponent": "zeruhh", "maps": 42, "matches": 9, "map_wins": 22,
              "map_losses": 20, "draws": 0, "map_win_pct": Decimal("52.4"), "seasons": [2024, 2025, 2026]}
ENTITIES = {
    "subject": {"entity_id": "p1", "entity_type": "player", "current_name": "sug2rfree"},
    "opponent": {"entity_id": "p2", "entity_type": "player", "current_name": "zeruhh"},
}


def test_the_versus_sentence_is_the_one_from_the_brief():
    s = render_sentence(VERSUS_Q, [VERSUS_ROW], ENTITIES)
    assert s.text == "sug2rfree is 22-20 in maps against zeruhh across 2024-2026."


def test_entities_are_marked_where_they_actually_are():
    s = render_sentence(VERSUS_Q, [VERSUS_ROW], ENTITIES)
    assert [(sp.text, sp.kind, sp.entity_id) for sp in s.spans] == [
        ("sug2rfree", "player", "p1"), ("zeruhh", "player", "p2")]
    for sp in s.spans:                       # offsets must index the text they claim
        assert s.text[sp.start:sp.end] == sp.text


def test_the_same_rows_always_produce_the_same_sentence():
    first = render_sentence(VERSUS_Q, [VERSUS_ROW], ENTITIES)
    for _ in range(5):
        again = render_sentence(VERSUS_Q, [dict(VERSUS_ROW)], dict(ENTITIES))
        assert again.text == first.text and [s.as_dict() for s in again.spans] == [s.as_dict() for s in first.spans]


def _numbers(sentence) -> set[str]:
    """Digit groups in the prose, with entity mentions blanked out.

    A nickname can contain digits (sug2rfree), and those are part of a name, not
    a claim about the data.
    """
    text = list(sentence.text)
    for sp in sentence.spans:
        if sp.kind not in ("season",):
            text[sp.start:sp.end] = [" "] * (sp.end - sp.start)
    return {t.replace(",", "") for t in re.findall(r"\d[\d,]*(?:\.\d+)?", "".join(text))}


def _row_numbers(row: dict) -> set[str]:
    out = set()
    for value in row.values():
        if isinstance(value, (list, tuple)):
            out |= {str(v) for v in value}
            if value and all(isinstance(v, int) for v in value):
                out |= {str(min(value)), str(max(value))}
        elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            out |= {num(value).replace(",", ""), pct(value).rstrip("%"), str(value)}
    return out


def test_no_number_in_a_sentence_is_invented():
    """Every digit group in the text has to come from the row it was built from."""
    cases = [
        (VERSUS_Q, [VERSUS_ROW]),
        ({"intent": "leaderboard", "entity": "player", "metric": "Final Blows", "filters": {}, "aggregation": "total"},
         [{"nickname": "IHaveLethal", "player_id": "p9", "total": 1471, "maps_with_stat": 165, "maps_played": 197,
           "avg_per_map": Decimal("8.92"), "seasons": [2025, 2026]}]),
        ({"intent": "team_record", "entity": "team", "metric": "record", "filters": {}},
         [{"team": "Twisted Minds", "org_key": "team:x", "matches": 65, "wins": 46, "losses": 19, "map_wins": 157,
           "map_losses": 78, "maps": 195, "win_pct": Decimal("70.8"), "seasons": [2024, 2025, 2026]}]),
        ({"intent": "entity_stat", "entity": "player", "metric": "Eliminations", "filters": {"season": 2024},
          "aggregation": "total"},
         [{"nickname": "KSAA0", "total": 710, "maps_with_stat": 35, "maps_played": 35, "seasons": [2024]}]),
    ]
    for query, rows in cases:
        s = render_sentence(query, rows, ENTITIES)
        assert s is not None, query["intent"]
        allowed = _row_numbers(rows[0]) | {str(len(rows) - 1)}
        for n in _numbers(s):
            assert n in allowed, f"{query['intent']}: {n} is not in the row: {s.text}"


def test_a_missing_number_shortens_the_sentence_instead_of_filling_it_in():
    row = {"subject": "a", "opponent": "b", "seasons": [2025]}      # no wins/losses at all
    assert render_sentence(VERSUS_Q, [row], ENTITIES) is None
    partial = dict(VERSUS_ROW)
    del partial["map_win_pct"]
    assert render_sentence(VERSUS_Q, [partial], ENTITIES).text.endswith("across 2024-2026.")


def test_draws_appear_only_when_there_are_any():
    with_draw = dict(VERSUS_ROW, draws=1)
    assert "22-20-1" in render_sentence(VERSUS_Q, [with_draw], ENTITIES).text
    assert "22-20." in render_sentence(VERSUS_Q, [VERSUS_ROW], ENTITIES).text or \
           "22-20 " in render_sentence(VERSUS_Q, [VERSUS_ROW], ENTITIES).text


def test_an_ascending_sort_does_not_claim_the_lead():
    q = {"intent": "leaderboard", "entity": "player", "metric": "Deaths", "filters": {}, "sort": "asc",
         "aggregation": "total"}
    row = {"nickname": "careful", "player_id": "p3", "total": 40, "maps_with_stat": 20, "seasons": [2026]}
    assert "has the lowest" in render_sentence(q, [row]).text


def test_season_phrases_read_like_english():
    assert seasons_phrase([2025]) == "in 2025"
    assert seasons_phrase([2024, 2025, 2026]) == "across 2024-2026"
    assert seasons_phrase([2024, 2026]) == "across 2024 and 2026"
    assert seasons_phrase([2024, 2026, 2028]) == "across 2024, 2026 and 2028"
    assert seasons_phrase(None) == ""
    assert seasons_phrase(2024) == "in 2024"


def test_numbers_are_formatted_for_people():
    assert num(1471) == "1,471"
    assert num(Decimal("8.920")) == "8.92"
    assert num(Decimal("42.00")) == "42"
    assert num(None) == "0"
    assert pct(Decimal("52.4")) == "52.4%"
    assert pct(Decimal("75.0")) == "75%"


def test_a_refusal_is_a_sentence_with_its_entities_marked():
    s = render_unanswerable("Quartz03 and Crazy Raccoons never faced each other in the competitions in scope",
                            {"subject": {"entity_id": "p1", "entity_type": "player", "current_name": "Quartz03"}})
    assert s.text.endswith("in scope.")
    assert s.spans and s.text[s.spans[0].start:s.spans[0].end] == "Quartz03"


def test_an_intent_with_no_template_returns_nothing_rather_than_guessing():
    assert render_sentence({"intent": "not_an_intent"}, [{"a": 1}]) is None
    assert render_sentence(VERSUS_Q, []) is None


def test_a_leaderboard_sentence_quotes_the_metrics_own_column():
    # every row also carries the columns that used to win: map_win_pct, win_pct, total. Attack's K/D (5.00) was once
    # printed as his map win % (77.80); Dallas Fuel's series won (14) as its win % (87.5); a per-map average as the total.
    base = {"nickname": "P", "player_id": "p1", "maps": 9, "map_win_pct": Decimal("77.8"), "win_pct": Decimal("87.5"),
            "total": 144, "seasons": [2026]}
    cases = [({"metric": "kd_ratio"}, {"kd_ratio": Decimal("5.00")}, "with 5 across"),
             ({"metric": "Eliminations", "aggregation": "avg_per_map"}, {"avg_per_map": Decimal("28.8")}, "at 28.80 per map"),
             ({"metric": "map_losses"}, {"map_losses": 3}, "with 3 across")]
    for q, extra, want in cases:
        s = render_sentence({"intent": "leaderboard", "entity": "player", "filters": {}, "sort": "desc", **q}, [{**base, **extra}])
        assert want in s.text, (q, s.text)
    team = {"team": "Dallas Fuel", "org_key": "dallas-fuel", "matches": 16, "wins": 14, "losses": 2, "maps": 61,
            "win_pct": Decimal("87.5"), "seasons": [2026]}
    s = render_sentence({"intent": "leaderboard", "entity": "team", "metric": "wins", "filters": {}, "sort": "desc"}, [team])
    assert "with 14 across" in s.text, s.text


def test_a_team_or_role_leaderboard_names_the_players_it_ranked():
    # a leaderboard that applied "which TM tank" must not read like one that dropped it
    row = {"player_id": "p1", "nickname": "TVNT", "total": 184, "maps_with_stat": 37, "seasons": [2026]}
    q = {"intent": "leaderboard", "entity": "player", "metric": "Deaths", "sort": "desc", "filters": {"season": 2026}}
    team = {"team": {"entity_type": "team", "entity_id": "t1", "current_name": "Twisted Minds"}}
    s = render_sentence(dict(q, filters={"season": 2026, "role": "Tank"}), [row], team)
    assert s.text.startswith("TVNT leads Deaths among Twisted Minds tanks with 184")
    assert [(sp.kind, sp.text) for sp in s.spans if sp.kind == "team"] == [("team", "Twisted Minds")]
    assert render_sentence(q, [row], team).text.startswith("TVNT leads Deaths among Twisted Minds players with 184")
    assert render_sentence(dict(q, filters={"role": "Support"}), [row], {}).text.startswith("TVNT leads Deaths among supports")
    assert render_sentence(q, [row], {}).text.startswith("TVNT leads Deaths with 184")



def test_a_tie_at_the_top_is_a_shared_lead_not_whoever_sorted_first():
    from owcsmuse.nlq.sentence import render_sentence
    rows = [{"team": "Dallas Fuel", "org_key": "dallas-fuel", "wins": 17, "matches": 21, "maps": 75},
            {"team": "Twisted Minds", "org_key": "team:tm", "wins": 17, "matches": 21, "maps": 80},
            {"team": "SpaceStation Gaming", "org_key": "ssg", "wins": 14, "matches": 20, "maps": 70}]
    text = render_sentence({"intent": "leaderboard", "metric": "wins", "filters": {"season": 2026}}, rows).text
    assert text.startswith("Dallas Fuel and Twisted Minds share the lead in series won with 17")
    assert "across" not in text.split(" in 2026")[0]          # no one leader's map sample for two
    assert "ahead of 1 other shown" in text


# ------------------------------------------------------------------ undefeated and filters (2026-10-17, owner)

H2H_Q = {"intent": "head_to_head", "entity": "team", "metric": "record", "filters": {"season": 2026}}


def test_an_unbeaten_series_record_says_so():
    s = render_sentence(H2H_Q, [{"team": "sugarfree", "opponent": "zeruhh", "wins": 5, "losses": 0, "map_wins": 15,
                                 "map_losses": 5, "seasons": [2026]}], ENTITIES)
    assert s.text == "sugarfree is undefeated against zeruhh in 2026 (5-0 in series), 15-5 in maps."


def test_a_record_with_a_loss_is_a_plain_score():
    s = render_sentence(H2H_Q, [{"team": "zeruhh", "opponent": "sugarfree", "wins": 0, "losses": 5, "map_wins": 5,
                                 "map_losses": 15, "seasons": [2026]}], ENTITIES)
    assert s.text.startswith("zeruhh is 0-5 in series against")


def test_an_unbeaten_map_record_with_a_draw_is_not_undefeated_in_words():
    row = dict(VERSUS_ROW, map_wins=3, map_losses=0, draws=1)
    assert "undefeated" not in render_sentence(VERSUS_Q, [row], ENTITIES).text
    assert "undefeated in maps against zeruhh" in render_sentence(VERSUS_Q, [dict(row, draws=0)], ENTITIES).text


def test_a_mode_filter_is_named_and_marked():
    q = {"intent": "entity_stat", "entity": "player", "metric": "map_win_rate", "filters": {"mode": "Push"}}
    s = render_sentence(q, [{"nickname": "sugarfree", "map_wins": 28, "map_losses": 17, "map_win_pct": Decimal("62.2"),
                             "maps": 45, "seasons": [2024, 2025, 2026]}], {"subject": ENTITIES["subject"]})
    assert s.text == "sugarfree is 28-17 on Push maps, a 62.2% map win rate across 45 maps in 2024-2026."
    assert [(sp.kind, sp.text) for sp in s.spans if sp.kind == "mode"] == [("mode", "Push")]


def test_a_map_filter_on_a_versus_record_is_named():
    q = dict(VERSUS_Q, filters={"map": "Ilios"})
    assert " against zeruhh on Ilios across 2024-2026" in render_sentence(q, [VERSUS_ROW], ENTITIES).text


def test_a_season_after_a_maps_count_is_not_a_second_across():
    q = {"intent": "entity_stat", "entity": "player", "metric": "Eliminations", "filters": {}}
    s = render_sentence(q, [{"nickname": "zeruhh", "total": 290, "maps": 15, "seasons": [2024, 2025]}],
                        {"subject": ENTITIES["opponent"]})
    assert "across 15 maps in 2024-2025" in s.text and s.text.count("across") == 1
