from django.utils.safestring import mark_safe

# Static, developer-controlled HTML literal: safe by construction.
LEGAL_BANNER = mark_safe("<strong>All rights reserved.</strong>")
