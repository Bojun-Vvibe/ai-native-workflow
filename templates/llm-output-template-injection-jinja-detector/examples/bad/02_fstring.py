from flask import request, render_template_string

def hello():
    name = request.args["name"]
    return render_template_string(f"<h1>Hi {name}</h1>")
