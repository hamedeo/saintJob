import re
from urllib.parse import urlencode, urljoin

from playwright.sync_api import sync_playwright

from src.models import Job
from src.sources.base import JobSource


class EightfoldSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.base_url = config["base_url"].rstrip("/")

        self.locations = config["locations"]
        self.keywords = config["keywords"]

        self.allowed_codes = {
            code.upper()
            for code in config["allowed_country_codes"]
        }

        self.timeout_ms = int(
            config.get("timeout_ms", 20000)
        )

    def fetch_jobs(self) -> list[Job]:
        jobs: dict[str, Job] = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True
            )

            page = browser.new_page()

            try:
                for location in self.locations:
                    for keyword in self.keywords:
                        url = self._search_url(
                            location,
                            keyword,
                        )

                        print(
                            f"Searching {keyword} "
                            f"| {location}"
                        )

                        page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=self.timeout_ms,
                        )

                        page.wait_for_timeout(2500)

                        links = page.locator(
                            'a[href*="/careers/job/"]'
                        )

                        for i in range(links.count()):
                            link = links.nth(i)

                            href = (
                                link.get_attribute("href")
                                or ""
                            )

                            match = re.search(
                                r"/careers/job/(\d+)",
                                href,
                            )

                            if not match:
                                continue

                            job_id = match.group(1)

                            text = " ".join(
                                link.inner_text().split()
                            )

                            if not text:
                                continue

                            country_code = (
                                self._country_code(text)
                            )

                            if (
                                country_code
                                not in self.allowed_codes
                            ):
                                continue

                            title = self._clean_title(
                                text
                            )

                            location_text = (
                                self._location(text)
                            )

                            jobs[job_id] = Job(
                                source_id=self.source_id,
                                source_name=self.source_name,
                                job_id=job_id,
                                title=title,
                                url=urljoin(
                                    self.base_url,
                                    href,
                                ),
                                company=self.company,
                                location=location_text,
                            )

            finally:
                browser.close()

        return list(jobs.values())

    @staticmethod
    def _country_code(text: str) -> str:
        match = re.search(
            r"\b(NL|BE|US|DE|AT|IN|KR|TW)-",
            text,
            flags=re.IGNORECASE,
        )

        return (
            match.group(1).upper()
            if match
            else ""
        )

    @staticmethod
    def _clean_title(text: str) -> str:
        return re.split(
            r"\s+(?:NL|BE|US|DE|AT|IN|KR|TW)-",
            text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()

    @staticmethod
    def _location(text: str) -> str:
        match = re.search(
            r"\b(NL|BE)-([A-Za-z-]+)",
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            return ""

        code = match.group(1).upper()

        city = (
            match.group(2)
            .replace("-", " ")
            .title()
        )

        country = {
            "NL": "Netherlands",
            "BE": "Belgium",
        }[code]

        return f"{city}, {country}"

    def _search_url(
        self,
        location: str,
        keyword: str,
    ) -> str:
        query = urlencode({
            "src": "Eightfold",
            "start": 0,
            "location": location,
            "query": keyword,
            "sort_by": "distance",
            "filter_include_remote": 0,
            "filter_include_relocation": 0,
        })

        return f"{self.base_url}?{query}"