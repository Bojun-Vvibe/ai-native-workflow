from flask import render_template

def page(user):
    # file-backed templates are developer-controlled; not SSTI.
    return render_template("page.html", user=user)
