"""Bad: assert in nested function — still production code."""

def outer(req):
    def inner(amount):
        assert amount > 0, "amount must be positive"
        return amount * 2
    return inner(req["amount"])
