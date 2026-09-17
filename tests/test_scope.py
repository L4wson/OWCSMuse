"""Scope classifier, decisions file and review report."""

import json
from datetime import datetime, timezone

import pytest

from owcsmuse.scope import Decisions, classify, classify_manifest_entries, render_report


def c(name, **kw):
    return classify(name, **kw)


def test_na_and_emea_main_stages_are_included():
    for name in (
        "OWCS 2024: NA Stage 1 - Main Event",
        "OWCS 2024: NA Stage 2 - Group C",
        "OWCS 2024: EMEA Stage 1 - Group A",
        "OWCS 2024: EMEA Stage 2 - Main Event",
        "OWCS 2025 NA Stage 1 - Playoffs",
    ):
        r = c(name, faceit_region="GLOBAL", status="finished")
        assert r.tier == "main" and r.region in ("na", "emea"), (name, r)
        assert r.include is True, (name, r.evidence)
        assert r.season in (2024, 2025)
    assert c("OWCS 2024: NA Stage 1 - Main Event").region == "na"
    assert c("OWCS 2024: EMEA Stage 1 - Main Event").region == "emea"


def test_open_qualifiers_and_relegation_are_excluded_with_evidence():
    r = c("OWCS 2024: NA Stage 1 - Open Qualifiers", status="finished")
    assert r.tier == "qualifier" and r.region == "na" and r.include is False
    assert any("qualifier" in e for e in r.evidence) and any(e.startswith("exclude:") for e in r.evidence)

    r = c("OWCS 2026 OQ - EMEA", faceit_region="EMEA", status="finished")
    assert r.tier == "qualifier" and r.region == "emea" and r.include is False

    r = c("OWCS 2025 EMEA - Open Qualifier LB Decider Match")
    assert r.tier == "qualifier" and r.include is False

    r = c("S5 NA OWCS Relegation Central - Not used", status="cancelled")
    assert r.tier == "relegation" and r.include is False
    joined = " ".join(r.evidence)
    assert "cancelled" in joined and "test/unused" in joined and "relegation" in joined


def test_cancelled_duplicate_of_a_main_event_is_excluded():
    live = c("OWCS 2024: NA Stage 1 - Group A", status="finished")
    dup = c("OWCS 2024: NA Stage 1 - Group A", status="cancelled")
    assert live.include is True and dup.include is False
    assert any("status=cancelled" in e for e in dup.evidence)


def test_asia_and_other_regions_are_excluded_even_when_main():
    for name in (
        "OWCS 2025 Korea Stage 1 - Main Event",
        "OWCS 2025 Japan Stage 1 - Playoffs",
        "OWCS 2025 Asia Stage 2 - Main Event",
        "OWCS 2025 China Stage 1 - Main Event",
        "OWCS 2025 Pacific Stage 1 - Main Event",
        "OWCS 2025 SA Stage 1 - Main Event",
    ):
        r = c(name)
        assert r.region == "other" and r.include is False, (name, r)
        assert r.tier == "main"


def test_international_events_with_na_and_emea_are_included():
    r = c("OWCS 2024 Midseason Championship", status="finished")
    assert (r.region, r.tier, r.include) == ("international", "main", True)
    r = c("OWCS 2025 World Finals", status="finished")
    assert (r.region, r.tier, r.include) == ("international", "main", True)
    r = c("OWCS 2025 Champions Clash")
    assert (r.region, r.tier, r.include) == ("international", "main", True)


def test_known_event_without_owcs_in_name():
    r = c("Dreamhack Dallas", status="finished", championship_start=datetime(2024, 5, 31, tzinfo=timezone.utc),
          organizer_is_owcs=True)
    assert (r.region, r.tier, r.season, r.include) == ("international", "main", 2024, True)
    assert any("known OWCS event" in e for e in r.evidence)


def test_non_owcs_events_are_excluded_and_flag_owcs_organizer():
    r = c("FACEIT League Season 6 - Expert Qualifier (EMEA)", faceit_region="EMEA", status="finished")
    assert r.include is False and r.tier == "qualifier" and r.region == "emea"
    assert any("does not match OWCS pattern" in e for e in r.evidence)
    r = c("Some Community Cup", organizer_is_owcs=True)
    assert r.include is False and any("review" in e for e in r.evidence)


def test_season_falls_back_to_start_date():
    r = c("OWCS Midseason Championship", championship_start=datetime(2025, 6, 1, tzinfo=timezone.utc))
    assert r.season == 2025 and any("championship_start" in e for e in r.evidence)
    assert c("OWCS Midseason Championship").season is None


def test_region_uses_faceit_field_when_name_is_silent():
    r = c("OWCS 2026 Stage 1 - Main Event", faceit_region="NA")
    assert r.region == "na" and any("FACEIT region field" in e for e in r.evidence)


def test_decisions_override_and_persist(tmp_path):
    path = tmp_path / "decisions.json"
    d = Decisions(path)
    proposed = c("OWCS 2024: NA Stage 1 - Open Qualifiers", status="finished")
    assert proposed.include is False
    d.set("abc", include=True, tier="main", note="actually the group stage", name="OWCS 2024: NA Stage 1 - Open Qualifiers")
    final = d.apply("abc", proposed)
    assert final.include is True and final.tier == "main" and final.region == "na"
    assert final.source == "manual" and final.note == "actually the group stage"
    assert any("manual decision" in e for e in final.evidence)
    assert d.apply("other", proposed).source == "auto"

    d.save()
    reloaded = Decisions(path)
    assert reloaded.get("abc")["include"] is True
    assert reloaded.apply("abc", proposed).include is True  # survives a re-run of discovery

    with pytest.raises(ValueError):
        d.set("abc", region="mars")
    with pytest.raises(ValueError):
        d.set("abc", tier="finals")


def test_classify_manifest_entries_and_report(tmp_path):
    entries = [
        {"championship_id": "1", "name": "OWCS 2024: NA Stage 1 - Main Event", "region": "GLOBAL", "status": "finished",
         "type": "doubleElimination", "championship_start": "2024-03-21T00:00:00+00:00", "organizer_id": "org"},
        {"championship_id": "2", "name": "OWCS 2024: NA Stage 1 - Open Qualifiers", "region": "GLOBAL", "status": "finished",
         "type": "swiss", "championship_start": "2024-03-01T00:00:00+00:00", "organizer_id": "org"},
        {"championship_id": "3", "name": "Dreamhack Dallas", "region": "GLOBAL", "status": "finished",
         "type": "doubleElimination", "championship_start": "2024-05-31T00:00:00+00:00", "organizer_id": "org"},
    ]
    d = Decisions(tmp_path / "d.json")
    d.set("2", include=True, tier="main", note="reviewed: keep")
    out = classify_manifest_entries(entries, d, owcs_organizer_ids=["org"])
    by_id = {e["championship_id"]: e for e in out}
    assert by_id["1"]["include"] and by_id["1"]["decision_source"] == "auto" and by_id["1"]["tier"] == "main"
    assert by_id["2"]["include"] and by_id["2"]["decision_source"] == "manual"
    assert by_id["2"]["proposed"] == {"region": "na", "tier": "qualifier", "season": 2024, "include": False}
    assert by_id["3"]["scope_region"] == "international" and by_id["3"]["season"] == 2024

    manifest = {"generated_at": "now", "championships": out}
    report = render_report(manifest)
    assert "| YES | manual | api | 2024 | na | main | OWCS 2024: NA Stage 1 - Open Qualifiers" in report
    assert "reviewed: keep" in report
    assert "name has a qualifier token" in report
    json.dumps(manifest)  # serialisable
