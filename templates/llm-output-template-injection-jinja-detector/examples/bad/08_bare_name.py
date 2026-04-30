from flask import request, render_template_string

def page():
    body = request.form.get("body", "")
    return render_template_string(body)
