from django.utils.safestring import mark_safe

def render_bio(request):
    bio = request.POST.get("bio", "")
    # Attacker-controlled HTML lands directly in the template.
    return mark_safe(bio)
