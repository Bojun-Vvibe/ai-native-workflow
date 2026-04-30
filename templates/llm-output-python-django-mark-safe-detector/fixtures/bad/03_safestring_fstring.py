from django.utils.safestring import SafeString

def render(comment):
    return SafeString(f"<p>{comment}</p>")
