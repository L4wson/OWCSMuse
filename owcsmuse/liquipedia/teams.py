"""Liquipedia team name -> FACEIT org, proposed with evidence and decided by a person. Never fuzzy-matched silently.

Liquipedia calls a team "Spacestation Gaming" where FACEIT says "SpaceStation Gaming", "Virtus.pro" where it says
"Virtus pro", "Gen.G Esports" where it says "GenG". Guessing which is which by string similarity is how two wrong
org merges got made once already, so this follows the same gate as org and alias decisions:

  1. `propose` reads the pairs already tied together by an exact FACEIT id - the strongest evidence there is, since
     each names both teams - and tallies which FACEIT org stood opposite each Liquipedia name;
  2. a person reviews `scope/liquipedia_team_report.md` and decides (`liquipedia teams decide`, or accepts the
     strong proposals in bulk);
  3. decided mappings live in scope/liquipedia_team_map.json, the alias machinery's file format (an alias file whose
     aliases are Liquipedia names); the matcher trusts those, and only those, without a "provisional" flag.

The reconciler may also USE a proposal whose evidence is strong, but every link that rests on one is marked
provisional until the mapping is decided.

A name alone is not always enough. "Geekay Esports" is two unrelated teams, one in NA and one in EMEA, and the same
Liquipedia name stood opposite both FACEIT teams in the id-linked matches. OWCS is region-locked, so where the regions
disagree the proposal is per region ("Geekay Esports" in na, in emea) and a decision may carry a region too.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional


from ..aliases import AliasDecisions
from ..resolve import fold
from .matches import LPMatch
from .model import FaceitSide, Resolve, orient

TeamWindows = dict[str, list[tuple[Optional[datetime], Optional[datetime], str]]]   # team_id -> [(from, to, org_id)]


def _covers(entry: dict[str, Any], at: Optional[datetime]) -> bool:
    """Whether a windowed entry holds at `at`. No window, or no time to test, means yes."""
    if at is None:
        return True
    lo, hi = entry.get("valid_from"), entry.get("valid_to")
    lo = datetime.fromisoformat(lo) if isinstance(lo, str) else lo
    hi = datetime.fromisoformat(hi) if isinstance(hi, str) else hi
    return (lo is None or at >= lo) and (hi is None or at < hi)

DEFAULT_TEAM_MAP_PATH = "scope/liquipedia_team_map.json"
LOCKED = ("na", "emea")


def region_bucket(region: Optional[str]) -> Optional[str]:
    """Only NA and EMEA split a name; every other page is 'region-agnostic' (None)."""
    return region if region in LOCKED else None


class TeamMap(AliasDecisions):
    FILE_NOTE = ("Reviewed Liquipedia team name -> FACEIT org/team. Keys are the folded Liquipedia name, or 'name|na' / "
                 "'name|emea' when the same name is two teams in two regions; entity_type is 'org' (entity_id is the org "
                 "slug) or 'team' (an unmapped FACEIT team id). The reconciler trusts these and only these without "
                 "marking a link provisional. Edit by hand or with `python -m owcsmuse liquipedia teams decide`.")

    def __init__(self, path: str | Path = DEFAULT_TEAM_MAP_PATH) -> None:
        super().__init__(path)

    @staticmethod
    def key(name: str, region: Optional[str] = None) -> str:
        return f"{fold(name)}|{region}" if region else fold(name)

    def find(self, name: str, region: Optional[str] = None, at: Optional[datetime] = None) -> Optional[dict]:
        """The decision for this name on a page of this region, at this moment.

        A region-specific entry wins over a general one. An entry may carry `valid_from` / `valid_to`, or `eras`: a
        list of {entity_type, entity_id, valid_from, valid_to} for a name that different team ids carried over time
        (a roster pickup on a stage boundary); the era covering `at` is the decision, and outside every era the name
        is undecided at that time - never the nearest one.
        """
        rb = region_bucket(region)
        for key in ([self.key(name, rb)] if rb else []) + [self.key(name)]:
            d = self.data.get(key)
            if not d:
                continue
            if d.get("eras"):
                era = next((e for e in d["eras"] if _covers(e, at)), None)
                return {**{k: v for k, v in d.items() if k != "eras"}, **era} if era else None
            return d if _covers(d, at) else None
        return None

    def decide(self, name: str, entity_type: str, entity_id: str, note: Optional[str] = None,
               region: Optional[str] = None, valid_from: Optional[str] = None, valid_to: Optional[str] = None) -> dict:
        d = self.set(name, entity_type, entity_id, note)          # validates the type; stores under the plain key
        if valid_from or valid_to:
            d.update({"valid_from": valid_from, "valid_to": valid_to})
        if region:
            self.data[self.key(name, region)] = self.data.pop(self.key(name))
        return d

    def org_key(self, name: str, region: Optional[str] = None, at: Optional[datetime] = None,
                team_windows: Optional[TeamWindows] = None) -> Optional[str]:
        """How the fact views key this name at `at`: an org's id, or a team id's org at that time, else `team:<id>`."""
        d = self.find(name, region, at)
        if not d:
            return None
        if d["entity_type"] == "org":
            return d["entity_id"]
        for lo, hi, org in (team_windows or {}).get(d["entity_id"], []):
            if at is not None and (lo is None or at >= lo) and (hi is None or at < hi):
                return org
        return f"team:{d['entity_id']}"


def entity_of_org_key(key: str) -> tuple[str, str]:
    """('org', slug) or ('team', team_id): the inverse of how the fact views key an org."""
    return ("team", key[len("team:"):]) if key.startswith("team:") else ("org", key)


@dataclass
class TeamProposal:
    lp_name: str
    org_key: Optional[str]
    strength: str                       # strong | review | none
    region: Optional[str] = None        # set when the same name is different teams in NA and EMEA
    evidence: list[str] = field(default_factory=list)
    pairs: int = 0                      # exact-linked matches that voted
    conflicts: dict[str, int] = field(default_factory=dict)   # other org keys that also stood opposite this name
    faceit_names: list[str] = field(default_factory=list)
    decided: bool = False

    @property
    def key(self) -> tuple[str, Optional[str]]:
        return fold(self.lp_name), self.region


def make_resolver(decided: TeamMap, proposals: Optional[dict[tuple[str, Optional[str]], TeamProposal]] = None,
                  use_proposals: bool = True, team_windows: Optional[TeamWindows] = None) -> Resolve:
    """Decided mappings first; then, when allowed, strong proposals (flagged 'proposed' so links can be marked provisional).

    `team_windows` (team id -> org windows, from team_orgs) keys a name decided to a team id the way the fact views
    key it at the series' time: the org inside its window, the team id itself outside.
    """
    def resolve(name: str, region: Optional[str] = None, at: Optional[datetime] = None) -> Optional[tuple[str, str]]:
        key = decided.org_key(name, region, at, team_windows)
        if key:
            return key, "decided"
        if use_proposals and proposals:
            rb = region_bucket(region)
            for k in ((fold(name), rb), (fold(name), None)):
                p = proposals.get(k)
                if p and p.org_key and p.strength == "strong":
                    return p.org_key, "proposed"
        return None
    return resolve


def propose(pairs: Iterable[tuple[LPMatch, FaceitSide]], all_lp_names: Iterable[str], decided: TeamMap,
            faceit_names: dict[str, set[str]], org_regions: dict[str, set[str]]) -> list[TeamProposal]:
    """Proposals for every Liquipedia team name, split by region only where the regions disagree.

    `pairs`: LP matches already tied to a FACEIT match by id. `faceit_names`: folded FACEIT team name -> org keys, the
    fallback evidence for a name that appears in no id-linked pair. `org_regions`: org key -> regions it has played in.
    """
    votes: dict[tuple[str, Optional[str]], Counter[str]] = defaultdict(Counter)
    seen_names: dict[tuple[str, Optional[str]], set[str]] = defaultdict(set)
    display: dict[str, str] = {}
    for lp, f in pairs:
        flip, basis = orient(lp, f)
        rb = region_bucket(lp.region)
        for n in (lp.team1, lp.team2):
            display.setdefault(fold(n), n)
        if flip is None or basis == "winner" or f.org1 is None or f.org2 is None:
            continue
        for name, org, fname in ((lp.team1, f.org2 if flip else f.org1, f.name2 if flip else f.name1),
                                 (lp.team2, f.org1 if flip else f.org2, f.name1 if flip else f.name2)):
            votes[(fold(name), rb)][org] += 1
            seen_names[(fold(name), rb)].add(fname)

    out: list[TeamProposal] = []
    for name in sorted({n for n in all_lp_names if n}, key=fold):
        k = fold(name)
        d = decided.org_key(name)
        decided_regions = [r for r in LOCKED if decided.data.get(TeamMap.key(name, r))]
        if d or len(decided_regions) == len(LOCKED):
            for r in (None, *LOCKED):
                key = decided.org_key(name, r) if r else d
                if key and (r is None or decided.data.get(TeamMap.key(name, r))):
                    out.append(TeamProposal(name, key, "strong", r, ["decided in scope/liquipedia_team_map.json"], decided=True))
            continue
        # one region decided, the other (or the region-agnostic case) is not: keep the decided half, still propose the rest
        for r in decided_regions:
            out.append(TeamProposal(name, decided.org_key(name, r), "strong", r, ["decided in scope/liquipedia_team_map.json"],
                                    decided=True))
        by_region = {rb: c for (kk, rb), c in votes.items() if kk == k and rb not in decided_regions}
        tops = {rb: c.most_common(1)[0][0] for rb, c in by_region.items()}
        # different orgs in different regions - or a region already decided separately, which is the same fact
        split = bool(decided_regions) or len({t for rb, t in tops.items() if rb in LOCKED}) > 1
        groups: dict[Optional[str], Counter[str]] = {}
        if split:
            groups = {rb: c for rb, c in by_region.items()}
        elif by_region:
            merged: Counter[str] = Counter()
            for c in by_region.values():
                merged.update(c)
            groups = {None: merged}
        for rb, tally in groups.items():
            (top, n), *rest = tally.most_common()
            names = set().union(*(seen_names[(k, r)] for r in (by_region if rb is None else [rb])))
            p = TeamProposal(name, top, "review", rb, pairs=sum(tally.values()), conflicts={o: c for o, c in rest},
                             faceit_names=sorted(names))
            name_equal = any(fold(fn) == k for fn in p.faceit_names)
            p.evidence.append(f"stood opposite FACEIT org '{top}' in {n} of {p.pairs} id-linked matches"
                              f"{f' on {rb} pages' if rb else ''} (FACEIT called it {', '.join(repr(x) for x in p.faceit_names)})")
            if name_equal:
                p.evidence.append("the folded names are identical")
            if split:
                p.evidence.append("REGION SPLIT: this name is different FACEIT teams in NA and EMEA, so it is decided per region")
            regs = [rb] if rb else [r for r in by_region if r in LOCKED]
            wrong = [r for r in regs if org_regions.get(top) and r not in org_regions[top]]
            if wrong:
                p.evidence.append(f"REGION: appears on {'/'.join(wrong)} pages but the org has only played "
                                  f"{'/'.join(sorted(org_regions[top]))}")
            if p.conflicts:
                p.evidence.append(f"CONFLICT: also stood opposite {p.conflicts}")
            if not p.conflicts and not wrong and (n >= 2 or name_equal):
                p.strength = "strong"
            out.append(p)
        if groups or decided_regions:
            continue
        cands = faceit_names.get(k, set())
        p = TeamProposal(name, None, "none")
        if len(cands) == 1:
            p.org_key, p.strength = next(iter(cands)), "review"
            p.evidence.append("no id-linked match to learn from; only the folded name equals a FACEIT team name")
        elif cands:
            p.evidence.append(f"no id-linked match; the folded name equals FACEIT teams of {len(cands)} different orgs")
        else:
            p.evidence.append("no id-linked match and no FACEIT team has this name")
        out.append(p)

    # Several Liquipedia names standing for one FACEIT team id is a rename or an acquisition (Rad -> LuneX, Team Z ->
    # Supernova, Ex Oblivione -> Virtus pro), and roster movement is not org identity. Each name may still be MATCHED to
    # that team id, but a person decides, and the histories are not to be merged until team-to-org mapping is date-bounded.
    by_org: dict[str, list[TeamProposal]] = defaultdict(list)
    for p in out:
        if p.org_key and not p.decided:
            by_org[p.org_key].append(p)
    for org, ps in by_org.items():
        if len({fold(x.lp_name) for x in ps}) > 1:
            names = ", ".join(sorted({repr(x.lp_name) for x in ps}))
            for p in ps:
                p.strength = "review"
                p.evidence.append(f"SHARED: {names} all stand for FACEIT team {org} - a rename or an acquisition; "
                                  "decide the name, but do not merge their histories")
    return out


def render_report(proposals: list[TeamProposal], n_pairs: int) -> str:
    strong = [p for p in proposals if p.strength == "strong" and not p.decided]
    review = [p for p in proposals if p.strength in ("review", "none") and not p.decided]
    decided = [p for p in proposals if p.decided]
    lines = [
        "# Liquipedia team names -> FACEIT orgs", "",
        f"{len({fold(p.lp_name) for p in proposals})} Liquipedia team names, learned from {n_pairs} matches Liquipedia ties "
        f"to FACEIT by match id. {len(decided)} decided, {len(strong)} proposed strong, {len(review)} need a person.", "",
        "Nothing is matched by fuzzy string similarity. Decide with:", "",
        "    python -m owcsmuse liquipedia teams decide \"<Liquipedia name>\" --org <org slug> [--region na|emea]   "
        "(or --team <FACEIT team id>)",
        "    python -m owcsmuse liquipedia teams accept        # accept every strong proposal below, in bulk", ""]

    def table(title: str, ps: list[TeamProposal]) -> None:
        if not ps:
            return
        lines.extend([f"## {title} ({len(ps)})", "", "| Liquipedia name | region | proposed org | matches | evidence |",
                      "|---|---|---|---|---|"])
        for p in ps:
            lines.append(f"| {p.lp_name} | {p.region or 'any'} | {p.org_key or '-'} | {p.pairs} | {'; '.join(p.evidence)} |")
        lines.append("")
    table("Proposed - strong evidence", strong)
    table("Needs review", review)
    table("Already decided", decided)
    return "\n".join(lines)
