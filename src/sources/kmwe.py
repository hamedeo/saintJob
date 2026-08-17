import re
from urllib.parse import urljoin, urlparse

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.models import Job
from src.sources.base import JobSource


class KmweSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "KMWE")
        self.url = config["url"]

        self.disciplines = [
            value.strip().casefold()
            for value in config.get("disciplines", [])
            if value.strip()
        ]

        self.timeout_ms = int(
            config.get("timeout_ms", 45000)
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
                # ---------------------------------
                # 1. Load KMWE vacancy listing
                # ---------------------------------

                page.goto(
                    self.url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )

                try:
                    page.wait_for_selector(
                        'a[href*="/vacancies/"]',
                        timeout=self.timeout_ms,
                    )
                except PlaywrightTimeoutError as error:
                    raise RuntimeError(
                        "KMWE loaded, but no vacancy links appeared."
                    ) from error

                # ---------------------------------
                # 2. Scroll until all vacancies
                #    have been loaded
                # ---------------------------------

                previous_count = 0
                stable_rounds = 0

                for _ in range(20):
                    links = page.locator(
                        'a[href*="/vacancies/"]'
                    )

                    current_count = links.count()

                    if current_count == previous_count:
                        stable_rounds += 1
                    else:
                        stable_rounds = 0

                    if stable_rounds >= 3:
                        break

                    previous_count = current_count

                    page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )

                    page.wait_for_timeout(750)

                # ---------------------------------
                # 3. Collect unique vacancy URLs
                # ---------------------------------

                vacancy_urls: set[str] = set()

                links = page.locator(
                    'a[href*="/vacancies/"]'
                )

                for index in range(links.count()):
                    href = (
                        links.nth(index)
                        .get_attribute("href")
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
                        r"/vacancies/(\d+)-",
                        path,
                        flags=re.IGNORECASE,
                    )

                    if not match:
                        continue

                    vacancy_urls.add(job_url)

                if not vacancy_urls:
                    raise RuntimeError(
                        "KMWE loaded, but no valid vacancy "
                        "URLs were extracted."
                    )

                # ---------------------------------
                # 4. Open each job and inspect
                #    its actual Discipline field
                # ---------------------------------

                for job_url in vacancy_urls:
                    page.goto(
                        job_url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )

                    page.wait_for_timeout(300)

                    heading = page.locator("h1")

                    if not heading.count():
                        continue

                    title = self._clean(
                        heading.first.inner_text()
                    )

                    if not title:
                        continue

                    body_text = page.locator(
                        "body"
                    ).inner_text()

                    fields = self._extract_fields(
                        body_text
                    )

                    discipline = fields.get(
                        "discipline",
                        "",
                    )

                    # Only Engineering discipline.
                    if self.disciplines and (
                        discipline.casefold()
                        not in self.disciplines
                    ):
                        continue

                    job_id = self._extract_job_id(
                        job_url
                    )

                    if not job_id:
                        continue

                    location = fields.get(
                        "location",
                        "",
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
    def _extract_job_id(
        job_url: str,
    ) -> str:
        match = re.search(
            r"/vacancies/(\d+)-",
            urlparse(job_url).path,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(1)

        return ""

    @staticmethod
    def _extract_fields(
        text: str,
    ) -> dict[str, str]:
        """
        KMWE job pages contain a metadata block like:

        Location
        Eindhoven, Nederland

        Hours
        40

        Experience
        Professional

        Level of education
        HBO/WO

        Discipline
        Engineering

        Company
        KMWE Precision B.V.
        """

        lines = [
            " ".join(line.split())
            for line in text.splitlines()
            if line.strip()
        ]

        labels = {
            "location": "location",
            "hours": "hours",
            "experience": "experience",
            "level of education": "level_of_education",
            "discipline": "discipline",
            "company": "company",
        }

        fields: dict[str, str] = {}

        # Work backwards because the actual vacancy
        # metadata block appears toward the bottom
        # of the page.
        for index in range(
            len(lines) - 1,
            -1,
            -1,
        ):
            label = lines[index].casefold()

            if label not in labels:
                continue

            key = labels[label]

            if key in fields:
                continue

            if index + 1 >= len(lines):
                continue

            value = lines[index + 1]

            # Do not accidentally use another field
            # label as the value.
            if value.casefold() in labels:
                continue

            fields[key] = value

        return fields

    @staticmethod
    def _clean(
        value: str,
    ) -> str:
        return " ".join(
            value.split()
        )