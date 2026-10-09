"""`liquipedia teams decide` refuses a target that does not exist, before anything is written to the team map."""

from owcsmuse.liquipedia.teams import decision_target_error

TEAM = "ec69a520-047f-4754-b36e-b0c95e2066ff"
TEAMS = {TEAM}
ORGS = {"spacestation-gaming", "quick-esports"}


def test_a_truncated_team_id_is_refused():
    # the id once accepted and written to the map (Shikigami); lp_name_resolution caught it only after the fact
    err = decision_target_error("team", "ec69a520-04", TEAMS, ORGS)
    assert err and "not a full FACEIT team id" in err


def test_a_well_formed_team_id_that_is_not_in_the_warehouse_is_refused():
    err = decision_target_error("team", "ec69a520-047f-4754-b36e-b0c95e2066fe", TEAMS, ORGS)
    assert err and "not a team in the warehouse" in err


def test_a_known_team_id_is_accepted():
    assert decision_target_error("team", TEAM, TEAMS, ORGS) is None


def test_an_unknown_or_malformed_org_is_refused():
    assert "not a known org" in decision_target_error("org", "spacestation", TEAMS, ORGS)
    assert "not an org slug" in decision_target_error("org", "SpaceStation Gaming", TEAMS, ORGS)
    assert "not an org slug" in decision_target_error("org", "quick--esports", TEAMS, ORGS)


def test_a_known_org_is_accepted():
    assert decision_target_error("org", "quick-esports", TEAMS, ORGS) is None
