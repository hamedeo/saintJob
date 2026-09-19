import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class MonumentalSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get(
            "company",
            "Monumental",
        )
        self.url = config["url"]

        self.keywords = [
            x.casefold()
            for x in config.get("keywords", [])
        ]

        self.locations = {
            x.casefold()
            for x in config.get("locations", [])
        }

    def fetch_jobs(self) -> list[Job]:
        response = requests.get(
            self.url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        jobs = {}

        for link in soup.select(
            'a[href*="/jobs/"]'
        ):
            href = link.get("href", "").strip()

            if not href:
                continue

            job_url = urljoin(
                self.url,
                href,
            )

            # Skip the careers homepage itself.
            if job_url.rstrip("/") == self.url.rstrip("/"):
                continue

            match = re.search(
                r"/jobs/([^/]+)/([^/]+)/?$",
                job_url,
            )

            if not match:
                continue

            job_id = (
                f"{match.group(1)}-"
                f"{match.group(2)}"
            )

            if job_id in jobs:
                continue

            job = self._read_job(
                job_id,
                job_url,
            )

            if job:
                jobs[job_id] = job

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    def _read_job(
        self,
        job_id: str,
        job_url: str,
    ):
        response = requests.get(
            job_url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        heading = soup.find("h1")

        if not heading:
            return None

        title = " ".join(
            heading.get_text(
                " ",
                strip=True,
            ).split()
        )

        if self.keywords and not any(
            keyword in title.casefold()
            for keyword in self.keywords
        ):
            return None

        text = soup.get_text(
            " ",
            strip=True,
        )

        location = self._location(text)

        if (
            self.locations
            and location.casefold()
            not in self.locations
        ):
            return None

        return Job(
            source_id=self.source_id,
            source_name=self.source_name,
            job_id=job_id,
            title=title,
            url=job_url,
            company=self.company,
            location=location,
        )

    def _location(
        self,
        text: str,
    ) -> str:
        for location in self.locations:
            if re.search(
                rf"\b{re.escape(location)}\b",
                text,
                flags=re.IGNORECASE,
            ):
                return location.title()

        return ""