import re
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from src.models import Job
from src.sources.base import JobSource


class PhenomSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.url = config["url"]

        self.keywords = [
            x.casefold()
            for x in config.get("keywords", [])
        ]

        self.location = config.get(
            "location",
            "",
        ).casefold()

        self.timeout_ms = int(
            config.get("timeout_ms", 20000)
        )

    def fetch_jobs(self) -> list[Job]:
        vacancy_urls = {}
        jobs = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True
            )

            page = browser.new_page()

            try:
                # Phenom uses from=0,10,20...
                for offset in range(0, 200, 10):
                    separator = (
                        "&"
                        if "?" in self.url
                        else "?"
                    )

                    page_url = (
                        f"{self.url}"
                        f"{separator}from={offset}"
                    )

                    page.goto(
                        page_url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )

                    page.wait_for_timeout(2500)

                    links = page.locator(
                        'a[href*="/global/en/job/"]'
                    )

                    found = 0

                    for i in range(links.count()):
                        href = (
                            links.nth(i)
                            .get_attribute("href")
                            or ""
                        )

                        match = re.search(
                            r"/job/(\d+)/",
                            href,
                        )

                        if not match:
                            continue

                        job_id = match.group(1)

                        if job_id not in vacancy_urls:
                            found += 1

                        vacancy_urls[job_id] = urljoin(
                            self.url,
                            href,
                        )

                    if found == 0:
                        break

                # Read the real title/location
                # from each vacancy page.
                for job_id, job_url in vacancy_urls.items():
                    page.goto(
                        job_url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )

                    page.wait_for_timeout(700)

                    heading = page.locator("h1").first

                    if not heading.count():
                        continue

                    title = " ".join(
                        heading.inner_text().split()
                    )

                    if not title:
                        continue

                    if self.keywords and not any(
                        keyword in title.casefold()
                        for keyword in self.keywords
                    ):
                        continue

                    body = page.locator(
                        "body"
                    ).inner_text()

                    # Strict Netherlands check.
                    if (
                        self.location
                        and self.location
                        not in body.casefold()
                    ):
                        continue

                    location = self._location(
                        body
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
    def _location(text: str) -> str:
        match = re.search(
            r"([A-Za-zÀ-ÿ .'-]+),\s*"
            r"(?:North Brabant,\s*)?"
            r"Netherlands",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            city = " ".join(
                match.group(1).split()
            )

            return (
                f"{city}, Netherlands"
            )

        if "Netherlands" in text:
            return "Netherlands"

        return ""