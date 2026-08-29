import re

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class FrenckenSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "Frencken")
        self.url = config["url"]

        self.keywords = [
            k.casefold()
            for k in config.get("keywords", [])
        ]

        self.locations = config.get("locations", [])

    def fetch_jobs(self) -> list[Job]:
        response = requests.get(
            self.url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        jobs = {}

        for link in soup.select(
            'a[href*="myworkdayjobs.com"]'
        ):
            href = link.get("href", "").strip()

            if "/job/" not in href:
                continue

            text = " ".join(
                link.get_text(" ", strip=True).split()
            )

            if not text:
                continue

            title, location = self._parse_card(text)

            if not title:
                continue

            if self.keywords and not any(
                keyword in title.casefold()
                for keyword in self.keywords
            ):
                continue

            match = re.search(
                r"_([A-Za-z0-9]+)(?:\?|$)",
                href,
            )

            job_id = (
                match.group(1)
                if match
                else href
            )

            jobs[job_id] = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=job_id,
                title=title,
                url=href,
                company=self.company,
                location=location,
            )

        return list(jobs.values())

    def _parse_card(
        self,
        text: str,
    ) -> tuple[str, str]:
        # Remove category prefix.
        if text.startswith("Engineering "):
            text = text[len("Engineering "):]

        for location in self.locations:
            marker = f" {location} - Netherlands"

            if marker in text:
                title = text.split(
                    marker,
                    1,
                )[0].strip()

                return (
                    title,
                    f"{location}, Netherlands",
                )

        return "", ""