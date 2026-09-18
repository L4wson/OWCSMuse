"""The clarify loop, end to end: every option offered must be answerable.

The frontend found this broken - the parser rejected `org:team-peps`, so an org
candidate was an option nobody could pick. The fix is that the service ships a
question with each candidate and the parser accepts the ids in it, and the test
for that is the obvious one: ask every candidate's question verbatim and check
each comes back answered, about that entity and no other.
"""

import pytest

from owcsmuse.aggregates import refresh
from owcsmuse.nlq.parser import is_entity_token, parse_question
from owcsmuse.nlq.pipeline import ask, candidate_question
from owcsmuse.resolve import Candidate, resolve


# Three entities that share a stem, two of them orgs with real matches behind
# them: the shape that produced the broken candidate list in production, built
# here so the test does not depend on which names happen to be ingested.
STEM = "tem record"


@pytest.fixture(scope="module")
def three_candidates(agg_db):
    with agg_db.cursor() as cur:
        cur.execute("""
            SELECT t.team_id, t.name FROM teams t
             WHERE EXISTS (SELECT 1 FROM fact_team_matches f WHERE f.team_id = t.team_id)
             ORDER BY t.name LIMIT 2""")
        teams = cur.fetchall()
        if len(teams) < 2:
            pytest.skip("the fixtures need two teams with matches")
        cur.execute("INSERT INTO orgs (org_id, name) VALUES ('tempest-alpha', 'Tempest Alpha'), "
                    "('tempest-bravo', 'Tempest Bravo')")
        cur.execute("INSERT INTO team_orgs (team_id, org_id) VALUES (%s, 'tempest-alpha'), (%s, 'tempest-bravo')",
                    (teams[0]["team_id"], teams[1]["team_id"]))
        cur.execute("INSERT INTO teams (team_id, name) VALUES ('tempest-charlie-id', 'Tempest Charlie')")
    agg_db.commit()
    refresh(agg_db, ["entity_names"])
    yield
    with agg_db.cursor() as cur:
        cur.execute("DELETE FROM team_orgs WHERE org_id IN ('tempest-alpha', 'tempest-bravo')")
        cur.execute("DELETE FROM orgs WHERE org_id IN ('tempest-alpha', 'tempest-bravo')")
        cur.execute("DELETE FROM teams WHERE team_id = 'tempest-charlie-id'")
    agg_db.commit()
    refresh(agg_db, ["entity_names"])


def _clarify(conn, question=STEM):
    answer = ask(conn, question, with_evidence=False)
    assert answer.status == "clarify", (answer.status, answer.reason)
    return answer


def test_every_candidate_carries_a_question_that_answers_about_that_entity(agg_db, three_candidates):
    answer = _clarify(agg_db)
    candidates = answer.candidates["subject"]
    assert len(candidates) == 3, [c["current_name"] for c in candidates]

    for candidate in candidates:
        question = candidate["question"]
        assert question, candidate
        assert is_entity_token(question.split()[0]), question   # an id, never a name

        again = ask(agg_db, question, with_evidence=False)
        assert again.status != "clarify", (question, again.reason)
        resolved = {e["entity_id"] for e in again.entities.values()}
        assert candidate["entity_id"] in resolved, (question, again.entities)


def test_the_org_candidate_is_choosable_too(agg_db, three_candidates):
    """The case that was broken: an org id is a slug, and the parser used to stop at the colon."""
    answer = _clarify(agg_db)
    orgs = [c for c in answer.candidates["subject"] if c["entity_type"] == "org"]
    assert len(orgs) == 2, [c["current_name"] for c in answer.candidates["subject"]]

    for candidate in orgs:
        assert candidate["question"].startswith("org:")
        again = ask(agg_db, candidate["question"], with_evidence=False)
        assert again.status != "clarify"
        assert candidate["entity_id"] in {e["entity_id"] for e in again.entities.values()}


def test_candidates_say_when_each_one_was_active(agg_db, three_candidates):
    answer = _clarify(agg_db)
    for candidate in answer.candidates["subject"]:
        assert "seasons" in candidate and "first_at" in candidate and "last_at" in candidate
    played = [c for c in answer.candidates["subject"] if c["matches"]]
    assert played, "at least one candidate has matches"
    assert all(c["seasons"] for c in played)


def test_the_question_keeps_the_rest_of_what_was_asked():
    candidate = Candidate(entity_type="team", entity_id="a58dedff-8045-46be-a13e-2402495b6a9d",
                          current_name="Team Liquid", matched_name="Team Liquid", name_kind="current_name", score=1.0)
    assert candidate_question("tea record in 2025 on Ilios", "tea", candidate) == (
        "team:a58dedff-8045-46be-a13e-2402495b6a9d record in 2025 on Ilios")

    org = Candidate(entity_type="org", entity_id="team-peps", current_name="Team Peps",
                    matched_name="Team Peps", name_kind="current_name", score=1.0)
    assert candidate_question("tea vs ENCE", "tea", org) == "org:team-peps vs ENCE"


def test_a_question_that_does_not_contain_the_name_still_names_the_entity():
    org = Candidate(entity_type="org", entity_id="team-peps", current_name="Team Peps",
                    matched_name="Team Peps", name_kind="current_name", score=1.0)
    assert candidate_question("who had the most eliminations", None, org) == "org:team-peps record"


def test_the_parser_takes_a_prefixed_id_wherever_a_name_goes():
    uuid = "a58dedff-8045-46be-a13e-2402495b6a9d"
    assert parse_question("org:team-peps record").filters.subject == "org:team-peps"
    assert parse_question(f"team:{uuid} record").filters.subject == f"team:{uuid}"
    assert parse_question(f"player:{uuid} eliminations in 2024").filters.player == f"player:{uuid}"
    versus = parse_question(f"org:team-peps vs team:{uuid}")
    assert versus.filters.subject == "org:team-peps" and versus.filters.opponent == f"team:{uuid}"
    assert is_entity_token("org:team-peps") and not is_entity_token("team peps")


def test_an_id_that_names_nothing_is_an_unknown_entity_not_a_crash(agg_db):
    answer = ask(agg_db, "org:no-such-org record", with_evidence=False)
    assert answer.status == "cannot_answer" and answer.code == "unknown_entity"


def test_resolving_by_prefixed_id_returns_exactly_one_entity(agg_db, three_candidates):
    with agg_db.cursor() as cur:
        cur.execute("SELECT entity_id FROM entity_names WHERE entity_type = 'player' LIMIT 1")
        player_id = cur.fetchone()["entity_id"]
    agg_db.commit()
    for token in (player_id, f"player:{player_id}"):
        found = resolve(agg_db, token)
        assert len(found) == 1 and found[0].entity_id == player_id
    assert resolve(agg_db, "org:tempest-alpha")[0].entity_id == "tempest-alpha"
