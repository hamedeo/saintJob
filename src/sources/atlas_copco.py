import re
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from src.models import Job
from src.sources.base import JobSource


class AtlasCopcoSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]

        self.company = config.get(
            "company",
            "Atlas Copco Group",
        )

        self.url = config["url"]

        self.timeout_ms = int(
            config.get(
                "timeout_ms",
                45000,
            )
        )

    def fetch_jobs(self) -> list[Job]:
        jobs: dict[str, Job] = {}

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True
            )

            page = browser.new_page(
                viewport={
                    "width": 1440,
                    "height": 1200,
                },
                user_agent=(
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/127.0 Safari/537.36"
                ),
            )

            try:
                page.goto(
                    self.url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )

                page.wait_for_selector(
                    'a[href*="/job-detail/"]',
                    timeout=self.timeout_ms,
                )

                # Let Algolia finish rendering.
                page.wait_for_timeout(1500)

                links = page.locator(
                    'a[href*="/job-detail/"]'
                )

                for index in range(
                    links.count()
                ):
                    link = links.nth(index)

                    href = (
                        link.get_attribute("href")
                        or ""
                    ).strip()

                    if not href:
                        continue

                    job_url = urljoin(
                        self.url,
                        href,
                    )

                    path = urlparse(
                        job_url
                    ).path.rstrip("/")

                    match = re.search(
                        r"/job-detail/([^/]+)/(\d+)$",
                        path,
                        flags=re.IGNORECASE,
                    )

                    if not match:
                        continue

                    slug = match.group(1)
                    job_id = match.group(2)

                    # Avoid duplicate links to the same vacancy.
                    if job_id in jobs:
                        continue

                    title = self._extract_title(
                        link,
                        slug,
                    )

                    if not title:
                        continue

                    location = (
                        self._extract_location(
                            link
                        )
                    )

                    jobs[job_id] = Job(
                        source_id=self.source_id,
                        source_name=self.source_name,
                        job_id=job_id,
                        title=title,
                        url=job_url,
                        company=self.company,
                        location=location,
                    )

            finally:
                browser.close()

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    @staticmethod
    def _extract_title(
        link,
        slug: str,
    ) -> str:
        """
        Extract only the actual vacancy title.

        Atlas Copco job links can contain the entire
        vacancy card, so using link.inner_text()
        directly may produce thousands of characters.
        """

        current = link

        for _ in range(8):
            headings = current.locator(
                "h1, h2, h3, h4, h5"
            )

            for index in range(
                headings.count()
            ):
                try:
                    title = " ".join(
                        headings
                        .nth(index)
                        .inner_text()
                        .split()
                    )
                except Exception:
                    continue

                if (
                    title
                    and 3 <= len(title) <= 200
                ):
                    return title

            current = current.locator("..")

            if current.count() == 0:
                break

        # Try the link text only if it looks
        # like a normal job title.
        try:
            link_text = " ".join(
                link.inner_text().split()
            )
        except Exception:
            link_text = ""

        if (
            link_text
            and 3 <= len(link_text) <= 200
        ):
            return link_text

        # Safe fallback: construct title from URL slug.
        return AtlasCopcoSource._title_from_slug(
            slug
        )

    @staticmethod
    def _extract_location(
        link,
    ) -> str:
        current = link

        for _ in range(8):
            location_element = current.locator(
                '[class*="location" i], '
                '[data-testid*="location" i]'
            )

            if location_element.count():
                try:
                    location = " ".join(
                        location_element
                        .first
                        .inner_text()
                        .split()
                    )
                except Exception:
                    location = ""

                if (
                    location
                    and len(location) <= 150
                ):
                    return location

            current = current.locator("..")

            if current.count() == 0:
                break

        return ""

    @staticmethod
    def _title_from_slug(
        slug: str,
    ) -> str:
        # Preserve separators such as:
        # mechanical-engineer---projects
        # -> Mechanical Engineer - Projects

        value = slug.replace(
            "---",
            " - ",
        )

        value = value.replace(
            "--",
            " - ",
        )

        value = value.replace(
            "-",
            " ",
        )

        value = " ".join(
            value.split()
        )

        return value.title()