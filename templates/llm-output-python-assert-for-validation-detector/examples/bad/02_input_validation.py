"""Bad: assert used for input validation in API handler."""

def create_user(payload):
    assert "email" in payload
    assert "@" in payload["email"], "invalid email"
    return {"ok": True}
