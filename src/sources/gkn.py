import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from src.models import Job
from src.sources.base import JobSource


class GknSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "GKN Aerospace")
        self.url = config["url"]

        self.keywords = [
            keyword.strip().casefold()
            for keyword in config.get("keywords", [])
            if keyword.strip()
        ]

    def fetch_jobs(self) -> list[Job]:
        response = requests.get(
            self.url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        jobs_by_id: dict[str, Job] = {}

        links = soup.select('a[href*="/job/"]')

        if not links:
            raise RuntimeError(
                "GKN loaded, but no job links were found."
            )

        for link in links:
            href = str(link.get("href", "")).strip()

            match = re.search(
                r"/job/(\d+)",
                href,
            )

            if not match:
                continue

            job_id = match.group(1)

            card = self._find_card(link)

            if card is None:
                continue

            heading = card.find(
                ["h2", "h3", "h4", "h5"]
            )

            if heading is None:
                continue

            title = " ".join(
                heading.get_text(" ", strip=True).split()
            )

            card_text = " ".join(
                card.get_text(" ", strip=True).split()
            )

            # Keep only Papendrecht Engineering jobs.
            if "papendrecht" not in card_text.casefold():
                continue

            if "engineering" not in card_text.casefold():
                continue

            # Mechanical OR project
            if self.keywords and not any(
                keyword in title.casefold()
                for keyword in self.keywords
            ):
                continue

            jobs_by_id[job_id] = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=job_id,
                title=title,
                url=urljoin(self.url, href),
                company=self.company,
                location="Papendrecht, NL",
            )

        return sorted(
            jobs_by_id.values(),
            key=lambda job: job.title.casefold(),
        )

    @staticmethod
    def _find_card(link: Tag) -> Tag | None:
        for parent in link.parents:
            if not isinstance(parent, Tag):
                continue

            text = parent.get_text(
                " ",
                strip=True,
            ).casefold()

            if (
                "papendrecht" in text
                and "engineering" in text
                and parent.find(
                    ["h2", "h3", "h4", "h5"]
                )
            ):
                return parent

        return None