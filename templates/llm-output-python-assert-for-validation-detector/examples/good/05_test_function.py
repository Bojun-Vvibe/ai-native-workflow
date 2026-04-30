"""Good: assert in a test_ function — that's exactly what asserts are for."""


def test_addition():
    assert 1 + 1 == 2
    assert "foo".upper() == "FOO"
