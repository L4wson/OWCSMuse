"""Every reviewed decision in scope/ is loaded, and nothing loaded is absent from scope/.

A decision recorded in a file and never loaded is invisible: answers read the tables, not the files. Production carried
166 player identity decisions with no player anchor loaded, 11 decided team names with no anchor, and a `timeless`
anchor still naming the NTMR org after the file had moved it to its own team id - the last of which failed five
series_integrity rows for two sessions. Same class as the materialized view that kept its old org_key: recorded, not
applied.

Each file is compared against what its loader writes, under the loader's own rule for a decision that does not apply
here (a team id, player, championship or Liquipedia record this warehouse does not hold is skipped by the loader, so
it is counted as not applicable rather than missing). Two directions are reported separately:

    decided_not_loaded   in the file, applicable, absent from the table
    loaded_not_decided   in the table, absent from the file (a withdrawn decision that still applies)
    loaded_differs       in both, with a different value (a changed decision that was never reloaded)

Each discrepancy names the file, the key and the command that loads it.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import psycopg

from .liquipedia.events import LP_CHAMPIONSHIP_PREFIX, championship_id as lp_championship_id, load_events

ROOT = Path(__file__).resolve().parent.parent
SCOPE = ROOT / "scope"

LOADERS = {
    "org_decisions.json": "python -m owcsmuse orgs load",
    "alias_decisions.json": "python -m owcsmuse alias load",
    "liquipedia_team_map.json": "python -m owcsmuse identity load",
    "player_identity_decisions.json": "python -m owcsmuse identity load",
    "liquipedia_link_decisions.json": "python -m owcsmuse liquipedia reconcile",
    "decisions.json": "python -m owcsmuse classify, then python -m owcsmuse load-manifest",
    "competition_names.json": "python -m owcsmuse competitions load",
    "liquipedia_events.json": "python -m owcsmuse liquipedia events load",
    "partner_teams.json": "python -m owcsmuse groups load",
}


def _rows(conn: psycopg.Connection, sql: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]


def _lp_champs(conn: psycopg.Connection) -> dict[str, dict[str, Any]]:
    return {r["championship_id"]: r for r in _rows(
        conn, "SELECT championship_id, name, scope_region, tier, season, include FROM championships "
              "WHERE championship_id LIKE 'lp:%'")}


def _ts(v: Any) -> Optional[datetime]:
    """A window bound as a comparable value: None for an open end, whatever form it arrives in."""
    if v is None or v in ("-infinity", "infinity"):
        return None
    return datetime.fromisoformat(v) if isinstance(v, str) else v


class _Diff:
    def __init__(self) -> None:
        self.discrepancies: list[dict[str, Any]] = []
        self.counts: dict[str, dict[str, int]] = {}

    def compare(self, file: str, decided: dict[Any, Any], loaded: dict[Any, Any], not_applicable: int = 0,
                counted: bool = True) -> None:
        """`decided` holds only the applicable decisions, keyed the way the table keys them. `counted=False` for a
        second table one file's decisions also write (a display name, a born team id): compared, not counted twice."""
        for key in sorted(set(decided) | set(loaded), key=str):
            if key not in loaded:
                kind = "decided_not_loaded"
            elif key not in decided:
                kind = "loaded_not_decided"
            elif decided[key] != loaded[key]:
                kind = "loaded_differs"
            else:
                continue
            self.discrepancies.append({"kind": kind, "file": f"scope/{file}", "key": _show(key),
                                       "decided": _show(decided.get(key)), "loaded": _show(loaded.get(key)),
                                       "hint": f"reload: {LOADERS[file]}"})
        if not counted:
            return
        prev = self.counts.get(file, {"decisions": 0, "not_applicable_here": 0})
        self.counts[file] = {"decisions": prev["decisions"] + len(decided) + not_applicable,
                             "not_applicable_here": prev["not_applicable_here"] + not_applicable}


def _show(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, tuple):
        return [_show(x) for x in v]
    return v


