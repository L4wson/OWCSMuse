"""OWCS names for FACEIT competitions: sourced from the committed Liquipedia page map, gated by review, display-only."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from owcsmuse.liquipedia import competition_names as cn

ROOT = Path(__file__).resolve().parent.parent
DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")


@pytest.mark.parametrize("page,expected", [
    ("Overwatch Champions Series/2026/NA/Stage 2/Regular Season", cn.PageName(2026, "NA", 2, "Regular Season")),
    ("Overwatch_Champions_Series/2025/EMEA/Stage_3", cn.PageName(2025, "EMEA", 3, None)),
    ("Overwatch Champions Series/2026/NA/Stage 1", cn.PageName(2026, "NA", 1, None)),
])
def test_page_titles_parse_to_year_region_stage(page, expected):
    assert cn.parse_page(page) == expected


def test_a_page_that_is_not_a_stage_page_parses_to_nothing():
    assert cn.parse_page("Overwatch Champions Series/2026/Korea/Stage 1") is None
    assert cn.parse_page("Some Other Page") is None


def test_the_proposal_covers_every_in_scope_competition_and_names_follow_the_pages():
    proposals = {p.faceit_name: p for p in cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH)}
    scope = json.loads((ROOT / cn.DEFAULT_SCOPE_PATH).read_text())["decisions"]
    assert len(proposals) == sum(1 for d in scope.values() if d.get("include")) == 43

    # FACEIT League season numbers are not OWCS stages: S5 is 2025 Stage 2, S9 is 2026 Stage 2.
    assert proposals["S9 NA OWCS Central - Playoffs"].proposed == "OWCS 2026 NA Stage 2 Playoffs"
    assert proposals["S5 EMEA OWCS Central - Regular Season"].proposed == "OWCS 2025 EMEA Stage 2 Regular Season"
    assert proposals["S6 EMEA OWCS Central - Playoffs"].proposed == "OWCS 2025 EMEA Stage 3 Playoffs"
    assert proposals["S8 NA OWCS Central - Regular Season"].proposed == "OWCS 2026 NA Stage 1 Regular Season"
    assert proposals["S9 NA OWCS Central - Playoffs"].basis == "liquipedia"
    assert proposals["OWCS 2024: EMEA Stage 1 - Group A"].proposed == "OWCS 2024 EMEA Stage 1 Group A"
    assert proposals["OWCS 2024: EMEA Stage 1 - Group A"].basis == "faceit-name"
    # no evidence, so no invented name
    assert proposals["Dreamhack Dallas"].proposed is None
    assert proposals["S8 NA OWCS Relegation S9 - Season 9"].proposed is None
    # all twenty FACEIT League competitions come from Liquipedia and none carries a contradiction
    league = [p for p in proposals.values() if p.basis == "liquipedia"]
    assert len(league) == 20 and not any(p.flags for p in league)
    assert len({p.proposed for p in proposals.values() if p.proposed}) == len([p for p in proposals.values() if p.proposed])


def test_a_contradiction_between_faceit_and_the_page_is_flagged_not_papered_over():
    p = cn._propose_one("c", "S9 NA OWCS Central - Playoffs", "Overwatch Champions Series/2026/NA/Stage 2/Regular Season")
    assert any("FACEIT says Playoffs" in f for f in p.flags)
    p = cn._propose_one("c", "S9 NA OWCS Central - Regular Season", "Overwatch Champions Series/2026/EMEA/Stage 2/Regular Season")
    assert any("differs" in f for f in p.flags)


def test_nothing_applies_until_it_is_decided(tmp_path):
    decisions = cn.CompetitionDecisions(tmp_path / "d.json")
    proposals = decisions.apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH))
    assert all(p.status in ("pending", "unproposed") or p.proposed is None for p in proposals)
    assert all(p.effective == p.current_display for p in proposals)     # nothing shown differently

    assert cn.accept(decisions, proposals) == 20                         # the Liquipedia-backed ones, in bulk
    assert sum(p.status == "pending" and bool(p.proposed) for p in proposals) == 20   # 2024 names still wait for a person
    decisions.save()
    again = cn.CompetitionDecisions(tmp_path / "d.json").apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH))
    assert sum(p.status == "decided" for p in again) == 20


def test_a_decision_made_against_a_renamed_competition_stops_applying(tmp_path):
    decisions = cn.CompetitionDecisions(tmp_path / "d.json")
    proposals = cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH)
    target = next(p for p in proposals if p.faceit_name == "S9 NA OWCS Central - Playoffs")
    decisions.set(target.championship_id, "S9 NA Old Name", "OWCS 2026 NA Stage 2 Playoffs", "manual")
    decisions.apply(proposals)
    assert target.status == "stale" and target.effective == target.current_display


def test_the_committed_report_matches_what_the_proposer_writes_today():
    """The review report is checked in; if the scope or the page map changes, regenerating it is part of the change."""
    report = (ROOT / cn.DEFAULT_REPORT_PATH).read_text(encoding="utf-8")
    decisions = cn.CompetitionDecisions(ROOT / cn.DEFAULT_DECISIONS_PATH)
    current = cn.render_report(decisions.apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH)))
    assert report == current, "run `python -m owcsmuse competitions propose`"


@pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")
def test_display_only_reviewed_names_change_what_is_shown_and_never_the_stored_name(agg_db, tmp_path):
    def shown(name):
        with agg_db.cursor() as cur:
            cur.execute("SELECT championship_display_name(%s) AS n", [name])
            n = cur.fetchone()["n"]
        agg_db.commit()
        return n

    with agg_db.cursor() as cur:
        cur.execute("SELECT championship_id, name FROM championships ORDER BY championship_id")
        stored_before = [tuple(r.values()) for r in cur.fetchall()]
    agg_db.commit()

    faceit = "S9 NA OWCS Central - Playoffs"
    assert shown(faceit) == "OWCS NA S9 Playoffs"                       # unreviewed: unchanged behaviour
    proposals = cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH)
    try:
        decisions = cn.CompetitionDecisions(tmp_path / "d.json")
        assert cn.load(agg_db, decisions, decisions.apply(list(proposals))) == {"names_written": 0, "stale_not_applied": 0}
        assert shown(faceit) == "OWCS NA S9 Playoffs"                   # proposals alone change nothing

        cn.accept(decisions, proposals)
        assert cn.load(agg_db, decisions, decisions.apply(proposals))["names_written"] == 20
        assert shown(faceit) == "OWCS 2026 NA Stage 2 Playoffs"
        assert shown("OWCS 2024: EMEA Stage 1 - Group A") == "OWCS 2024: EMEA Stage 1 - Group A"   # undecided: as before
    finally:
        with agg_db.cursor() as cur:
            cur.execute("DELETE FROM competition_names")
        agg_db.commit()
    assert shown(faceit) == "OWCS NA S9 Playoffs"

    with agg_db.cursor() as cur:
        cur.execute("SELECT championship_id, name FROM championships ORDER BY championship_id")
        assert [tuple(r.values()) for r in cur.fetchall()] == stored_before   # FACEIT's name is untouched
    agg_db.commit()
