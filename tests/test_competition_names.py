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
    assert len(proposals) == sum(1 for d in scope.values() if d.get("include")) == 45

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
    # every 2024 path is confirmed: the NA ones by the owner, the EMEA ones by the probe (scope/competition_pages.json)
    emea = proposals["OWCS 2024: EMEA Stage 1 - Group A"]
    assert emea.page == "Overwatch_Champions_Series/2024/EMEA/Stage_1/Group_Stage"
    assert not any(cn.UNSEEN in f for p in proposals.values() for f in p.flags)

    # no page for these: named from the owner's description of the event, and said so
    dallas = proposals["Dreamhack Dallas"]
    assert dallas.proposed == "OWCS 2024 Dreamhack Dallas" and dallas.basis == "owner" and dallas.page is None
    for region in ("NA", "EMEA"):
        rel = proposals[f"S8 {region} OWCS Relegation S9 - Season 9"]
        # named by the stage it feeds into, as FACEIT's own "Relegation S9" does
        assert rel.proposed == f"OWCS 2026 {region} Stage 2 Relegation" and rel.basis == "owner"

    by_basis = {b: [p for p in proposals.values() if p.basis == b] for b in ("liquipedia", "liquipedia-owner", "owner")}
    assert [len(v) for v in by_basis.values()] == [22, 20, 3]
    assert not any(p.flags for p in by_basis["liquipedia"])                   # the reviewed map has no contradictions
    assert not any("says" in f or "differ" in f for p in proposals.values() for f in p.flags)
    names = [p.proposed for p in proposals.values()]
    assert len(set(names)) == len(names) == 45                                 # every name is distinct


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

    assert cn.accept(decisions, proposals) == 22                         # the reviewed page map, in bulk
    assert sum(p.status == "pending" and bool(p.proposed) for p in proposals) == 23   # the rest wait for a person
    assert cn.accept(decisions, proposals) == 0                          # and a second accept does not widen itself
    decisions.save()
    again = cn.CompetitionDecisions(tmp_path / "d.json").apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH))
    assert sum(p.status == "decided" for p in again) == 22


def test_owner_sourced_proposals_need_an_explicit_basis_to_be_bulk_accepted(tmp_path):
    decisions = cn.CompetitionDecisions(tmp_path / "d.json")
    proposals = decisions.apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH))
    assert cn.accept(decisions, proposals, ("liquipedia-owner",)) == 20
    assert cn.accept(decisions, proposals, ("owner",)) == 3
    assert not [p for p in proposals if p.status == "pending" and p.proposed and p.basis != "liquipedia"]


def test_an_unseen_page_path_is_never_bulk_accepted(tmp_path):
    """Whatever its basis: a path nobody has seen waits until scope/competition_pages.json marks it verified."""
    extra = json.loads((ROOT / cn.DEFAULT_EXTRA_PATH).read_text())
    for entry in extra["pages"].values():
        if "EMEA" in entry["page"]:
            entry["verified"] = False
    path = tmp_path / "pages.json"
    path.write_text(json.dumps(extra))
    decisions = cn.CompetitionDecisions(tmp_path / "d.json")
    proposals = decisions.apply(cn.propose(ROOT / cn.DEFAULT_MAP_PATH, ROOT / cn.DEFAULT_SCOPE_PATH, path))
    assert cn.accept(decisions, proposals, ("liquipedia-owner",)) == 10         # the NA ones only
    unseen = [p for p in proposals if p.status == "pending" and p.basis == "liquipedia-owner"]
    assert len(unseen) == 10 and all("EMEA" in p.faceit_name and any(cn.UNSEEN in f for f in p.flags) for p in unseen)


def test_the_committed_decisions_cover_every_in_scope_competition():
    decided = cn.CompetitionDecisions(ROOT / cn.DEFAULT_DECISIONS_PATH).data
    by_basis = {b: [d for d in decided.values() if d["basis"] == b] for b in ("liquipedia", "liquipedia-owner", "owner")}
    assert [len(v) for v in by_basis.values()] == [22, 20, 3] and len(decided) == 45
    scope = json.loads((ROOT / cn.DEFAULT_SCOPE_PATH).read_text())["decisions"]
    assert set(decided) == {cid for cid, d in scope.items() if d.get("include")}        # nothing missing, nothing extra
    assert all(d["display_name"].startswith(("OWCS 2025 ", "OWCS 2026 ")) for d in by_basis["liquipedia"])
    assert all(d["page"] for d in by_basis["liquipedia"] + by_basis["liquipedia-owner"])   # every page-backed name carries it
    assert {d["display_name"] for d in by_basis["owner"]} == {
        "OWCS 2024 Dreamhack Dallas", "OWCS 2026 NA Stage 2 Relegation", "OWCS 2026 EMEA Stage 2 Relegation"}
    assert len({d["display_name"] for d in decided.values()}) == 45                     # every name is distinct


def test_every_2024_page_path_is_recorded_as_verified_with_the_probe_result():
    extra = json.loads((ROOT / cn.DEFAULT_EXTRA_PATH).read_text())
    assert all(v["verified"] for v in extra["pages"].values())
    probe = extra["probe"]
    assert probe["requests_sent"] == 1 and probe["truncated"] is False
    assert sum(probe["matches_per_page"].values()) == probe["rows_returned"] == 136
    assert set(probe["matches_per_page"]) == {v["page"] for v in extra["pages"].values()}


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
        assert cn.load(agg_db, decisions, decisions.apply(proposals))["names_written"] == 22
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


# -------------------------------------------------------------------------- the one-request page probe

def test_the_probe_is_one_request_and_says_which_pages_exist(monkeypatch):
    import httpx
    from liquipedia_support import Wire, make_client, query_of

    from owcsmuse import liquipedia as LP
    from owcsmuse.liquipedia.stage1 import probe_pages, project_page_probe

    monkeypatch.setenv(LP.ENABLE_ENV, "1")
    pages = ["Overwatch_Champions_Series/2024/EMEA/Stage_1/Group_Stage", "Overwatch_Champions_Series/2024/EMEA/Stage_1",
             "Overwatch_Champions_Series/2024/Europe/Stage_1"]
    rows = ([{"pagename": pages[0]}] * 7) + ([{"pagename": pages[1]}] * 3)
    wire = Wire(lambda req: httpx.Response(200, json={"result": rows}))
    client, store, _ = make_client(wire)

    projection = project_page_probe(pages, client.budget_state())
    assert projection["requests"] == 1 and wire.requests == []             # the projection sends nothing

    report = probe_pages(client, pages)
    assert len(wire.requests) == 1 and report["requests_sent"] == 1          # exactly one
    q = query_of(wire.requests[0])
    assert all(p in q["conditions"] for p in pages) and q["query"] == "pagename"
    assert report["found"] == sorted(pages[:2]) and report["not_found"] == [pages[2]]
    assert report["matches_per_page"][pages[0]] == 7 and report["truncated"] is False

    probe_pages(client, pages)                                              # asking again is answered from the store
    assert len(wire.requests) == 1


def test_the_probe_command_without_execute_sends_nothing(monkeypatch, capsys):
    """The CLI path needs a database for the stored budget, so what is asserted here is the pure part: the plan."""
    from owcsmuse.liquipedia.stage1 import page_probe_params

    params = page_probe_params(["A/B", "C D"])
    assert params["limit"] == 500 and "[[pagename::C_D]]" in params["conditions"]
