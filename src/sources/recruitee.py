import requests

from src.models import Job
from src.sources.base import JobSource


class RecruiteeSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]

        self.base_url = config["base_url"].rstrip("/")

        self.keywords = [
            keyword.strip().casefold()
            for keyword in config.get("keywords", [])
            if keyword.strip()
        ]

        self.countries = [
            country.strip().upper()
            for country in config.get("countries", [])
            if country.strip()
        ]

    def fetch_jobs(self) -> list[Job]:
        response = requests.get(
            f"{self.base_url}/api/offers/",
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )

        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict):
            offers = data.get("offers", [])
        elif isinstance(data, list):
            offers = data
        else:
            offers = []

        jobs: dict[str, Job] = {}

        for offer in offers:
            title = str(
                offer.get("title", "")
            ).strip()

            slug = str(
                offer.get("slug", "")
            ).strip()

            if not title or not slug:
                continue

            # Filter by relevant title keywords.
            if self.keywords and not any(
                keyword in title.casefold()
                for keyword in self.keywords
            ):
                continue

            locations = offer.get("locations") or []

            # Optional country filter.
            if self.countries:
                country_codes = {
                    str(
                        location.get(
                            "country_code",
                            "",
                        )
                    ).upper()
                    for location in locations
                    if isinstance(location, dict)
                }

                if (
                    country_codes
                    and not country_codes.intersection(
                        self.countries
                    )
                ):
                    continue

            location = self._location_text(
                locations
            )

            job_id = str(
                offer.get("id", slug)
            )

            job = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=job_id,
                title=title,
                url=f"{self.base_url}/o/{slug}",
                company=self.company,
                location=location,
            )

            jobs[job_id] = job

            # Print matched vacancy + location.
            print(
                f"{title} | "
                f"{location or 'Location not specified'}"
            )

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    @staticmethod
    def _location_text(
        locations: list[dict],
    ) -> str:
        values = []

        for location in locations:
            if not isinstance(location, dict):
                continue

            # Prefer Recruitee's complete address.
            full_address = str(
                location.get(
                    "full_address",
                    "",
                )
            ).strip()

            if full_address:
                values.append(full_address)
                continue

            # Fallback if full_address is unavailable.
            city = str(
                location.get(
                    "city",
                    "",
                )
            ).strip()

            country = str(
                location.get(
                    "country",
                    "",
                )
            ).strip()

            parts = [
                part
                for part in (city, country)
                if part
            ]

            if parts:
                values.append(", ".join(parts))

        # Remove duplicate locations.
        return " | ".join(
            dict.fromkeys(values)
        )