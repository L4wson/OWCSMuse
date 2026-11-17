"""OWCS Grid beta: the puzzle generator and the HTTP routes, on a hand-built warehouse. No database, no network.

The warehouse below is small enough to read. Every expectation is stated from those rows, never read back from the
code under test.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "grid"))

import generate_puzzles as gen  # noqa: E402
from data import Appearance, Championship, MapRow, Warehouse  # noqa: E402

from owcsmuse.grid.store import GridStore, UnknownPuzzle, utc_date  # noqa: E402

SEASONS = (2024, 2025, 2026)
ROLE_OF = {"t": "Tank", "d": "Damage", "s": "Support"}
STAMP = "2026-11-01T00:00:00Z"


def when(season: int) -> datetime:
    return datetime(season, 6, 1, tzinfo=timezone.utc)


def champ(season: int, region: str, tier: str = "main", stats: bool = True) -> Championship:
    return Championship(f"{region}-{season}-{tier}", f"{region} {season} {tier}", season, region, tier, stats)


def played(player: str, season: int, region: str, org: str = "org", tier: str = "main") -> Appearance:
    return Appearance(player, f"series-{player}-{season}-{region}-{tier}", when(season), season, region,
                      f"{region}-{season}-{tier}", org, "faceit")


def maps(player: str, season: int, region: str, role: str, n: int, tier: str = "main") -> list[MapRow]:
    return [MapRow(player, f"m-{player}-{season}-{region}-{role}-{tier}", i, when(season), season, region,
                   f"{region}-{season}-{tier}", "org", role, 10, 5, 0.0, 0.0, 0.0, 600.0) for i in range(n)]


def warehouse() -> Warehouse:
    """Six regulars a role, each with 12 maps in the role in NA in every season, plus the awkward cases:

    - `fill`: 12 Support maps in NA 2025 and 9 Tank maps there. A fill-in Tank, under the floor.
    - `late`: line-ups in NA 2024 with no map stats at all (a Stages 3-4 player).
    - `intl`: only an international event in 2025.
    - `releg`: 12 Tank maps in 2026, all in relegation.
    - `t-twin`: a second player shown as "Tank0", with 12 Tank maps in NA 2025 only.
    """
    championships = {c.championship_id: c for c in (
        *(champ(s, r) for s in SEASONS for r in ("na", "emea")),
        champ(2025, "international", stats=False), champ(2026, "na", tier="relegation"),
    )}
    appearances, map_rows, names = [], [], {}
    for letter, role in ROLE_OF.items():
        for i in range(6):
            pid = f"{letter}{i}"
            names[pid] = f"{role.replace('Damage', 'Dps')}{i}"
            for season in SEASONS:
                appearances.append(played(pid, season, "na"))
                map_rows += maps(pid, season, "na", role, 12)
    appearances += [played("fill", 2025, "na"), played("late", 2024, "na"), played("intl", 2025, "international"),
                    played("releg", 2026, "na", tier="relegation"), played("t-twin", 2025, "na", org="other")]
    map_rows += (maps("fill", 2025, "na", "Support", 12) + maps("fill", 2025, "na", "Tank", 9)
                 + maps("releg", 2026, "na", "Tank", 12, tier="relegation") + maps("t-twin", 2025, "na", "Tank", 12))
    names.update({"fill": "Fill", "late": "Late", "intl": "Intl", "releg": "Releg", "t-twin": "Tank0"})
    return Warehouse(appearances, map_rows, [], [], championships, names, {"org": "Org One", "other": "Other Org"})


def build(wh: Warehouse, columns=("2024", "2025", "2026"), number=1, day=date(2026, 11, 18)):
    return gen.build_puzzle(gen.in_scope(wh), gen.presence_rows(wh), number, day, columns, STAMP, "test snapshot")


def cell(entry: dict, row: int, col: int) -> set[str]:
    return set(entry["cells"][row * 3 + col]["answers"])


# ---- the generator ----------------------------------------------------------------------------------------------

def test_a_cell_is_the_players_with_ten_maps_in_the_role_inside_the_column():
    entry = build(warehouse()).entry
    assert entry is not None
    assert cell(entry, 0, 0) == {f"t{i}" for i in range(6)}                        # Tank x 2024
    assert cell(entry, 0, 1) == {f"t{i}" for i in range(6)} | {"t-twin"}           # Tank x 2025
    assert cell(entry, 2, 1) == {f"s{i}" for i in range(6)} | {"fill"}             # Support x 2025
    assert entry["cells"][1]["answers"]["t0"] == {"name": "Tank0", "maps": 12}
    assert entry["rules"] == {"min_maps": 10, "min_answers": 5, "guesses": 9}


def test_the_ten_map_floor_leaves_out_a_fill_in():
    entry = build(warehouse()).entry
    assert "fill" not in cell(entry, 0, 1)          # 9 Tank maps in 2025
    assert "fill" in cell(entry, 2, 1)              # 12 Support maps in 2025


def test_relegation_and_international_play_are_out_of_scope():
    entry = build(warehouse()).entry
    assert "releg" not in cell(entry, 0, 2)         # 12 Tank maps in 2026, every one in relegation
    assert all("intl" not in c["answers"] for c in entry["cells"])


def test_a_player_seen_in_the_column_with_no_role_on_record_is_unverifiable():
    entry = build(warehouse()).entry
    assert entry["unverifiable"][0] == ["late"]     # 2024: line-ups only
    assert entry["unverifiable"][1] == ["intl"]     # 2025: an international event only
    assert entry["unverifiable"][2] == []           # releg has roles on record; relegation is simply not counted
    by_region = build(warehouse(), ("na", "emea", "all3"))
    assert by_region.entry is None                  # nobody in this warehouse played in EMEA
    assert any("EMEA has 0 answers" in r for r in by_region.reasons)


def test_all_three_seasons_needs_the_seasons_and_the_role():
    wh = warehouse()
    wh.appearances += [played(f"t{i}", s, "emea") for i in range(6) for s in SEASONS]
    wh.map_rows += [m for i in range(6) for s in SEASONS for letter, role in ROLE_OF.items()
                    for m in maps(f"{letter}{i}", s, "emea", role, 12)]
    wh.appearances += [played(f"{letter}{i}", s, "emea") for letter in "ds" for i in range(6) for s in SEASONS]
    entry = build(wh, ("all3", "na", "emea")).entry
    assert entry is not None
    assert cell(entry, 0, 0) == {f"t{i}" for i in range(6)}        # t-twin has the Tank maps but one season
    assert entry["cells"][0]["answers"]["t0"]["maps"] == 72         # 12 maps x 3 seasons x 2 regions


def test_a_cell_under_five_answers_rejects_the_grid_and_names_the_cell():
    wh = warehouse()
    gone = {"t4", "t5"}                             # leaves four Tanks in 2026
    wh = replace(wh, map_rows=[m for m in wh.map_rows if not (m.player_id in gone and m.season == 2026)])
    built = build(wh)
    assert built.entry is None
    assert built.counts[0][2] == 4
    assert built.reasons == ["Tank x 2026 has 4 answers (needs 5)"]


def test_a_grid_that_nine_different_players_cannot_fill_is_rejected():
    # eight flex players, each with 12 maps in every role in every season: every cell holds all eight, and
    # nine cells cannot be filled by eight people
    appearances, map_rows = [], []
    for i in range(8):
        for season in SEASONS:
            appearances.append(played(f"f{i}", season, "na"))
            for role in ROLE_OF.values():
                map_rows += maps(f"f{i}", season, "na", role, 12)
    base = warehouse()
    wh = replace(base, appearances=appearances, map_rows=map_rows, player_names={f"f{i}": f"Flex{i}" for i in range(8)})
    built = build(wh)
    assert built.entry is None
    assert built.counts == [[8, 8, 8]] * 3
    assert built.reasons == ["only 8 of 9 cells can be filled with different players"]


def test_a_published_date_is_never_changed():
    today = date(2026, 11, 18)
    existing = [{"number": 1, "date": "2026-11-17", "cols": []}, {"number": 2, "date": "2026-11-18", "cols": []},
                {"number": 3, "date": "2026-11-19", "cols": []}]
    for start in (date(2026, 11, 17), today):                       # yesterday, and today itself
        with pytest.raises(gen.PublishedError, match="today or earlier"):
            gen.plan_dates(existing, start, 3, today)
        with pytest.raises(gen.PublishedError):
            gen.plan_dates(existing, start, 3, today, replace_future=True)
    kept, todo, skipped = gen.plan_dates(existing, date(2026, 11, 19), 3, today)
    assert kept == existing and skipped == [date(2026, 11, 19)]
    assert todo == [date(2026, 11, 20), date(2026, 11, 21)]          # appended after the last one
    kept, todo, _ = gen.plan_dates(existing, date(2026, 11, 19), 2, today, replace_future=True)
    assert [p["number"] for p in kept] == [1, 2] and todo == [date(2026, 11, 19), date(2026, 11, 20)]


def test_generate_numbers_puzzles_in_date_order_and_does_not_repeat_columns_within_a_week():
    wh = warehouse()
    for letter, role in ROLE_OF.items():            # give everyone EMEA too, so all six columns are usable
        for i in range(6):
            for season in SEASONS:
                wh.appearances.append(played(f"{letter}{i}", season, "emea"))
                wh.map_rows += maps(f"{letter}{i}", season, "emea", role, 12)
    dates = [date(2026, 11, 18 + i) for i in range(10)]
    new, rejected = gen.generate(gen.in_scope(wh), gen.presence_rows(wh), [], dates, 3, STAMP, "test snapshot")
    assert [p["number"] for p in new] == list(range(1, 11))
    assert [p["date"] for p in new] == [d.isoformat() for d in dates]
    used = [frozenset(c["key"] for c in p["cols"]) for p in new]
    for i, columns in enumerate(used):
        assert columns not in used[max(0, i - 6):i], f"puzzle {i + 1} repeats a column set within 7 days"
    assert all(r["reasons"] for r in rejected)
    again, _ = gen.generate(gen.in_scope(wh), gen.presence_rows(wh), [], dates, 3, STAMP, "test snapshot")
    assert again == new                             # the same seed gives the same puzzles


# ---- the routes -------------------------------------------------------------------------------------------------

fastapi = pytest.importorskip("fastapi", reason="the api extra is not installed")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from owcsmuse.grid.router import build_router  # noqa: E402


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture()
def files(tmp_path):
    """Three puzzles, dated 17, 18 and 19 November 2026, and the player index, written as the generator writes them."""
    wh = warehouse()
    puzzles = [build(wh, number=n, day=date(2026, 11, 16 + n)).entry for n in (1, 2, 3)]
    other_names = {"t0": {"Tank0", "OldTankName"}, "s3": {"Élan"}}
    gen.write_json(tmp_path / "puzzles.json", {"version": 1, "note": "test", "puzzles": puzzles})
    gen.write_json(tmp_path / "players.json", {"players": gen.player_index(wh, other_names)})
    return tmp_path / "puzzles.json", tmp_path / "players.json", puzzles


@pytest.fixture()
def clock():
    return Clock(datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc))        # puzzle 2's day


@pytest.fixture()
def client(files, clock):
    app = FastAPI()
    app.include_router(build_router(GridStore(files[0], files[1]), clock=clock))
    with TestClient(app) as c:
        yield c


def every_answer_id(puzzles: list[dict]) -> set[str]:
    ids = set()
    for p in puzzles:
        for c in p["cells"]:
            ids |= set(c["answers"])
        for column in p["unverifiable"]:
            ids |= set(column)
    return ids


def test_today_a_past_puzzle_and_the_archive_carry_no_answer_data(client, files):
    secret = every_answer_id(files[2])
    assert {"t0", "fill", "late", "intl"} <= secret
    for path in ("/api/grid/today", "/api/grid/1", "/api/grid/2", "/api/grid/archive"):
        response = client.get(path)
        assert response.status_code == 200, path
        text = response.text
        for word in ("answers", "unverifiable", "\"maps\"", "\"cells\"", "\"spec\"", "\"count\""):
            assert word not in text, f"{path} carries {word}"
        strings = set(_strings(response.json()))
        assert not (strings & secret), f"{path} carries a player id"
    today = client.get("/api/grid/today").json()
    assert (today["number"], today["date"], today["is_today"], today["guesses"]) == (2, "2026-11-18", True, 9)
    assert [r["label"] for r in today["rows"]] == ["Tank", "DPS", "Support"]
    assert [c["label"] for c in today["cols"]] == ["2024", "2025", "2026"]
    assert "can't verify" in today["coverage"]


def _strings(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, str):
        yield value


def test_the_archive_lists_published_puzzles_only_newest_first(client):
    listed = client.get("/api/grid/archive").json()["puzzles"]
    assert [(p["number"], p["is_today"]) for p in listed] == [(2, True), (1, False)]     # 3 is tomorrow's


def test_a_puzzle_dated_tomorrow_does_not_exist_yet(client):
    assert client.get("/api/grid/3").status_code == 404
    assert client.get("/api/grid/3/reveal").status_code == 404
    assert client.post("/api/grid/3/guess", json={"cell": 0, "player_id": "t0"}).status_code == 404


def test_a_guess_is_correct_wrong_or_cannot_verify(client):
    def guess(cell_index, player_id, n=2):
        return client.post(f"/api/grid/{n}/guess", json={"cell": cell_index, "player_id": player_id})

    right = guess(1, "t0").json()                   # Tank x 2025: 12 Tank maps
    assert right["result"] == "correct" and right["uses_guess"] is True
    assert right["explanation"] == "12 Tank maps in 2025 (FACEIT map stats)"
    assert right["player"] == {"id": "t0", "name": "Tank0"} and right["link"] is None

    wrong = guess(1, "d0").json()                   # a DPS, in the Tank cell
    assert wrong["result"] == "wrong" and wrong["uses_guess"] is True
    assert "explanation" not in wrong and "maps" not in wrong

    fill_in = guess(1, "fill").json()               # 9 Tank maps: has role data, under the floor, so plainly wrong
    assert fill_in["result"] == "wrong"

    unknown = guess(0, "late").json()               # Tank x 2024: line-ups in 2024, no role on record
    assert unknown["result"] == "cannot_verify" and unknown["uses_guess"] is False
    assert "Late" in unknown["explanation"]
    assert guess(1, "late").json()["result"] == "wrong"             # never seen in 2025: that is checkable
    assert guess(4, "intl").json()["result"] == "cannot_verify"     # DPS x 2025: international events only


def test_a_guess_for_an_unknown_puzzle_cell_or_player_is_a_4xx(client):
    post = client.post
    assert post("/api/grid/99/guess", json={"cell": 0, "player_id": "t0"}).status_code == 404
    assert post("/api/grid/2/guess", json={"cell": 9, "player_id": "t0"}).status_code == 422
    assert post("/api/grid/2/guess", json={"cell": -1, "player_id": "t0"}).status_code == 422
    assert post("/api/grid/2/guess", json={"cell": 0, "player_id": "nobody"}).status_code == 422
    assert post("/api/grid/2/guess", json={"cell": 0, "player_id": "Tank0"}).status_code == 422    # a name is not an id
    assert post("/api/grid/2/guess", json={"cell": 0}).status_code == 422
    assert client.get("/api/grid/99").status_code == 404
    assert client.get("/api/grid/not-a-number").status_code == 422


def test_an_earlier_name_finds_the_canonical_player(client):
    found = client.get("/api/grid/players", params={"q": "oldtankname"}).json()["players"]
    assert [(p["id"], p["name"], p["matched"]) for p in found] == [("t0", "Tank0", "OldTankName")]
    accented = client.get("/api/grid/players", params={"q": "elan"}).json()["players"]
    assert [(p["id"], p["matched"]) for p in accented] == [("s3", "Élan")]
    # the id it found is the one that scores
    guess = client.post("/api/grid/2/guess", json={"cell": 1, "player_id": found[0]["id"]}).json()
    assert guess["result"] == "correct"


def test_two_players_with_one_name_stay_two_players(client):
    found = client.get("/api/grid/players", params={"q": "tank0"}).json()["players"]
    assert {p["id"] for p in found} == {"t0", "t-twin"}
    assert all(p["name"] == "Tank0" for p in found)
    details = {p["id"]: p["detail"] for p in found}
    assert details == {"t0": "Org One, 2024-2026", "t-twin": "Other Org, 2025"}
    # each is judged by its own id: the twin has Tank maps in 2025 only
    assert client.post("/api/grid/2/guess", json={"cell": 0, "player_id": "t-twin"}).json()["result"] == "wrong"
    assert client.post("/api/grid/2/guess", json={"cell": 0, "player_id": "t0"}).json()["result"] == "correct"


def test_search_orders_exact_then_prefix_then_contains_and_caps_the_list(client):
    names = [p["name"] for p in client.get("/api/grid/players", params={"q": "tank"}).json()["players"]]
    assert len(names) == 7 and all(n.startswith("Tank") for n in names)
    assert client.get("/api/grid/players", params={"q": ""}).json()["players"] == []
    assert len(client.get("/api/grid/players", params={"q": "s"}).json()["players"]) == 8


def test_reveal_gives_at_most_five_examples_a_cell(client, files):
    reveal = client.get("/api/grid/2/reveal").json()
    assert [c["cell"] for c in reveal["cells"]] == list(range(9))
    assert all(1 <= len(c["examples"]) <= 5 for c in reveal["cells"])
    tank_2025 = files[2][1]["cells"][1]["answers"]
    assert len(tank_2025) == 7                                      # more answers than are shown
    assert len(reveal["cells"][1]["examples"]) == 5
    assert all(e["id"] in tank_2025 for e in reveal["cells"][1]["examples"])


def test_the_puzzle_rolls_over_at_midnight_utc(files):
    store = GridStore(files[0], files[1])
    before = datetime(2026, 11, 18, 23, 59, 59, tzinfo=timezone.utc)
    after = datetime(2026, 11, 19, 0, 0, 1, tzinfo=timezone.utc)
    assert store.today(before)["number"] == 2
    assert store.today(after)["number"] == 3
    with pytest.raises(UnknownPuzzle):
        store.get(3, before)                                        # not published a second earlier
    assert store.get(3, after)["number"] == 3
    # the day is UTC's, wherever the clock that asked is: 16:30 on the 18th in Los Angeles is 00:30 on the 19th
    from datetime import timedelta
    pacific = datetime(2026, 11, 18, 16, 30, tzinfo=timezone(timedelta(hours=-8)))
    assert utc_date(pacific) == date(2026, 11, 19) and store.today(pacific)["number"] == 3
    with pytest.raises(UnknownPuzzle):
        store.today(datetime(2026, 11, 20, 0, 0, 1, tzinfo=timezone.utc))      # nothing published for the 20th


def test_the_route_follows_the_clock(client, clock):
    clock.now = datetime(2026, 11, 18, 23, 59, 59, tzinfo=timezone.utc)
    assert client.get("/api/grid/today").json()["number"] == 2
    clock.now = datetime(2026, 11, 19, 0, 0, 1, tzinfo=timezone.utc)
    assert client.get("/api/grid/today").json()["number"] == 3
    clock.now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    assert client.get("/api/grid/today").status_code == 404
    assert client.get("/api/grid/3").json()["is_today"] is False


def test_missing_files_are_no_puzzles_not_a_crash(tmp_path, clock):
    app = FastAPI()
    app.include_router(build_router(GridStore(tmp_path / "none.json", tmp_path / "none2.json"), clock=clock))
    with TestClient(app) as c:
        assert c.get("/api/grid/today").status_code == 404
        assert c.get("/api/grid/archive").json() == {"puzzles": []}
        assert c.get("/api/grid/players", params={"q": "a"}).json()["players"] == []


def test_the_app_serves_grid_without_a_database_and_throttles_guesses(files, monkeypatch):
    """The real app factory, with a database URL nothing listens on: Grid's routes never open a connection."""
    from owcsmuse.api import ConnectionPool, create_app
    from owcsmuse.config import Settings
    import owcsmuse.grid.store as store_module

    monkeypatch.setattr(store_module, "PUZZLES_PATH", files[0])
    monkeypatch.setattr(store_module, "PLAYERS_PATH", files[1])
    settings = Settings(_env_file=None, database_url="postgresql://nobody@127.0.0.1:1/none", api_rate_burst=2,
                        api_rate_per_minute=1)
    app = create_app(settings, ConnectionPool(settings, size=1))
    with TestClient(app) as c:
        assert c.get("/api/grid/archive").status_code == 200
        assert c.get("/api/grid/players", params={"q": "tank"}).status_code == 200
        statuses = [c.post("/api/grid/1/guess", json={"cell": 0, "player_id": "t0"}).status_code for _ in range(4)]
        assert statuses[:2] == [200, 200] and statuses[-1] == 429      # the app's per-client limit covers guesses
        assert all(c.get("/api/grid/archive").status_code == 200 for _ in range(5))    # and not the clue routes


def test_the_committed_puzzle_file_is_well_formed():
    """scope/grid_puzzles.json as committed: nine cells, each at its floor, numbered in date order."""
    path = Path(__file__).resolve().parents[2] / "scope" / "grid_puzzles.json"
    if not path.exists():
        pytest.skip("no puzzles have been generated")
    puzzles = json.loads(path.read_text(encoding="utf-8"))["puzzles"]
    assert [p["number"] for p in puzzles] == list(range(1, len(puzzles) + 1))
    assert [p["date"] for p in puzzles] == sorted(p["date"] for p in puzzles)
    for p in puzzles:
        assert [r["key"] for r in p["rows"]] == ["tank", "dps", "support"]
        assert len({c["key"] for c in p["cols"]}) == 3 and len(p["cells"]) == 9 and len(p["unverifiable"]) == 3
        for i, c in enumerate(p["cells"]):
            assert c["row"] * 3 + c["col"] == i and c["count"] == len(c["answers"]) >= p["rules"]["min_answers"]
            assert all(a["maps"] >= p["rules"]["min_maps"] for a in c["answers"].values())
            assert not (set(c["answers"]) & set(p["unverifiable"][c["col"]]))
