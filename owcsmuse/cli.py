"""Command line entry point: `python -m owcsmuse <command>`."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from . import __version__
from .aggregates import MATERIALIZED_VIEWS, available_stats, refresh, stat_coverage_summary, stat_leaderboard
from .collector import Collector
from .config import Settings, load_settings
from .consistency import CHECKS, render_text as render_checks, run_checks
from .limitations import LIMITATIONS, render_text as render_limitations
from .db import RawPayloadStore, connect, migrate
from .discovery import (
    DEFAULT_SEARCH_NAMES,
    discover,
    read_manifest,
    reclassify_manifest,
    write_manifest,
    write_report,
)
from .faceit.client import FaceitClient
from .logging import configure_logging
from .parsers.championships import OWCS_PATTERN
from .resolve import resolve
from .orgs import (DEFAULT_ORG_DECISIONS_PATH, DEFAULT_ORG_REPORT_PATH, OrgDecisions,
                   load_decisions as load_org_decisions, propose as propose_orgs,
                   render_report as render_org_report, unmapped_teams)
from .scope import DEFAULT_DECISIONS_PATH, REGIONS, TIERS, Decisions

DEFAULT_REPORT_PATH = "scope/classification_report.md"


def _safe_stdout() -> None:
    """A cp1252 console cannot encode every FACEIT nickname; never crash on output."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _client(settings: Settings, raw_conn=None) -> FaceitClient:
    sink = RawPayloadStore(raw_conn) if raw_conn is not None else None
    return FaceitClient(settings, sink=sink)


def cmd_migrate(args: argparse.Namespace, settings: Settings) -> int:
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        applied = migrate(conn, settings.migrations_dir, settings.db_schema)
    _print({"applied": applied})
    return 0


def cmd_discover(args: argparse.Namespace, settings: Settings) -> int:
    pattern = re.compile(args.pattern, re.IGNORECASE) if args.pattern else OWCS_PATTERN
    names = args.name or list(DEFAULT_SEARCH_NAMES)
    raw_conn = None
    if not args.no_db:
        raw_conn = connect(settings.database_url, autocommit=True, schema=settings.db_schema)
    decisions = Decisions(args.decisions)
    try:
        with _client(settings, raw_conn) as client:
            manifest = discover(client, names, args.organizer_id or (), pattern, args.game, decisions)
    finally:
        if raw_conn is not None:
            raw_conn.close()
    path = write_manifest(manifest, args.out)
    report = write_report(manifest, args.report)
    _print(_scope_summary(manifest, path, report))
    return 0


def _scope_summary(manifest: dict[str, Any], manifest_path: Any, report_path: Any) -> dict[str, Any]:
    champs = manifest["championships"]
    return {
        "manifest": str(manifest_path),
        "report": str(report_path),
        "organizers": manifest.get("organizers"),
        "championships": len(champs),
        "included": sum(1 for c in champs if c["include"]),
        "manual_decisions": sum(1 for c in champs if c.get("decision_source") == "manual"),
        "by_region_tier": _count_by(champs, lambda c: f"{c.get('scope_region')}/{c.get('tier')}"),
        "included_names": sorted(c["name"] for c in champs if c["include"]),
    }


def _count_by(items: list[dict[str, Any]], key) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        k = key(it)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def cmd_classify(args: argparse.Namespace, settings: Settings) -> int:
    """Re-run classifier + decisions over an existing manifest (no network) and re-render the report."""
    manifest = read_manifest(args.manifest)
    reclassify_manifest(manifest, Decisions(args.decisions))
    path = write_manifest(manifest, args.manifest)
    report = write_report(manifest, args.report)
    _print(_scope_summary(manifest, path, report))
    return 0


def cmd_decide(args: argparse.Namespace, settings: Settings) -> int:
    """Record a reviewed decision for one championship in the decisions file."""
    decisions = Decisions(args.decisions)
    include = True if args.include else (False if args.exclude else None)
    name = None
    if args.manifest:
        for c in read_manifest(args.manifest)["championships"]:
            if c["championship_id"] == args.championship_id:
                name = c["name"]
                break
    d = decisions.set(args.championship_id, region=args.region, tier=args.tier, include=include,
                      season=args.season, note=args.note, name=name)
    path = decisions.save()
    _print({"decisions_file": str(path), "championship_id": args.championship_id, "decision": d})
    return 0


