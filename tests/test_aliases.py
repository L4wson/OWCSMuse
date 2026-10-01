"""Community shorthand ("SSG" -> SpaceStation Gaming): decisions file, and resolution.

FACEIT's own name history already resolves an abbreviation a team really was
named at some point; this only covers the ones nobody on FACEIT ever typed,
which is why every mapping here comes from a reviewed decision, never a guess.
"""

from __future__ import annotations

import os

import pytest

from owcsmuse.aliases import AliasDecisions, list_aliases, load_decisions
from owcsmuse.resolve import resolve, resolve_alias

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
dbonly = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")


# ------------------------------------------------------------------ decisions

def test_decisions_round_trip_folded_by_key(tmp_path):
    d = AliasDecisions(tmp_path / "a.json")
    d.set("SSG", "org", "spacestation-gaming", note="community shorthand")
    d.save()
    again = AliasDecisions(tmp_path / "a.json")
    # the alias is looked up by its fold, so casing and surrounding whitespace
    # at the call site never matter (fold() turns punctuation into a separator,
    # not nothing, so "S.S.G" folds to three words, not "ssg" - not this test's
    # concern, just what fold() already does everywhere else)
    for spelling in ("SSG", "ssg", "  ssg  ", "Ssg"):
        got = again.get(spelling)
        assert got is not None and got["entity_id"] == "spacestation-gaming"
    assert again.get("not-an-alias") is None       # no silent fallback


def test_unset_removes_it_and_is_idempotent(tmp_path):
    d = AliasDecisions(tmp_path / "a.json")
    d.set("TL", "team", "t1")
    assert d.unset("tl") is True
    assert d.get("TL") is None
    assert d.unset("TL") is False


def test_an_unknown_entity_type_is_refused(tmp_path):
    d = AliasDecisions(tmp_path / "a.json")
    with pytest.raises(ValueError, match="entity_type"):
        d.set("X", "match", "id1")


def test_an_alias_that_folds_to_nothing_is_refused(tmp_path):
    d = AliasDecisions(tmp_path / "a.json")
    with pytest.raises(ValueError):
        d.set("!!!", "team", "t1")


def test_saved_file_documents_itself_and_is_stable_on_reload(tmp_path):
    d = AliasDecisions(tmp_path / "a.json")
    d.set("TM", "team", "t1", note="Twisted Minds")
    d.set("CR", "team", "t2")
    path = d.save()
    doc = path.read_text(encoding="utf-8")
    assert '"note"' in doc and "aliases" in doc
    again = AliasDecisions(path)
    assert set(again.data) == {"tm", "cr"}


# ------------------------------------------------------------------- DB-backed

@dbonly
def test_load_decisions_writes_entity_aliases_and_is_a_full_replace(tmp_path, agg_db):
    with agg_db.cursor() as cur:
        cur.execute("SELECT team_id, name FROM teams LIMIT 1")
        team = cur.fetchone()
    agg_db.commit()

    d = AliasDecisions(tmp_path / "a.json")
    d.set("XYZ", "team", team["team_id"], note="test alias")
    out = load_decisions(agg_db, d)
    assert out["aliases_written"] == 1

    rows = list_aliases(agg_db)
    assert len(rows) == 1
    assert rows[0]["alias"] == "xyz" and rows[0]["entity_id"] == team["team_id"]
    assert rows[0]["current_name"] == team["name"]

    # loading again with a different (smaller) file is a full replace, not a merge
    d2 = AliasDecisions(tmp_path / "b.json")
    out2 = load_decisions(agg_db, d2)
    assert out2["aliases_written"] == 0
    assert list_aliases(agg_db) == []


@dbonly
def test_resolve_alias_is_an_exact_authoritative_lookup(tmp_path, agg_db):
    with agg_db.cursor() as cur:
        cur.execute("SELECT team_id, name FROM teams LIMIT 1")
        team = cur.fetchone()
    agg_db.commit()

    d = AliasDecisions(tmp_path / "a.json")
    d.set("XYZ", "team", team["team_id"])
    load_decisions(agg_db, d)

    hit = resolve_alias(agg_db, "XYZ")
    assert len(hit) == 1 and hit[0].entity_id == team["team_id"] and hit[0].score == 1.0
    assert hit[0].name_kind == "alias"
    # case and whitespace at the call site do not matter
    assert resolve_alias(agg_db, "  xyz  ")[0].entity_id == team["team_id"]
    assert resolve_alias(agg_db, "not-an-alias") == []
    # scoped by entity_type when asked
    assert resolve_alias(agg_db, "XYZ", entity_type="player") == []
    assert resolve_alias(agg_db, "XYZ", entity_type="team")[0].entity_id == team["team_id"]

    load_decisions(agg_db, AliasDecisions(tmp_path / "empty.json"))  # clean up


@dbonly
def test_resolve_returns_the_alias_alone_never_a_clarify_shaped_tie(tmp_path, agg_db):
    """The bug this exists to prevent: on real data, "TM" -> Twisted Minds (an
    exact reviewed alias, score 1.0) sat close enough to "TML Nightmare"
    (fuzzy startswith, score 0.9) that the ordinary ambiguity margin treated
    them as a tie and asked which one was meant - exactly what an alias is
    supposed to make unnecessary. resolve() must short-circuit before that
    scoring ever runs, so this checks the general case: whatever else in the
    warehouse might fuzzy-match the same short string, an exact alias hit is
    the only thing resolve() returns."""
    with agg_db.cursor() as cur:
        cur.execute("SELECT team_id, name FROM teams LIMIT 1")
        team = cur.fetchone()
    agg_db.commit()

    d = AliasDecisions(tmp_path / "a.json")
    d.set("ZQX", "team", team["team_id"])
    load_decisions(agg_db, d)
    try:
        found = resolve(agg_db, "ZQX")
        assert len(found) == 1, found          # never a clarify-shaped list of near-ties
        assert found[0].entity_id == team["team_id"] and found[0].score == 1.0
    finally:
        load_decisions(agg_db, AliasDecisions(tmp_path / "empty.json"))
