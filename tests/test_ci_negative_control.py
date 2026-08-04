"""TEMPORARY — deliberate failures, to be REVERTED in the very next commit.

This is the S1 negative control: "at least one deliberately broken test proves the CI lane
actually fails when it should."

Real failures have already shown each gate firing — the lint gate on run #1, the SQLite suite
on #1-#5, the Postgres suite on #10, the dependency audit on #11. What none of those prove is
that a **plain failing assertion** fails the build, because every one of them failed for some
other reason: a lint rule, a missing git object, a fixture deadlock, a CVE feed.

That distinction matters here specifically. This project's recurring defect is the check that
reports nothing — a suite whose exit code was swallowed by `tail`, a CI gate configured
`continue-on-error`, a probe that raised instead of asserting, an assertion written
`assert x not in y or True`. A green suite that collects zero tests is also green. This
proves collection, assertion and exit-code propagation end to end, on both database lanes.

If you are reading this on main, something went wrong with the revert: delete this file.
"""


def test_negative_control_plain_assertion():
    """No fixtures, no database — the narrowest possible proof that a failure fails."""
    assert False, "DELIBERATE CI NEGATIVE CONTROL — this test is meant to fail; revert it"


def test_negative_control_through_the_client_fixture(client):
    """Same, but through the `client` fixture, so the Postgres lane exercises its own path."""
    assert client.get("/api/health").status_code == 599, (
        "DELIBERATE CI NEGATIVE CONTROL — this test is meant to fail; revert it"
    )
