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
    ("Overwatch_Champions_Series/2024/North_America/Stage_1/Group_Stage", cn.PageName(2024, "NA", 1, "Group Stage")),
    ("Overwatch_Champions_Series/2024/North_America/Stage_2", cn.PageName(2024, "NA", 2, None)),
    ("Overwatch Champions Series/2026/NA/Stage 1", cn.PageName(2026, "NA", 1, None)),
])
def test_page_titles_parse_to_year_region_stage(page, expected):
    assert cn.parse_page(page) == expected


def test_a_page_that_is_not_a_stage_page_parses_to_nothing():
    assert cn.parse_page("Overwatch Champions Series/2026/Korea/Stage 1") is None
    assert cn.parse_page("Some Other Page") is None


def test_the_proposal_covers_every_in_scope_competition_and_names_follow_the_pages():
    proposals = {p.faceit_name: p for p in cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH,
                                                      ROOT / cn.DEFAULT_EXTRA_PATH)}
    scope = json.loads((ROOT / cn.DEFAULT_SCOPE_PATH).read_text())["decisions"]
    assert len(proposals) == sum(1 for d in scope.values() if d.get("include")) == 43

    # FACEIT League season numbers are not OWCS stages: S5 is 2025 Stage 2, S9 is 2026 Stage 2.
    assert proposals["S9 NA OWCS Central - Playoffs"].proposed == "OWCS 2026 NA Stage 2 Playoffs"
    assert proposals["S5 EMEA OWCS Central - Regular Season"].proposed == "OWCS 2025 EMEA Stage 2 Regular Season"
    assert proposals["S6 EMEA OWCS Central - Playoffs"].proposed == "OWCS 2025 EMEA Stage 3 Playoffs"
    assert proposals["S8 NA OWCS Central - Regular Season"].proposed == "OWCS 2026 NA Stage 1 Regular Season"
    assert proposals["S9 NA OWCS Central - Playoffs"].basis == "liquipedia"

    # 2024: groups share the stage's Group_Stage page, main events are the stage page itself.
    group = proposals["OWCS 2024: NA Stage 1 - Group C"]
    assert group.proposed == "OWCS 2024 NA Stage 1 Group C" and group.basis == "liquipedia-owner"
    assert group.page == "Overwatch_Champions_Series/2024/North_America/Stage_1/Group_Stage"
    assert proposals["OWCS 2024: NA Stage 2 - Main Event"].page == "Overwatch_Champions_Series/2024/North_America/Stage_2"
    assert not any(f for f in group.flags if "inferred" in f)                 # the NA path was supplied
    assert any("inferred" in f for f in proposals["OWCS 2024: EMEA Stage 1 - Group A"].flags)   # the EMEA one was not seen

    # no page for these: named from the owner's description of the event, and said so
    dallas = proposals["Dreamhack Dallas"]
    assert dallas.proposed == "OWCS 2024 Dreamhack Dallas" and dallas.basis == "owner" and dallas.page is None
    for region in ("NA", "EMEA"):
        rel = proposals[f"S8 {region} OWCS Relegation S9 - Season 9"]
        assert rel.proposed == f"OWCS 2026 {region} Stage 1 Relegation" and rel.basis == "owner"

    by_basis = {b: [p for p in proposals.values() if p.basis == b] for b in ("liquipedia", "liquipedia-owner", "owner")}
    assert [len(v) for v in by_basis.values()] == [20, 20, 3]
    assert not any(p.flags for p in by_basis["liquipedia"])                   # the reviewed map has no contradictions
    assert not any("says" in f or "differ" in f for p in proposals.values() for f in p.flags)
    names = [p.proposed for p in proposals.values()]
    assert len(set(names)) == len(names) == 43                                 # every name is distinct


def test_a_contradiction_between_faceit_and_the_page_is_flagged_not_papered_over():
    p = cn._propose_one("c", "S9 NA OWCS Central - Playoffs", "Overwatch Champions Series/2026/NA/Stage 2/Regular Season")
    assert any("FACEIT says Playoffs" in f for f in p.flags)
    p = cn._propose_one("c", "S9 NA OWCS Central - Regular Season", "Overwatch Champions Series/2026/EMEA/Stage 2/Regular Season")
    assert any("differs" in f for f in p.flags)


def test_nothing_applies_until_it_is_decided(tmp_path):
    decisions = cn.CompetitionDecisions(tmp_path / "d.json")
    proposals = decisions.apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH,
                                           ROOT / cn.DEFAULT_EXTRA_PATH))
    assert all(p.status in ("pending", "unproposed") or p.proposed is None for p in proposals)
    assert all(p.effective == p.current_display for p in proposals)     # nothing shown differently

    assert cn.accept(decisions, proposals) == 20                         # the reviewed page map, in bulk
    assert sum(p.status == "pending" and bool(p.proposed) for p in proposals) == 23   # the rest wait for a person
    assert cn.accept(decisions, proposals) == 0                          # and a second accept does not widen itself
    decisions.save()
    again = cn.CompetitionDecisions(tmp_path / "d.json").apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH))
    assert sum(p.status == "decided" for p in again) == 20


def test_owner_sourced_proposals_need_an_explicit_basis_to_be_bulk_accepted(tmp_path):
    decisions = cn.CompetitionDecisions(tmp_path / "d.json")
    proposals = decisions.apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH))
    assert cn.accept(decisions, proposals, ("liquipedia-owner",)) == 20
    assert cn.accept(decisions, proposals, ("owner",)) == 3


def test_the_committed_decisions_are_exactly_the_twenty_approved_2025_2026_names():
    decided = cn.CompetitionDecisions(ROOT / cn.DEFAULT_DECISIONS_PATH).data
    assert len(decided) == 20 and {d["basis"] for d in decided.values()} == {"liquipedia"}
    assert all(d["display_name"].startswith(("OWCS 2025 ", "OWCS 2026 ")) for d in decided.values())
    assert all(d["page"] for d in decided.values())          # every applied name carries the page behind it


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
    current = cn.render_report(decisions.apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH,
                                                          ROOT / cn.DEFAULT_EXTRA_PATH)))
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
        assert shown("Dreamhack Dallas") == "Dreamhack Dallas"
    finally:
        with agg_db.cursor() as cur:
            cur.execute("DELETE FROM competition_names")
        agg_db.commit()
    assert shown(faceit) == "OWCS NA S9 Playoffs"

    with agg_db.cursor() as cur:
        cur.execute("SELECT championship_id, name FROM championships ORDER BY championship_id")
        assert [tuple(r.values()) for r in cur.fetchall()] == stored_before   # FACEIT's name is untouched
    agg_db.commit()