def cmd_load_manifest(args: argparse.Namespace, settings: Settings) -> int:
    manifest = read_manifest(args.manifest)
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        out = Collector(conn, None, settings).load_manifest(manifest, accept_proposals=args.accept_proposals)
    _print(out)
    return 0


def cmd_check_listings(args: argparse.Namespace, settings: Settings) -> int:
    """Page the match listing of every included championship (read-only) and report sizes and truncation."""
    if args.manifest:
        champs = [c for c in read_manifest(args.manifest)["championships"] if c.get("include")]
        if args.championship:
            champs = [c for c in champs if c["championship_id"] in args.championship]
    else:
        conn = connect(settings.database_url, schema=settings.db_schema)
        try:
            champs = Collector(conn, None, settings).included_championships(args.championship or None)
        finally:
            conn.close()
    rows = []
    with _client(settings, None) as client:
        for ch in champs:
            listing = client.list_championship_matches(ch["championship_id"], "all")
            rows.append({"championship_id": ch["championship_id"], "name": ch["name"], "matches": len(listing.items),
                         "pages": listing.pages, "truncated": listing.truncated})
    out = {"championships": len(rows), "truncated": [r for r in rows if r["truncated"]], "listings": rows}
    _print(out)
    return 1 if out["truncated"] else 0


def cmd_refresh(args: argparse.Namespace, settings: Settings) -> int:
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        timings = refresh(conn, args.view or None)
    _print({"refreshed": timings, "total_seconds": round(sum(timings.values()), 3)})
    return 0


def cmd_stats(args: argparse.Namespace, settings: Settings) -> int:
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        if args.stat:
            if args.leaderboard:
                out = stat_leaderboard(conn, args.stat, args.season, args.championship, args.min_maps, args.limit, args.order)
            else:
                out = stat_coverage_summary(conn, args.stat, args.season, args.championship)
        else:
            out = available_stats(conn, args.season, args.include_non_numeric)
    _print(out)
    return 0


def cmd_resolve(args: argparse.Namespace, settings: Settings) -> int:
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        cands = resolve(conn, args.query, args.type, args.limit, args.min_score)
    _print([c.as_dict() for c in cands])
    return 0


def _crawler(settings: Settings, with_client: bool, decisions_path: Optional[str] = None):
    from .crawl import Crawler

    raw_conn = connect(settings.database_url, autocommit=True, schema=settings.db_schema)
    conn = connect(settings.database_url, schema=settings.db_schema)
    client = _client(settings, raw_conn) if with_client else None
    decisions = Decisions(decisions_path or DEFAULT_DECISIONS_PATH)
    return conn, raw_conn, client, Crawler(conn, client, settings, RawPayloadStore(raw_conn), decisions)


