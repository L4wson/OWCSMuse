"""History-crawl LIST phase.

FACEIT does not expose the 2025/2026 OWCS main series through the
championship endpoints; the only route is /players/{id}/history, which names
the competition on every match. The crawl:

  1. seeds crawl_players (from ingested rosters, explicit ids or team search),
  2. walks the frontier generation by generation: for each uncrawled player it
     pages the ow2 history since HISTORY_START in adaptive time windows,
  3. records every history item in history_matches (main series or not),
  4. classifies each competition with scope.classify_history_competition plus
     the reviewed decisions; main-series matches become match stubs for the
     unchanged DETAIL phase, and their rosters extend the frontier,
  5. writes per-generation counters so the convergence curve is inspectable.

Every write is an upsert keyed by id, and each player's crawl commits on its
own, so an interrupted run resumes from the frontier.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import psycopg
from psycopg.types.json import Jsonb

from .collector import Collector
from .config import Settings
from .db import RawPayloadStore
from .faceit.client import FaceitClient, FaceitClientError, FaceitNotFound, FaceitRetryExhausted
from .logging import get_logger, log_event
from .parsers.matches import MatchRecord, parse_history_item
from .scope import Classification, Decisions, classify_history_competition

log = get_logger("owcsmuse.crawl")

HISTORY_START = datetime(2025, 1, 1, tzinfo=timezone.utc)
WINDOW_DAYS = 91
MIN_WINDOW_DAYS = 7
PAGE = 100
MAX_ITEMS_PER_WINDOW = 600  # FACEIT offset cap: a full 600 means we are probably missing items


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CrawlStats:
    run_id: Optional[int] = None
    generations: int = 0
    players_crawled: int = 0
    requests: int = 0
    history_items: int = 0
    new_main_matches: int = 0
    new_players: int = 0
    errors: int = 0
    per_generation: list[dict[str, Any]] = field(default_factory=list)


class Crawler:
    def __init__(self, conn: psycopg.Connection, client: Optional[FaceitClient], settings: Settings,
                 raw_store: Optional[RawPayloadStore] = None, decisions: Optional[Decisions] = None) -> None:
        self.conn = conn
        self.client = client
        self.settings = settings
        self.raw_store = raw_store
        self.decisions = decisions or Decisions()
        self.collector = Collector(conn, client, settings, raw_store)
        self._class_cache: dict[str, Classification] = {}

    # ------------------------------------------------------------------ seeding

    def seed_from_rosters(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawl_players (player_id, nickname, source, generation)
                SELECT DISTINCT ON (r.player_id) r.player_id, r.nickname_at_match, 'roster_db', 0
                FROM match_rosters r JOIN matches m USING (match_id)
                ORDER BY r.player_id, m.started_at DESC NULLS LAST
                ON CONFLICT (player_id) DO NOTHING
                """
            )
            n = cur.rowcount
        self.conn.commit()
        log_event(log, logging.INFO, "crawl_seeded", source="roster_db", added=n)
        return n

    def seed_players(self, player_ids: Iterable[str], source: str = "explicit", nicknames: Optional[dict[str, str]] = None) -> int:
        n = 0
        with self.conn.cursor() as cur:
            for pid in player_ids:
                cur.execute(
                    "INSERT INTO crawl_players (player_id, nickname, source, generation) VALUES (%s, %s, %s, 0) ON CONFLICT DO NOTHING",
                    (pid, (nicknames or {}).get(pid), source),
                )
                n += cur.rowcount
        self.conn.commit()
        log_event(log, logging.INFO, "crawl_seeded", source=source, added=n)
        return n

    def seed_from_team_search(self, team_names: Iterable[str], exact: bool = True) -> dict[str, int]:
        """Search FACEIT teams by name and seed their members."""
        assert self.client is not None
        out: dict[str, int] = {}
        for name in team_names:
            res = self.client.search_teams(name)
            hits = [t for t in res.items if not exact or (t.get("name") or "").strip().lower() == name.strip().lower()]
            ids: list[str] = []
            nicks: dict[str, str] = {}
            for t in hits[:5]:
                try:
                    team = self.client.get_team(t["team_id"]).payload or {}
                except FaceitClientError:
                    continue
                for m in team.get("members") or []:
                    if m.get("user_id"):
                        ids.append(m["user_id"])
                        nicks[m["user_id"]] = m.get("nickname")
            out[name] = self.seed_players(ids, "team_search", nicks)
        return out

    # ---------------------------------------------------------------- frontier

    def frontier(self, generation: Optional[int] = None, limit: Optional[int] = None) -> list[dict[str, Any]]:
        sql = "SELECT player_id, nickname, generation FROM crawl_players WHERE crawled_at IS NULL"
        params: list[Any] = []
        if generation is not None:
            sql += " AND generation = %s"
            params.append(generation)
        sql += " ORDER BY generation, added_at, player_id"
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        self.conn.commit()
        return rows

    def projection(self) -> dict[str, Any]:
        """Estimate the request cost of crawling the current frontier."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n, min(generation) AS g FROM crawl_players WHERE crawled_at IS NULL")
            f = cur.fetchone()
            cur.execute("SELECT avg(requests) AS avg_req, count(*) AS n FROM crawl_players WHERE crawled_at IS NOT NULL AND requests IS NOT NULL")
            done = cur.fetchone()
        self.conn.commit()
        n_windows = max(1, int(((_now() - HISTORY_START).days + WINDOW_DAYS - 1) // WINDOW_DAYS))
        default_per_player = n_windows * 2  # most windows fit in one page; some need two
        avg = float(done["avg_req"]) if done["avg_req"] is not None else float(default_per_player)
        proj = int(round(f["n"] * avg))
        return {
            "frontier_players": f["n"],
            "next_generation": f["g"],
            "avg_requests_per_crawled_player": round(avg, 2),
            "basis": f"{done['n']} crawled players" if done["n"] else f"default {n_windows} windows x 2 pages",
            "projected_requests_this_frontier": proj,
            "projected_minutes_at_10_rps": round(proj / 10 / 60, 1),
            "note": "transitive expansion adds further generations; each is projected again before it runs",
        }

    # ------------------------------------------------------------------- crawl

    def _classify(self, competition_id: str, name: str, first_match_at: Optional[datetime], region: Optional[str]) -> Classification:
        key = competition_id or name
        if key not in self._class_cache:
            proposed = classify_history_competition(name, first_match_at, region)
            self._class_cache[key] = self.decisions.apply(competition_id, proposed) if competition_id else proposed
        return self._class_cache[key]

    def fetch_history(self, player_id: str, start: datetime, end: datetime, stats: CrawlStats) -> list[dict[str, Any]]:
        """All history items in [start, end), splitting windows that hit the offset cap."""
        assert self.client is not None
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            res = self.client.player_history(player_id, "ow2", int(start.timestamp()), int(end.timestamp()), offset, PAGE)
            stats.requests += 1
            page = (res.payload or {}).get("items") or []
            items.extend(page)
            if len(page) < PAGE:
                return items
            offset += PAGE
            if offset > self.settings.max_offset:
                break
        # hit the cap: split the window unless it is already small
        span = end - start
        if span <= timedelta(days=MIN_WINDOW_DAYS):
            log_event(log, logging.WARNING, "history_window_truncated", player_id=player_id, start=start, end=end, items=len(items))
            return items
        mid = start + span / 2
        return self.fetch_history(player_id, start, mid, stats) + self.fetch_history(player_id, mid, end, stats)

    def crawl_player(self, player: dict[str, Any], generation: int, run_id: Optional[int], stats: CrawlStats) -> dict[str, Any]:
        pid = player["player_id"]
        t0 = stats.requests
        try:
            items: list[dict[str, Any]] = []
            start = HISTORY_START
            end = _now() + timedelta(days=1)
            while start < end:
                w_end = min(start + timedelta(days=WINDOW_DAYS), end)
                items.extend(self.fetch_history(pid, start, w_end, stats))
                start = w_end
        except FaceitNotFound:
            self._mark_player(pid, error="history 404", requests=stats.requests - t0)
            stats.errors += 1
            return {"player_id": pid, "error": "404"}
        except FaceitRetryExhausted:
            self._mark_player(pid, error="retries exhausted", requests=stats.requests - t0, crawled=False)
            raise
        except FaceitClientError as exc:
            self._mark_player(pid, error=str(exc)[:200], requests=stats.requests - t0)
            stats.errors += 1
            return {"player_id": pid, "error": str(exc)[:100]}

        # de-duplicate (windows can overlap at boundaries)
        seen: dict[str, dict[str, Any]] = {}
        for it in items:
            seen.setdefault(it["match_id"], it)
        new_main = new_players = main_items = 0
        try:
            with self.conn.cursor() as cur:
                # Every history item is archived, but one INSERT per item is a round trip
                # per item against a remote pooler; batch them first.
                batch: list[tuple[dict[str, Any], MatchRecord, bool]] = []
                for it in seen.values():
                    rec = parse_history_item(it)
                    cls = self._classify(rec.championship_id or "", rec.competition_name or "", rec.started_at, rec.region)
                    is_main = cls.include
                    main_items += int(is_main)
                    batch.append((it, rec, is_main))
                self._record_history_matches(cur, batch, generation, pid)
                for _item, rec, is_main in batch:
                    if is_main:
                        self._ensure_history_championship(cur, rec, cls)
                        self.collector._upsert_teams(cur, rec)
                        if self.collector._upsert_stub(cur, rec, rec.championship_id):
                            new_main += 1
                            cur.execute(
                                "UPDATE matches SET discovered_via = 'history', discovered_generation = %s, discovered_by_player = %s WHERE match_id = %s",
                                (generation, pid, rec.match_id),
                            )
                        if rec.roster:
                            before = cur.execute(
                                "SELECT count(*) AS n FROM crawl_players WHERE player_id = ANY(%s)",
                                ([e.player_id for e in rec.roster],),
                            ).fetchone()["n"]
                            cur.executemany(
                                """
                                INSERT INTO crawl_players (player_id, nickname, source, discovered_from_match, generation)
                                VALUES (%s, %s, 'history_roster', %s, %s) ON CONFLICT (player_id) DO NOTHING
                                """,
                                [(e.player_id, e.nickname, rec.match_id, generation + 1) for e in rec.roster],
                            )
                            new_players += len({e.player_id for e in rec.roster}) - before
                cur.execute(
                    """
                    UPDATE crawl_players SET crawled_at = now(), history_items = %s, main_series_items = %s, requests = %s, last_error = NULL
                    WHERE player_id = %s
                    """,
                    (len(seen), main_items, stats.requests - t0, pid),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        stats.players_crawled += 1
        stats.history_items += len(seen)
        stats.new_main_matches += new_main
        stats.new_players += new_players
        log_event(log, logging.INFO, "player_crawled", player_id=pid, nickname=player.get("nickname"), generation=generation,
                  items=len(seen), main_series_items=main_items, new_main_matches=new_main, new_players=new_players,
                  requests=stats.requests - t0)
        return {"player_id": pid, "items": len(seen), "main": main_items, "new_main": new_main, "new_players": new_players}

    def _mark_player(self, pid: str, error: str, requests: int, crawled: bool = True) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE crawl_players SET crawled_at = CASE WHEN %s THEN now() ELSE crawled_at END, last_error = %s, requests = %s WHERE player_id = %s",
                (crawled, error, requests, pid),
            )
        self.conn.commit()

    def _record_history_matches(self, cur: psycopg.Cursor, batch: list[tuple[dict[str, Any], MatchRecord, bool]],
                                generation: int, pid: str) -> None:
        """Archive every history item seen, in one round trip."""
        if not batch:
            return
        rows = []
        for item, rec, is_main in batch:
            teams = [{"team_id": t.team_id, "name": t.name} for t in (rec.faction1, rec.faction2) if t]
            rows.append((
                rec.match_id, rec.championship_id, rec.competition_name, item.get("competition_type"), rec.organizer_id,
                rec.region, rec.status, rec.started_at, rec.finished_at, Jsonb(item.get("results")), Jsonb(teams),
                list(item.get("playing_players") or [e.player_id for e in rec.roster]), is_main, generation, pid,
            ))
        cur.executemany(
            """
            INSERT INTO history_matches (match_id, competition_id, competition_name, competition_type, organizer_id, region, status,
                started_at, finished_at, list_results, teams, player_ids, main_series, first_seen_generation, first_seen_player)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id) DO UPDATE SET seen_count = history_matches.seen_count + 1,
                main_series = history_matches.main_series OR EXCLUDED.main_series
            """,
            rows,
        )

    def _ensure_history_championship(self, cur: psycopg.Cursor, rec: MatchRecord, cls: Classification) -> None:
        if rec.organizer_id:
            cur.execute("INSERT INTO organizers (organizer_id) VALUES (%s) ON CONFLICT DO NOTHING", (rec.organizer_id,))
        cur.execute(
            """
            INSERT INTO championships (championship_id, organizer_id, name, game_id, region, derived_region, status, source,
                                       first_match_at, last_match_at, matches_seen, championship_start)
            VALUES (%(id)s, %(org)s, %(name)s, %(game)s, %(region)s, %(dregion)s, 'discovered', 'history', %(at)s, %(at)s, 1, %(at)s)
            ON CONFLICT (championship_id) DO UPDATE SET
                first_match_at = LEAST(championships.first_match_at, EXCLUDED.first_match_at),
                last_match_at  = GREATEST(championships.last_match_at, EXCLUDED.last_match_at),
                championship_start = LEAST(championships.championship_start, EXCLUDED.championship_start),
                matches_seen = COALESCE(championships.matches_seen, 0) + 1,
                updated_at = now()
            """,
            {"id": rec.championship_id, "org": rec.organizer_id, "name": rec.competition_name or rec.championship_id,
             "game": rec.game_id, "region": rec.region, "dregion": cls.region.upper() if cls.region in ("na", "emea") else None,
             "at": rec.started_at},
        )

    def run(self, max_generations: Optional[int] = None, max_players: Optional[int] = None) -> CrawlStats:
        assert self.client is not None, "the crawl needs a FACEIT client"
        stats = CrawlStats()
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO crawl_runs DEFAULT VALUES RETURNING run_id")
            stats.run_id = cur.fetchone()["run_id"]
        self.conn.commit()
        crawled_total = 0
        gens_done = 0
        try:
            while True:
                front = self.frontier()
                if not front or (max_generations is not None and gens_done >= max_generations):
                    break
                generation = front[0]["generation"]
                players = [p for p in front if p["generation"] == generation]
                if max_players is not None:
                    players = players[: max(0, max_players - crawled_total)]
                    if not players:
                        break
                proj = self.projection()
                log_event(log, logging.INFO, "crawl_generation_start", run_id=stats.run_id, generation=generation,
                          players=len(players), projected_requests=proj["projected_requests_this_frontier"])
                g_start = stats.requests
                g_items = stats.history_items
                g_main = stats.new_main_matches
                g_players = stats.new_players
                with self.conn.cursor() as cur:
                    cur.execute("INSERT INTO crawl_generations (run_id, generation) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                                (stats.run_id, generation))
                self.conn.commit()
                for p in players:
                    self.crawl_player(p, generation, stats.run_id, stats)
                    crawled_total += 1
                summary = {
                    "generation": generation, "players_crawled": len(players), "requests": stats.requests - g_start,
                    "history_items": stats.history_items - g_items, "new_main_matches": stats.new_main_matches - g_main,
                    "new_players": stats.new_players - g_players,
                }
                stats.per_generation.append(summary)
                gens_done += 1
                stats.generations = gens_done
                with self.conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE crawl_generations SET finished_at = now(), players_crawled = %s, requests = %s, history_items = %s,
                               new_main_matches = %s, new_players = %s WHERE run_id = %s AND generation = %s
                        """,
                        (summary["players_crawled"], summary["requests"], summary["history_items"], summary["new_main_matches"],
                         summary["new_players"], stats.run_id, generation),
                    )
                self.conn.commit()
                log_event(log, logging.INFO, "crawl_generation_done", run_id=stats.run_id, **summary)
        finally:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE crawl_runs SET finished_at = now(), generations = %s, players_crawled = %s, requests = %s,
                           new_matches = %s, new_players = %s, notes = %s WHERE run_id = %s
                    """,
                    (stats.generations, stats.players_crawled, stats.requests, stats.new_main_matches, stats.new_players,
                     Jsonb({"errors": stats.errors, "per_generation": stats.per_generation}), stats.run_id),
                )
            self.conn.commit()
        log_event(log, logging.INFO, "crawl_run_complete", run_id=stats.run_id, generations=stats.generations,
                  players=stats.players_crawled, requests=stats.requests, new_main_matches=stats.new_main_matches,
                  frontier_left=len(self.frontier()))
        return stats

    # ------------------------------------------------------------ inspection

    def competitions(self) -> list[dict[str, Any]]:
        """Every competition seen in crawled histories with counts, date range and classification proposal."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                -- count DISTINCT match_id: the lateral join over teams duplicates each match row per side
                SELECT competition_id, competition_name, organizer_id, max(region) AS region,
                       count(DISTINCT match_id) AS matches_seen,
                       min(started_at) AS first_match_at, max(started_at) AS last_match_at, bool_or(main_series) AS main_series,
                       count(DISTINCT t->>'team_id') AS teams
                FROM history_matches LEFT JOIN LATERAL jsonb_array_elements(teams) AS t ON true
                WHERE competition_id IS NOT NULL
                GROUP BY competition_id, competition_name, organizer_id
                ORDER BY min(started_at)
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT organizer_id, name FROM organizers")
            org_names = {r["organizer_id"]: r["name"] for r in cur.fetchall()}
        self.conn.commit()
        out = []
        for r in rows:
            cls = self._classify(r["competition_id"], r["competition_name"] or "", r["first_match_at"], r["region"])
            last = r["last_match_at"]
            out.append({
                "championship_id": r["competition_id"],
                "name": r["competition_name"],
                "organizer_id": r["organizer_id"],
                "organizer_name": org_names.get(r["organizer_id"]),
                "region": r["region"],
                "derived_region": cls.region.upper() if cls.region in ("na", "emea") else None,
                "status": "ongoing" if last and (_now() - last) < timedelta(days=14) else "finished",
                "type": None,
                "game_id": "ow2",
                "championship_start": r["first_match_at"].isoformat() if r["first_match_at"] else None,
                "first_match_at": r["first_match_at"].isoformat() if r["first_match_at"] else None,
                "last_match_at": last.isoformat() if last else None,
                "matches_seen": r["matches_seen"],
                "teams_seen": r["teams"],
                "subscription_start": None, "subscription_end": None, "faceit_url": None,
                "include": cls.include,
                "found_via": "history_crawl",
            })
        return out

    def status(self) -> dict[str, Any]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM crawl_generations ORDER BY run_id, generation")
            gens = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT count(*) FILTER (WHERE crawled_at IS NULL) AS frontier, count(*) FILTER (WHERE crawled_at IS NOT NULL) AS crawled, "
                        "count(*) FILTER (WHERE last_error IS NOT NULL) AS errored, coalesce(sum(requests), 0) AS requests FROM crawl_players")
            players = dict(cur.fetchone())
            cur.execute("SELECT generation, count(*) AS n FROM crawl_players WHERE crawled_at IS NULL GROUP BY generation ORDER BY generation")
            frontier_by_gen = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT c.championship_id, c.name, c.include, c.scope_region, c.tier, c.season, c.first_match_at, c.last_match_at,
                       count(m.match_id) AS matches, count(*) FILTER (WHERE m.ingest_state = 'complete') AS complete,
                       count(DISTINCT m.faction1_team_id) + 0 AS _f1
                FROM championships c LEFT JOIN matches m USING (championship_id)
                WHERE c.source = 'history'
                GROUP BY c.championship_id ORDER BY c.first_match_at
                """
            )
            comps = [dict(r) for r in cur.fetchall()]
            for comp in comps:
                cur.execute(
                    """
                    SELECT date_trunc('week', started_at)::date AS week, count(*) AS n
                    FROM matches WHERE championship_id = %s AND started_at IS NOT NULL GROUP BY 1 ORDER BY 1
                    """,
                    (comp["championship_id"],),
                )
                weeks = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    "SELECT count(DISTINCT team_id) AS teams FROM (SELECT faction1_team_id AS team_id FROM matches WHERE championship_id = %s "
                    "UNION SELECT faction2_team_id FROM matches WHERE championship_id = %s) t WHERE team_id IS NOT NULL",
                    (comp["championship_id"], comp["championship_id"]),
                )
                comp["teams"] = cur.fetchone()["teams"]
                comp.pop("_f1", None)
                comp["weeks"] = weeks
                comp["gaps"] = _gap_flags(weeks, comp)
        self.conn.commit()
        return {"players": players, "frontier_by_generation": frontier_by_gen, "generations": gens, "competitions": comps}


def _gap_flags(weeks: list[dict[str, Any]], comp: dict[str, Any]) -> list[str]:
    """Signals that a competition's matches are incomplete."""
    flags: list[str] = []
    if not weeks:
        return ["no matches"]
    counts = [w["n"] for w in weeks]
    first, last = weeks[0]["week"], weeks[-1]["week"]
    expected_weeks = int((last - first).days // 7) + 1
    if expected_weeks > len(weeks):
        present = {w["week"] for w in weeks}
        missing = [(first + timedelta(days=7 * i)).isoformat() for i in range(expected_weeks) if (first + timedelta(days=7 * i)) not in present]
        flags.append(f"{len(missing)} empty week(s) inside the span: {', '.join(missing[:6])}")
    if len(counts) >= 3:
        med = statistics.median(counts[1:-1]) if len(counts) > 2 else statistics.median(counts)
        low = [f"{w['week'].isoformat()}={w['n']}" for w in weeks[1:-1] if med and w["n"] < 0.25 * med]
        if low:
            flags.append(f"thin week(s) vs median {med:g}: {', '.join(low)}")
    n_teams = comp.get("teams") or 0
    name = (comp.get("name") or "").lower()
    if n_teams >= 4 and "regular season" in name:
        single_rr = n_teams * (n_teams - 1) // 2
        found = comp.get("matches") or 0
        if found < single_rr:
            flags.append(f"{found} matches < single round robin of {n_teams} teams ({single_rr})")
        elif single_rr < found < 2 * single_rr:
            flags.append(f"{found} matches between single ({single_rr}) and double ({2 * single_rr}) round robin of {n_teams} teams")
    if n_teams % 2 == 1 and n_teams > 1:
        flags.append(f"odd team count ({n_teams}); a team may be missing")
    return flags
