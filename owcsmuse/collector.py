"""Deliverable 3: two-phase, resumable, idempotent collector.

LIST phase   : page /championships/{id}/matches for every included championship
               and upsert match stubs (ingest_state='stub').
DETAIL phase : for every match not yet complete, fetch /matches/{id} and
               /matches/{id}/stats, re-derive the series result from the detail
               payload (overwriting whatever LIST wrote; flips are logged), and
               replace the match's rounds / player rows inside one transaction.

State lives in matches.ingest_state, so an interrupted run resumes where it
stopped. Every write is an upsert or a delete+insert scoped to one match, so
re-running never duplicates rows. `reprocess` re-applies the latest stored raw
payloads without touching FACEIT.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import psycopg
from psycopg.types.json import Jsonb

from .config import Settings
from .db import RawPayloadStore
from .faceit.client import FaceitClient, FaceitClientError, FaceitNotFound, FaceitRetryExhausted
from .log import get_logger, log_event
from .parsers.matches import (
    BYE_NOTE,
    MatchRecord,
    SeriesResult,
    parse_match_detail,
    parse_match_stub,
    results_differ,
    winner_flipped,
)
from .parsers.stats import RoundRecord, parse_match_stats

log = get_logger("owcsmuse.collector")

RESUMABLE_STATES = ("stub", "detail_fetched")


@dataclass
class ListRunStats:
    championships: int = 0
    matches_seen: int = 0
    matches_inserted: int = 0
    matches_updated: int = 0
    truncated_championships: list[str] = field(default_factory=list)


@dataclass
class DetailRunStats:
    selected: int = 0
    complete: int = 0
    skipped: int = 0
    failed: int = 0
    result_flips: int = 0
    result_changes: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Collector:
    def __init__(
        self,
        conn: psycopg.Connection,
        client: Optional[FaceitClient],
        settings: Settings,
        raw_store: Optional[RawPayloadStore] = None,
    ) -> None:
        self.conn = conn
        self.client = client
        self.settings = settings
        self.raw_store = raw_store

    # ================================================================ manifest

    def load_manifest(self, manifest: dict[str, Any], accept_proposals: bool = False) -> dict[str, int]:
        """Upsert organizers + championships from a reviewed discovery manifest.

        `include` is only honoured for entries with a manual decision unless
        accept_proposals=True; classifier proposals alone never mark a
        championship included.
        """
        n_inc = n_manual = n_proposed_only = 0
        with self.conn.cursor() as cur:
            for org in manifest.get("organizers") or []:
                cur.execute(
                    """
                    INSERT INTO organizers (organizer_id, name)
                    VALUES (%s, %s)
                    ON CONFLICT (organizer_id) DO UPDATE
                        SET name = COALESCE(EXCLUDED.name, organizers.name), updated_at = now()
                    """,
                    (org["organizer_id"], org.get("name")),
                )
            for c in manifest["championships"]:
                if c.get("organizer_id"):
                    cur.execute(
                        "INSERT INTO organizers (organizer_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (c["organizer_id"], c.get("organizer_name")),
                    )
                manual = c.get("decision_source") == "manual"
                proposed_include = bool(c.get("include", False))
                include = proposed_include and (manual or accept_proposals)
                n_inc += int(include)
                n_manual += int(manual)
                n_proposed_only += int(proposed_include and not include)
                is_history = c.get("found_via") == "history_crawl"
                cur.execute(
                    """
                    INSERT INTO championships (championship_id, organizer_id, name, game_id, region, derived_region,
                        status, type, championship_start, subscription_start, subscription_end, faceit_url, include,
                        scope_region, tier, season, classification_source, classification_evidence, decision_note, classified_at,
                        source, organizer_name, first_match_at, last_match_at, matches_seen)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s, %s, %s, %s, %s)
                    ON CONFLICT (championship_id) DO UPDATE SET
                        source = EXCLUDED.source,
                        organizer_name = COALESCE(EXCLUDED.organizer_name, championships.organizer_name),
                        first_match_at = COALESCE(EXCLUDED.first_match_at, championships.first_match_at),
                        last_match_at = COALESCE(EXCLUDED.last_match_at, championships.last_match_at),
                        matches_seen = COALESCE(EXCLUDED.matches_seen, championships.matches_seen),
                        organizer_id = COALESCE(EXCLUDED.organizer_id, championships.organizer_id),
                        name = EXCLUDED.name,
                        game_id = COALESCE(EXCLUDED.game_id, championships.game_id),
                        region = COALESCE(EXCLUDED.region, championships.region),
                        derived_region = COALESCE(EXCLUDED.derived_region, championships.derived_region),
                        status = COALESCE(EXCLUDED.status, championships.status),
                        type = COALESCE(EXCLUDED.type, championships.type),
                        championship_start = COALESCE(EXCLUDED.championship_start, championships.championship_start),
                        subscription_start = COALESCE(EXCLUDED.subscription_start, championships.subscription_start),
                        subscription_end = COALESCE(EXCLUDED.subscription_end, championships.subscription_end),
                        faceit_url = COALESCE(EXCLUDED.faceit_url, championships.faceit_url),
                        include = EXCLUDED.include,
                        scope_region = EXCLUDED.scope_region,
                        tier = EXCLUDED.tier,
                        season = EXCLUDED.season,
                        classification_source = EXCLUDED.classification_source,
                        classification_evidence = EXCLUDED.classification_evidence,
                        decision_note = EXCLUDED.decision_note,
                        classified_at = now(),
                        updated_at = now()
                    """,
                    (
                        c["championship_id"], c.get("organizer_id"), c["name"], c.get("game_id"),
                        c.get("region"), c.get("derived_region"), c.get("status"), c.get("type"),
                        c.get("championship_start"), c.get("subscription_start"), c.get("subscription_end"),
                        c.get("faceit_url"), include,
                        c.get("scope_region"), c.get("tier"), c.get("season"),
                        "manual" if manual else "auto", Jsonb(c.get("evidence") or []), c.get("decision_note"),
                        "history" if is_history else "championship_api", c.get("organizer_name"),
                        c.get("first_match_at"), c.get("last_match_at"), c.get("matches_seen"),
                    ),
                )
        self.conn.commit()
        out = {"championships": len(manifest["championships"]), "included": n_inc, "manual_decisions": n_manual,
               "proposed_but_not_included": n_proposed_only}
        log_event(log, logging.INFO, "manifest_loaded", **out)
        return out

    def included_championships(self, ids: Optional[Sequence[str]] = None) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            if ids:
                cur.execute(
                    "SELECT championship_id, name FROM championships WHERE championship_id = ANY(%s) ORDER BY championship_start",
                    (list(ids),),
                )
            else:
                cur.execute("SELECT championship_id, name FROM championships WHERE include ORDER BY championship_start")
            rows = cur.fetchall()
        self.conn.commit()
        return rows

    # ==================================================================== LIST

    def run_list(self, championship_ids: Optional[Sequence[str]] = None) -> ListRunStats:
        assert self.client is not None, "LIST phase needs a FACEIT client"
        stats = ListRunStats()
        for ch in self.included_championships(championship_ids):
            cid = ch["championship_id"]
            listing = self.client.list_championship_matches(cid, "all")
            stats.championships += 1
            inserted = updated = 0
            try:
                with self.conn.cursor() as cur:
                    for item in listing.items:
                        rec = parse_match_stub(item)
                        stats.matches_seen += 1
                        self._upsert_teams(cur, rec)
                        if self._upsert_stub(cur, rec, cid):
                            inserted += 1
                        else:
                            updated += 1
                    cur.execute(
                        """
                        UPDATE championships
                        SET list_truncated = %s, list_completed_at = now(), updated_at = now()
                        WHERE championship_id = %s
                        """,
                        (listing.truncated, cid),
                    )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            stats.matches_inserted += inserted
            stats.matches_updated += updated
            if listing.truncated:
                stats.truncated_championships.append(cid)
                log_event(log, logging.WARNING, "championship_listing_truncated", championship_id=cid,
                          name=ch["name"], reachable=len(listing.items))
            log_event(log, logging.INFO, "championship_listed", championship_id=cid, name=ch["name"],
                      matches=len(listing.items), inserted=inserted, updated=updated, pages=listing.pages)
        log_event(log, logging.INFO, "list_phase_complete", championships=stats.championships,
                  matches_seen=stats.matches_seen, inserted=stats.matches_inserted, updated=stats.matches_updated)
        return stats

    def _upsert_stub(self, cur: psycopg.Cursor, rec: MatchRecord, championship_id: str) -> bool:
        """Insert or refresh a match stub. Never clobbers a DETAIL-derived result. Returns True on insert."""
        r = rec.result
        cur.execute(
            """
            INSERT INTO matches (
                match_id, championship_id, competition_name, game_id, region, best_of, status, round, "group",
                scheduled_at, configured_at, started_at, finished_at, faceit_url,
                faction1_team_id, faction2_team_id, faction1_name, faction2_name,
                winner_faction, winner_team_id, faction1_score, faction2_score, result_source,
                list_winner_faction, list_faction1_score, list_faction2_score,
                maps_picked, ingest_state, listed_at
            ) VALUES (
                %(match_id)s, %(championship_id)s, %(competition_name)s, %(game_id)s, %(region)s, %(best_of)s,
                %(status)s, %(round)s, %(group)s,
                %(scheduled_at)s, %(configured_at)s, %(started_at)s, %(finished_at)s, %(faceit_url)s,
                %(f1_id)s, %(f2_id)s, %(f1_name)s, %(f2_name)s,
                %(winner)s, %(winner_team)s, %(f1_score)s, %(f2_score)s, 'list',
                %(winner)s, %(f1_score)s, %(f2_score)s,
                %(maps_picked)s, %(ingest_state)s, now()
            )
            ON CONFLICT (match_id) DO UPDATE SET
                championship_id  = COALESCE(EXCLUDED.championship_id, matches.championship_id),
                competition_name = COALESCE(EXCLUDED.competition_name, matches.competition_name),
                game_id          = COALESCE(EXCLUDED.game_id, matches.game_id),
                region           = COALESCE(EXCLUDED.region, matches.region),
                best_of          = COALESCE(EXCLUDED.best_of, matches.best_of),
                status           = COALESCE(EXCLUDED.status, matches.status),
                round            = COALESCE(EXCLUDED.round, matches.round),
                "group"          = COALESCE(EXCLUDED."group", matches."group"),
                scheduled_at     = COALESCE(EXCLUDED.scheduled_at, matches.scheduled_at),
                configured_at    = COALESCE(EXCLUDED.configured_at, matches.configured_at),
                started_at       = COALESCE(EXCLUDED.started_at, matches.started_at),
                finished_at      = COALESCE(EXCLUDED.finished_at, matches.finished_at),
                faceit_url       = COALESCE(EXCLUDED.faceit_url, matches.faceit_url),
                faction1_team_id = COALESCE(EXCLUDED.faction1_team_id, matches.faction1_team_id),
                faction2_team_id = COALESCE(EXCLUDED.faction2_team_id, matches.faction2_team_id),
                faction1_name    = COALESCE(EXCLUDED.faction1_name, matches.faction1_name),
                faction2_name    = COALESCE(EXCLUDED.faction2_name, matches.faction2_name),
                -- LIST audit columns always reflect the latest listing
                list_winner_faction = EXCLUDED.list_winner_faction,
                list_faction1_score = EXCLUDED.list_faction1_score,
                list_faction2_score = EXCLUDED.list_faction2_score,
                -- the authoritative result is only touched while it is still LIST-sourced
                winner_faction = CASE WHEN matches.result_source = 'detail' THEN matches.winner_faction ELSE EXCLUDED.winner_faction END,
                winner_team_id = CASE WHEN matches.result_source = 'detail' THEN matches.winner_team_id ELSE EXCLUDED.winner_team_id END,
                faction1_score = CASE WHEN matches.result_source = 'detail' THEN matches.faction1_score ELSE EXCLUDED.faction1_score END,
                faction2_score = CASE WHEN matches.result_source = 'detail' THEN matches.faction2_score ELSE EXCLUDED.faction2_score END,
                maps_picked    = COALESCE(EXCLUDED.maps_picked, matches.maps_picked),
                -- a status change (e.g. ONGOING -> FINISHED) re-queues the match for DETAIL
                ingest_state   = CASE WHEN matches.status IS DISTINCT FROM EXCLUDED.status THEN 'stub' ELSE matches.ingest_state END,
                listed_at      = now(),
                updated_at     = now()
            RETURNING (xmax = 0) AS inserted
            """,
            {
                "match_id": rec.match_id,
                "championship_id": rec.championship_id or championship_id,
                "competition_name": rec.competition_name,
                "game_id": rec.game_id,
                "region": rec.region,
                "best_of": rec.best_of,
                "status": rec.status,
                "round": rec.round,
                "group": rec.group,
                "scheduled_at": rec.scheduled_at,
                "configured_at": rec.configured_at,
                "started_at": rec.started_at,
                "finished_at": rec.finished_at,
                "faceit_url": rec.faceit_url,
                "f1_id": rec.faction1.team_id if rec.faction1 else None,
                "f2_id": rec.faction2.team_id if rec.faction2 else None,
                "f1_name": rec.faction1.name if rec.faction1 else None,
                "f2_name": rec.faction2.name if rec.faction2 else None,
                "ingest_state": "skipped" if rec.involves_bye else "stub",
                "winner": r.winner_faction,
                "winner_team": rec.winner_team_id,
                "f1_score": r.faction1_score,
                "f2_score": r.faction2_score,
                "maps_picked": len(rec.picks) or None,
            },
        )
        row = cur.fetchone()
        return bool(row and row["inserted"])

    # ================================================================== DETAIL

    def pending_match_ids(
        self,
        championship_ids: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
        include_failed: bool = False,
        refresh: bool = False,
        states: Optional[Sequence[str]] = None,
    ) -> list[str]:
        if states is None:
            states = list(RESUMABLE_STATES)
            if include_failed:
                states += ["failed", "result_only"]
            if refresh:
                states += ["complete", "skipped"]
        sql = """
            SELECT match_id FROM matches m
            WHERE m.ingest_state = ANY(%(states)s)
              AND (%(cids)s::text[] IS NULL OR m.championship_id = ANY(%(cids)s))
              AND (%(cids)s::text[] IS NOT NULL OR EXISTS (
                    SELECT 1 FROM championships c WHERE c.championship_id = m.championship_id AND c.include))
            ORDER BY m.started_at NULLS LAST, m.match_id
        """
        params: dict[str, Any] = {"states": list(states), "cids": list(championship_ids) if championship_ids else None}
        if limit:
            sql += " LIMIT %(limit)s"
            params["limit"] = limit
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            ids = [r["match_id"] for r in cur.fetchall()]
        self.conn.commit()
        return ids

    def run_detail(
        self,
        championship_ids: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
        include_failed: bool = False,
        refresh: bool = False,
    ) -> DetailRunStats:
        assert self.client is not None, "DETAIL phase needs a FACEIT client"
        ids = self.pending_match_ids(championship_ids, limit, include_failed, refresh)
        stats = DetailRunStats(selected=len(ids))
        log_event(log, logging.INFO, "detail_phase_start", selected=len(ids))
        for i, mid in enumerate(ids, start=1):
            outcome = self.process_match(mid)
            self._tally(stats, outcome)
            if i % 50 == 0:
                log_event(log, logging.INFO, "detail_phase_progress", done=i, of=len(ids),
                          complete=stats.complete, failed=stats.failed, flips=stats.result_flips)
        log_event(log, logging.INFO, "detail_phase_complete", selected=stats.selected, complete=stats.complete,
                  skipped=stats.skipped, failed=stats.failed, result_flips=stats.result_flips,
                  result_changes=stats.result_changes)
        return stats

    @staticmethod
    def _tally(stats: DetailRunStats, outcome: dict[str, Any]) -> None:
        state = outcome.get("state")
        if state == "complete":
            stats.complete += 1
        elif state == "skipped":
            stats.skipped += 1
        elif state == "failed":
            stats.failed += 1
        stats.result_flips += int(bool(outcome.get("flipped")))
        stats.result_changes += int(bool(outcome.get("changed")))

    def process_match(self, match_id: str) -> dict[str, Any]:
        """Fetch detail (+stats when finished) and apply. Returns a small outcome dict."""
        assert self.client is not None
        try:
            detail = self.client.get_match(match_id)
        except FaceitNotFound as exc:
            return self._mark_failed(match_id, f"detail 404: {exc.body!r}"[:500])
        except FaceitRetryExhausted as exc:
            self._mark_failed(match_id, f"detail retries exhausted: {exc}")
            raise
        except FaceitClientError as exc:
            return self._mark_failed(match_id, f"detail {exc.status}: {exc.body!r}"[:500])

        rec = parse_match_detail(detail.payload)
        stats_payload = None
        stats_raw_id = None
        stats_error = None
        if rec.status == "FINISHED":
            try:
                st = self.client.get_match_stats(match_id)
                stats_payload, stats_raw_id = st.payload, st.raw_id
            except FaceitNotFound as exc:
                stats_error = f"stats 404: {exc.body!r}"[:500]
            except FaceitRetryExhausted as exc:
                self._mark_failed(match_id, f"stats retries exhausted: {exc}")
                raise
            except FaceitClientError as exc:
                stats_error = f"stats {exc.status}: {exc.body!r}"[:500]

        return self.apply_detail(rec, detail.raw_id, stats_payload, stats_raw_id, stats_error)

    def _mark_failed(self, match_id: str, error: str) -> dict[str, Any]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE matches SET ingest_state = 'failed', ingest_error = %s,
                       ingest_attempts = ingest_attempts + 1, updated_at = now()
                WHERE match_id = %s
                """,
                (error, match_id),
            )
        self.conn.commit()
        log_event(log, logging.ERROR, "match_ingest_failed", match_id=match_id, error=error)
        return {"match_id": match_id, "state": "failed", "error": error}

    def apply_detail(
        self,
        rec: MatchRecord,
        detail_raw_id: Optional[int],
        stats_payload: Optional[dict[str, Any]],
        stats_raw_id: Optional[int],
        stats_error: Optional[str] = None,
    ) -> dict[str, Any]:
        """Write everything derived from a detail (+stats) payload in one transaction."""
        mid = rec.match_id
        rounds: list[RoundRecord] = []
        if stats_payload is not None:
            rounds = parse_match_stats(stats_payload, rec.map_names, mid)

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT winner_faction, faction1_score, faction2_score, result_source,
                           list_winner_faction, list_faction1_score, list_faction2_score, status, championship_id
                    FROM matches WHERE match_id = %s FOR UPDATE
                    """,
                    (mid,),
                )
                existing = cur.fetchone()
                flipped = changed = False
                if existing:
                    list_result = SeriesResult(
                        existing["list_winner_faction"], existing["list_faction1_score"], existing["list_faction2_score"]
                    )
                    current = SeriesResult(existing["winner_faction"], existing["faction1_score"], existing["faction2_score"])
                    flipped = winner_flipped(list_result, rec.result)
                    changed = current.is_known and results_differ(current, rec.result)
                    if flipped:
                        log_event(
                            log, logging.WARNING, "series_result_flipped", match_id=mid,
                            championship_id=rec.championship_id,
                            list_winner=list_result.winner_faction,
                            list_score=f"{list_result.faction1_score}-{list_result.faction2_score}",
                            detail_winner=rec.result.winner_faction,
                            detail_score=f"{rec.result.faction1_score}-{rec.result.faction2_score}",
                            faction1=rec.faction1.name if rec.faction1 else None,
                            faction2=rec.faction2.name if rec.faction2 else None,
                        )
                    elif changed:
                        log_event(
                            log, logging.INFO, "series_result_changed", match_id=mid,
                            previous_source=existing["result_source"],
                            previous=f"{current.winner_faction} {current.faction1_score}-{current.faction2_score}",
                            detail=f"{rec.result.winner_faction} {rec.result.faction1_score}-{rec.result.faction2_score}",
                        )
                else:
                    # A detail applied without a stub (reprocess of an orphan) still needs a championship row.
                    self._ensure_championship(cur, rec)

                self._upsert_teams(cur, rec)
                seen_at = rec.event_time or _now()
                # Stats rows can name players missing from the declared roster; make sure they exist.
                # The roster (detail payload) is authoritative for nicknames seen at this match.
                player_batch: dict[str, dict[str, Any]] = {}
                for entry in rec.roster:
                    player_batch.setdefault(entry.player_id, {
                        "id": entry.player_id, "nick": entry.nickname or entry.player_id, "nickname": entry.nickname,
                        "gpid": entry.game_player_id, "gpname": entry.game_player_name, "avatar": entry.avatar or None, "seen": seen_at,
                    })
                for rnd in rounds:
                    for t in rnd.teams:
                        self._upsert_team(cur, t.team_id, t.name, None, seen_at)
                    for p in rnd.players:
                        player_batch.setdefault(p.player_id, {
                            "id": p.player_id, "nick": p.nickname or p.player_id, "nickname": p.nickname,
                            "gpid": None, "gpname": None, "avatar": None, "seen": seen_at,
                        })
                self._upsert_players_batch(cur, list(player_batch.values()))

                if rec.involves_bye:
                    state, error = "skipped", BYE_NOTE  # never a series: no result, map or record to keep
                elif rec.status == "FINISHED":
                    if rounds:
                        state, error = "complete", None
                    elif stats_error and "404" in stats_error:
                        # FACEIT has the series result but no map stats (admin-scored decider, LAN event):
                        # keep the result for team records, nothing for map/player aggregates.
                        state, error = "result_only", stats_error
                    else:
                        state, error = "failed", stats_error or "stats missing or empty rounds[]"
                else:
                    state, error = "skipped", None  # cancelled / not played: nothing to score

                r = rec.result
                cur.execute(
                    """
                    INSERT INTO matches (match_id, championship_id, status, result_source, ingest_state)
                    VALUES (%(match_id)s, %(championship_id)s, %(status)s, 'detail', 'stub')
                    ON CONFLICT (match_id) DO NOTHING
                    """,
                    {"match_id": mid, "championship_id": rec.championship_id, "status": rec.status},
                )
                cur.execute(
                    """
                    UPDATE matches SET
                        championship_id  = COALESCE(%(championship_id)s, championship_id),
                        competition_name = COALESCE(%(competition_name)s, competition_name),
                        game_id = COALESCE(%(game_id)s, game_id),
                        region  = COALESCE(%(region)s, region),
                        best_of = COALESCE(%(best_of)s, best_of),
                        status  = COALESCE(%(status)s, status),
                        round   = COALESCE(%(round)s, round),
                        "group" = COALESCE(%(group)s, "group"),
                        scheduled_at  = COALESCE(%(scheduled_at)s, scheduled_at),
                        configured_at = COALESCE(%(configured_at)s, configured_at),
                        started_at    = COALESCE(%(started_at)s, started_at),
                        finished_at   = COALESCE(%(finished_at)s, finished_at),
                        faceit_url    = COALESCE(%(faceit_url)s, faceit_url),
                        faction1_team_id = COALESCE(%(f1_id)s, faction1_team_id),
                        faction2_team_id = COALESCE(%(f2_id)s, faction2_team_id),
                        faction1_name = COALESCE(%(f1_name)s, faction1_name),
                        faction2_name = COALESCE(%(f2_name)s, faction2_name),
                        -- DETAIL is authoritative: overwrite unconditionally
                        winner_faction = %(winner)s,
                        winner_team_id = %(winner_team)s,
                        faction1_score = %(f1_score)s,
                        faction2_score = %(f2_score)s,
                        result_source  = 'detail',
                        result_flipped = result_flipped OR %(flipped)s,
                        maps_picked = COALESCE(%(maps_picked)s, maps_picked),
                        maps_played = %(maps_played)s,
                        ingest_state = %(state)s,
                        ingest_error = %(error)s,
                        ingest_attempts = ingest_attempts + 1,
                        detail_raw_id = COALESCE(%(detail_raw_id)s, detail_raw_id),
                        stats_raw_id  = COALESCE(%(stats_raw_id)s, stats_raw_id),
                        detail_fetched_at = now(),
                        stats_fetched_at  = CASE WHEN %(has_stats)s THEN now() ELSE stats_fetched_at END,
                        updated_at = now()
                    WHERE match_id = %(match_id)s
                    """,
                    {
                        "match_id": mid,
                        "championship_id": rec.championship_id,
                        "competition_name": rec.competition_name,
                        "game_id": rec.game_id,
                        "region": rec.region,
                        "best_of": rec.best_of,
                        "status": rec.status,
                        "round": rec.round,
                        "group": rec.group,
                        "scheduled_at": rec.scheduled_at,
                        "configured_at": rec.configured_at,
                        "started_at": rec.started_at,
                        "finished_at": rec.finished_at,
                        "faceit_url": rec.faceit_url,
                        "f1_id": rec.faction1.team_id if rec.faction1 else None,
                        "f2_id": rec.faction2.team_id if rec.faction2 else None,
                        "f1_name": rec.faction1.name if rec.faction1 else None,
                        "f2_name": rec.faction2.name if rec.faction2 else None,
                        "winner": r.winner_faction,
                        "winner_team": rec.winner_team_id,
                        "f1_score": r.faction1_score,
                        "f2_score": r.faction2_score,
                        "flipped": flipped,
                        "maps_picked": len(rec.picks) or None,
                        "maps_played": len(rounds) if stats_payload is not None else None,
                        "state": state,
                        "error": error,
                        "detail_raw_id": detail_raw_id,
                        "stats_raw_id": stats_raw_id,
                        "has_stats": stats_payload is not None,
                    },
                )

                # roster + picks: replace wholesale (scoped to this match => idempotent)
                # Batched writes (executemany pipelines the round trips, which matters on a remote pooler).
                cur.execute("DELETE FROM match_rosters WHERE match_id = %s", (mid,))
                seen_roster: dict[str, Any] = {}
                for e in rec.roster:
                    prev = seen_roster.get(e.player_id)
                    if prev is None or (prev.is_substitute and not e.is_substitute):
                        seen_roster[e.player_id] = e
                if seen_roster:
                    cur.executemany(
                        """
                        INSERT INTO match_rosters (match_id, player_id, faction, team_id, is_substitute,
                                                   nickname_at_match, game_player_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        [(mid, e.player_id, e.faction, e.team_id, e.is_substitute, e.nickname, e.game_player_name)
                         for e in seen_roster.values()],
                    )
                cur.execute("DELETE FROM match_map_picks WHERE match_id = %s", (mid,))
                if rec.picks:
                    cur.executemany(
                        "INSERT INTO match_map_picks (match_id, pick_order, map_guid, map_name) VALUES (%s, %s, %s, %s)",
                        [(mid, p.pick_order, p.map_guid, p.map_name) for p in rec.picks],
                    )

                # rounds + per-round players: only when we have stats (never wipe good data on a stats miss)
                if stats_payload is not None:
                    cur.execute("DELETE FROM match_rounds WHERE match_id = %s", (mid,))  # cascades match_players
                    if rounds:
                        cur.executemany(
                            """
                            INSERT INTO match_rounds (match_id, round_number, map_guid, map_name, game_mode, score_summary,
                                winner_team_id, team1_team_id, team1_score, team2_team_id, team2_score, team_stats, raw_round_stats)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            [
                                (
                                    mid, rnd.round_number, rnd.map_guid, rnd.map_name, rnd.game_mode, rnd.score_summary,
                                    rnd.winner_team_id,
                                    rnd.team1.team_id if rnd.team1 else None, rnd.team1.score if rnd.team1 else None,
                                    rnd.team2.team_id if rnd.team2 else None, rnd.team2.score if rnd.team2 else None,
                                    Jsonb({t.team_id: t.stats for t in rnd.teams}), Jsonb(rnd.raw_round_stats),
                                )
                                for rnd in rounds
                            ],
                        )
                        player_rows = []
                        seen_pr: set[tuple[int, str]] = set()
                        for rnd in rounds:
                            for p in rnd.players:
                                key = (rnd.round_number, p.player_id)
                                if key in seen_pr:
                                    continue
                                seen_pr.add(key)
                                player_rows.append((
                                    mid, rnd.round_number, p.player_id, p.team_id, p.nickname, p.role, p.result,
                                    p.eliminations, p.final_blows, p.deaths, p.assists, p.solo_kills, p.multi_kills,
                                    p.environmental_kills, p.damage_dealt, p.healing_done, p.damage_mitigated,
                                    p.objective_time, p.time_played, Jsonb(p.stats),
                                ))
                        if player_rows:
                            cur.executemany(
                                """
                                INSERT INTO match_players (match_id, round_number, player_id, team_id, nickname_at_match, role,
                                    result, eliminations, final_blows, deaths, assists, solo_kills, multi_kills,
                                    environmental_kills, damage_dealt, healing_done, damage_mitigated, objective_time,
                                    time_played, stats)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """,
                                player_rows,
                            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            log_event(log, logging.ERROR, "match_apply_failed", match_id=mid, exc_info=True)
            self._mark_failed(mid, "apply failed; see log")
            raise

        log_event(
            log, logging.INFO, "match_applied", match_id=mid, state=state, status=rec.status,
            winner=rec.result.winner_faction, score=f"{rec.result.faction1_score}-{rec.result.faction2_score}",
            maps_played=len(rounds) if stats_payload is not None else None, maps_picked=len(rec.picks),
            flipped=flipped, changed=changed, error=error,
        )
        return {"match_id": mid, "state": state, "flipped": flipped, "changed": changed, "error": error,
                "maps_played": len(rounds), "maps_picked": len(rec.picks)}

    # ================================================================ reprocess

    def reprocess(self, championship_ids: Optional[Sequence[str]] = None, limit: Optional[int] = None) -> DetailRunStats:
        """Re-apply the latest stored /matches/{id} (+/stats) payloads without contacting FACEIT."""
        assert self.raw_store is not None, "reprocess needs a RawPayloadStore"
        ids = self.pending_match_ids(championship_ids, limit, states=["stub", "detail_fetched", "complete", "skipped", "failed"])
        stats = DetailRunStats(selected=len(ids))
        for mid in ids:
            detail = self.raw_store.latest(f"/matches/{mid}", match_id=mid)
            if not detail:
                log_event(log, logging.INFO, "reprocess_no_detail_payload", match_id=mid)
                continue
            st = self.raw_store.latest(f"/matches/{mid}/stats", match_id=mid)
            rec = parse_match_detail(detail["payload"])
            outcome = self.apply_detail(rec, detail["id"], st["payload"] if st else None, st["id"] if st else None,
                                        None if st else "no stored stats payload")
            self._tally(stats, outcome)
        log_event(log, logging.INFO, "reprocess_complete", selected=stats.selected, complete=stats.complete,
                  skipped=stats.skipped, failed=stats.failed, result_flips=stats.result_flips)
        return stats

    # =================================================================== status

    def status(self) -> dict[str, Any]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT ingest_state, count(*) AS n FROM matches GROUP BY ingest_state ORDER BY ingest_state")
            by_state = {r["ingest_state"]: r["n"] for r in cur.fetchall()}
            cur.execute(
                """
                SELECT c.championship_id, c.name, c.include, c.list_truncated, c.list_completed_at,
                       count(m.match_id) AS matches,
                       count(*) FILTER (WHERE m.ingest_state = 'complete') AS complete,
                       count(*) FILTER (WHERE m.ingest_state = 'failed') AS failed,
                       count(*) FILTER (WHERE m.result_flipped) AS flipped
                FROM championships c LEFT JOIN matches m USING (championship_id)
                WHERE c.include
                GROUP BY c.championship_id ORDER BY c.championship_start
                """
            )
            per_champ = cur.fetchall()
            cur.execute("SELECT count(*) AS n, count(DISTINCT match_id) AS matches FROM match_rounds")
            rounds = cur.fetchone()
            cur.execute("SELECT count(*) AS n FROM raw_payloads")
            raw = cur.fetchone()
            cur.execute("SELECT championship_id, name FROM championships WHERE include AND list_truncated ORDER BY name")
            truncated = cur.fetchall()
        self.conn.commit()
        if truncated:
            log_event(log, logging.WARNING, "included_championships_truncated", count=len(truncated),
                      championships=[t["name"] for t in truncated])
        return {
            "truncated_included_championships": truncated,
            "matches_by_state": by_state,
            "rounds": rounds["n"],
            "matches_with_rounds": rounds["matches"],
            "raw_payloads": raw["n"],
            "championships": per_champ,
        }

    # ================================================================== helpers

    def _ensure_championship(self, cur: psycopg.Cursor, rec: MatchRecord) -> None:
        if not rec.championship_id:
            return
        if rec.organizer_id:
            cur.execute("INSERT INTO organizers (organizer_id) VALUES (%s) ON CONFLICT DO NOTHING", (rec.organizer_id,))
        cur.execute(
            """
            INSERT INTO championships (championship_id, organizer_id, name, game_id, region)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT (championship_id) DO NOTHING
            """,
            (rec.championship_id, rec.organizer_id, rec.competition_name or rec.championship_id, rec.game_id, rec.region),
        )

    def _upsert_teams(self, cur: psycopg.Cursor, rec: MatchRecord) -> None:
        seen_at = rec.event_time or _now()
        for team in (rec.faction1, rec.faction2):
            if team:
                self._upsert_team(cur, team.team_id, team.name, team.avatar, seen_at)

    @staticmethod
    def _upsert_team(cur: psycopg.Cursor, team_id: Optional[str], name: Optional[str], avatar: Optional[str], seen_at: datetime) -> None:
        if not team_id:
            return
        cur.execute(
            """
            INSERT INTO teams (team_id, name, avatar, first_seen_at, last_seen_at)
            VALUES (%(id)s, %(name)s, %(avatar)s, %(seen)s, %(seen)s)
            ON CONFLICT (team_id) DO UPDATE SET
                name = CASE WHEN EXCLUDED.name IS NOT NULL AND %(seen)s >= COALESCE(teams.last_seen_at, %(seen)s)
                            THEN EXCLUDED.name ELSE teams.name END,
                avatar = COALESCE(EXCLUDED.avatar, teams.avatar),
                first_seen_at = LEAST(teams.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at  = GREATEST(teams.last_seen_at, EXCLUDED.last_seen_at),
                updated_at = now()
            """,
            {"id": team_id, "name": name, "avatar": avatar, "seen": seen_at},
        )
        if name:
            cur.execute(
                """
                INSERT INTO team_names (team_id, name, first_seen_at, last_seen_at)
                VALUES (%(id)s, %(name)s, %(seen)s, %(seen)s)
                ON CONFLICT (team_id, name) DO UPDATE SET
                    first_seen_at = LEAST(team_names.first_seen_at, EXCLUDED.first_seen_at),
                    last_seen_at  = GREATEST(team_names.last_seen_at, EXCLUDED.last_seen_at)
                """,
                {"id": team_id, "name": name, "seen": seen_at},
            )

    @staticmethod
    def _upsert_players_batch(cur: psycopg.Cursor, rows: list[dict[str, Any]]) -> None:
        """Batched form of _upsert_player: one executemany for players, one for nickname history."""
        if not rows:
            return
        cur.executemany(
            """
            INSERT INTO players (player_id, nickname, game_player_id, game_player_name, avatar, first_seen_at, last_seen_at)
            VALUES (%(id)s, %(nick)s, %(gpid)s, %(gpname)s, %(avatar)s, %(seen)s, %(seen)s)
            ON CONFLICT (player_id) DO UPDATE SET
                nickname = CASE WHEN %(seen)s >= COALESCE(players.last_seen_at, %(seen)s) THEN EXCLUDED.nickname ELSE players.nickname END,
                game_player_name = CASE WHEN EXCLUDED.game_player_name IS NOT NULL
                                         AND %(seen)s >= COALESCE(players.last_seen_at, %(seen)s)
                                        THEN EXCLUDED.game_player_name ELSE players.game_player_name END,
                game_player_id = COALESCE(EXCLUDED.game_player_id, players.game_player_id),
                avatar = COALESCE(EXCLUDED.avatar, players.avatar),
                first_seen_at = LEAST(players.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at  = GREATEST(players.last_seen_at, EXCLUDED.last_seen_at),
                updated_at = now()
            """,
            rows,
        )
        nick_rows = [{"id": r["id"], "nick": r["nickname"], "seen": r["seen"]} for r in rows if r.get("nickname")]
        if nick_rows:
            cur.executemany(
                """
                INSERT INTO player_nicknames (player_id, nickname, first_seen_at, last_seen_at)
                VALUES (%(id)s, %(nick)s, %(seen)s, %(seen)s)
                ON CONFLICT (player_id, nickname) DO UPDATE SET
                    first_seen_at = LEAST(player_nicknames.first_seen_at, EXCLUDED.first_seen_at),
                    last_seen_at  = GREATEST(player_nicknames.last_seen_at, EXCLUDED.last_seen_at)
                """,
                nick_rows,
            )

    @staticmethod
    def _upsert_player(
        cur: psycopg.Cursor,
        player_id: str,
        nickname: Optional[str],
        game_player_id: Optional[str],
        game_player_name: Optional[str],
        avatar: Optional[str],
        seen_at: datetime,
    ) -> None:
        """GUID is identity; nickname is a mutable attribute with history in player_nicknames."""
        nick = nickname or player_id
        cur.execute(
            """
            INSERT INTO players (player_id, nickname, game_player_id, game_player_name, avatar, first_seen_at, last_seen_at)
            VALUES (%(id)s, %(nick)s, %(gpid)s, %(gpname)s, %(avatar)s, %(seen)s, %(seen)s)
            ON CONFLICT (player_id) DO UPDATE SET
                nickname = CASE WHEN %(seen)s >= COALESCE(players.last_seen_at, %(seen)s) THEN EXCLUDED.nickname ELSE players.nickname END,
                game_player_name = CASE WHEN EXCLUDED.game_player_name IS NOT NULL
                                         AND %(seen)s >= COALESCE(players.last_seen_at, %(seen)s)
                                        THEN EXCLUDED.game_player_name ELSE players.game_player_name END,
                game_player_id = COALESCE(EXCLUDED.game_player_id, players.game_player_id),
                avatar = COALESCE(EXCLUDED.avatar, players.avatar),
                first_seen_at = LEAST(players.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at  = GREATEST(players.last_seen_at, EXCLUDED.last_seen_at),
                updated_at = now()
            """,
            {"id": player_id, "nick": nick, "gpid": game_player_id, "gpname": game_player_name,
             "avatar": avatar or None, "seen": seen_at},
        )
        if nickname:
            cur.execute(
                """
                INSERT INTO player_nicknames (player_id, nickname, first_seen_at, last_seen_at)
                VALUES (%(id)s, %(nick)s, %(seen)s, %(seen)s)
                ON CONFLICT (player_id, nickname) DO UPDATE SET
                    first_seen_at = LEAST(player_nicknames.first_seen_at, EXCLUDED.first_seen_at),
                    last_seen_at  = GREATEST(player_nicknames.last_seen_at, EXCLUDED.last_seen_at)
                """,
                {"id": player_id, "nick": nickname, "seen": seen_at},
            )
