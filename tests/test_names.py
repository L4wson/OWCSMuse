"""One spelling per map and per mode: FACEIT's, and the same choice in every process (048)."""

import os
import subprocess
import sys

from owcsmuse.names import Canon, _pick
from owcsmuse.nlq.validate import SchemaInfo


def test_faceit_spelling_wins_over_a_more_common_liquipedia_one():
    rows = [("Watchpoint Gibraltar", True, 29), ("Watchpoint: Gibraltar", False, 60),
            ("Control", True, 465), ("control", False, 2), ("Paraiso", True, 11), ("Paraíso", False, 11)]
    canon = _pick(rows)
    assert canon["watchpoint gibraltar"] == "Watchpoint Gibraltar"
    assert canon["control"] == "Control" and canon["paraiso"] == "Paraiso"


def test_without_a_faceit_spelling_the_most_common_one_wins():
    assert _pick([("Antarctic Peninsula", False, 10), ("antarctic peninsula", False, 1)])["antarctic peninsula"] == \
        "Antarctic Peninsula"


def test_canon_leaves_unknown_names_alone():
    c = Canon(maps={"ilios": "Ilios"}, modes={"control": "Control"})
    assert c.map("ILIOS") == "Ilios" and c.mode("control") == "Control"
    assert c.map("New Map") == "New Map" and c.mode(None) is None


def test_the_mode_a_question_reads_does_not_depend_on_the_hash_seed():
    code = ("from owcsmuse.nlq.validate import SchemaInfo; i = SchemaInfo(); i.modes = {'Control', 'control', 'Push'}; "
            "i.maps = {'Watchpoint Gibraltar', 'Watchpoint: Gibraltar'}; "
            "print(i.match_mode('control'), i.match_mode('CONTROL'), i.match_map('watchpoint gibraltar'))")
    seen = set()
    for seed in ("1", "2", "3", "4", "5", "6"):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": seed}, check=True).stdout.strip()
        seen.add(out)
    assert len(seen) == 1, seen     # before 048 seeds 1-3 read "control", 4-6 "Control"


def test_a_typed_spelling_never_picks_the_rarer_stored_one():
    i = SchemaInfo()
    i.modes = {"Control", "control"}
    assert i.match_mode("control") == "Control" and i.match_mode("Control") == "Control"
