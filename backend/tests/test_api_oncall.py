"""GET /oncall: each team's on-call person now (the web top bar)."""

OCT_16_NOON = 1_792_152_000  # docs/contracts.md: priya and raj are on call on Oct 16


def test_one_person_per_team_at_a_time(api, tool_graph):
    rows = api.get("/oncall", params={"at": OCT_16_NOON}).json()

    teams = [r["team"] for r in rows]
    assert teams == sorted(teams) and len(teams) == len(set(teams)) == 6
    by_team = {r["team"]: r for r in rows}
    assert by_team["Payments"]["handle"] == "priya"
    assert by_team["Ledger"]["handle"] == "raj"
    assert all(r["name"] and r["until"] > OCT_16_NOON for r in rows)


def test_nobody_before_the_rota_starts(api, tool_graph):
    assert api.get("/oncall", params={"at": 0}).json() == []
