from urllib.parse import urlparse

import requests

from src.models import Job
from src.sources.base import JobSource


class AshbySource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]

        self.board_names = config.get(
            "board_names",
            [config.get("board_name", "")]
        )

        self.keywords = [
            value.strip().casefold()
            for value in config.get("keywords", [])
            if value.strip()
        ]

        self.locations = [
            value.strip().casefold()
            for value in config.get("locations", [])
            if value.strip()
        ]

        self.employment_types = [
            value.strip().casefold()
            for value in config.get("employment_types", [])
            if value.strip()
        ]

    def fetch_jobs(self) -> list[Job]:
        data = self._fetch_board()

        postings = data.get("jobs", [])
        jobs: dict[str, Job] = {}

        for posting in postings:
            if posting.get("isListed") is False:
                continue

            title = str(
                posting.get("title", "")
            ).strip()

            job_url = str(
                posting.get("jobUrl", "")
            ).strip()

            if not title or not job_url:
                continue

            # Employment type:
            # FullTime, PartTime, Intern, Contract, Temporary
            employment_type = str(
                posting.get("employmentType", "")
            ).strip()

            if self.employment_types:
                if (
                    employment_type.casefold()
                    not in self.employment_types
                ):
                    continue

            # Combine primary + secondary locations.
            job_locations = self._all_locations(
                posting
            )

            if self.locations:
                location_text = " | ".join(
                    job_locations
                ).casefold()

                if not any(
                    location in location_text
                    for location in self.locations
                ):
                    continue

            # Relevant title filter.
            if self.keywords and not any(
                keyword in title.casefold()
                for keyword in self.keywords
            ):
                continue

            job_id = self._job_id(
                job_url
            )

            if not job_id:
                continue

            location = " | ".join(
                job_locations
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

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    def _fetch_board(self) -> dict:
        last_error = None

        for board_name in self.board_names:
            if not board_name:
                continue

            url = (
                "https://api.ashbyhq.com/"
                "posting-api/job-board/"
                f"{board_name}"
            )

            try:
                response = requests.get(
                    url,
                    timeout=30,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )

                response.raise_for_status()

                data = response.json()

                if data.get("jobs") is not None:
                    return data

            except (
                requests.RequestException,
                ValueError,
            ) as error:
                last_error = error

        raise RuntimeError(
            "Ashby job board could not be loaded."
        ) from last_error

    @staticmethod
    def _all_locations(
        posting: dict,
    ) -> list[str]:
        locations: list[str] = []

        primary = str(
            posting.get("location", "")
        ).strip()

        if primary:
            locations.append(primary)

        for secondary in (
            posting.get("secondaryLocations")
            or []
        ):
            if not isinstance(
                secondary,
                dict,
            ):
                continue

            location = str(
                secondary.get(
                    "location",
                    "",
                )
            ).strip()

            if location:
                locations.append(
                    location
                )

        # Remove duplicates while preserving order.
        return list(
            dict.fromkeys(locations)
        )

    @staticmethod
    def _job_id(
        job_url: str,
    ) -> str:
        path = urlparse(
            job_url
        ).path.rstrip("/")

        if not path:
            return ""

        return path.split("/")[-1]