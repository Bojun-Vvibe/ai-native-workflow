from flask import render_template_string

def hello(name):
    # safe: literal template body, name is just context
    return render_template_string("Hello {{ name }}", name=name)
