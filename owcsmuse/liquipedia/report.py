"""The reconciliation report: what linked, what did not on either side, and what a person has to decide."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .model import FaceitSide
from .pipeline import Run
from .reconcile import AMBIGUOUS, EXACT, STRONG, UNMATCHED


def _lp_line(lp) -> str:
    sc = f"{lp.score1}-{lp.score2}" if lp.score1 is not None and lp.score2 is not None else f"{lp.status1 or '?'}-{lp.status2 or '?'}"
    return f"{lp.played_at:%Y-%m-%d %H:%M}Z  {lp.team1} {sc} {lp.team2}  (bo{lp.best_of})"


def _f_line(f: FaceitSide) -> str:
    when = f"{f.time:%Y-%m-%d %H:%M}Z" if f.time else "no time"
    return f"{when}  {f.name1} {f.score1}-{f.score2} {f.name2}  (bo{f.best_of}, {f.state})  {f.match_id}"


def _bye_hint(run: Run, f: FaceitSide) -> str:
    """Why a FACEIT-only match may not be a played series: it was scored in the same minute the bracket's byes were."""
    near = [b for b in run.bye_times.get(f.championship_id, []) if f.time and abs((b - f.time).total_seconds()) <= 120]
    if near and f.state == "result_only":
        return f"    - suspect: no map stats, and scored within {min(abs((b - f.time).total_seconds()) for b in near):.0f} s of a bracket bye"
    return ""


