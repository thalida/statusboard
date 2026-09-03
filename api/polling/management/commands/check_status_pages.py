"""Check the recorded status pages against what they serve today."""

import concurrent.futures
import json
import pathlib

from django.core.management.base import BaseCommand

from polling.adapters.registry import identify

PAGES = pathlib.Path(__file__).resolve().parents[2] / "data" / "status_pages.json"


def probe(page):
    """What reads this page now, or None."""
    try:
        adapter_class, _ = identify(page["url"])
        return page, adapter_class.__name__
    except Exception:  # noqa: BLE001 — every failure is the same answer here
        return page, None


class Command(BaseCommand):
    """Report pages that moved, broke, or started working.

    Status pages are somebody else's software. They get rebuilt, moved to
    another platform, or retired, and the first sign is a service that
    quietly stops updating. This is how that surfaces on purpose.

    It reaches the live internet, so it is a command and not a test. The
    suite blocks sockets for good reason.
    """

    help = "Probe the recorded status pages and report any drift."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update",
            action="store_true",
            help="Record what the pages serve today as the new baseline.",
        )

    def handle(self, *args, **options):
        pages = json.loads(PAGES.read_text())
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(probe, pages))

        broke, moved, fixed = [], [], []
        for page, found in results:
            was = page["adapter"]
            if was == found:
                continue
            if was and not found:
                broke.append((page, was, found))
            elif found and not was:
                fixed.append((page, was, found))
            else:
                moved.append((page, was, found))

        readable = sum(1 for _, found in results if found)
        self.stdout.write(f"{readable} of {len(results)} pages readable")

        for label, rows, style in (
            ("no longer readable", broke, self.style.ERROR),
            ("changed platform", moved, self.style.WARNING),
            ("now readable", fixed, self.style.SUCCESS),
        ):
            if not rows:
                continue
            self.stdout.write(style(f"\n{len(rows)} {label}:"))
            for page, was, found in rows:
                self.stdout.write(
                    f"  {page['name']:18} {was or '—'} -> {found or '—'}\n"
                    f"  {'':18} {page['url']}"
                )

        if options["update"]:
            for page, found in results:
                page["adapter"] = found
            PAGES.write_text(json.dumps(pages, indent=2) + "\n")
            self.stdout.write(self.style.SUCCESS("\nBaseline updated."))
            return

        if broke or moved:
            # A page that stopped working is the thing worth failing on.
            # A page that started is good news and never a failure.
            raise SystemExit(1)
