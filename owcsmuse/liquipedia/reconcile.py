"""Tie Liquipedia matches to FACEIT matches, in tiers, and record which tier tied each pair.

Liquipedia is crowdsourced: most pages record the FACEIT match id, some do not, and either source can be wrong. So
the id is used when it is there and never relied on alone:

  exact      The record carries a FACEIT match id and we hold that match. (Then the two are compared anyway, and any
             disagreement - teams, score, winner, date, best-of - is reported, because a wrong id looks exactly like this.)
  strong     No id. Both teams resolve to known orgs, the same region, the time within a window, the same best-of, the
             same series score, and exactly one FACEIT match fits (and only this Liquipedia match claims it).
  ambiguous  Several candidates, or the pair matches but something disagrees. NEVER linked automatically: it goes to
             the review report, decided the way org and scope decisions are.
  unmatched  Nothing on the other side. Reported for both sources.

Traps handled on purpose:
  * The same two teams twice in a day (bracket, then grand final; a reset): separated by series score; if the scores
    are equal too, by nothing - order alone is offered as a suggestion, never applied.
  * Liquipedia team names do not match FACEIT names: they go through a reviewed mapping (teams.py), and a link that
    rests on an unreviewed proposal is marked provisional.
  * NA and EMEA are region-locked: a candidate in the other region is a mismatch, recorded, never a match.
  * A record that carries a FACEIT id is never re-matched by teams and time: if we do not hold that match, that is the
    finding (our crawl missed it), not a licence to link something else.
  * A record whose FACEIT id is a room FACEIT aborted, cancelled or paused with no result, opened for the same two teams, has
    no FACEIT counterpart: FACEIT holds nothing about the series, so the record stands alone as a Liquipedia-only
    series. A result entered later makes the room FINISHED, and the next run links it like any other.
  * A FACEIT match is tied to at most one Liquipedia match, so a match known to both sources is one match.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .matches import LPMatch
from .model import FaceitSide, Resolve, orient

EXACT, STRONG, AMBIGUOUS, UNMATCHED = "exact", "strong", "ambiguous", "unmatched"
# Disagreements that annotate an exact link without downgrading it.
SOFT_DISAGREEMENTS = frozenset({"date"})


@dataclass(frozen=True)
class Window:
    """How far a FACEIT match's time may sit from Liquipedia's scheduled time (minutes; FACEIT minus Liquipedia).

    Set from the 296 id-linked pairs of the Stage 1 fetch: FACEIT starts a median 45 minutes after Liquipedia's
    scheduled time (10 to 129 for 95% of them), so a match may start up to 6h later or 60 min sooner and still be
    the same match. `partial_hours` is how far apart two matches of the same pair may be before they are no longer
    even worth a reviewer's time.
    """
    before_min: int = 60
    after_min: int = 360
    partial_hours: int = 24


DEFAULT_WINDOW = Window()


@dataclass
class Link:
    lp: LPMatch
    tier: str
    faceit_id: Optional[str] = None
    basis: str = ""
    provisional: bool = False
    candidates: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    disagreements: list[dict[str, Any]] = field(default_factory=list)
    decision: Optional[str] = None


@dataclass
class Result:
    links: list[Link]
    faceit_unlinked: list[FaceitSide]
    region_rejections: list[dict[str, Any]] = field(default_factory=list)
    placeholders: list[LPMatch] = field(default_factory=list)
    window: Window = DEFAULT_WINDOW

    def by_tier(self) -> dict[str, list[Link]]:
        out: dict[str, list[Link]] = defaultdict(list)
        for link in self.links:
            out[link.tier].append(link)
        return out


def _minutes(f: FaceitSide, lp: LPMatch) -> Optional[float]:
    return (f.time - lp.played_at).total_seconds() / 60 if f.time else None


def _region_conflict(lp: LPMatch, f: FaceitSide) -> bool:
    """NA and EMEA are region-locked; 'international' fits any region."""
    return bool(lp.region and f.region and f.region != "international" and lp.region != f.region)


def _same_teams(lp: LPMatch, f: FaceitSide, resolve: Resolve) -> bool:
    """Both of the record's teams resolve, and to the two orgs of the FACEIT room: the room was opened for this series."""
    a, b = resolve(lp.team1, lp.region, lp.played_at), resolve(lp.team2, lp.region, lp.played_at)
    return bool(a and b and f.org1 and f.org2 and {a[0], b[0]} == {f.org1, f.org2})


