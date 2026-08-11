from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class ProdriveSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get(
            "company",
            "Prodrive Technologies",
        )
        self.url = config["url"]
        self.max_pages = int(config.get("max_pages", 20))

        self.keywords = [
            value.casefold()
            for value in config.get("keywords", [])
        ]

        self.fields = [
            value.casefold()
            for value in config.get("fields", [])
        ]

        self.education = [
            value.casefold()
            for value in config.get("education", [])
        ]

        self.locations = [
            value.casefold()
            for value in config.get("locations", [])
        ]

    def fetch_jobs(self) -> list[Job]:
        jobs: dict[str, Job] = {}
        seen_page_jobs: set[str] = set()

        for page_number in range(1, self.max_pages + 1):
            page_url = f"{self.url}?page={page_number}"

            response = requests.get(
                page_url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()

            soup = BeautifulSoup(
                response.text,
                "html.parser",
            )

            page_jobs: set[str] = set()

            for link in soup.select(
                'a[href^="/vacancies/"]'
            ):
                href = str(
                    link.get("href", "")
                ).strip()

                if not href:
                    continue

                job_url = urljoin(self.url, href)
                path = urlparse(job_url).path.rstrip("/")
                slug = path.split("/")[-1]

                if not slug:
                    continue

                heading = link.find(
                    ["h2", "h3", "h4", "h5"]
                )

                if heading:
                    title = " ".join(
                        heading.get_text(
                            " ",
                            strip=True,
                        ).split()
                    )
                else:
                    # First text node normally contains
                    # the vacancy title.
                    title = " ".join(
                        link.get_text(
                            " ",
                            strip=True,
                        ).split()
                    )

                card_text = " ".join(
                    link.get_text(
                        " ",
                        strip=True,
                    ).split()
                )

                card_lower = card_text.casefold()
                title_lower = title.casefold()

                page_jobs.add(slug)

                if self.keywords and not any(
                    keyword in title_lower
                    for keyword in self.keywords
                ):
                    continue

                if self.fields and not any(
                    field in card_lower
                    for field in self.fields
                ):
                    continue

                if self.education and not any(
                    education in card_lower
                    for education in self.education
                ):
                    continue

                if self.locations and not any(
                    location in card_lower
                    for location in self.locations
                ):
                    continue

                location = next(
                    (
                        location
                        for location in config_locations(self)
                        if location.casefold()
                        in card_lower
                    ),
                    "",
                )

                jobs[slug] = Job(
                    source_id=self.source_id,
                    source_name=self.source_name,
                    job_id=slug,
                    title=title,
                    url=job_url,
                    company=self.company,
                    location=location,
                )

            # Stop when pagination ends or repeats.
            if not page_jobs:
                break

            if page_jobs.issubset(seen_page_jobs):
                break

            seen_page_jobs.update(page_jobs)

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )


def config_locations(source: ProdriveSource) -> list[str]:
    mapping = {
        "the netherlands - eindhoven":
            "The Netherlands - Eindhoven",
        "germany - köln":
            "Germany - Köln",
    }

    return [
        mapping.get(location, location)
        for location in source.locations
    ]