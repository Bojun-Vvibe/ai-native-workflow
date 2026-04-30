from jinja2 import Environment

env = Environment()

def render(user_input):
    tpl = env.from_string(user_input)
    return tpl.render()
