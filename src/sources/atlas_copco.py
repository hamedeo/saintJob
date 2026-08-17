import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

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
            config.get("timeout_ms", 45000)
        )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/127.0 Safari/537.36"
            )
        })

    def fetch_jobs(self) -> list[Job]:
        vacancies = self._fetch_listing()

        jobs: dict[str, Job] = {}

        for vacancy in vacancies:
            job_id = vacancy["job_id"]
            job_url = vacancy["url"]
            fallback_title = vacancy["title"]

            details = self._fetch_details(
                job_url
            )

            title = (
                details.get("title")
                or fallback_title
            )

            location = self._format_location(
                details.get("city", ""),
                details.get("country", ""),
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

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    def _fetch_listing(
        self,
    ) -> list[dict]:
        """
        Atlas Copco's search page is rendered by
        JavaScript/Algolia, so Playwright is used here.
        """

        vacancies: dict[str, dict] = {}

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

                try:
                    page.wait_for_selector(
                        'a[href*="/job-detail/"]',
                        timeout=self.timeout_ms,
                    )
                except PlaywrightTimeoutError as error:
                    raise RuntimeError(
                        "Atlas Copco loaded, but no "
                        "job-detail links appeared."
                    ) from error

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

                    if job_id in vacancies:
                        continue

                    title = self._title_from_link(
                        link,
                        slug,
                    )

                    vacancies[job_id] = {
                        "job_id": job_id,
                        "title": title,
                        "url": job_url,
                    }

            finally:
                browser.close()

        if not vacancies:
            raise RuntimeError(
                "Atlas Copco loaded, but no "
                "valid vacancies were extracted."
            )

        return list(
            vacancies.values()
        )

    def _fetch_details(
        self,
        job_url: str,
    ) -> dict[str, str]:
        """
        Individual Atlas Copco job pages are
        server-rendered, so requests is sufficient.
        """

        try:
            response = self.session.get(
                job_url,
                timeout=20,
            )
            response.raise_for_status()

        except requests.RequestException as error:
            print(
                "Atlas Copco warning: "
                f"could not read {job_url}: {error}"
            )

            return {}

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        text = soup.get_text(
            "\n",
            strip=True,
        )

        title = self._extract_page_title(
            soup,
            job_url,
        )

        country = self._extract_field(
            text,
            "Location",
        )

        city = self._extract_field(
            text,
            "City",
        )

        return {
            "title": title,
            "country": country,
            "city": city,
        }

    @staticmethod
    def _extract_field(
        text: str,
        field: str,
    ) -> str:
        """
        Handles Atlas Copco metadata such as:

        Location: | Netherlands
        City: | Oosterhout
        """

        pattern = (
            rf"{re.escape(field)}\s*:"
            rf"\s*(?:\|\s*)?"
            rf"([^\n]+)"
        )

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            return ""

        value = match.group(1).strip()

        value = re.sub(
            r"^[|•:\-\s]+",
            "",
            value,
        )

        return " ".join(
            value.split()
        )

    @staticmethod
    def _extract_page_title(
        soup: BeautifulSoup,
        job_url: str,
    ) -> str:
        # Try H1 if one exists.
        heading = soup.find("h1")

        if heading is not None:
            title = " ".join(
                heading.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            if (
                title
                and len(title) <= 200
            ):
                return title

        # Atlas Copco's HTML title is also reliable.
        if soup.title:
            title = " ".join(
                soup.title.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            # Remove possible site suffix.
            title = re.sub(
                r"\s*[|\-]\s*Atlas Copco.*$",
                "",
                title,
                flags=re.IGNORECASE,
            ).strip()

            if (
                title
                and len(title) <= 200
            ):
                return title

        # Final fallback from URL.
        path = urlparse(
            job_url
        ).path.rstrip("/")

        parts = path.split("/")

        if len(parts) >= 2:
            return (
                parts[-2]
                .replace("---", " - ")
                .replace("--", " - ")
                .replace("-", " ")
                .strip()
                .title()
            )

        return ""

    @staticmethod
    def _title_from_link(
        link,
        slug: str,
    ) -> str:
        """
        Avoid using huge Atlas Copco card text
        as the job title.
        """

        try:
            text = " ".join(
                link.inner_text().split()
            )
        except Exception:
            text = ""

        if (
            text
            and 3 <= len(text) <= 200
        ):
            return text

        return (
            slug
            .replace("---", " - ")
            .replace("--", " - ")
            .replace("-", " ")
            .strip()
            .title()
        )

    @staticmethod
    def _format_location(
        city: str,
        country: str,
    ) -> str:
        city = " ".join(
            city.split()
        )

        country = " ".join(
            country.split()
        )

        if city and country:
            if (
                city.casefold()
                == country.casefold()
            ):
                return city

            return f"{city}, {country}"

        if city:
            return city

        if country:
            return country

        return ""