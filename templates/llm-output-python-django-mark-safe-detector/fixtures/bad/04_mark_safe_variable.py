from django.utils.safestring import mark_safe

def render(value):
    html = "<span>%s</span>" % value
    return mark_safe(html)
