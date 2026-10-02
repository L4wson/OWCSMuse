"""The reviewed decision files say what the owner decided on 2026-10-02, and only that."""

import json

from owcsmuse.liquipedia.identity import PlayerDecisions
from owcsmuse.liquipedia.teams import TeamMap
from owcsmuse.orgs import OrgDecisions

SSG_2024, SSG_NA = "a359db61-26e2-44e0-8961-e0b373f4db21", "6ddc0431-0e9c-4b95-8658-e3e5b181d0bf"


def test_the_only_undecided_strong_proposals_are_the_four_held_for_review():
    d = PlayerDecisions("scope/player_identity_decisions.json")
    rep = open("scope/identity_report.md", encoding="utf-8").read().splitlines()
    start = next(i for i, l in enumerate(rep) if l.startswith("## Proposed - strong"))
    end = next(i for i, l in enumerate(rep) if l.startswith("## Needs a person"))
    # held for the owner (2026-10-02): strong by the name rule, but each page sits on Liquipedia's lineup in 2024 Stage 2
    # series whose FACEIT roster on that side does not carry the proposed GUID (W1ll 6, Ailiseu 2, Aniyun 1, Niann03 1)
    held = {"W1ll", "Ailiseu", "Aniyun", "Niann03"}
    strong = set()
    for l in rep[start:end]:
        if l.startswith("| ") and not l.startswith("| page"):
            page, _handle, _real, _nat, guid, *_ = [c.strip() for c in l.strip().strip("|").split("|")]
            strong.add(page)
            assert page not in d.data, page
    assert strong == held
    assert len(d.data) == 349                                  # 166 + the 183 accepted 2026-10-02
    assert d.data["Zzz"] == {**d.data["Zzz"], "entity_id": "0a7555bc-8cd2-44bd-b1d5-df0c528dddea", "display": "ZZZ", "handle": "zzz"}
    # Astro was once decided on production by FACEIT name and never recorded here; the 2026-10-02 batch decides the page to
    # that same GUID (Astronexz), on the same side's FACEIT roster in all 30 of its linked series
    assert d.data["Astro_(Canadian_player)"]["entity_id"] == "e78965e3-6fdc-437d-ab8f-b859e283dfdf"


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
    want = {"Crazy Raccoon": "4cbafe8a-486c-41f9-82e3-b7b84f1855d7", "ENCE": "62f7752b-0b79-4fa8-9a23-78800e2b4539",
            "M80": "3aca5abd-ee5d-4542-92e9-392b6f5d0dbc", "Team Falcons": "2ab92d33-4c33-46e1-a13f-743a95291d0e",
            "Toronto Defiant": "8f632648-b26f-4554-bae4-40f9aee1773b", "NRG Shock": "d566d889-7885-4e74-a9dc-d29c111d2c1e"}
    for name, tid in want.items():
        d = t.find(name)
        assert d and (d["entity_type"], d["entity_id"]) == ("team", tid), name
    d = t.find("Spacestation Gaming")
    assert (d["entity_type"], d["entity_id"]) == ("org", "spacestation-gaming")
    assert t.find("Timeless")["entity_id"] == "c5116cb3-1e5d-457f-9c4a-52a5dd75ab6e"
    pages = json.load(open("scope/liquipedia_map.json", encoding="utf-8"))["pages"]
    assert sum(1 for v in pages.values() if "/2024/" in v["page"]) == 21        # the Major and the 20 stage/group competitions
    assert len({v["page"] for v in pages.values() if "/2024/" in v["page"]}) == 9   # over 9 distinct pages: one request
