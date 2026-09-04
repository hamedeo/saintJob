import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class VarbiSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.url = config["url"]

        self.phd_department = (
            config.get("phd_department", "")
            .casefold()
        )

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

        vacancy_urls = {}

        for link in soup.select(
            'a[href*="what:job/jobID:"]'
        ):
            href = link.get("href", "")

            match = re.search(
                r"jobID:(\d+)",
                href,
            )

            if not match:
                continue

            job_id = match.group(1)

            vacancy_urls[job_id] = urljoin(
                self.url,
                href,
            )

        jobs = {}

        for job_id, job_url in vacancy_urls.items():
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

        title_lower = title.casefold()

        # --------------------------------
        # ALL EngD vacancies
        # --------------------------------
        if re.search(
            r"\bengd\b",
            title,
            flags=re.IGNORECASE,
        ):
            return self._make_job(
                job_id,
                title,
                job_url,
            )

        # --------------------------------
        # Only PhD vacancies after this
        # --------------------------------
        if not re.search(
            r"\bphd\b",
            title,
            flags=re.IGNORECASE,
        ):
            return None

        # --------------------------------
        # PhD must belong to
        # Mechanical Engineering
        # --------------------------------
        page_text = " ".join(
            soup.get_text(
                " ",
                strip=True,
            ).split()
        ).casefold()

        if (
            self.phd_department
            not in page_text
        ):
            return None

        return self._make_job(
            job_id,
            title,
            job_url,
        )

    def _make_job(
        self,
        job_id: str,
        title: str,
        job_url: str,
    ) -> Job:
        return Job(
            source_id=self.source_id,
            source_name=self.source_name,
            job_id=job_id,
            title=title,
            url=job_url,
            company=self.company,
            location="Eindhoven",
        )