"""Derive the pairs warehouse's golden cases (tests/golden/pairs/cases.json) from raw payloads, never from ask().

One pairing's every series - sug2rfree v zeruhh, 11 series 2024-2026 - in a warehouse of its own, so pinning it does
not move the main golden set's confirmed values. The values come from tests/golden/independent.py, reading the
captured FACEIT payloads and Liquipedia records only.

    python tests/golden/pairs/derive.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import independent as I  # noqa: E402

I.use_fixtures(HERE)
S = I.all_series()

# The owner chose Option A on 2026-10-17 (every played map counts) and confirmed these values, which were derived from
# the source tables before any code changed: 7-4 over 11 series, 29-21 over 50 maps, at both grains.
CONFIRMED = {"G93", "G94"}
SUG, ZRH = "sug2rfree", "zeruhh"
sug, zrh = I.player_id_by_nickname(S, SUG), I.player_id_by_nickname(S, ZRH)
sug_name, zrh_name = I.display_name(S, sug), I.display_name(S, zrh)

series = I.opposed_record(S, ("player", {sug}), ("player", {zrh}))
maps = I.opposed_maps(S, ("player", {sug}), ("player", {zrh}))
assert (series["matches"], series["wins"], series["losses"]) == (11, 7, 4), series
assert (maps["maps"], maps["map_wins"], maps["map_losses"], maps["matches"]) == (50, 29, 21, 11), maps
assert maps["by_source"] == {"faceit stats": 42, "faceit detailed_results, on Liquipedia": 1, "liquipedia": 7}, maps

CASES = [
    {"id": "G93", "title": "A player v player series record: every series, and the same maps as the map record",
     "kind": "exact", "regression": "series maps (49) disagreed with the series' own map score (29-21 = 50) (2026-10-17)",
     "question": f"{sug_name} series record against {zrh_name}",
     "expect": {"status": "ok",
                "rows": [{"matches": series["matches"], "wins": series["wins"], "losses": series["losses"],
                          "map_wins": maps["map_wins"], "map_losses": maps["map_losses"], "maps": maps["maps"]}],
                "other_grain": f"{sug_name} map record against {zrh_name}"},
     "derivation": f"Series with {sug_name} and {zrh_name} on opposite declared line-ups: {series['matches']} "
                   f"({', '.join(m[:10] for m in series['match_ids'])}), {series['wins']}-{series['losses']} from "
                   f"{sug_name}'s side; their played maps {maps['map_wins']}-{maps['map_losses']} ({maps['maps']}: "
                   f"{maps['by_source']}). maps read 49 while the stored maps_played of 1-1d2eaf73 said 3 of its 4."},
    {"id": "G94", "title": "A player v player map record counts every played map, stats or not",
     "kind": "exact", "regression": "map grain counted only maps with player stats: 22-20 against 29-21 (2026-10-17)",
     "question": f"{sug_name} map record against {zrh_name}",
     "expect": {"status": "ok",
                "rows": [{"maps": maps["maps"], "map_wins": maps["map_wins"], "map_losses": maps["map_losses"],
                          "matches": maps["matches"]}],
                "other_grain": f"{sug_name} series record against {zrh_name}"},
     "derivation": f"Every map of the {maps['matches']} series: {maps['by_source']} -> "
                   f"{maps['map_wins']}-{maps['map_losses']}. Before: 22-20 in 42, the maps FACEIT returned player stats "
                   "for. Missing were the 7 maps of the two results-only 2026 series (Liquipedia's games) and "
                   "1-1d2eaf73's map 1, Ilios (dropped by /stats; in detailed_results, and Liquipedia's game 1)."},
]
for c in CASES:
    c["status"] = "confirmed" if c["id"] in CONFIRMED else "proposed"

(HERE / "cases.json").write_text(json.dumps({
    "note": "Golden cases for the pairs warehouse (tests/golden/pairs). Derived by derive.py from raw payloads via "
            "independent.py, never from ask() output; only 'confirmed' cases run.",
    "cases": CASES}, indent=1) + "\n", encoding="utf-8")
print(f"wrote {len(CASES)} cases ({sum(c['status'] == 'confirmed' for c in CASES)} confirmed)")
