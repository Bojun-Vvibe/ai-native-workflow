from flask import request, render_template_string

def greet():
    return render_template_string("Hello {{ name }}".replace("name", request.args["x"]))
