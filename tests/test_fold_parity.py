"""SQL fold_name() and Python fold() agree: anchors are written with one and looked up with the other (migration 040)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from owcsmuse.resolve import fold

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

NAMES = ["Virtus.pro", "Anyone's Legend", "Supernova (American team)", "Team CC (Chinese orgless team)", "LGD.OA",
         "Gen.G Esports", "A-Square Tengu", "Nah I'd Win", "Beluga's Platoon", "  Twisted   Minds ", "Esperança",
         "Paraíso", "Łukasz", "Øystein", "Straße", "Ætherium", "Œuvre", "ĿƗƇĦ", "Ex Oblivione", "9z Team",
         "Team Falcons", "T1", "ZETA DIVISION", "ROC Esports", "Sign Esports", "Weibo Gaming", "Crazy Raccoon"]


def _sql_fold(conn, names):
    with conn.cursor() as cur:
        cur.execute("SELECT n, fold_name(n) AS f FROM unnest(%s::text[]) AS n", (names,))
        return {r["n"]: r["f"] for r in cur.fetchall()}


@pytest.fixture(scope="module")
def conn():
    from agg_support import build_scratch_db

    c, raw = build_scratch_db(DB_URL, "owcs_test_fold")
    yield c
    c.close()
    raw.close()


def test_sql_and_python_fold_the_same_names_the_same_way(conn):
    got = _sql_fold(conn, NAMES)
    assert {n: got[n] for n in NAMES} == {n: fold(n) for n in NAMES}


def test_every_team_map_key_is_what_sql_folds_its_names_to(conn):
    # the keys are Python-folded names; a key SQL could never produce from any name would be an anchor nothing meets
    keys = [k.split("|")[0] for k in json.loads(Path("scope/liquipedia_team_map.json").read_text(encoding="utf-8"))["aliases"]]
    got = _sql_fold(conn, keys)
    assert [k for k in keys if got[k] != k] == []
