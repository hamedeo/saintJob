import math

import requests

from src.models import Job
from src.sources.base import JobSource


class AppliedMedicalSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get(
            "company",
            "Applied Medical",
        )

        self.api_url = (
            "https://careers.appliedmedical.com/api/jobs"
        )

        self.locations = [
            value.strip()
            for value in config.get("locations", [])
            if value.strip()
        ]

        self.keywords = [
            value.strip().casefold()
            for value in config.get("keywords", [])
            if value.strip()
        ]

        self.max_pages = int(
            config.get("max_pages", 20)
        )

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })

    def fetch_jobs(self) -> list[Job]:
        jobs: dict[str, Job] = {}

        # Applied Medical API location syntax:
        #
        # Amersfoort,,Netherlands
        # |
        # The Hague,,Netherlands
        location_filter = "|".join(
            f"{city},,Netherlands"
            for city in self.locations
        )

        allowed_locations = {
            city.casefold()
            for city in self.locations
        }

        for page_number in range(
            1,
            self.max_pages + 1,
        ):
            response = self.session.get(
                self.api_url,
                params={
                    "page": page_number,
                    "locations": location_filter,
                    "sortBy": "relevance",
                    "descending": "false",
                    "internal": "false",
                },
                timeout=30,
            )

            response.raise_for_status()

            data = response.json()

            page_jobs = data.get(
                "jobs",
                [],
            )

            if not page_jobs:
                break

            for item in page_jobs:
                vacancy = item.get(
                    "data",
                    {},
                )

                job_id = str(
                    vacancy.get(
                        "req_id",
                        "",
                    )
                ).strip()

                title = str(
                    vacancy.get(
                        "title",
                        "",
                    )
                ).strip()

                city = str(
                    vacancy.get(
                        "city",
                        "",
                    )
                ).strip()

                country = str(
                    vacancy.get(
                        "country",
                        "",
                    )
                ).strip()

                country_code = str(
                    vacancy.get(
                        "country_code",
                        "",
                    )
                ).strip().upper()

                if not job_id or not title:
                    continue

                # -------------------------
                # Netherlands only
                # -------------------------
                if not (
                    country_code == "NL"
                    or country.casefold()
                    == "netherlands"
                ):
                    continue

                # -------------------------
                # Amersfoort / The Hague
                # only
                # -------------------------
                if (
                    allowed_locations
                    and city.casefold()
                    not in allowed_locations
                ):
                    continue

                # -------------------------
                # Relevant job titles
                # -------------------------
                if self.keywords and not any(
                    keyword in title.casefold()
                    for keyword in self.keywords
                ):
                    continue

                # -------------------------
                # Job URL
                # -------------------------
                metadata = (
                    vacancy.get(
                        "meta_data",
                        {},
                    )
                    or {}
                )

                job_url = str(
                    metadata.get(
                        "canonical_url",
                        "",
                    )
                ).strip()

                if not job_url:
                    job_url = (
                        "https://careers.appliedmedical.com"
                        f"/jobs/{job_id}"
                    )

                # -------------------------
                # Location
                # -------------------------
                location = (
                    f"{city}, Netherlands"
                    if city
                    else "Netherlands"
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

            # -------------------------
            # Pagination
            # -------------------------
            total_count = int(
                data.get(
                    "totalCount",
                    0,
                )
                or 0
            )

            count = int(
                data.get(
                    "count",
                    len(page_jobs),
                )
                or len(page_jobs)
            )

            if count <= 0:
                break

            total_pages = math.ceil(
                total_count / count
            )

            if page_number >= total_pages:
                break

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )