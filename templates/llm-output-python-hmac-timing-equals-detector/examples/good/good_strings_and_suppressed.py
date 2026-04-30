"""Good: secret-named identifier appears, but only inside string / comment,
or on a line suppressed by `# timing-safe-ok` for a unit test fixture."""

ERROR_MSG = "expected_token must equal provided_token"  # docs only


def test_round_trip():
    # Unit test asserts plaintext equality on a *non-secret* fixture.
    expected_token = "FIXTURE-CONSTANT"
    provided_token = "FIXTURE-CONSTANT"
    assert expected_token == provided_token  # timing-safe-ok
