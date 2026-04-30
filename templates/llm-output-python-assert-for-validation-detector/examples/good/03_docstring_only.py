"""Good: docstring mentions assert without using it as a statement."""


def example():
    """Do not write `assert user.is_admin` for authorization;

    use `if not user.is_admin: raise PermissionError(...)` instead.
    """
    return None