def _implausible(score: tuple[Optional[int], Optional[int]], best_of: Optional[int]) -> bool:
    """More wins than a best-of-N allows (a 4-0 in a best-of-5): one source has counted something other than won maps."""
    return bool(best_of and score[0] is not None and score[1] is not None and max(score) > (best_of + 1) // 2)


def compare(lp: LPMatch, f: FaceitSide, resolve: Optional[Resolve], comps: Optional[set[str]], window: Window,
            flip: Optional[bool], basis: str) -> list[dict[str, Any]]:
    """Where a linked pair disagrees. Empty means the two sources tell the same story."""
    out: list[dict[str, Any]] = []

    def add(field_: str, lp_v: Any, f_v: Any, **extra: Any) -> None:
        out.append({"field": field_, "liquipedia": lp_v, "faceit": f_v, **extra})

    if resolve:
        a, b = resolve(lp.team1, lp.region, lp.played_at), resolve(lp.team2, lp.region, lp.played_at)
        if a and b and {a[0], b[0]} != {f.org1, f.org2}:
            add("teams", f"{lp.team1} / {lp.team2}", f"{f.name1} / {f.name2}",
                note="the two records name different teams: the page's FACEIT id may be wrong")
    if None in (lp.score1, lp.score2):
        add("score", f"{lp.status1 or '?'}-{lp.status2 or '?'} (no played score)", f"{f.score1}-{f.score2}")
    elif None not in (f.score1, f.score2):
        l_s, f_s = ((lp.score1, lp.score2), (f.score1, f.score2))
        if flip is not None:
            f_s = (f.score2, f.score1) if flip else (f.score1, f.score2)
        same = l_s == f_s if flip is not None else sorted(l_s) == sorted(f_s)
        if not same:
            notes = [f"FACEIT has stats for {f.maps} maps; Liquipedia lists {lp.n_games} games"]
            if _implausible((f.score1, f.score2), f.best_of):
                notes.append(f"FACEIT's {f.score1}-{f.score2} is more wins than a best-of-{f.best_of} allows")
            if _implausible((lp.score1, lp.score2), lp.best_of):
                notes.append(f"Liquipedia's {lp.score1}-{lp.score2} is more wins than a best-of-{lp.best_of} allows")
            add("score", f"{lp.score1}-{lp.score2}", f"{f.score1}-{f.score2}" if not flip else f"{f.score2}-{f.score1} (as LP orders them)",
                note="; ".join(notes))
    if flip is not None and basis in ("orgs", "names", "score") and lp.winner and f.winner:
        f_side = (3 - f.winner) if flip else f.winner
        if lp.winner != f_side:
            add("winner", f"team {lp.winner} ({lp.team1 if lp.winner == 1 else lp.team2})",
                f"faction {f.winner} ({f.name1 if f.winner == 1 else f.name2})")
    if lp.best_of and f.best_of and lp.best_of != f.best_of:
        wins = max(f.score1 or 0, f.score2 or 0, lp.score1 or 0, lp.score2 or 0)
        add("best_of", lp.best_of, f.best_of,
            note=f"a series won {wins}-x needs at least a best-of-{2 * wins - 1}" if wins > (min(lp.best_of, f.best_of) + 1) // 2 else None)
    dt = _minutes(f, lp)
    if dt is not None and not (-window.before_min <= dt <= window.after_min):
        add("date", lp.played_at.isoformat(timespec="minutes"), f.time.isoformat(timespec="minutes"),
            note=(f"FACEIT is {dt / 60:+.1f} h from Liquipedia's time; FACEIT has no start time for this series, so its "
                  "time is when the result was entered, and Liquipedia's is more likely the play time") if not f.time_reliable
            else f"FACEIT is {dt / 60:+.1f} h from Liquipedia's time")
    if comps and f.championship_id not in comps:
        add("competition", lp.pagename, f.competition)
    if not lp.finished:
        add("finished", "not finished", "finished")
    return out


def reconcile(lps: Iterable[LPMatch], faceit: Iterable[FaceitSide], resolve: Resolve,
              comps_of_page: Optional[dict[str, set[str]]] = None, window: Window = DEFAULT_WINDOW,
              decisions: Optional[dict[str, dict[str, Any]]] = None,
              no_result: Optional[dict[str, FaceitSide]] = None) -> Result:
    """`decisions`: {lp objectname: {"faceit_match_id": id | None}} - a reviewer's word on an ambiguous match.
    `no_result`: FACEIT rooms held but ended with no result (model.load_faceit_no_result), by match id."""
    comps_of_page = comps_of_page or {}
    decisions = decisions or {}
    no_result = no_result or {}
    faceit = list(faceit)
    by_id = {f.match_id: f for f in faceit}
    result = Result(links=[], faceit_unlinked=[], window=window)
    taken: dict[str, Link] = {}

    real = []
    for lp in lps:
        (result.placeholders if lp.placeholder else real).append(lp)

    # ---- tier 1: the page names the FACEIT match
    claims: dict[str, list[LPMatch]] = defaultdict(list)
    for lp in real:
        if lp.faceit_match_id:
            claims[lp.faceit_match_id].append(lp)
    idless: list[LPMatch] = []
    for lp in real:
        fid = lp.faceit_match_id
        if not fid:
            idless.append(lp)
        elif fid not in by_id and fid in no_result and _same_teams(lp, no_result[fid], resolve):
            room = no_result[fid]
            result.links.append(Link(lp, UNMATCHED, basis=f"its FACEIT room was {room.state} with no result: FACEIT holds "
                                                          "nothing about this series",
                                     evidence={"kind": "no_faceit_counterpart", "faceit_match_id": fid,
                                               "faceit_room": f"{room.state}_no_result"}))
        elif fid not in by_id:
            result.links.append(Link(lp, UNMATCHED, basis="its FACEIT match id is not in our warehouse",
                                     evidence={"faceit_match_id": fid, "kind": "faceit_missing_from_warehouse"}))
        elif len(claims[fid]) > 1:
            result.links.append(Link(lp, AMBIGUOUS, basis="another Liquipedia match claims the same FACEIT id",
                                     candidates=[{"faceit_id": fid, "also_claimed_by": [x.objectname for x in claims[fid] if x is not lp]}],
                                     evidence={"kind": "duplicate_faceit_id"}))
        else:
            f = by_id[fid]
            flip, basis = orient(lp, f, resolve)
            dis = compare(lp, f, resolve, comps_of_page.get(lp.pagename), window, flip, basis)
            hard = sorted({d["field"] for d in dis} - SOFT_DISAGREEMENTS)
            if hard:
                # The id says one thing and the records another: a wrong id looks exactly like this, and a wrong link
                # silently gives one team another team's result. Ambiguous, with the id as the one candidate, until a
                # person confirms or rejects it. A date gap alone is expected (FACEIT's result_only times are entry
                # times) and does not downgrade.
                link = Link(lp, AMBIGUOUS, basis=f"the page's FACEIT id disagrees with the FACEIT record on {', '.join(hard)}",
                            candidates=[{"faceit_id": fid, "disagrees_on": hard}],
                            evidence={"kind": "exact_id_disagrees", "orientation": basis}, disagreements=dis)
                dec = decisions.get(lp.objectname) or decisions.get(f"faceit:{fid}")   # a decision may name the FACEIT id
                if dec is not None:
                    want = dec.get("faceit_match_id")
                    if want and want in by_id and want not in taken:
                        link.decision, link.faceit_id = "confirmed", want
                        taken[want] = link
                    elif not want:
                        link.decision = "rejected"
            else:
                link = Link(lp, EXACT, fid, basis="FACEIT match id in links.faceit", evidence={"orientation": basis},
                            disagreements=dis)
                taken[fid] = link
            result.links.append(link)

    # ---- tiers 2-4: records with no id, against the FACEIT matches nothing has claimed
    pool = [f for f in faceit if f.match_id not in taken]
    strict: dict[str, list[tuple[FaceitSide, dict[str, Any]]]] = {}
    partial: dict[str, list[dict[str, Any]]] = {}
    unresolved: dict[str, list[str]] = {}
    for lp in idless:
        a, b = resolve(lp.team1, lp.region, lp.played_at), resolve(lp.team2, lp.region, lp.played_at)
        if not (a and b) or a[0] == b[0]:
            unresolved[lp.objectname] = [n for n, r in ((lp.team1, a), (lp.team2, b)) if not r]
            continue
        pair = frozenset({a[0], b[0]})
        comps = comps_of_page.get(lp.pagename)
        strict[lp.objectname], partial[lp.objectname] = [], []
        for f in pool:
            if f.pair != pair:
                continue
            if _region_conflict(lp, f):
                # one entry per (record, FACEIT match) pair: two meetings of the same teams give two records each
                result.region_rejections.append({"lp": lp.objectname, "lp_time": f"{lp.played_at:%Y-%m-%d %H:%M}Z",
                                                 "faceit_id": f.match_id, "lp_region": lp.region,
                                                 "faceit_region": f.region, "teams": f"{lp.team1} / {lp.team2}"})
                continue
            dt = _minutes(f, lp)
            # a FACEIT time that is only when the result was entered can be days off: still a candidate, never a strong one
            if dt is None or abs(dt) > (window.partial_hours if f.time_reliable else 24 * 7) * 60:
                continue
            flip = f.org1 != a[0]                           # orientation from the orgs: pair equality makes it exact
            failed = []
            if not f.time_reliable:
                failed.append("time (FACEIT has no start time: its time is when the result was entered)")
            elif not (-window.before_min <= dt <= window.after_min):
                failed.append("time")
            if lp.best_of and f.best_of and lp.best_of != f.best_of:
                failed.append("best_of")
            if None in (lp.score1, lp.score2) or None in (f.score1, f.score2):
                failed.append("score (not comparable)")
            elif ((lp.score1, lp.score2) != ((f.score2, f.score1) if flip else (f.score1, f.score2))):
                failed.append("score")
            if comps and f.championship_id not in comps:
                failed.append("competition")
            cand = {"faceit_id": f.match_id, "competition": f.competition,
                    "teams": f"{f.name1} {f.score1}-{f.score2} {f.name2}",
                    "faceit_time": f.time.isoformat(timespec="minutes") if f.time else None,
                    "minutes_from_liquipedia": round(dt), "disagrees_on": failed}
            if failed:
                partial[lp.objectname].append(cand)
            else:
                strict[lp.objectname].append((f, cand))

    claimants: dict[str, list[str]] = defaultdict(list)
    for name, cs in strict.items():
        for f, _ in cs:
            claimants[f.match_id].append(name)

    for lp in idless:
        n = lp.objectname
        dec = decisions.get(n)
        provisional = any((resolve(t, lp.region, lp.played_at) or ("", ""))[1] == "proposed" for t in (lp.team1, lp.team2))
        if n in unresolved:
            link = Link(lp, UNMATCHED, basis="team name not mapped: " + ", ".join(unresolved[n]),
                        evidence={"kind": "team_unmapped", "names": unresolved[n]})
        elif len(strict[n]) == 1 and len(claimants[strict[n][0][0].match_id]) == 1:
            f, cand = strict[n][0]
            same_pair = [g for g in pool if g.pair == f.pair and g is not f and g.time and f.time
                         and abs((g.time - f.time).total_seconds()) < 24 * 3600 and not _region_conflict(lp, g)]
            basis = "teams, region, time, best-of and series score agree; the only FACEIT match that fits"
            if same_pair:
                basis = (f"the same two teams met {len(same_pair) + 1} times within a day; separated by series score "
                         f"({lp.score1}-{lp.score2})")
            link = Link(lp, STRONG, f.match_id, basis=basis, provisional=provisional,
                        evidence={"minutes_from_liquipedia": cand["minutes_from_liquipedia"]},
                        disagreements=compare(lp, f, resolve, comps_of_page.get(lp.pagename), window,
                                              f.org1 != (resolve(lp.team1, lp.region, lp.played_at) or ("", ""))[0], "orgs"))
            taken[f.match_id] = link
        elif strict[n]:
            cands = [c for _, c in strict[n]]
            why = ("several FACEIT matches fit equally well" if len(strict[n]) > 1
                   else "another Liquipedia match fits the same FACEIT match")
            ev: dict[str, Any] = {"kind": "multiple_candidates"}
            if len(strict[n]) > 1:
                ev["suggestion"] = ("by time order: " + " -> ".join(c["faceit_id"] for c in sorted(cands, key=lambda c: c["faceit_time"] or "")))
            link = Link(lp, AMBIGUOUS, basis=why, provisional=provisional, candidates=cands, evidence=ev)
        elif partial[n]:
            link = Link(lp, AMBIGUOUS, basis="the same two teams within a day, but the records disagree",
                        provisional=provisional, candidates=partial[n], evidence={"kind": "partial_agreement"})
        else:
            link = Link(lp, UNMATCHED, basis="no FACEIT match with these two teams within "
                                             f"{window.partial_hours} h in the same region", provisional=provisional,
                        evidence={"kind": "no_faceit_counterpart"})
        # a reviewer's decision settles an ambiguous match: it names the FACEIT match, or says there is none
        if dec is not None and link.tier == AMBIGUOUS:
            want = dec.get("faceit_match_id")
            if want and want in by_id and want not in taken:
                link.decision, link.faceit_id = "confirmed", want
                taken[want] = link
            elif not want:
                link.decision = "rejected"
        result.links.append(link)

    result.faceit_unlinked = [f for f in faceit if f.match_id not in taken]
    return result
