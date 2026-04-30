from django.utils.html import format_html, escape

def render_bio(bio):
    # Use format_html with auto-escaping and a literal template string.
    return format_html("<div class='bio'>{}</div>", bio)


def render_label(name):
    # Or escape explicitly.
    return "<b>" + escape(name) + "</b>"
