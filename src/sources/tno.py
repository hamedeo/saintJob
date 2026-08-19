import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class TnoSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "TNO")
        self.url = config["url"]

        self.keywords = [
            k.casefold()
            for k in config.get("keywords", [])
        ]

    def fetch_jobs(self) -> list[Job]:
        jobs = {}

        for page_number in range(10):
            url = self.url

            if page_number:
                url += f"?pager_page={page_number}"

            response = requests.get(
                url,
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

            found = 0

            for link in soup.select("a[href]"):
                href = link.get("href", "")

                if not re.search(
                    r"/careers/vacancies/"
                    r"(?:\d{4}/\d{2}/|%40|@)",
                    href,
                    re.IGNORECASE,
                ):
                    continue

                heading = link.find(
                    ["h2", "h3", "h4"]
                )

                if heading:
                    title = heading.get_text(
                        " ",
                        strip=True,
                    )
                else:
                    title = link.get_text(
                        " ",
                        strip=True,
                    )

                title = " ".join(
                    title.split()
                )

                if not title:
                    continue

                if self.keywords and not any(
                    keyword in title.casefold()
                    for keyword in self.keywords
                ):
                    continue

                job_url = urljoin(
                    self.url,
                    href,
                )

                path = urlparse(
                    job_url
                ).path.rstrip("/")

                job_id = path

                location = self._location(
                    link.get_text(
                        " ",
                        strip=True,
                    )
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

                found += 1

            # No vacancy links = end of pagination
            if found == 0 and page_number > 0:
                break

        return list(jobs.values())

    @staticmethod
    def _location(text: str) -> str:
        locations = [
            "Eindhoven",
            "Delft",
            "Helmond",
            "Leiden",
            "Petten",
            "Rijswijk",
            "The Hague",
            "Utrecht",
        ]

        for location in locations:
            if location.casefold() in text.casefold():
                return location

        return ""