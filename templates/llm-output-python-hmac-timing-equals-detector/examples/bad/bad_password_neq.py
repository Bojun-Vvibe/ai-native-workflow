"""Bad: password compared as plain string with !=."""


def login(submitted_password: str, stored_password: str) -> bool:
    if submitted_password != stored_password:
        return False
    return True