def cmd_crawl(args: argparse.Namespace, settings: Settings) -> int:
    conn, raw_conn, client, crawler = _crawler(settings, with_client=args.crawl_cmd in ("seed", "run"), decisions_path=args.decisions)
    try:
        if args.crawl_cmd == "seed":
            out: dict[str, Any] = {}
            if args.from_rosters:
                out["from_rosters"] = crawler.seed_from_rosters()
            if args.player:
                out["explicit"] = crawler.seed_players(args.player)
            if args.file:
                with open(args.file, encoding="utf-8") as f:
                    ids = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
                out["file"] = crawler.seed_players(ids, "explicit")
            if args.team:
                out["team_search"] = crawler.seed_from_team_search(args.team)
            out["projection"] = crawler.projection()
            _print(out)
        elif args.crawl_cmd == "run":
            proj = crawler.projection()
            _print({"projection_before_run": proj})
            if args.dry_run:
                return 0
            stats = crawler.run(args.max_generations, args.max_players)
            _print({"run": stats.__dict__, "frontier_left": len(crawler.frontier()), "projection_next": crawler.projection()})
        elif args.crawl_cmd == "status":
            _print(crawler.status())
        elif args.crawl_cmd == "competitions":
            comps = crawler.competitions()
            path = Path(args.out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(comps, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
            _print({"written": str(path), "competitions": len(comps), "proposed_included": sum(1 for c in comps if c["include"]),
                    "names": [(c["name"], c["matches_seen"], c["include"]) for c in comps]})
    finally:
        if client:
            client.close()
        conn.close()
        raw_conn.close()
    return 0


def cmd_liquipedia(args: argparse.Namespace, settings: Settings) -> int:
    from .liquipedia import LiquipediaClient, compare, parse_matches

    lp = LiquipediaClient()
    if args.lp_cmd == "search":
        _print(lp.search(args.query, args.limit))
        return 0
    if args.lp_cmd == "check-all":
        with open(args.map, encoding="utf-8") as f:
            pages = json.load(f)["pages"]
        results = []
        with connect(settings.database_url, schema=settings.db_schema) as conn:
            for cid, entry in pages.items():
                try:
                    matches = parse_matches(lp.wikitext(entry["page"]))
                except Exception as exc:  # a missing page is a finding, not a crash
                    results.append({"championship_id": cid, "name": entry["name"], "page": entry["page"], "error": str(exc)[:200]})
                    continue
                r = compare(conn, cid, entry["page"], matches, args.date_tolerance).as_dict()
                r["name"] = entry["name"]
                results.append(r)
        totals = {
            "liquipedia_matches": sum(r.get("lp_matches", 0) for r in results),
            "db_matches": sum(r.get("db_matches", 0) for r in results),
            "matched": sum(r.get("matched", 0) for r in results),
            "missing_in_db": sum(len(r.get("lp_only", [])) for r in results),
            "extra_in_db": sum(len(r.get("db_only", [])) for r in results),
            "score_mismatches": sum(len(r.get("score_mismatches", [])) for r in results),
        }
        _print({"totals": totals, "per_competition": results})
        return 0
    text = lp.wikitext(args.page)
    matches = parse_matches(text)
    if args.lp_cmd == "parse":
        _print({"page": args.page, "matches": len(matches), "sample": [m.__dict__ for m in matches[: args.limit]]})
        return 0
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        result = compare(conn, args.championship, args.page, matches, args.date_tolerance)
    _print(result.as_dict())
    return 0


def cmd_orgs(args: argparse.Namespace, settings: Settings) -> int:
    decisions = OrgDecisions(args.decisions)
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        if args.orgs_cmd == "decide":
            decisions.set(args.team_id, args.org, args.org_name or args.org, args.note)
            path = decisions.save()
            _print({"decisions_file": str(path), "team_id": args.team_id, "decision": decisions.get(args.team_id)})
            return 0
        if args.orgs_cmd == "forget":
            removed = decisions.unset(args.team_id)
            decisions.save()
            _print({"team_id": args.team_id, "removed": removed})
            return 0
        if args.orgs_cmd == "reject":
            names = _team_names(conn, [args.team_id_a, args.team_id_b])
            d = decisions.reject(args.team_id_a, args.team_id_b, args.reason, names)
            path = decisions.save()
            _print({"decisions_file": str(path), "rejected": d})
            return 0
        if args.orgs_cmd == "unreject":
            removed = decisions.unreject(args.team_id_a, args.team_id_b)
            decisions.save()
            _print({"team_ids": [args.team_id_a, args.team_id_b], "removed": removed})
            return 0
        if args.orgs_cmd == "load":
            _print(load_org_decisions(conn, decisions))
            return 0
        proposals = decisions.apply(propose_orgs(conn))
        if args.orgs_cmd == "propose":
            report = Path(args.report)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(render_org_report(proposals, unmapped_teams(conn)), encoding="utf-8")
            _print({
                "report": str(report),
                "proposals": len(proposals),
                "strong": sum(1 for p in proposals if p.strength == "strong" and p.decision_source != "rejected"),
                "review_required": sum(1 for p in proposals
                                       if p.strength != "strong" and p.decision_source != "rejected"),
                "already_decided": sum(1 for p in proposals if p.decision_source == "manual"),
                "rejected": sum(1 for p in proposals if p.decision_source == "rejected"),
                "pairs": [{"org": p.org_name, "names": p.names, "overlap": p.roster_overlap,
                           "shared": f"{p.shared_players}/{p.smaller_roster}", "seasons": p.seasons,
                           "strength": p.strength, "decided": p.include, "decision": p.decision_source,
                           "team_ids": p.team_ids}
                          for p in proposals],
            })
            return 0
        if args.orgs_cmd == "status":
            with conn.cursor() as cur:
                cur.execute("SELECT o.org_id, o.name, count(tm.team_id) AS team_ids,"
                            " array_agg(tm.team_id) AS ids FROM orgs o"
                            " LEFT JOIN team_orgs tm USING (org_id) GROUP BY o.org_id, o.name ORDER BY o.name")
                orgs = [dict(r) for r in cur.fetchall()]
            conn.commit()
            _print({"orgs": orgs, "unmapped_team_ids": len(unmapped_teams(conn)),
                    "rejected_pairs": len(decisions.rejections)})
            return 0
    return 0


def _team_names(conn, team_ids: list[str]) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT team_id, name FROM teams WHERE team_id = ANY(%s)", (team_ids,))
        by_id = {r["team_id"]: r["name"] for r in cur.fetchall()}
    conn.commit()
    return [by_id.get(t, t) for t in team_ids]


def cmd_serve(args: argparse.Namespace, settings: Settings) -> int:
    """Run the HTTP API. Needs the optional `api` extra."""
    try:
        from .api import serve
    except ImportError as exc:
        print(f"the HTTP API needs the api extra: pip install -e \".[api]\"  ({exc})", file=sys.stderr)
        return 2
    print(f"serving owcsmuse on http://{args.host}:{args.port}  (schema {settings.db_schema})")
    serve(args.host, args.port, args.reload)
    return 0


def cmd_limitations(args: argparse.Namespace, settings: Settings) -> int:
    """What the warehouse does not know. The same objects the ask layer surfaces."""
    if args.json:
        _print([{"id": lim.id, "title": lim.title, "detail": lim.detail} for lim in LIMITATIONS])
    else:
        print(render_limitations())
    return 0


def cmd_check(args: argparse.Namespace, settings: Settings) -> int:
    """Warehouse invariants. Exit 1 on any discrepancy, so CI fails on a wrong-but-plausible answer."""
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        results = run_checks(conn, args.only or None)
        conn.rollback()  # read-only
    if args.json:
        _print({"ok": all(r.ok for r in results), "checks": [r.as_dict() for r in results]})
    else:
        print(render_checks(results))
    return 0 if all(r.ok for r in results) else 1


def cmd_ask(args: argparse.Namespace, settings: Settings) -> int:
    from .nlq.pipeline import ask, render_text

    with connect(settings.database_url, schema=settings.db_schema) as conn:
        answer = ask(conn, args.question, parser=args.parser, debug=args.debug,
                     with_evidence=not args.no_evidence, evidence_for=args.evidence_for,
                     evidence_page=args.page, evidence_page_size=args.page_size)
    if args.json:
        _print(answer.as_dict())
    else:
        print(render_text(answer, evidence_rows=args.evidence_rows))
        if args.debug and answer.sql:
            print("\n-- sql --\n" + answer.sql + "\n-- params --\n" + json.dumps(answer.params, default=str))
    return 0 if answer.status == "ok" else 2


def _run_phases(args: argparse.Namespace, settings: Settings, do_list: bool, do_detail: bool) -> int:
    raw_conn = connect(settings.database_url, autocommit=True, schema=settings.db_schema)
    conn = connect(settings.database_url, schema=settings.db_schema)
    out: dict[str, Any] = {}
    try:
        with _client(settings, raw_conn) as client:
            collector = Collector(conn, client, settings, RawPayloadStore(raw_conn))
            if do_list:
                out["list"] = collector.run_list(args.championship or None).__dict__
            if do_detail:
                out["detail"] = collector.run_detail(
                    args.championship or None,
                    getattr(args, "limit", None),
                    getattr(args, "include_failed", False),
                    getattr(args, "refresh", False),
                ).__dict__
    finally:
        conn.close()
        raw_conn.close()
    _print(out)
    return 0


def cmd_list(args: argparse.Namespace, settings: Settings) -> int:
    return _run_phases(args, settings, do_list=True, do_detail=False)


def cmd_detail(args: argparse.Namespace, settings: Settings) -> int:
    return _run_phases(args, settings, do_list=False, do_detail=True)


def cmd_backfill(args: argparse.Namespace, settings: Settings) -> int:
    return _run_phases(args, settings, do_list=True, do_detail=True)


def cmd_reprocess(args: argparse.Namespace, settings: Settings) -> int:
    raw_conn = connect(settings.database_url, autocommit=True, schema=settings.db_schema)
    conn = connect(settings.database_url, schema=settings.db_schema)
    try:
        collector = Collector(conn, None, settings, RawPayloadStore(raw_conn))
        out = collector.reprocess(args.championship or None, args.limit)
    finally:
        conn.close()
        raw_conn.close()
    _print(out.__dict__)
    return 0


def cmd_status(args: argparse.Namespace, settings: Settings) -> int:
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        out = Collector(conn, None, settings).status()
    _print(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="owcsmuse", description="OWCS Muse: FACEIT -> Postgres ingestion")
    p.add_argument("--version", action="version", version=f"owcsmuse {__version__}")
    p.add_argument("--log-level", default=None, help="override OWCS_LOG_LEVEL")
    p.add_argument("--log-format", choices=["json", "text"], default=None, help="override OWCS_LOG_FORMAT")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="apply pending SQL migrations").set_defaults(func=cmd_migrate)

    d = sub.add_parser("discover", help="find OWCS organizers/championships and write a manifest for review")
    d.add_argument("--out", default="manifest.json")
    d.add_argument("--name", action="append", help="organizer/championship search term (repeatable)")
    d.add_argument("--organizer-id", action="append", help="organizer id to enumerate explicitly (repeatable)")
    d.add_argument("--pattern", help="regex marking a championship as OWCS (default: %s)" % OWCS_PATTERN.pattern)
    d.add_argument("--game", default="ow2")
    d.add_argument("--no-db", action="store_true", help="do not store raw payloads (no database needed)")
    d.add_argument("--decisions", default=str(DEFAULT_DECISIONS_PATH), help="reviewed decisions file")
    d.add_argument("--report", default=DEFAULT_REPORT_PATH, help="markdown review report path")
    d.set_defaults(func=cmd_discover)

    cl = sub.add_parser("classify", help="re-run classifier + decisions on an existing manifest (no network)")
    cl.add_argument("--manifest", default="manifest.json")
    cl.add_argument("--decisions", default=str(DEFAULT_DECISIONS_PATH))
    cl.add_argument("--report", default=DEFAULT_REPORT_PATH)
    cl.set_defaults(func=cmd_classify)

    de = sub.add_parser("decide", help="record a reviewed scope decision for one championship")
    de.add_argument("championship_id")
    de.add_argument("--region", choices=REGIONS)
    de.add_argument("--tier", choices=TIERS)
    de.add_argument("--season", type=int)
    g = de.add_mutually_exclusive_group()
    g.add_argument("--include", action="store_true")
    g.add_argument("--exclude", action="store_true")
    de.add_argument("--note")
    de.add_argument("--decisions", default=str(DEFAULT_DECISIONS_PATH))
    de.add_argument("--manifest", default="manifest.json", help="used only to record the championship name")
    de.set_defaults(func=cmd_decide)

    lm = sub.add_parser("load-manifest", help="upsert championships from a reviewed manifest")
    lm.add_argument("manifest")
    lm.add_argument("--accept-proposals", action="store_true",
                    help="also mark classifier-proposed (undecided) championships included")
    lm.set_defaults(func=cmd_load_manifest)

    ck = sub.add_parser("check-listings", help="read-only: list sizes and offset-cap truncation for included championships")
    ck.add_argument("--championship", action="append")
    ck.add_argument("--manifest", help="take the included set from this manifest instead of the database")
    ck.set_defaults(func=cmd_check_listings)

    rf = sub.add_parser("refresh", help="refresh the aggregation materialized views")
    rf.add_argument("--view", action="append", choices=MATERIALIZED_VIEWS, help="refresh only these (repeatable)")
    rf.set_defaults(func=cmd_refresh)

    st = sub.add_parser("stats", help="stat availability, coverage window, or a coverage-aware leaderboard")
    st.add_argument("--stat", help="FACEIT stat key, e.g. 'Eliminations' or 'Final Blows'")
    st.add_argument("--season", type=int)
    st.add_argument("--championship")
    st.add_argument("--leaderboard", action="store_true")
    st.add_argument("--min-maps", type=int, default=1)
    st.add_argument("--limit", type=int, default=20)
    st.add_argument("--order", choices=["total", "avg"], default="total")
    st.add_argument("--include-non-numeric", action="store_true", help="also list label keys such as Role")
    st.set_defaults(func=cmd_stats)

    rs = sub.add_parser("resolve", help="resolve a typed player/team name to candidates")
    rs.add_argument("query")
    rs.add_argument("--type", choices=["player", "team"])
    rs.add_argument("--limit", type=int, default=5)
    rs.add_argument("--min-score", type=float, default=0.5)
    rs.set_defaults(func=cmd_resolve)

    cr = sub.add_parser("crawl", help="history-crawl LIST phase for competitions hidden from the championship endpoints")
    cr.add_argument("--decisions", default=str(DEFAULT_DECISIONS_PATH))
    crs = cr.add_subparsers(dest="crawl_cmd", required=True)
    seed = crs.add_parser("seed", help="add players to the crawl frontier")
    seed.add_argument("--from-rosters", action="store_true", help="every player on an ingested match roster")
    seed.add_argument("--player", action="append", help="FACEIT player id (repeatable)")
    seed.add_argument("--file", help="text file with one player id per line")
    seed.add_argument("--team", action="append", help="exact FACEIT team name to search and seed members of (repeatable)")
    run = crs.add_parser("run", help="crawl the frontier generation by generation")
    run.add_argument("--max-generations", type=int)
    run.add_argument("--max-players", type=int)
    run.add_argument("--dry-run", action="store_true", help="print the request projection and stop")
    crs.add_parser("status", help="convergence curve, frontier, per-competition coverage and gap flags")
    comp = crs.add_parser("competitions", help="write discovered competitions for `classify` review")
    comp.add_argument("--out", default="scope/history_competitions.json")
    cr.set_defaults(func=cmd_crawl)

    lq = sub.add_parser("liquipedia", help="cross-check a championship against a Liquipedia results page")
    lqs = lq.add_subparsers(dest="lp_cmd", required=True)
    s = lqs.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=10)
    p_ = lqs.add_parser("parse"); p_.add_argument("page"); p_.add_argument("--limit", type=int, default=5)
    ck = lqs.add_parser("check"); ck.add_argument("page"); ck.add_argument("--championship", required=True)
    ck.add_argument("--date-tolerance", type=int, default=1)
    ca = lqs.add_parser("check-all", help="cross-check every competition in scope/liquipedia_map.json")
    ca.add_argument("--map", default="scope/liquipedia_map.json")
    ca.add_argument("--date-tolerance", type=int, default=1)
    lq.set_defaults(func=cmd_liquipedia)

    og = sub.add_parser("orgs", help="org-level team identity: propose, review, apply")
    og.add_argument("--decisions", default=str(DEFAULT_ORG_DECISIONS_PATH))
    ogs = og.add_subparsers(dest="orgs_cmd", required=True)
    pr = ogs.add_parser("propose", help="write the proposal report with evidence")
    pr.add_argument("--report", default=str(DEFAULT_ORG_REPORT_PATH))
    de = ogs.add_parser("decide", help="map one team id to an org")
    de.add_argument("team_id"); de.add_argument("--org", required=True); de.add_argument("--org-name"); de.add_argument("--note")
    fg = ogs.add_parser("forget", help="unmap a team id"); fg.add_argument("team_id")
    rj = ogs.add_parser("reject", help="record a reviewed rejection: these two team ids are different orgs")
    rj.add_argument("team_id_a"); rj.add_argument("team_id_b"); rj.add_argument("--reason", required=True)
    ur = ogs.add_parser("unreject", help="drop a recorded rejection so the pair is proposed again")
    ur.add_argument("team_id_a"); ur.add_argument("team_id_b")
    ogs.add_parser("load", help="write decided mappings into orgs / team_orgs")
    ogs.add_parser("status", help="orgs and how many team ids each covers")
    og.set_defaults(func=cmd_orgs)

    sv = sub.add_parser("serve", help="run the HTTP API (POST /ask, GET /query/{slug}, GET /suggestions)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true", help="development autoreload")
    sv.set_defaults(func=cmd_serve)

    li = sub.add_parser("limitations", help="known gaps in the data, the ones the ask layer surfaces")
    li.add_argument("--json", action="store_true")
    li.set_defaults(func=cmd_limitations)

    ch = sub.add_parser("check", help="consistency checks: reconcile every derived view against its source")
    ch.add_argument("--only", action="append", choices=list(CHECKS), help="run only this check (repeatable)")
    ch.add_argument("--json", action="store_true")
    ch.set_defaults(func=cmd_check)

    ak = sub.add_parser("ask", help="answer a natural-language stats question (structured query, never free SQL)")
    ak.add_argument("question")
    ak.add_argument("--parser", choices=["rules", "llm", "auto"], default="rules",
                    help="rules: deterministic parser; llm: Claude structured-output parser; auto: llm with rules fallback")
    ak.add_argument("--json", action="store_true", help="print the full answer object as JSON")
    ak.add_argument("--page", type=int, default=1, help="evidence page")
    ak.add_argument("--page-size", type=int, default=25, help="evidence rows per page")
    ak.add_argument("--evidence-for", help="expand a ranked row: a player id, org key, map or mode")
    ak.add_argument("--evidence-rows", type=int, default=5, help="evidence rows to print")
    ak.add_argument("--no-evidence", action="store_true", help="skip the rows behind the answer")
    ak.add_argument("--debug", action="store_true", help="include the compiled SQL and parameters")
    ak.set_defaults(func=cmd_ask)

    for name, func, help_ in (
        ("list", cmd_list, "LIST phase: page championship match listings into match stubs"),
        ("detail", cmd_detail, "DETAIL phase: fetch /matches/{id} and /stats for pending matches"),
        ("backfill", cmd_backfill, "LIST then DETAIL"),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--championship", action="append", help="restrict to championship id (repeatable)")
        if name != "list":
            sp.add_argument("--limit", type=int, help="max matches to process this run")
            sp.add_argument("--include-failed", action="store_true", help="retry matches in state 'failed'")
            sp.add_argument("--refresh", action="store_true", help="also re-fetch matches already complete/skipped")
        sp.set_defaults(func=func)

    rp = sub.add_parser("reprocess", help="re-parse stored raw payloads without calling FACEIT")
    rp.add_argument("--championship", action="append")
    rp.add_argument("--limit", type=int)
    rp.set_defaults(func=cmd_reprocess)

    sub.add_parser("status", help="ingest progress per state and championship").set_defaults(func=cmd_status)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    _safe_stdout()
    settings = load_settings()
    configure_logging(args.log_level or settings.log_level, args.log_format or settings.log_format)
    return args.func(args, settings)


if __name__ == "__main__":
    sys.exit(main())