def render(run: Run) -> str:
    res = run.result
    tiers = res.by_tier()
    by_comp: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(list))
    for lk in res.links:
        by_comp[run.page_names.get(lk.lp.pagename, lk.lp.pagename)][lk.tier].append(lk)
    for f in res.faceit_unlinked:
        by_comp[f.competition]["faceit_only"].append(f)
    faceit_total = defaultdict(int)
    for f in run.faceit:
        faceit_total[f.competition] += 1

    L: list[str] = []
    a = run.alignment()
    L += ["# Liquipedia <-> FACEIT reconciliation", "",
          f"Built from {len(run.raw_ids)} stored Liquipedia response(s) (raw_payloads id {', '.join(map(str, run.raw_ids))}); "
          f"no request was made to build this report. {len(run.lps)} Liquipedia records "
          f"({len(res.placeholders)} placeholder rows excluded) against {len(run.faceit)} FACEIT series in the same "
          f"{len(run.page_names)} competitions.", "",
          "Nothing here links into an answer. Exact and strong links are proposed; ambiguous matches and team-name "
          "mappings wait for review, and the disagreements section says where either source may be wrong.", ""]
    L += ["## Timezones", "",
          "Liquipedia's `date` is UTC (it equals `extradata.timestamp`, an epoch, exactly on every row). FACEIT's times are "
          "epoch seconds, so also UTC. Across the id-linked pairs FACEIT's start minus Liquipedia's scheduled time is: " +
          (f"median {a['median_min']} min, 5th-95th percentile {a['p05_min']} to {a['p95_min']}, extremes {a['min']} to {a['max']}; "
           f"{a['inside_window']} of {a['pairs']} inside the matching window "
           f"(-{res.window.before_min} to +{res.window.after_min} min)." if a else "no id-linked pairs."), ""]

    tot = {k: 0 for k in ("lp", "exact", "strong", "ambiguous", "unmatched", "faceit_only", "disagree")}
    L += ["## Summary by competition", "",
          "| competition | Liquipedia | FACEIT | exact | strong | ambiguous | Liquipedia only | FACEIT only | disagreements |",
          "|---|---|---|---|---|---|---|---|---|"]
    for name in sorted(by_comp):
        c = by_comp[name]
        n_lp = sum(len(c[t]) for t in (EXACT, STRONG, AMBIGUOUS, UNMATCHED))
        dis = sum(1 for lk in c[EXACT] + c[STRONG] if lk.disagreements)
        row = (n_lp, faceit_total.get(name, 0), len(c[EXACT]), len(c[STRONG]), len(c[AMBIGUOUS]), len(c[UNMATCHED]),
               len(c["faceit_only"]), dis)
        L.append(f"| {name} | " + " | ".join(map(str, row)) + " |")
        for k, v in zip(("lp", "faceit", "exact", "strong", "ambiguous", "unmatched", "faceit_only", "disagree"), row,
                        strict=True):
            tot[k] = tot.get(k, 0) + v
    L.append(f"| **total** | **{tot['lp']}** | **{len(run.faceit)}** | **{tot['exact']}** | **{tot['strong']}** | "
             f"**{tot['ambiguous']}** | **{tot['unmatched']}** | **{tot['faceit_only']}** | **{tot['disagree']}** |")
    L.append("")
    prov = [lk for lk in res.links if lk.faceit_id and lk.provisional]
    if prov:
        L += [f"{len(prov)} link(s) rest on a team-name mapping nobody has reviewed yet (marked provisional below).", ""]

    # ------------------------------------------------------------------ review
    amb = [lk for lk in tiers.get(AMBIGUOUS, []) if not lk.decision]        # a decided one is settled, below
    decided_amb = [lk for lk in tiers.get(AMBIGUOUS, []) if lk.decision]
    L += [f"## Needs review: ambiguous matches ({len(amb)})", ""]
    if not amb:
        L += ["None.", ""]
    for lk in amb:
        L += [f"### {_lp_line(lk.lp)}", f"- page: {lk.lp.page_url}", f"- why it is ambiguous: {lk.basis}"
              + (f" ({lk.decision})" if lk.decision else "")]
        for c in lk.candidates:
            bits = ", ".join(f"{k}={v}" for k, v in c.items() if k not in ("teams", "faceit_id", "competition") and v not in (None, [], ""))
            L.append(f"  - candidate {c.get('faceit_id')}: {c.get('teams', '')} - {bits}")
        if lk.evidence.get("suggestion"):
            L.append(f"- {lk.evidence['suggestion']} (a suggestion only: order is not evidence)")
        L += [f"- decide: `python -m owcsmuse liquipedia links decide {lk.lp.objectname} --faceit-id <id>` "
              f"or `--none`", ""]
    if decided_amb:
        L += ["", f"## Ambiguous matches already decided ({len(decided_amb)})", ""]
        for lk in decided_amb:
            L.append(f"- [{lk.decision}] {_lp_line(lk.lp)}" + (f"  -> FACEIT {lk.faceit_id}" if lk.faceit_id else "") + f"  ({lk.basis})")
        L.append("")

    dis = [lk for lk in res.links if lk.faceit_id and lk.disagreements]
    L += [f"## Linked pairs where the two sources disagree ({len(dis)})", "",
          "Either source can be wrong. `maps` tells which is more likely: FACEIT's own stats count the maps played.", ""]
    for lk in dis:
        f = next(x for x in run.faceit if x.match_id == lk.faceit_id)
        L += [f"- [{lk.tier}] {_lp_line(lk.lp)}", f"  FACEIT: {_f_line(f)}", f"  page: {lk.lp.page_url}"]
        for d in lk.disagreements:
            L.append(f"  - **{d['field']}**: Liquipedia {d['liquipedia']!r}, FACEIT {d['faceit']!r}" + (f" - {d['note']}" if d.get("note") else ""))
    L.append("")

    missing = [lk for lk in res.links if lk.evidence.get("kind") == "faceit_missing_from_warehouse"]
    L += [f"## Liquipedia records a FACEIT id we do not hold ({len(missing)})", "",
          "These are FACEIT matches that exist (Liquipedia names them) but our history crawl never found.", ""]
    for lk in missing:
        L.append(f"- {_lp_line(lk.lp)}  FACEIT id {lk.evidence['faceit_match_id']}  {lk.lp.page_url}")
    L.append("")

    aborted = [lk for lk in res.links if lk.evidence.get("faceit_room")]
    L += [f"## Liquipedia-only: the FACEIT room ended with no result ({len(aborted)})", "",
          "The page names a FACEIT room opened for these two teams that FACEIT aborted or cancelled with no result, so "
          "the record is the series' only source. A result entered later links the room on the next run.", ""]
    for lk in aborted:
        L.append(f"- {_lp_line(lk.lp)}  FACEIT room {lk.evidence['faceit_match_id']} ({lk.evidence['faceit_room']})  "
                 f"{lk.lp.page_url}")
    L.append("")

    if res.region_rejections:
        L += [f"## Cross-region candidates rejected ({len(res.region_rejections)})", ""]
        for r in res.region_rejections:
            L.append(f"- {r['teams']} ({r['lp']}, {r['lp_time']}): Liquipedia {r['lp_region']}, "
                     f"FACEIT {r['faceit_region']} ({r['faceit_id']})")
        L.append("")
    if run.duplicates.same_match or run.duplicates.same_faceit_id:
        L += ["## Duplicates", "",
              f"{len(run.duplicates.same_match)} record(s) repeated under the same (bracket, match2id), dropped; "
              f"{len(run.duplicates.same_faceit_id)} FACEIT id(s) claimed by more than one record, kept and flagged.", ""]
    else:
        L += ["## Duplicates", "", "None: every record had a distinct (bracket, match2id), and no FACEIT id appears twice.", ""]

    # ------------------------------------------------------------------ per competition
    L += ["## Completeness by competition", ""]
    for name in sorted(by_comp):
        c = by_comp[name]
        L += [f"### {name}", "",
              f"- links: {len(c[EXACT])} exact, {len(c[STRONG])} strong, {len(c[AMBIGUOUS])} ambiguous; "
              f"{len(c[UNMATCHED])} Liquipedia-only; {len(c['faceit_only'])} FACEIT-only"]
        for lk in c[STRONG]:
            L.append(f"  - strong{' (provisional)' if lk.provisional else ''}: {_lp_line(lk.lp)} -> {lk.faceit_id} - {lk.basis}")
        if c["faceit_only"]:
            L.append("- FACEIT matches with no Liquipedia counterpart:")
            for f in sorted(c["faceit_only"], key=lambda f: f.time.timestamp() if f.time else 0):
                L.append(f"  - {_f_line(f)}")
                if _bye_hint(run, f):
                    L.append(_bye_hint(run, f))
        if c[UNMATCHED]:
            L.append("- Liquipedia matches with no FACEIT counterpart:")
            for lk in c[UNMATCHED]:
                L.append(f"  - {_lp_line(lk.lp)}  ({lk.basis})  {lk.lp.page_url}")
        L.append("")
    return "\n".join(L)
