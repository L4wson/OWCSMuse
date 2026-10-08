"""The scheduled ingest's scope report: it lists what awaits a decision and never decides anything."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import scope_report  # noqa: E402


def test_an_undecided_competition_the_classifier_would_include_is_listed_and_nothing_is_written(tmp_path, capsys):
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({"decisions": {"c-decided": {"include": True}}}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"championships": [
        {"championship_id": "c-decided", "name": "Decided", "proposed": {"include": True}},
        {"championship_id": "c-new", "name": "OWCS 2027 NA Stage 1", "scope_region": "na", "tier": "main",
         "proposed": {"include": True, "season": 2027}},
        {"championship_id": "c-qual", "name": "Open Qualifier", "proposed": {"include": False}},
    ]}))
    history = tmp_path / "history.json"
    history.write_text(json.dumps([{"championship_id": "c-hidden", "name": "S10 NA OWCS Central", "include": True}]))
    before = {p: p.read_text() for p in (decisions, manifest, history)}

    assert scope_report.main(["--manifest", str(manifest), "--history", str(history), "--decisions", str(decisions),
                              "--github"]) == 0
    out = capsys.readouterr()
    assert "2 competition(s) the classifier would include have no reviewed decision" in out.out
    assert "`c-new`" in out.out and "`c-hidden`" in out.out and "c-decided" not in out.out and "c-qual" not in out.out
    assert out.err.count("::warning") == 2
    assert {p: p.read_text() for p in before} == before                     # a report, never a decision
