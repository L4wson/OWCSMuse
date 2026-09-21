"""One regression test per fixed bug, so none of them can come back quietly."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from owcsmuse.nlq.pipeline import _fmt
from owcsmuse.nlq.schema import StructuredQuery, Unanswerable
from owcsmuse.nlq.validate import SchemaInfo, Validated, validate
from owcsmuse.resolve import ENTITY_ID, rank_candidates


# --------------------------------------------------- Liquipedia: the old client is gone

def test_the_old_mediawiki_client_is_gone_and_the_api_client_is_the_only_one():
    """The first client scraped `action=parse` wikitext with per-action throttles we had inverted (parse is the slow
    one), and got rate limited. It is replaced by the LiquipediaDB API client; tests/test_liquipedia.py holds its
    guard, budget, cache and 429 behaviour."""
    from owcsmuse import liquipedia as LP
    assert not hasattr(LP, "interval_for") and not hasattr(LP, "parse_matches")
    assert LP.API_BASE == "https://api.liquipedia.net/api/v3"


# ------------------------------------------------------------- Decimal formatting

def test_decimal_averages_are_quantized_to_two_places():
    """avg_per_map arrives from Postgres as Decimal and printed 18 significant digits."""
    assert _fmt(Decimal("22.6326530612244898")) == "22.63"
    assert _fmt(Decimal("100.0")) == "100"
    assert _fmt(Decimal("0.005")) == "0.01"
    assert _fmt(22.6326530612244898) == "22.63"
    assert _fmt(None) == "-"
    assert _fmt(1109) == "1109"          # ints stay exact
    assert _fmt([2024, 2026]) == "2024,2026"


# --------------------------------------------------- identical-name disambiguation

def test_entity_id_is_accepted_as_a_query():
    m = ENTITY_ID.match("13576d6f-57ae-4b08-9755-89c14455667e")
    assert m and m.group("id") == "13576d6f-57ae-4b08-9755-89c14455667e"
    assert ENTITY_ID.match("team:13576d6f-57ae-4b08-9755-89c14455667e").group("kind") == "team"
    assert ENTITY_ID.match("Sheer Cold") is None


def test_two_entities_with_the_identical_name_stay_ambiguous():
    """'Re-ask with the exact name' is useless here: both are spelled the same."""
    names = [
        {"entity_type": "team", "entity_id": "t1", "name": "Sheer Cold", "name_kind": "current_name", "current_name": "Sheer Cold"},
        {"entity_type": "team", "entity_id": "t2", "name": "Sheer Cold", "name_kind": "current_name", "current_name": "Sheer Cold"},
    ]
    cands = rank_candidates("sheer cold", names)
    assert len(cands) == 2 and {c.entity_id for c in cands} == {"t1", "t2"}
    assert all(c.score == 1.0 for c in cands)
    assert len({c.current_name for c in cands}) == 1  # nothing distinguishes them but the id


# ------------------------------------------------------ non-numeric stats rejected

def _info() -> SchemaInfo:
    return SchemaInfo(
        stat_keys={"Eliminations": {2024}, "Role": {2024}, "K/D Ratio": {2024}, "Deaths": {2024}},
        stat_kinds={"Eliminations": "countable", "Role": "non_numeric", "K/D Ratio": "derived_rate", "Deaths": "countable"},
        maps={"Ilios"}, modes={"Control"}, seasons={2024}, championships={"c1": "OWCS 2024: NA Stage 1 - Main Event"}, regions={"na"},
    )


def test_a_label_stat_cannot_be_ranked():
    u = validate(StructuredQuery(intent="leaderboard", entity="player", metric="Role"), _info())
    assert isinstance(u, Unanswerable) and u.code == "unsupported_metric"
    assert "label, not a number" in u.reason
    # a countable key of the same shape still validates
    assert isinstance(validate(StructuredQuery(intent="leaderboard", entity="player", metric="Eliminations"), _info()), Validated)
    # a derived rate is allowed through: the SQL recomputes it from components
    assert isinstance(validate(StructuredQuery(intent="leaderboard", entity="player", metric="K/D Ratio"), _info()), Validated)


# ------------------------------------------------------------------- DB-backed

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
dbonly = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")


@dbonly
def test_stat_kinds_classify_the_real_key_set(agg_db):
    def q(sql, *a):
        return agg_db.execute(sql, a).fetchall()

    kinds = {k: q("select stat_kind(%s) k", k)[0]["k"] for k in
             ("Eliminations", "Final Blows", "Role", "Team", "K/D Ratio", "Eliminations/10m",
              "Damage as percent of total output", "Healing Done", "Time Played")}
    agg_db.commit()
    assert kinds["Eliminations"] == kinds["Final Blows"] == kinds["Healing Done"] == kinds["Time Played"] == "countable"
    assert kinds["Role"] == kinds["Team"] == "non_numeric"
    assert kinds["K/D Ratio"] == kinds["Eliminations/10m"] == kinds["Damage as percent of total output"] == "derived_rate"


@dbonly
def test_derived_rates_are_recomputed_from_components_never_summed(agg_db):
    """K/D Ratio must be sum(elims)/sum(deaths), not a sum or a mean of per-map ratios."""
    rows = agg_db.execute("select * from stat_leaderboard('K/D Ratio', null, null, 1, 5, 'total')").fetchall()
    agg_db.commit()
    assert rows
    top = rows[0]
    comp = agg_db.execute(
        "select sum(sum_eliminations) e, sum(sum_deaths) d,"
        " round(sum(sum_eliminations)::numeric/nullif(sum(sum_deaths),0),4) kd"
        " from agg_player_stats where player_id=%s", (top["player_id"],)).fetchone()
    naive = agg_db.execute(
        "select round(sum(stat_num(stats->>'K/D Ratio')),4) s, round(avg(stat_num(stats->>'K/D Ratio')),4) m"
        " from fact_player_maps where player_id=%s", (top["player_id"],)).fetchone()
    agg_db.commit()
    assert top["total"] == comp["kd"]
    if comp["d"] and comp["e"] and naive["s"] != comp["kd"]:
        assert top["total"] != naive["s"], "leaderboard is summing a ratio"
    # the long format refuses to publish a total for a rate at all
    long_total = agg_db.execute(
        "select count(*) n from agg_player_stat_long where stat_kind='derived_rate' and total is not null").fetchone()["n"]
    agg_db.commit()
    assert long_total == 0


@dbonly
def test_non_numeric_stats_never_reach_a_leaderboard_or_the_stats_listing(agg_db):
    from owcsmuse.aggregates import available_stats
    assert agg_db.execute("select count(*) n from stat_leaderboard('Role', null, null, 1, 10, 'total')").fetchone()["n"] == 0
    agg_db.commit()
    listed = {r["stat_key"] for r in available_stats(agg_db)}
    assert "Role" not in listed and "Eliminations" in listed
    assert "Role" in {r["stat_key"] for r in available_stats(agg_db, include_non_numeric=True)}


@dbonly
def test_coverage_reports_the_queried_slice_not_the_whole_warehouse(agg_db):
    from owcsmuse.aggregates import stat_coverage_summary
    whole = stat_coverage_summary(agg_db, "Eliminations")
    one_season = stat_coverage_summary(agg_db, "Eliminations", season=2024)
    assert one_season["maps_total"] < whole["maps_total"], "a season filter must shrink the denominator"
    assert one_season["slice"] == "season 2024"
    team = agg_db.execute("select team_id from fact_player_maps limit 1").fetchone()["team_id"]
    agg_db.commit()
    sliced = stat_coverage_summary(agg_db, "Eliminations", team_id=team)
    assert 0 < sliced["maps_total"] < whole["maps_total"]
    assert f"team {team}" in sliced["slice"]


@dbonly
def test_a_championship_without_a_season_still_appears_in_coverage(agg_db):
    """A NULL season used to drop every row of that championship from availability."""
    n_before = agg_db.execute("select count(*) n from stat_coverage_season").fetchone()["n"]
    agg_db.execute("update championships set season = null where championship_id = "
                   "(select championship_id from championships where include order by championship_id limit 1)")
    agg_db.commit()
    from owcsmuse.aggregates import refresh
    refresh(agg_db, ["stat_coverage_season"])
    rows = agg_db.execute("select count(*) n, count(*) filter (where season is null) nulls from stat_coverage_season").fetchone()
    agg_db.commit()
    assert rows["nulls"] > 0, "rows under a NULL season disappeared instead of being reported"
    assert rows["n"] >= n_before


@dbonly
def test_response_headers_are_archived(agg_db):
    from datetime import datetime, timezone
    from owcsmuse.db import RawPayloadStore
    store = RawPayloadStore(agg_db)
    rid = store.store(endpoint="/x", params={}, http_status=200, payload={"ok": True}, body_text=None,
                      fetched_at=datetime.now(timezone.utc),
                      headers={"ratelimit-limit": "20, 20;w=1", "ratelimit-remaining": "18"})
    row = agg_db.execute("select headers from raw_payloads where id=%s", (rid,)).fetchone()
    agg_db.commit()
    assert row["headers"]["ratelimit-remaining"] == "18"
    assert row["headers"]["ratelimit-limit"] == "20, 20;w=1"


# ------------------------------------------------------- manual-testing batch

@dbonly
def test_a_players_own_org_never_pulls_in_an_unrelated_regions_matches(agg_db):
    """SpaceStation Gaming (na) was merged with SpaceStation (emea, 0% roster
    overlap) on a contained-name match; sug2rfree's record showed EMEA matches
    he never played. region_conflict() now refuses that merge outright."""
    from owcsmuse.orgs import TeamFacts, propose, region_conflict

    na = TeamFacts(team_id="na1", name="SpaceStation Gaming", matches=50, regions={"na"})
    emea = TeamFacts(team_id="emea1", name="SpaceStation", matches=19, regions={"emea", "international"})
    assert region_conflict(na, emea) is not None
    assert propose(agg_db, {"na1": na, "emea1": emea}) == []

    # an identical name does not override the region rule either
    geekay_na = TeamFacts(team_id="g1", name="Geekay Esports", matches=39, regions={"na"})
    geekay_emea = TeamFacts(team_id="g2", name="Geekay Esports", matches=23, regions={"emea"})
    assert propose(agg_db, {"g1": geekay_na, "g2": geekay_emea}) == []


@dbonly
def test_role_reaches_the_query_layer_and_a_flex_player_counts_once_per_role(agg_db):
    """"tank with the most kills" used to drop "tank" silently and rank everyone.
    KSAA0 is Tank for all 8 fixture maps; the unfiltered leaderboard and the
    tank leaderboard must therefore agree on his number, and a differently
    played role must return a different leaderboard. He is searchable by his
    FACEIT nickname "KSAA0" but displays as his in-game name "KSAA" (bug 5)."""
    from owcsmuse.nlq.pipeline import ask

    unfiltered = ask(agg_db, "who had the most eliminations", with_evidence=False)
    tank = ask(agg_db, "tank with the most kills", with_evidence=False)
    assert unfiltered.status == tank.status == "ok"
    assert {r["nickname"] for r in unfiltered.rows} != {r["nickname"] for r in tank.rows}, \
        "the role filter changed nothing: it is being silently dropped again"

    ksaa_unfiltered = next(r for r in unfiltered.rows if r["nickname"] == "KSAA")
    ksaa_tank = next(r for r in tank.rows if r["nickname"] == "KSAA")
    assert ksaa_tank["total"] == ksaa_unfiltered["total"] == 139   # every fixture map of his is Tank
    assert ksaa_tank["maps_with_stat"] == ksaa_unfiltered["maps_with_stat"] == 8

    per_player = ask(agg_db, "KSAA0 eliminations as tank", with_evidence=False)
    assert per_player.status == "ok" and per_player.rows[0]["total"] == 139

    # a role that player never played returns no_data, not a wrong number
    off_role = ask(agg_db, "KSAA0 eliminations as support", with_evidence=False)
    assert off_role.status == "cannot_answer" and off_role.code == "no_data"


@dbonly
def test_owcs_competition_names_display_reordered_and_shorn_of_central(agg_db):
    """'S9 EMEA OWCS Central - Playoffs' must read 'OWCS EMEA S9 Playoffs' - display
    only, so the stored FACEIT name (still 'S9 EMEA...') keeps matching free text."""
    row = agg_db.execute(
        "select championship_display_name('S9 EMEA OWCS Central - Playoffs') d, "
        "championship_display_name('S4 NA OWCS Central - Regular Season') r, "
        "championship_display_name('Dreamhack Dallas') u"       # unrecognised: passes through unchanged
    ).fetchone()
    agg_db.commit()
    assert row["d"] == "OWCS EMEA S9 Playoffs"
    assert row["r"] == "OWCS NA S4 Regular Season"
    assert row["u"] == "Dreamhack Dallas"
