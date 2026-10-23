"""The reviewed decision files say what the owner decided on 2026-10-02, and only that."""

import json

from owcsmuse.liquipedia.identity import PlayerDecisions
from owcsmuse.liquipedia.teams import TeamMap
from owcsmuse.orgs import OrgDecisions

SSG_2024, SSG_NA = "a359db61-26e2-44e0-8961-e0b373f4db21", "6ddc0431-0e9c-4b95-8658-e3e5b181d0bf"


def test_the_only_undecided_strong_proposals_are_the_ones_held_for_review():
    d = PlayerDecisions("scope/player_identity_decisions.json")
    rep = open("scope/identity_report.md", encoding="utf-8").read().splitlines()
    start = next(i for i, l in enumerate(rep) if l.startswith("## Proposed - strong"))
    end = next(i for i, l in enumerate(rep) if l.startswith("## Needs a person"))
    # held for the owner (2026-10-02): strong by the name rule, but each page sits on Liquipedia's lineup in 2024 Stage 2
    # series whose FACEIT roster on that side does not carry the proposed GUID (W1ll 6, Ailiseu 2, Aniyun 1, Niann03 1)
    # Niann03 was decided by the owner on 2026-10-23 (scope/lp_only_identity_report.md class A: the one FACEIT namesake,
    # who played for the same team, Vice), with the hold's reason still on record above
    held = {"W1ll", "Ailiseu", "Aniyun", "Niann03"}
    decided_since = {"Niann03"}
    strong = set()
    for l in rep[start:end]:
        if l.startswith("| ") and not l.startswith("| page"):
            page, _handle, _real, _nat, guid, *_ = [c.strip() for c in l.strip().strip("|").split("|")]
            strong.add(page)
            assert (page in d.data) == (page in decided_since), page
    assert strong == held
    assert d.data["Niann03"]["entity_id"] == "b5fe588f-39bc-439a-bf83-ddfe2e22f0e0"
    # 166 + 183 strong + 14 unmatched decided by the owner, 2026-10-02; then 152 Liquipedia-only-series pages, 2026-10-23
    # (scope/lp_only_identity_report.md: class A 2, class D 150 as Liquipedia-born)
    assert len(d.data) == 363 + 152
    assert sum(v["entity_id"] is None and "class D" in (v.get("note") or "") for v in d.data.values()) == 150
    assert "Shaq" not in d.data and "Massivepoop" not in d.data    # left undecided by the owner
    assert not [p for p, v in d.data.items() if (v.get("real_name") or "").lower().endswith("player")]   # disambiguators
    assert d.data["Zzz"] == {**d.data["Zzz"], "entity_id": "0a7555bc-8cd2-44bd-b1d5-df0c528dddea", "display": "ZZZ", "handle": "zzz"}
    # Astro = Astronexz, displayed as Astro: the owner's decision, committed after PR #6 merged and restored 2026-10-02
    assert d.data["Astro_(Canadian_player)"]["entity_id"] == "e78965e3-6fdc-437d-ab8f-b859e283dfdf"
    assert d.data["Astro_(Canadian_player)"]["display"] == "Astro"           # restored from 363a35e, never merged


def test_spacestation_gaming_is_one_org_over_two_eras_and_the_old_rejection_is_gone():
    o = OrgDecisions("scope/org_decisions.json")
    assert o.rejection(SSG_2024, SSG_NA) is None
    a, b = o.get(SSG_2024), o.get(SSG_NA)
    assert a["org_id"] == b["org_id"] == "spacestation-gaming"
    assert a.get("valid_from_name") is None and b.get("valid_from_name") is None      # each id's whole life is this org
    assert all(any(e.startswith("cross_region_ok") for e in x["evidence"]) for x in (a, b))
    al = json.load(open("scope/alias_decisions.json", encoding="utf-8"))["aliases"]["ssg"]
    assert (al["entity_type"], al["entity_id"]) == ("org", "spacestation-gaming")


def test_the_dallas_names_and_the_2024_pages_are_decided():
    t = TeamMap("scope/liquipedia_team_map.json")
    want = {"ENCE": "62f7752b-0b79-4fa8-9a23-78800e2b4539", "M80": "3aca5abd-ee5d-4542-92e9-392b6f5d0dbc",
            "Toronto Defiant": "8f632648-b26f-4554-bae4-40f9aee1773b",
            "Toronto Ultra": "8f632648-b26f-4554-bae4-40f9aee1773b"}   # Defiant's EWC 2024 name (owner, 2026-10-09)
    for name, tid in want.items():
        d = t.find(name)
        assert d and (d["entity_type"], d["entity_id"]) == ("team", tid), name
        # played 2024 and never returned (owner, 2026-10-09): the 2024 season, EWC 2024 and the World Finals included
        assert (d["valid_from"][:10], d["valid_to"][:10]) == ("2024-01-01", "2025-01-01"), name
    # Crazy Raccoon and Team Falcons are one continuous org each, the Dallas id included (owner, 2026-10-09)
    od = json.load(open("scope/org_decisions.json", encoding="utf-8"))["decisions"]
    for name, org, tid in (("Crazy Raccoon", "crazy-raccoon", "4cbafe8a-486c-41f9-82e3-b7b84f1855d7"),
                           ("Team Falcons", "team-falcons", "2ab92d33-4c33-46e1-a13f-743a95291d0e")):
        d = t.find(name)
        assert (d["entity_type"], d["entity_id"]) == ("org", org), name
        assert od[tid]["org_id"] == org and "valid_from" not in od[tid] and "valid_to" not in od[tid], name
    # NRG Shock (FACEIT 'SOG', d566d889) routes to the org that id belongs to for its whole life: anchored to the bare
    # id, "NRG Shock record" found nothing (search routing, owner 2026-10-02; lp_name_resolution guards it)
    d = t.find("NRG Shock")
    assert (d["entity_type"], d["entity_id"]) == ("org", "students-of-the-game")
    d = t.find("Spacestation Gaming")
    assert (d["entity_type"], d["entity_id"]) == ("org", "spacestation-gaming")
    assert t.find("Timeless")["entity_id"] == "c5116cb3-1e5d-457f-9c4a-52a5dd75ab6e"
    pages = json.load(open("scope/liquipedia_map.json", encoding="utf-8"))["pages"]
    assert sum(1 for v in pages.values() if "/2024/" in v["page"]) == 21        # the Major and the 20 stage/group competitions
    assert len({v["page"] for v in pages.values() if "/2024/" in v["page"]}) == 9   # over 9 distinct pages: one request
