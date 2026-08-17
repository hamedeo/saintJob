from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class FouritegoSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "4ITEGO Group")
        self.url = config["url"]

        self.keywords = [
            keyword.strip().casefold()
            for keyword in config.get("keywords", [])
            if keyword.strip()
        ]

        self.locations = [
            location.strip().casefold()
            for location in config.get("locations", [])
            if location.strip()
        ]

    def fetch_jobs(self) -> list[Job]:
        response = requests.get(
            self.url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        jobs: dict[str, Job] = {}

        for link in soup.select('a[href*="/en/jobs/"]'):
            href = str(
                link.get("href", "")
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

            parts = path.strip("/").split("/")

            if len(parts) != 3:
                continue

            if parts[:2] != ["en", "jobs"]:
                continue

            job_id = parts[-1]

            # Open the job page because title/location
            # are easy to extract reliably there.
            job_response = requests.get(
                job_url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            job_response.raise_for_status()

            job_soup = BeautifulSoup(
                job_response.text,
                "html.parser",
            )

            heading = job_soup.find("h1")

            if heading is None:
                continue

            title = " ".join(
                heading.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            if not title:
                continue

            if self.keywords and not any(
                keyword in title.casefold()
                for keyword in self.keywords
            ):
                continue

            page_text = " ".join(
                job_soup.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            location = self._extract_location(
                page_text
            )

            if self.locations and not any(
                allowed in location.casefold()
                for allowed in self.locations
            ):
                continue

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

    @staticmethod
    def _extract_location(text: str) -> str:
        if "The Netherlands" in text:
            return "The Netherlands"

        if "Belgium" in text:
            return "Belgium"

        if "France" in text:
            return "France"

        return ""