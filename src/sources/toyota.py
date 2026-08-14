from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class ToyotaSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get(
            "company",
            "Toyota Motor Europe",
        )
        self.url = config["url"]

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0"
        })

    def fetch_jobs(self) -> list[Job]:
        response = self.session.get(
            self.url,
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        job_urls: set[str] = set()

        # Find all Toyota job-detail links.
        for link in soup.select("a[href]"):
            href = str(
                link.get("href", "")
            ).strip()

            if not href:
                continue

            job_url = urljoin(
                self.url,
                href,
            )

            parsed = urlparse(job_url)
            path = parsed.path.rstrip("/")

            parts = path.strip("/").split("/")

            # Valid vacancy:
            # /jobs/body-design-engineer-graduate-2
            if len(parts) != 2:
                continue

            if parts[0].casefold() != "jobs":
                continue

            slug = parts[1].casefold()

            # Exclude non-vacancy routes.
            if slug in {
                "domains",
                "levels",
                "locations",
            }:
                continue

            job_urls.add(job_url)

        if not job_urls:
            raise RuntimeError(
                "Toyota loaded, but no job-detail links "
                "were found."
            )

        jobs: list[Job] = []

        for job_url in job_urls:
            job = self._fetch_job(job_url)

            if job is not None:
                jobs.append(job)

        if not jobs:
            raise RuntimeError(
                "Toyota job links were found, but vacancy "
                "details could not be extracted."
            )

        return sorted(
            jobs,
            key=lambda job: job.title.casefold(),
        )

    def _fetch_job(
        self,
        job_url: str,
    ) -> Job | None:
        response = self.session.get(
            job_url,
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        heading = soup.find("h1")

        if heading is None:
            return None

        title = " ".join(
            heading.get_text(
                " ",
                strip=True,
            ).split()
        )

        if not title:
            return None

        path = urlparse(
            job_url
        ).path.rstrip("/")

        job_id = path.split("/")[-1].casefold()

        page_text = " ".join(
            soup.get_text(
                " ",
                strip=True,
            ).split()
        )

        if "Brussels (Zaventem)" in page_text:
            location = "Brussels (Zaventem)"
        elif "Brussels (Evere)" in page_text:
            location = "Brussels (Evere)"
        else:
            location = "Belgium"

        return Job(
            source_id=self.source_id,
            source_name=self.source_name,
            job_id=job_id,
            title=title,
            url=job_url,
            company=self.company,
            location=location,
        )