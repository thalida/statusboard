"""The mail this project sends.

One message so far. Each is three templates under `templates/email`: a
subject, a plaintext body, and an HTML one. A client that refuses HTML
still gets a readable message, and both carry the same link.

The templates are files, not rows. They are part of the sign-in flow, so
a broken placeholder is a broken sign-in. A file is reviewed and tested
with the code that renders it.
"""

from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _render(name, context):
    """Subject, text and HTML from one name.

    A subject cannot hold a newline, and a template file ends with one.
    """
    subject = render_to_string(f"email/{name}.subject.txt", context)
    return (
        " ".join(subject.split()),
        render_to_string(f"email/{name}.txt", context),
        render_to_string(f"email/{name}.html", context),
    )


def magic_link_url(token):
    """Where the person clicking the link lands.

    Not `reverse("verify")`. That names this project's own endpoint, a
    POST that answers JSON, and a browser opening it sends a GET. The
    page is the client's, on its own origin, so APP_URL says where.

    Not `request.build_absolute_uri` either. That reads the Host header
    of the request being served, which is the caller's to set.
    """
    if not settings.APP_URL:
        raise ImproperlyConfigured(
            "APP_URL is unset, so a sign-in link would go nowhere. "
            "Set it to the address the client app is served from."
        )
    query = urlencode({"token": token})
    return f"{settings.APP_URL}{settings.APP_MAGIC_LINK_PATH}?{query}"


def send_magic_link(link):
    """The one email that signs somebody in."""
    context = {
        "url": magic_link_url(link.token),
        "minutes": int(settings.MAGIC_LINK_TTL.total_seconds() // 60),
        "app": settings.APP_URL,
    }
    subject, text, html = _render("magic_link", context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        to=[link.user.email],
    )
    message.attach_alternative(html, "text/html")
    message.send()
    return message
