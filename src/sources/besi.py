import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class BesiSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "Besi")
        self.url = config["url"]
        self.apply_url = config["apply_url"]

        self.keywords = [
            x.casefold()
            for x in config.get("keywords", [])
        ]

    def fetch_jobs(self) -> list[Job]:
        jobs = {}

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        # ---------------------------------
        # Main Besi vacancy page
        # ---------------------------------

        response = requests.get(
            self.url,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for row in soup.select("tr"):
            cells = row.find_all("td")

            if len(cells) < 3:
                continue

            company = cells[0].get_text(
                " ",
                strip=True,
            )

            location = cells[1].get_text(
                " ",
                strip=True,
            )

            title = cells[2].get_text(
                " ",
                strip=True,
            )

            if "besi netherlands" not in company.casefold():
                continue

            if not self._matches(title):
                continue

            link = cells[2].find(
                "a",
                href=True,
            )

            job_url = (
                urljoin(self.url, link["href"])
                if link
                else self.apply_url
            )

            job_id = self._job_id(
                title,
                location,
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

        # ---------------------------------
        # Application form
        #
        # Sometimes contains NL vacancies
        # missing from the main table.
        # ---------------------------------

        response = requests.get(
            self.apply_url,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for option in soup.select("option"):
            text = " ".join(
                option.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            if "the netherlands" not in text.casefold():
                continue

            # Example:
            # Mechanical Developer,
            # Den Bosch, The Netherlands

            match = re.match(
                r"(.+?),\s*([^,]+),\s*"
                r"The Netherlands$",
                text,
                flags=re.IGNORECASE,
            )

            if not match:
                continue

            title = match.group(1).strip()
            location = match.group(2).strip()

            if not self._matches(title):
                continue

            job_id = self._job_id(
                title,
                location,
            )

            # Main-table version wins when available.
            if job_id in jobs:
                continue

            jobs[job_id] = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=job_id,
                title=title,
                url=self.apply_url,
                company=self.company,
                location=location,
            )

        return list(jobs.values())

    def _matches(self, title: str) -> bool:
        if not self.keywords:
            return True

        title = title.casefold()

        return any(
            keyword in title
            for keyword in self.keywords
        )

    @staticmethod
    def _job_id(
        title: str,
        location: str,
    ) -> str:
        value = (
            f"{title}-{location}"
            .casefold()
        )

        return re.sub(
            r"[^a-z0-9]+",
            "-",
            value,
        ).strip("-")