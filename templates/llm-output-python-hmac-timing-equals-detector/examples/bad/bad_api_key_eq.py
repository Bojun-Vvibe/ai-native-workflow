"""Bad: comparing API key headers with == leaks length-prefix timing."""


def authenticated(request, settings):
    api_key = request.headers.get("X-Api-Key", "")
    if api_key == settings.API_KEY:
        return True
    return False
