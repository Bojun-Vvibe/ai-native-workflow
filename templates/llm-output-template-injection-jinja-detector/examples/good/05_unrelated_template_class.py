# Template here refers to a sqlalchemy / dataclass shape, unrelated
# to the SSTI surface. The file does not import the templating lib
# and does not call render_template_string.
class Template:
    def __init__(self, body):
        self.body = body

def make(user_input):
    return Template(user_input)
