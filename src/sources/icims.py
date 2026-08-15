import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from src.models import Job
from src.sources.base import JobSource


class IcimsSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.url = config["url"]

        self.keywords = [
            value.strip().casefold()
            for value in config.get("keywords", [])
            if value.strip()
        ]

        self.exclude_keywords = [
            value.strip().casefold()
            for value in config.get("exclude_keywords", [])
            if value.strip()
        ]

        self.locations = [
            value.strip().casefold()
            for value in config.get("locations", [])
            if value.strip()
        ]

    def fetch_jobs(self) -> list[Job]:
        response = requests.get(
            self.url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0",
            },
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        jobs: dict[str, Job] = {}

        for link in soup.select(
            'a[href*="/jobs/"][href$="/job"]'
        ):
            href = str(
                link.get("href", "")
            ).strip()

            title = " ".join(
                link.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            if not href or not title:
                continue

            match = re.search(
                r"/jobs/(\d+)/",
                href,
                flags=re.IGNORECASE,
            )

            if not match:
                continue

            job_id = match.group(1)

            card = self._find_card(
                link,
                job_id,
            )

            if card is None:
                continue

            card_text = " ".join(
                card.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            location = self._extract_location(
                card_text
            )

            # Optional location filtering.
            if self.locations and not any(
                allowed in location.casefold()
                for allowed in self.locations
            ):
                continue

            title_lower = title.casefold()

            # Relevant technical titles.
            if self.keywords and not any(
                keyword in title_lower
                for keyword in self.keywords
            ):
                continue

            # Remove obvious irrelevant matches.
            if any(
                keyword in title_lower
                for keyword in self.exclude_keywords
            ):
                continue

            jobs[job_id] = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=job_id,
                title=title,
                url=urljoin(
                    self.url,
                    href,
                ),
                company=self.company,
                location=location,
            )

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    @staticmethod
    def _find_card(
        link: Tag,
        job_id: str,
    ) -> Tag | None:
        for parent in link.parents:
            if not isinstance(parent, Tag):
                continue

            text = " ".join(
                parent.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            if (
                job_id in text
                and "Job ID" in text
            ):
                return parent

        return None

    @staticmethod
    def _extract_location(
        text: str,
    ) -> str:
        match = re.search(
            r"Job Locations?\s+(.+?)"
            r"(?:\s+Requisition|\s+Posted Date|\s+Job ID)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(1).strip()

        return ""