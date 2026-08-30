"""Find a service's own logo on its status page.

Providers do not publish one in their JSON, so it comes from the page's
icon links. Statuspage uploads a per-page favicon to its CDN, incident.io
serves one through an image proxy; both identify the product.
"""

import html
import re
from urllib.parse import urljoin, urlparse

import requests

ICON_LINK = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
REL_ICON = re.compile(r'rel=["\'][^"\']*\bicon\b[^"\']*["\']', re.IGNORECASE)
HREF = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
SIZES = re.compile(r'sizes=["\'](\d+)x\d+["\']', re.IGNORECASE)


def find_logo(page_url: str, session=None) -> str:
    """The product's icon from its status page, or "" if there is none.

    Returns the largest icon offered. A favicon is often 16px and a row
    wants better.

    An icon from a parent domain is discarded. Google's mark on a Google
    Slides page names the wrong product. A wrong logo misidentifies a
    row; a missing one falls back to an initial.
    """
    try:
        response = (session or requests).get(page_url, timeout=10)
        response.raise_for_status()
        markup = response.text
    except Exception:  # noqa: BLE001 — a logo is never worth failing a poll
        return ""

    best, best_size = "", -1
    for tag in ICON_LINK.findall(markup):
        if not REL_ICON.search(tag):
            continue
        href = HREF.search(tag)
        if not href:
            continue
        candidate = urljoin(page_url, html.unescape(href.group(1)))
        if is_parent_domain(candidate, page_url):
            continue
        size = SIZES.search(tag)
        size = int(size.group(1)) if size else 0
        if size > best_size:
            best, best_size = candidate, size
    return best


def is_parent_domain(icon_url: str, page_url: str) -> bool:
    """Is the icon served from a domain the page sits underneath?

    status.slides.google.com linking google.com's favicon is the parent
    company's mark, not the product's. A page logo on an unrelated CDN is
    not: that is where the provider keeps them.
    """
    icon_host = urlparse(icon_url).netloc.lower().removeprefix("www.")
    page_host = urlparse(page_url).netloc.lower().removeprefix("www.")
    return bool(icon_host) and page_host.endswith(f".{icon_host}")
