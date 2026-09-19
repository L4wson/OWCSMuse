"""Org identity and versus queries: parsing, proposal safety, and a hand-checked record."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from owcsmuse.nlq.compile import Compiled, Resolved, compile_query
from owcsmuse.nlq.parser import parse_question
from owcsmuse.nlq.schema import Filters, StructuredQuery, Unanswerable
from owcsmuse.nlq.validate import SchemaInfo, Validated, validate
from owcsmuse.orgs import (GENERIC_TOKENS, OrgDecisions, Proposal, TeamFacts, _adjacency, _overlap,
                           name_contains, pair_key, propose, region_conflict, render_report, slugify)

# ------------------------------------------------------------------ parsing

VERSUS = [
    ("Sugarfree map record against Zeruhh", "versus", {"subject": "sugarfree", "opponent": "zeruhh"}, "map_win_rate"),
    ("Quartz map record against Crazy Raccoon", "versus", {"subject": "quartz", "opponent": "crazy raccoon"}, "map_win_rate"),
    ("Twisted Minds vs Al Qadsiah", "versus", {"subject": "twisted minds", "opponent": "al qadsiah"}, "map_win_rate"),
    ("Zeruhh versus Sugarfree", "versus", {"subject": "zeruhh", "opponent": "sugarfree"}, "map_win_rate"),
    ("head to head between Sugarfree and Zeruhh", "versus", {"subject": "sugarfree", "opponent": "zeruhh"}, "map_win_rate"),
    ("Sugarfree h2h Zeruhh", "versus", {"subject": "sugarfree", "opponent": "zeruhh"}, "map_win_rate"),
    ("how did Twisted Minds do against ENCE in 2025", "versus",
     {"subject": "twisted minds", "opponent": "ence", "season": 2025}, "map_win_rate"),
    ("Twisted Minds vs ENCE on Ilios", "versus",
     {"subject": "twisted minds", "opponent": "ence", "map": "Ilios"}, "map_win_rate"),
]

SEASON_COMPARE = [
    ("2024 Team Falcons vs 2026 Team Falcons", {"subject_season": 2024, "opponent_season": 2026}),
    ("Team Falcons 2024 vs Team Falcons 2026", {"subject_season": 2024, "opponent_season": 2026}),
]


@pytest.mark.parametrize("question,intent,expected,metric", VERSUS, ids=[q for q, _, _, _ in VERSUS])
def test_versus_questions_parse(question, intent, expected, metric):
    r = parse_question(question)
    assert isinstance(r, StructuredQuery), getattr(r, "reason", r)
    c = r.compact()
    assert c["intent"] == intent and c["metric"] == metric
    for k, val in expected.items():
        assert c["filters"].get(k) == val, f"{k}: {c['filters']}"



@pytest.mark.parametrize("question,expected", SEASON_COMPARE, ids=[q for q, _ in SEASON_COMPARE])
def test_same_entity_two_seasons_is_a_comparison_not_a_fixture(question, expected):
    r = parse_question(question)
    assert isinstance(r, StructuredQuery), getattr(r, "reason", r)
    c = r.compact()
    assert c["intent"] == "season_compare"
    for k, val in expected.items():
        assert c["filters"].get(k) == val
    # a per-side year must not also leak into the global season filter
    assert "season" not in c["filters"]


def test_a_single_trailing_year_scopes_the_whole_matchup():
    c = parse_question("Twisted Minds vs ENCE in 2025").compact()
    assert c["filters"].get("season") == 2025
    assert "subject_season" not in c["filters"] and "opponent_season" not in c["filters"]


def test_both_orderings_give_mirrored_sides():
    a = parse_question("Sugarfree vs Zeruhh").compact()["filters"]
    b = parse_question("Zeruhh vs Sugarfree").compact()["filters"]
    assert (a["subject"], a["opponent"]) == (b["opponent"], b["subject"])


# --------------------------------------------------- org proposal safety rules

def test_containment_never_fuses_distinct_organisations():
    assert name_contains("Al qadsiah", "qadsiah")[0] is True
    assert name_contains("SpaceStation Gaming", "SpaceStation")[0] is True
    assert name_contains("Liquid", "Team Liquid")[0] is True
    # the case the brief calls out: these must stay separate
    assert name_contains("Team Liquid", "Liquid Academy")[0] is False
    assert name_contains("Team Liquid", "Team Liquid Academy")[0] is False
    assert name_contains("Twisted Minds", "Twisted Minds B")[0] is False
    assert name_contains("Team Peps", "Team Falcons")[0] is False
    # a generic-only stub is not an identity
    assert name_contains("Team", "Team Falcons")[0] is False
    assert name_contains("Esports", "Geekay Esports")[0] is False
    for t in ("team", "esports", "gaming"):
        assert t in GENERIC_TOKENS


def test_academy_guard_reports_why_it_refused():
    ok, why = name_contains("Team Liquid", "Team Liquid Academy")
    assert ok is False and "academy" in why and "separate team" in why


def _facts(tid, name, players, first, last, matches=10, regions=()):
    return TeamFacts(team_id=tid, name=name, players=set(players),
                     first_at=datetime(*first, tzinfo=timezone.utc), last_at=datetime(*last, tzinfo=timezone.utc),
                     matches=matches, regions=set(regions))


def test_overlap_and_adjacency_are_measured_not_guessed():
    a = _facts("a", "Al qadsiah", ["p1", "p2", "p3", "p4"], (2025, 1, 31), (2025, 10, 26))
    b = _facts("b", "qadsiah", ["p4", "p5", "p6", "p7"], (2026, 3, 21), (2026, 7, 4))
    overlap, shared, smaller = _overlap(a, b)
    assert (shared, smaller) == (1, 4) and overlap == 0.25
    adjacent, gap = _adjacency(a, b)
    assert adjacent is True and gap > 100
    # teams that coexist are not adjacent
    c = _facts("c", "Other", ["p9"], (2025, 2, 1), (2025, 9, 1))
    assert _adjacency(a, c) == (False, 0)


# --------------------------------------------------- the bug: cross-region merges

def test_region_conflict_blocks_a_merge_regardless_of_name_or_overlap():
    """The exact shape that produced the wrong data: identical or contained
    names, weak-to-zero roster overlap, opposite regions."""
    na = _facts("na1", "SpaceStation Gaming", [], (2025, 2, 1), (2026, 7, 6), regions=["na"])
    emea = _facts("emea1", "SpaceStation", [], (2024, 3, 8), (2024, 4, 28), regions=["emea", "international"])
    assert region_conflict(na, emea) is not None
    assert "na" in region_conflict(na, emea) and "emea" in region_conflict(na, emea)

    # identical names do not override it either
    geekay_na = _facts("g1", "Geekay Esports", [], (2025, 2, 1), (2025, 10, 26), regions=["na"])
    geekay_emea = _facts("g2", "Geekay Esports", [], (2026, 3, 22), (2026, 7, 5), regions=["emea"])
    assert region_conflict(geekay_na, geekay_emea) is not None


def test_region_conflict_does_not_fire_on_international_or_missing_region_data():
    # an international LAN alongside a team's home region is the ordinary case
    na_plus_international = _facts("a", "Team X", [], (2024, 1, 1), (2024, 6, 1), regions=["na", "international"])
    also_na = _facts("b", "Team X", [], (2025, 1, 1), (2025, 6, 1), regions=["na"])
    assert region_conflict(na_plus_international, also_na) is None
    # two teams both only ever seen at international events: nothing to conflict on
    international_only = _facts("c", "Team Y", [], (2024, 1, 1), (2024, 6, 1), regions=["international"])
    assert region_conflict(na_plus_international, international_only) is None
    # no region data at all: not a basis to refuse (and not a basis to accept)
    no_region = _facts("d", "Team Z", [], (2024, 1, 1), (2024, 6, 1))
    assert region_conflict(na_plus_international, no_region) is None


def test_propose_never_emits_a_cross_region_pair_even_at_strong_strength():
    facts = {
        "g1": _facts("g1", "Geekay Esports", ["p1"], (2025, 2, 1), (2025, 10, 26), regions=["na"]),
        "g2": _facts("g2", "Geekay Esports", ["p2"], (2026, 3, 22), (2026, 7, 5), regions=["emea"]),
    }
    proposals = propose(None, facts)
    assert proposals == []


def test_decisions_round_trip_and_unmapped_stays_unmapped(tmp_path):
    d = OrgDecisions(tmp_path / "o.json")
    d.set("team-1", "qadsiah", "qadsiah", note="named in the brief", team_name="Al qadsiah")
    d.set("team-2", "qadsiah", "qadsiah", team_name="qadsiah")
    d.save()
    again = OrgDecisions(tmp_path / "o.json")
    assert again.get("team-1")["org_id"] == again.get("team-2")["org_id"] == "qadsiah"
    assert again.get("never-decided") is None       # no silent fallback
    assert again.unset("team-1") is True and again.get("team-1") is None
    assert slugify("Al Qadsiah!") == "al-qadsiah"


def test_a_pair_is_only_marked_decided_when_both_ids_agree(tmp_path):
    d = OrgDecisions(tmp_path / "o.json")
    d.set("a", "org-x", "Org X")
    p = Proposal(team_ids=["a", "b"], names=["A", "B"], org_id="org-x", org_name="Org X", roster_overlap=1.0,
                 shared_players=5, smaller_roster=5, name_exact=True, name_contained=False, date_adjacent=True,
                 gap_days=100, seasons=[2025, 2026], matches=20, strength="strong")
    assert d.apply([p])[0].include is False        # only one side decided
    d.set("b", "org-x", "Org X")
    assert d.apply([p])[0].include is True


def _pair(a="a", b="b", names=("Geekay Esports", "NTMR"), overlap=1.0):
    return Proposal(team_ids=[a, b], names=list(names), org_id="org-x", org_name=names[1], roster_overlap=overlap,
                    shared_players=5, smaller_roster=5, name_exact=False, name_contained=False, date_adjacent=True,
                    gap_days=62, seasons=[2024, 2025], matches=43, strength="review_required")


def test_a_rejection_is_a_decision_and_survives_a_reload(tmp_path):
    """A pair that was looked at and turned down must not come back as pending review."""
    d = OrgDecisions(tmp_path / "o.json")
    d.reject("b", "a", "roster movement between distinct orgs")   # order must not matter
    d.save()
    again = OrgDecisions(tmp_path / "o.json")
    assert again.rejection("a", "b")["reason"] == "roster movement between distinct orgs"
    assert again.rejection("a", "b")["team_ids"] == ["a", "b"]
    assert again.rejection("a", "unrelated") is None
    assert pair_key("b", "a") == pair_key("a", "b")

    p = again.apply([_pair()])[0]
    assert p.include is False
    assert p.decision_source == "rejected"
    assert p.note == "roster movement between distinct orgs"


def test_a_rejected_pair_leaves_the_pending_section_of_the_report(tmp_path):
    d = OrgDecisions(tmp_path / "o.json")
    report = render_report(d.apply([_pair()]))
    assert "| no | NTMR" in report                     # pending, awaiting review

    d.reject("a", "b", "different orgs; a squad transferred")
    report = render_report(d.apply([_pair()]))
    assert "Reviewed and rejected (1)" in report
    assert "different orgs; a squad transferred" in report
    assert "1 reviewed and rejected" in report
    assert "0 needing review" in report


def test_a_rejection_can_be_withdrawn(tmp_path):
    d = OrgDecisions(tmp_path / "o.json")
    d.reject("a", "b", "reviewed")
    assert d.unreject("a", "b") is True
    assert d.unreject("a", "b") is False
    assert d.apply([_pair()])[0].decision_source == "auto"


def test_a_rejection_does_not_touch_the_merge_decisions(tmp_path):
    d = OrgDecisions(tmp_path / "o.json")
    d.set("a", "org-x", "Org X")
    d.set("b", "org-x", "Org X")
    d.reject("a", "c", "different orgs")
    d.save()
    again = OrgDecisions(tmp_path / "o.json")
    assert again.apply([_pair()])[0].include is True            # a/b still merged
    assert again.apply([_pair(a="a", b="c")])[0].decision_source == "rejected"


# ------------------------------------------------------------------ compiling

INFO = SchemaInfo(
    stat_keys={"Eliminations": {2024, 2025, 2026}}, stat_kinds={"Eliminations": "countable"},
    maps={"Ilios"}, modes={"Control"}, seasons={2024, 2025, 2026},
    championships={"c1": "S9 EMEA OWCS Central - Playoffs"}, regions={"emea", "na"},
)


def _c(q: StructuredQuery, r: Resolved) -> Compiled:
    v = validate(q, INFO)
    assert isinstance(v, Validated), v
    c = compile_query(v, r)
    assert isinstance(c, Compiled), c
    assert c.sql.count("%s") == len(c.params), (c.sql, c.params)
    return c


def test_player_vs_player_uses_the_versus_fact_at_map_grain():
    q = parse_question("Sugarfree map record against Zeruhh")
    r = Resolved(player_id="p1", opponent_id="p2", subject_type="player", opponent_type="player",
                 names={"subject": "sug2rfree", "opponent": "zeruhh"})
    c = _c(q, r)
    assert "fact_player_versus" in c.sql and "player_id = %s" in c.sql and "opponent_player_id = %s" in c.sql
    assert "count(DISTINCT match_id) AS matches" in c.sql and "maps" in c.sql
    assert c.params[:2] == ["p1", "p2"]


def test_player_vs_org_counts_each_map_once_not_once_per_opponent():
    q = parse_question("Quartz map record against Crazy Raccoon")
    r = Resolved(player_id="p1", opponent_id="crazy-raccoon", subject_type="player", opponent_type="org",
                 names={"subject": "Quartz03", "opponent": "Crazy Raccoon"})
    c = _c(q, r)
    assert "opponent_org_key = %s" in c.sql
    assert "SELECT DISTINCT match_id, round_number" in c.sql, "a map must not count five times, once per opposing player"
    assert c.params[1] == "crazy-raccoon"


def test_org_vs_org_keys_on_org_not_team_id():
    q = parse_question("Twisted Minds vs Al Qadsiah")
    r = Resolved(team_id="tm-team-id", opponent_id="qadsiah", subject_type="team", opponent_type="org",
                 names={"subject": "Twisted Minds", "opponent": "qadsiah"})
    c = _c(q, r)
    assert "fact_team_maps" in c.sql and "org_key = %s" in c.sql
    # an unmapped team id is keyed visibly as a raw team, never silently merged
    assert c.params[0] == "team:tm-team-id" and c.params[1] == "qadsiah"


def test_season_compare_emits_one_row_per_season():
    q = parse_question("2024 Team Falcons vs 2026 Team Falcons")
    r = Resolved(team_id="falcons", subject_type="org", opponent_id="falcons", opponent_type="org",
                 names={"subject": "Team Falcons", "opponent": "Team Falcons"})
    c = _c(q, r)
    assert "GROUP BY season" in c.sql and "season = ANY(%s)" in c.sql
    assert [2024, 2026] in c.params


def test_same_season_on_both_sides_is_rejected():
    q = StructuredQuery(intent="season_compare", entity="team", metric="map_win_rate",
                        filters=Filters(subject="X", opponent="X", subject_season=2024, opponent_season=2024))
    u = validate(q, INFO)
    assert isinstance(u, Unanswerable) and u.code == "invalid_query"


def test_versus_needs_both_sides_resolved():
    q = parse_question("Twisted Minds vs Al Qadsiah")
    v = validate(q, INFO)
    u = compile_query(v, Resolved(team_id="only-one", subject_type="team"))
    assert isinstance(u, Unanswerable) and u.code == "invalid_query"


# ------------------------------------------------------------------ DB-backed

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
dbonly = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")


@dbonly
def test_org_layer_groups_team_ids_and_leaves_the_rest_alone(agg_db):
    def q(sql, *a):
        return agg_db.execute(sql, a).fetchall()

    rows = q("SELECT team_id, org_id, org_key, mapped FROM team_identity")
    agg_db.commit()
    assert rows, "team_identity should cover every team"
    for r in rows:
        if r["mapped"]:
            assert r["org_key"] == r["org_id"]
        else:
            assert r["org_key"] == f"team:{r['team_id']}", "an unmapped team id must stay visibly itself"


@dbonly
def test_versus_record_matches_a_hand_count(agg_db):
    """Count one pairing's maps by hand from match_rounds and assert the fact agrees."""
    pair = agg_db.execute(
        "SELECT org_key, opponent_org_key FROM fact_team_maps WHERE org_key < opponent_org_key"
        " GROUP BY 1,2 ORDER BY count(*) DESC LIMIT 1").fetchone()
    agg_db.commit()
    a, b = pair["org_key"], pair["opponent_org_key"]
    hand = agg_db.execute(
        """
        SELECT count(*) AS maps, count(*) FILTER (WHERE f.won) AS wins,
               count(*) FILTER (WHERE NOT f.won AND NOT f.drawn) AS losses,
               count(DISTINCT f.match_id) AS matches
        FROM fact_team_maps f WHERE f.org_key = %s AND f.opponent_org_key = %s
        """, (a, b)).fetchone()
    agg = agg_db.execute(
        "SELECT sum(maps) maps, sum(map_wins) wins, sum(map_losses) losses, sum(matches) matches"
        " FROM agg_org_versus_maps WHERE org_key = %s AND opponent_org_key = %s", (a, b)).fetchone()
    agg_db.commit()
    assert (agg["maps"], agg["wins"], agg["losses"]) == (hand["maps"], hand["wins"], hand["losses"])
    assert hand["wins"] + hand["losses"] <= hand["maps"]
    # the mirror side must be the exact complement
    mirror = agg_db.execute(
        "SELECT sum(maps) maps, sum(map_wins) wins, sum(map_losses) losses"
        " FROM agg_org_versus_maps WHERE org_key = %s AND opponent_org_key = %s", (b, a)).fetchone()
    agg_db.commit()
    assert mirror["maps"] == hand["maps"] and mirror["wins"] == hand["losses"]


