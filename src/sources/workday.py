import re
from urllib.parse import urlparse

import requests

from src.models import Job
from src.sources.base import JobSource


class WorkdaySource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]

        self.base_url = config["base_url"].rstrip("/")
        self.tenant = config["tenant"]
        self.site = config["site"]

        self.facets = config.get("facets", {})

        self.keywords = [
            keyword.strip().casefold()
            for keyword in config.get("keywords", [])
            if keyword.strip()
        ]

        parsed = urlparse(self.base_url)

        self.api_url = (
            f"{parsed.scheme}://{parsed.netloc}"
            f"/wday/cxs/{self.tenant}/{self.site}/jobs"
        )

    def fetch_jobs(self) -> list[Job]:
        jobs: dict[str, Job] = {}

        offset = 0
        limit = 20

        while True:
            response = requests.post(
                self.api_url,
                json={
                    "appliedFacets": self.facets,
                    "limit": limit,
                    "offset": offset,
                    "searchText": "",
                },
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Content-Type": "application/json",
                },
            )

            response.raise_for_status()
            data = response.json()

            postings = data.get("jobPostings", [])

            if not postings:
                break

            for posting in postings:
                title = posting.get("title", "").strip()
                external_path = posting.get(
                    "externalPath",
                    "",
                ).strip()

                if not title or not external_path:
                    continue

                if self.keywords and not any(
                    keyword in title.casefold()
                    for keyword in self.keywords
                ):
                    continue

                match = re.search(
                    r"_(JR\d+)$",
                    external_path,
                    flags=re.IGNORECASE,
                )

                if match:
                    job_id = match.group(1)
                else:
                    job_id = external_path.rstrip("/").split("/")[-1]

                jobs[job_id] = Job(
                    source_id=self.source_id,
                    source_name=self.source_name,
                    job_id=job_id,
                    title=title,
                    url=f"{self.base_url}{external_path}",
                    company=self.company,
                    location=posting.get(
                        "locationsText",
                        "",
                    ),
                )

            offset += len(postings)

            total = data.get("total", 0)

            if offset >= total:
                break

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )