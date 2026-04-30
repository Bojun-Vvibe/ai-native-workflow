from django.utils.safestring import mark_safe

def make_label(name):
    return mark_safe("<b>" + name + "</b>")
