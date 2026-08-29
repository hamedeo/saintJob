import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class NtsSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "NTS")
        self.url = config["url"]

        self.keywords = [
            value.casefold()
            for value in config.get("keywords", [])
        ]

        self.allowed_locations = {
            value.casefold()
            for value in config.get("locations", [])
        }

    def fetch_jobs(self) -> list[Job]:
        vacancy_urls = set()
        jobs = {}

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        for page_number in range(1, 10):
            if page_number == 1:
                page_url = self.url
            else:
                page_url = (
                    "https://www.nts-group.com/en/"
                    f"vacancies/page/{page_number}/"
                    "?job_areas%5B0%5D=engineering-technology"
                )

            response = requests.get(
                page_url,
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()

            soup = BeautifulSoup(
                response.text,
                "html.parser",
            )

            page_urls = {
                urljoin(page_url, link["href"])
                for link in soup.select(
                    'a[href*="/en/vacancy/"]'
                )
                if link.get("href")
            }

            new_urls = page_urls - vacancy_urls

            if not new_urls:
                break

            vacancy_urls.update(new_urls)

        for job_url in vacancy_urls:
            response = requests.get(
                job_url,
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()

            soup = BeautifulSoup(
                response.text,
                "html.parser",
            )

            heading = soup.find("h1")

            if not heading:
                continue

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
                continue

            location = self._extract_location(
                soup,
                title,
            )

            # Netherlands locations only
            if (
                self.allowed_locations
                and location.casefold()
                not in self.allowed_locations
            ):
                continue

            match = re.search(
                r"/vacancy/([^/]+)/?$",
                job_url,
            )

            if not match:
                continue

            job_id = match.group(1)

            jobs[job_id] = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=job_id,
                title=title,
                url=job_url,
                company=self.company,
                location=location,
            )

        return list(jobs.values())

    @staticmethod
    def _extract_location(
        soup: BeautifulSoup,
        title: str,
    ) -> str:
        """
        NTS puts the real location directly below
        the main vacancy heading.
        """

        heading = soup.find("h1")

        if heading:
            parent = heading.parent

            if parent:
                for element in parent.find_all(
                    ["li", "p", "span"],
                    limit=10,
                ):
                    text = " ".join(
                        element.get_text(
                            " ",
                            strip=True,
                        ).split()
                    )

                    if (
                        text
                        and not re.search(
                            r"\bhours?\b",
                            text,
                            flags=re.IGNORECASE,
                        )
                        and len(text) < 80
                    ):
                        return text

        # Safe fallback from title:
        #
        # Project Manager | NTS Singapore
        # Project Manager | NTS Brno

        match = re.search(
            r"\|\s*NTS\s+(.+)$",
            title,
            flags=re.IGNORECASE,
        )

        if match:
            site = match.group(1).strip()

            mapping = {
                "eindhoven": "Eindhoven",
                "optel": "Nijmegen",
                "bergeijk": "Bergeijk",
                "drachten": "Drachten",
                "helmond": "Helmond",
                "hengelo": "Hengelo",
                "brno": "Brno",
                "singapore": "Singapore",
                "slavičín": "Slavičín",
                "shanghai": "Shanghai",
                "silicon valley": "Silicon Valley",
            }

            return mapping.get(
                site.casefold(),
                site,
            )

        return ""