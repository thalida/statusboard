"""The recorded page list, checked without touching the network.

Probing them for real is `manage.py check_status_pages`. The suite
blocks sockets, and 101 third parties are not a test dependency.
"""

import json
from urllib.parse import urlparse

import pytest

from polling.adapters.registry import ADAPTERS, RSSAdapter
from polling.management.commands.check_status_pages import PAGES

KNOWN = {adapter.__name__ for adapter in (*ADAPTERS, RSSAdapter)}


@pytest.fixture(scope="module")
def pages():
    return json.loads(PAGES.read_text())


def test_the_list_is_not_empty(pages):
    assert len(pages) > 50


def test_every_page_names_a_service_once(pages):
    names = [page["name"] for page in pages]
    assert len(names) == len(set(names)), "a service is listed twice"


def test_every_url_appears_once(pages):
    urls = [page["url"] for page in pages]
    assert len(urls) == len(set(urls)), "a URL is listed twice"


def test_every_url_is_absolute_and_https(pages):
    # A relative or bare-host entry would probe something unintended.
    for page in pages:
        parts = urlparse(page["url"])
        assert parts.scheme == "https", f"{page['name']}: {page['url']}"
        assert parts.netloc, f"{page['name']}: {page['url']}"


def test_every_recorded_adapter_still_exists(pages):
    """A renamed adapter would otherwise show as every page breaking.

    The baseline stores class names. Deleting or renaming one has to
    fail here, not in a probe against the live internet.
    """
    for page in pages:
        if page["adapter"] is not None:
            assert page["adapter"] in KNOWN, f"{page['name']} names {page['adapter']}"
