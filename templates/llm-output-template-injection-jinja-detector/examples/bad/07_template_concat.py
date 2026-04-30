from jinja2 import Template

def greet(name):
    return Template("Hello " + name).render()
