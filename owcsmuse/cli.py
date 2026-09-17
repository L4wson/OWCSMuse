"""Command line entry point: `python -m owcsmuse <command>`."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Optional

from . import __version__
from .collector import Collector
from .config import Settings, load_settings
from .db import RawPayloadStore, connect, migrate
from .discovery import DEFAULT_SEARCH_NAMES, discover, read_manifest, write_manifest
from .faceit.client import FaceitClient
from .logging import configure_logging
from .parsers.championships import OWCS_PATTERN


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _client(settings: Settings, raw_conn=None) -> FaceitClient:
    sink = RawPayloadStore(raw_conn) if raw_conn is not None else None
    return FaceitClient(settings, sink=sink)


def cmd_migrate(args: argparse.Namespace, settings: Settings) -> int:
    with connect(settings.database_url) as conn:
        applied = migrate(conn, settings.migrations_dir)
    _print({"applied": applied})
    return 0


def cmd_discover(args: argparse.Namespace, settings: Settings) -> int:
    pattern = re.compile(args.pattern, re.IGNORECASE) if args.pattern else OWCS_PATTERN
    names = args.name or list(DEFAULT_SEARCH_NAMES)
    raw_conn = None
    if not args.no_db:
        raw_conn = connect(settings.database_url, autocommit=True)
    try:
        with _client(settings, raw_conn) as client:
            manifest = discover(client, names, args.organizer_id or (), pattern, args.game)
    finally:
        if raw_conn is not None:
            raw_conn.close()
    path = write_manifest(manifest, args.out)
    summary = {
        "manifest": str(path),
        "organizers": manifest["organizers"],
        "championships": len(manifest["championships"]),
        "included": sum(1 for c in manifest["championships"] if c["include"]),
    }
    _print(summary)
    return 0


def cmd_load_manifest(args: argparse.Namespace, settings: Settings) -> int:
    manifest = read_manifest(args.manifest)
    with connect(settings.database_url) as conn:
        out = Collector(conn, None, settings).load_manifest(manifest)
    _print(out)
    return 0


def _run_phases(args: argparse.Namespace, settings: Settings, do_list: bool, do_detail: bool) -> int:
    raw_conn = connect(settings.database_url, autocommit=True)
    conn = connect(settings.database_url)
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
    raw_conn = connect(settings.database_url, autocommit=True)
    conn = connect(settings.database_url)
    try:
        collector = Collector(conn, None, settings, RawPayloadStore(raw_conn))
        out = collector.reprocess(args.championship or None, args.limit)
    finally:
        conn.close()
        raw_conn.close()
    _print(out.__dict__)
    return 0


def cmd_status(args: argparse.Namespace, settings: Settings) -> int:
    with connect(settings.database_url) as conn:
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
    d.set_defaults(func=cmd_discover)

    lm = sub.add_parser("load-manifest", help="upsert championships from a reviewed manifest")
    lm.add_argument("manifest")
    lm.set_defaults(func=cmd_load_manifest)

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
    settings = load_settings()
    configure_logging(args.log_level or settings.log_level, args.log_format or settings.log_format)
    return args.func(args, settings)


if __name__ == "__main__":
    sys.exit(main())
