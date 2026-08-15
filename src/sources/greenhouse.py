import requests

from src.models import Job
from src.sources.base import JobSource


class GreenhouseSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.board_token = config["board_token"]

        self.keywords = [
            keyword.strip().casefold()
            for keyword in config.get("keywords", [])
            if keyword.strip()
        ]

        self.api_url = (
            "https://boards-api.greenhouse.io/"
            f"v1/boards/{self.board_token}/jobs"
        )

    def fetch_jobs(self) -> list[Job]:
        response = requests.get(
            self.api_url,
            params={"content": "true"},
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )

        response.raise_for_status()

        data = response.json()
        postings = data.get("jobs", [])

        jobs: dict[str, Job] = {}

        for posting in postings:
            job_id = str(
                posting.get("id", "")
            ).strip()

            title = str(
                posting.get("title", "")
            ).strip()

            job_url = str(
                posting.get("absolute_url", "")
            ).strip()

            if not job_id or not title or not job_url:
                continue

            if self.keywords and not any(
                keyword in title.casefold()
                for keyword in self.keywords
            ):
                continue

            location_data = (
                posting.get("location") or {}
            )

            location = str(
                location_data.get("name", "")
            ).strip()

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