from flask import request, render_template_string

def greet():
    return render_template_string("Hi {0}".format(request.args["x"]))
