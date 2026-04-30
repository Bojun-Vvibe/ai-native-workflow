"""Bad: CSRF token equality and OTP equality on the same handler."""


def submit(form, session):
    csrf_token = form.get("csrf_token")
    if csrf_token == session["csrf_token"]:
        otp = form.get("otp")
        if otp == session["otp"]:
            return "ok"
    return "deny"
