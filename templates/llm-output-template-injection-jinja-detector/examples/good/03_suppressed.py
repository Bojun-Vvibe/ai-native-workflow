from flask import render_template_string

def page(user):
    body = "Welcome " + "back, {{ user }}!"
    return render_template_string(body, user=user)  # ssti-ok: audited constant
