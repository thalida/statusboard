from pathlib import Path

from polling.logo import find_logo, is_parent_domain

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class StubPage:
    """Serves one recorded page. No network."""

    def __init__(self, name):
        self.markup = (FIXTURES / name).read_text()

    def get(self, url, **kwargs):
        return type(
            "R",
            (),
            {
                "text": self.markup,
                "status_code": 200,
                "raise_for_status": lambda self: None,
            },
        )()


def test_it_finds_the_page_logo_statuspage_uploads():
    # Statuspage keeps a per-page favicon on its CDN. That is the
    # product's own mark, not Statuspage's.
    logo = find_logo(
        "https://www.githubstatus.com/", session=StubPage("page_githubstatus.html")
    )
    assert logo.startswith("https://")
    assert "favicon" in logo or "logo" in logo


def test_it_prefers_the_largest_icon_offered():
    # A favicon is often 16px and a service row wants better.
    logo = find_logo("https://status.openai.com/", session=StubPage("page_openai.html"))
    assert "w=96" in logo


def test_a_relative_icon_becomes_absolute():
    logo = find_logo("https://status.openai.com/", session=StubPage("page_openai.html"))
    assert logo.startswith("https://status.openai.com/")


def test_a_parent_company_mark_is_discarded():
    # Google's mark on a Google Slides page names the wrong product. A
    # wrong logo misidentifies a row; a missing one falls back to an
    # initial and merely looks incomplete.
    assert (
        find_logo(
            "https://status.slides.google.com/",
            session=StubPage("page_parent_favicon.html"),
        )
        == ""
    )


def test_a_page_logo_on_an_unrelated_cdn_is_kept():
    # That is where the provider keeps them, not a parent company.
    assert not is_parent_domain(
        "https://dka575ofm4ao0.cloudfront.net/pages-favicon_logos/x",
        "https://www.githubstatus.com/",
    )


def test_a_page_that_cannot_be_read_yields_nothing():
    # A logo is never worth failing a poll over.
    class Broken:
        def get(self, url, **kwargs):
            raise OSError("down")

    assert find_logo("https://status.example.com/", session=Broken()) == ""
