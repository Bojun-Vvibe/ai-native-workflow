from flask import request, render_template_string

def greet():
    tpl = "Hello %s" % request.args["name"]
    return render_template_string(tpl)