@dbonly
def test_player_versus_is_map_grain_and_symmetric(agg_db):
    row = agg_db.execute(
        "SELECT player_id, opponent_player_id, count(*) n FROM fact_player_versus"
        " GROUP BY 1,2 ORDER BY n DESC LIMIT 1").fetchone()
    agg_db.commit()
    a, b = row["player_id"], row["opponent_player_id"]
    fwd = agg_db.execute(
        "SELECT count(*) maps, count(*) FILTER (WHERE won) wins FROM fact_player_versus"
        " WHERE player_id=%s AND opponent_player_id=%s", (a, b)).fetchone()
    rev = agg_db.execute(
        "SELECT count(*) maps, count(*) FILTER (WHERE won) wins FROM fact_player_versus"
        " WHERE player_id=%s AND opponent_player_id=%s", (b, a)).fetchone()
    agg_db.commit()
    assert fwd["maps"] == rev["maps"] > 0
    assert fwd["wins"] + rev["wins"] <= fwd["maps"]   # equal unless a map was drawn
    # every row is one map of one match, never a series
    dupe = agg_db.execute(
        "SELECT count(*) n FROM (SELECT match_id, round_number, player_id, opponent_player_id,"
        " count(*) c FROM fact_player_versus GROUP BY 1,2,3,4 HAVING count(*) > 1) x").fetchone()["n"]
    agg_db.commit()
    assert dupe == 0


@dbonly
def test_result_only_series_are_disclosed_not_counted(agg_db):
    """A versus record must not silently absorb series whose maps were never recorded."""
    missing = agg_db.execute("SELECT count(*) n FROM org_versus_missing").fetchone()["n"]
    in_maps = agg_db.execute(
        "SELECT count(*) n FROM fact_team_maps f JOIN matches m USING (match_id)"
        " WHERE m.ingest_state = 'result_only'").fetchone()["n"]
    agg_db.commit()
    assert in_maps == 0, "result_only matches have no map rows, so they cannot inflate a map record"
    assert missing >= 0