def check(conn: psycopg.Connection, scope_dir: Path = SCOPE) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .aliases import AliasDecisions
    from .liquipedia import competition_names as comp_names
    from .liquipedia.identity import BORN_PREFIX, BORN_TEAM_PREFIX, PlayerDecisions
    from .liquipedia.pipeline import LinkDecisions
    from .liquipedia.teams import TeamMap
    from .orgs import OrgDecisions
    from .scope import Decisions

    d = _Diff()
    teams = {r["team_id"] for r in _rows(conn, "SELECT team_id FROM teams")}
    players = {r["player_id"] for r in _rows(conn, "SELECT player_id FROM players")}
    orgs = {r["org_id"] for r in _rows(conn, "SELECT org_id FROM orgs")}

    # ---- org decisions -> team_orgs (FACEIT team ids; `lp:team:` rows belong to the team map below)
    od = OrgDecisions(scope_dir / "org_decisions.json")
    decided: Counter = Counter()
    na = 0
    for tid in od.data:
        for m in od.mappings(tid):
            if tid in teams:
                decided[(tid, m["org_id"])] += 1
            else:
                na += 1
    loaded = Counter((r["team_id"], r["org_id"]) for r in _rows(
        conn, "SELECT team_id, org_id FROM team_orgs WHERE team_id NOT LIKE 'lp:team:%'"))
    d.compare("org_decisions.json", dict(decided), dict(loaded), na)

    # ---- aliases -> entity_aliases (the loader writes every one, so all apply)
    ad = AliasDecisions(scope_dir / "alias_decisions.json")
    d.compare("alias_decisions.json", {a: (v["entity_type"], v["entity_id"]) for a, v in ad.data.items()},
              {r["alias"]: (r["entity_type"], r["entity_id"])
               for r in _rows(conn, "SELECT alias, entity_type, entity_id FROM entity_aliases")})

    # ---- team map -> entity_anchors (team_name), and an org's Liquipedia-born team id -> team_orgs
    tm = TeamMap(scope_dir / "liquipedia_team_map.json")
    decided_anchors: dict[Any, Any] = {}
    decided_born: dict[str, str] = {}
    for key, v in tm.data.items():
        name, _, region = key.partition("|")
        eras = v.get("eras") or [v]
        for e in eras:
            decided_anchors[(name, region, _ts(e.get("valid_from")))] = (e["entity_type"], e["entity_id"], _ts(e.get("valid_to")))
        org_eras = [{**v, **e} for e in eras if e.get("entity_type") == "org"
                    and (e["entity_id"] in orgs or e.get("org_name") or v.get("org_name"))]
        if org_eras:
            decided_born[BORN_TEAM_PREFIX + key] = tuple(sorted(
                ((e["entity_id"], None if len(eras) == 1 else _ts(e.get("valid_from")),
                  None if len(eras) == 1 else _ts(e.get("valid_to"))) for e in org_eras), key=str))
    d.compare("liquipedia_team_map.json", decided_anchors,
              {(r["anchor"], r["region"], _ts(r["vf"])): (r["entity_type"], r["entity_id"], _ts(r["vt"]))
               for r in _rows(conn, """SELECT anchor, region, entity_type, entity_id,
                                              CASE WHEN valid_from = '-infinity' THEN NULL ELSE valid_from END AS vf,
                                              CASE WHEN valid_to = 'infinity' THEN NULL ELSE valid_to END AS vt
                                         FROM entity_anchors WHERE anchor_kind = 'team_name'""")})
    born_rows: dict[str, list] = {}
    for r in _rows(conn, """SELECT team_id, org_id,
                                   CASE WHEN valid_from = '-infinity' THEN NULL ELSE valid_from END AS vf,
                                   CASE WHEN valid_to = 'infinity' THEN NULL ELSE valid_to END AS vt
                              FROM team_orgs WHERE team_id LIKE 'lp:team:%'"""):
        born_rows.setdefault(r["team_id"], []).append((r["org_id"], _ts(r["vf"]), _ts(r["vt"])))
    d.compare("liquipedia_team_map.json", decided_born, {k: tuple(sorted(v, key=str)) for k, v in born_rows.items()},
              counted=False)

    # ---- player identities -> entity_anchors (player_page), and the owner's display names -> players.display_name
    pd = PlayerDecisions(scope_dir / "player_identity_decisions.json")
    decided_pages: dict[str, str] = {}
    decided_display: dict[str, str] = {}
    na = 0
    for page, v in pd.data.items():
        pid = v["entity_id"] or BORN_PREFIX + page            # a null decision is a Liquipedia-born player
        if v["entity_id"] and pid not in players:
            na += 1
            continue
        decided_pages[page] = pid
        if v.get("display"):
            decided_display[pid] = v["display"]
    d.compare("player_identity_decisions.json", decided_pages,
              {r["anchor"]: r["entity_id"] for r in _rows(conn, "SELECT anchor, entity_id FROM entity_anchors WHERE anchor_kind = 'player_page'")},
              na)
    d.compare("player_identity_decisions.json", {("display_name", k): v for k, v in decided_display.items()},
              {("display_name", r["player_id"]): r["display_name"]
               for r in _rows(conn, "SELECT player_id, display_name FROM players WHERE display_name IS NOT NULL")},
              counted=False)

    # ---- link decisions -> liquipedia_links.decision. A decision settles an ambiguous record; on a record that has
    # since linked exactly/strongly to the same FACEIT match it is moot, and counts as applied.
    ld = LinkDecisions(scope_dir / "liquipedia_link_decisions.json")
    links = _rows(conn, """SELECT lk.lp_objectname, lk.faceit_match_id, lk.tier, lk.decision, lm.faceit_match_id AS named
                             FROM liquipedia_links lk JOIN liquipedia_matches lm ON lm.objectname = lk.lp_objectname""")
    by_obj = {r["lp_objectname"]: r for r in links}
    by_named = {r["named"]: r for r in links if r["named"]}
    decided_links: dict[str, Any] = {}
    loaded_links: dict[str, Any] = {}
    na = 0
    for key, v in ld.data.items():
        r = by_named.get(key.removeprefix("faceit:")) if key.startswith("faceit:") else by_obj.get(key)
        if r is None:
            na += 1
            continue
        want = v.get("faceit_match_id")
        decided_links[key] = ("confirmed", want) if want else ("rejected", None)
        if r["decision"]:
            loaded_links[key] = (r["decision"], r["faceit_match_id"])
        elif want and r["tier"] in ("exact", "strong") and r["faceit_match_id"] == want:
            loaded_links[key] = ("confirmed", want)
    keyed = {k for k in decided_links}
    for r in links:   # a decision in the table that no file entry explains
        if r["decision"] and r["lp_objectname"] not in keyed and f"faceit:{r['named']}" not in keyed:
            loaded_links[r["lp_objectname"]] = (r["decision"], r["faceit_match_id"])
    d.compare("liquipedia_link_decisions.json", decided_links, loaded_links, na)

    # ---- scope decisions -> championships (applied through the manifest; a decision only binds the fields it sets)
    sd = Decisions(scope_dir / "decisions.json")
    champs = {r["championship_id"]: r for r in _rows(
        conn, "SELECT championship_id, scope_region, tier, season, include, classification_source FROM championships")}
    cols = {"region": "scope_region", "tier": "tier", "season": "season", "include": "include"}
    decided_scope: dict[str, Any] = {}
    loaded_scope: dict[str, Any] = {}
    na = 0
    for cid, v in sd.data.items():
        if cid not in champs:
            na += 1
            continue
        decided_scope[cid] = tuple(sorted((f, v[f]) for f in cols if f in v)) + (("source", "manual"),)
        loaded_scope[cid] = tuple(sorted((f, champs[cid][cols[f]]) for f in cols if f in v)) + (("source", champs[cid]["classification_source"]),)
    for cid, r in champs.items():
        if r["classification_source"] == "manual" and cid not in sd.data and not cid.startswith(LP_CHAMPIONSHIP_PREFIX):
            loaded_scope[cid] = (("source", "manual"),)
    d.compare("decisions.json", decided_scope, loaded_scope, na)

    # ---- Stage 4 events -> lp: championships (`liquipedia events load`; the file is the whole truth for them)
    decided_events = {lp_championship_id(root): (e["display_name"], e["region"], e["tier"], int(e["season"]), bool(e["include"]))
                      for root, e in load_events(scope_dir / "liquipedia_events.json").items()}
    loaded_events = {cid: (r["name"], r["scope_region"], r["tier"], r["season"], r["include"])
                     for cid, r in _lp_champs(conn).items()}
    d.compare("liquipedia_events.json", decided_events, loaded_events, 0)

    # ---- season-scoped groups (043) -> team_groups (`groups load`; the file is the whole truth)
    from .groups import load_file as load_groups_file
    decided_groups = {(g["group_key"], g["season"], g["region"], g["liquipedia_name"]): g["page"]
                      for g in load_groups_file(scope_dir / "partner_teams.json")}
    loaded_groups = {(r["group_key"], r["season"], r["region"], r["liquipedia_name"]): r["page"]
                     for r in _rows(conn, "SELECT group_key, season, region, liquipedia_name, page FROM team_groups")} \
        if _rows(conn, "SELECT 1 FROM information_schema.tables WHERE table_name = 'team_groups' AND table_schema = current_schema()") else {}
    d.compare("partner_teams.json", decided_groups, loaded_groups, 0)

    # ---- competition names -> competition_names (a decision made against a FACEIT name since renamed is stale and,
    # by the loader's own rule, not applied)
    cd = comp_names.CompetitionDecisions(scope_dir / "competition_names.json")
    proposals = cd.apply(comp_names.propose(scope_dir / "liquipedia_map.json", scope_dir / "decisions.json",
                                            scope_dir / "competition_pages.json"))
    decided_names = {p.championship_id: cd.data[p.championship_id]["display_name"] for p in proposals if p.status == "decided"}
    d.compare("competition_names.json", decided_names,
              {r["championship_id"]: r["display_name"] for r in _rows(conn, "SELECT championship_id, display_name FROM competition_names")},
              sum(p.status == "stale" for p in proposals))

    by_kind = Counter(x["kind"] for x in d.discrepancies)
    return d.discrepancies, {"files": d.counts, **{k: by_kind.get(k, 0) for k in
                                                   ("decided_not_loaded", "loaded_not_decided", "loaded_differs")}}
