from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from src.models import Job
from src.sources.base import JobSource


class VanderlandeSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get(
            "company",
            "Vanderlande",
        )
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
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        jobs_by_url: dict[str, Job] = {}

        for link in soup.select(
            'a[href*="/all-jobs/"]'
        ):
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

            if len(parts) != 2:
                continue

            if parts[0].casefold() != "all-jobs":
                continue

            slug = parts[1]

            card = self._find_card(link)

            if card is None:
                continue

            heading = card.find(
                ["h2", "h3", "h4"]
            )

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

            card_text = " ".join(
                card.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            if "netherlands" not in card_text.casefold():
                continue

            location = self._extract_location(
                card_text
            )

            jobs_by_url[job_url] = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=slug.casefold(),
                title=title,
                url=job_url,
                company=self.company,
                location=location,
            )

        return sorted(
            jobs_by_url.values(),
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
                "netherlands" in text
                and parent.find(
                    ["h2", "h3", "h4"]
                )
            ):
                return parent

        return None

    @staticmethod
    def _extract_location(text: str) -> str:
        locations = [
            "Veghel",
            "Schiphol",
            "Zaltbommel",
        ]

        for location in locations:
            if location.casefold() in text.casefold():
                return f"{location}, Netherlands"

        return "Netherlands"