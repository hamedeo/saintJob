import requests

from src.models import Job
from src.sources.base import JobSource


class SmartrecruitersSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.company_id = config["company_id"]

        self.country = config.get("country", "")
        self.functions = {
            x.casefold()
            for x in config.get("functions", [])
        }

        self.keywords = [
            x.casefold()
            for x in config.get("keywords", [])
        ]

        self.exclude_keywords = [
            x.casefold()
            for x in config.get("exclude_keywords", [])
        ]

    def fetch_jobs(self) -> list[Job]:
        jobs = {}
        offset = 0
        limit = 100

        while True:
            url = (
                "https://api.smartrecruiters.com/v1/companies/"
                f"{self.company_id}/postings"
            )

            params = {
                "limit": limit,
                "offset": offset,
                "destination": "PUBLIC",
            }

            if self.country:
                params["country"] = self.country

            response = requests.get(
                url,
                params=params,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0"
                },
            )
            response.raise_for_status()

            data = response.json()
            postings = data.get("content", [])

            if not postings:
                break

            for posting in postings:
                title = posting.get("name", "").strip()

                if not title:
                    continue

                function = (
                    posting.get("function", {})
                    .get("label", "")
                    .strip()
                )

                if (
                    self.functions
                    and function.casefold()
                    not in self.functions
                ):
                    continue

                title_lower = title.casefold()

                if self.keywords and not any(
                    word in title_lower
                    for word in self.keywords
                ):
                    continue

                if any(
                    word in title_lower
                    for word in self.exclude_keywords
                ):
                    continue

                job_id = str(posting["id"])

                location_data = posting.get(
                    "location",
                    {},
                )

                city = location_data.get(
                    "city",
                    "",
                ).strip()

                country = location_data.get(
                    "country",
                    "",
                ).strip()

                location = city

                if country:
                    location = (
                        f"{city}, {country}"
                        if city
                        else country
                    )

                # Detail call gives us postingUrl.
                detail_url = (
                    "https://api.smartrecruiters.com/v1/"
                    f"companies/{self.company_id}/"
                    f"postings/{job_id}"
                )

                detail = requests.get(
                    detail_url,
                    timeout=20,
                    headers={
                        "User-Agent": "Mozilla/5.0"
                    },
                )
                detail.raise_for_status()

                detail_data = detail.json()

                posting_url = detail_data.get(
                    "postingUrl",
                    "",
                )

                if not posting_url:
                    continue

                jobs[job_id] = Job(
                    source_id=self.source_id,
                    source_name=self.source_name,
                    job_id=job_id,
                    title=title,
                    url=posting_url,
                    company=self.company,
                    location=location,
                )

            offset += limit

            if offset >= data.get(
                "totalFound",
                0,
            ):
                break

        return list(jobs.values())