"""The mail this project sends.

One message so far. Each is three templates under `templates/email`: a
subject, a plaintext body, and an HTML one. A client that refuses HTML
still gets a readable message, and both carry the same link.

The templates are files, not rows. They are part of the sign-in flow, so
a broken placeholder is a broken sign-in. A file is reviewed and tested
with the code that renders it.
"""

from django.conf import settings
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


def send_magic_link(link):
    """The one email that signs somebody in.

    The address is built from SITE_URL, so a development link opens the
    development site. Hardcoding the production host sent every tester a
    link to somewhere they were not working.
    """
    minutes = int(settings.MAGIC_LINK_TTL.total_seconds() // 60)
    context = {
        "url": f"{settings.SITE_URL}{settings.MAGIC_LINK_PATH}?token={link.token}",
        "minutes": minutes,
        "site": settings.SITE_URL,
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
