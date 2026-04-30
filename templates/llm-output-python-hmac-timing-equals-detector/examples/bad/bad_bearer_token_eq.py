"""Bad: bearer token equality."""


def check(auth_header: str, expected_token: str) -> bool:
    bearer = auth_header.removeprefix("Bearer ")
    return bearer == expected_token
