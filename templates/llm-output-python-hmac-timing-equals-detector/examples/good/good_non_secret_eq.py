"""Good: comparing non-secret values (counts, status codes, sentinels)."""


def is_ok(status_code: int) -> bool:
    if status_code == 200:
        return True
    return False


def at_limit(count: int, limit: int) -> bool:
    return count == limit


def done(state) -> bool:
    return state is None or state == "done"
