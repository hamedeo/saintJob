import requests

from src.models import Job
from src.sources.base import JobSource


class OracleSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]

        self.host = config["host"].rstrip("/")
        self.site = config.get("site", "CX_1")

        self.location_id = config.get("location_id", "")
        self.title_facet = config.get("title_facet", "")

        self.countries = {
            x.upper()
            for x in config.get("countries", [])
        }

        self.keywords = [
            x.casefold()
            for x in config.get("keywords", [])
        ]

    def fetch_jobs(self) -> list[Job]:
        jobs = {}

        limit = 25
        offset = 0

        api_url = (
            f"{self.host}/hcmRestApi/resources/latest/"
            "recruitingCEJobRequisitions"
        )

        while True:
            finder = (
                f"findReqs;"
                f"siteNumber={self.site},"
                f"limit={limit},"
                f"offset={offset}"
            )

            if self.location_id:
                finder += (
                    f",locationId={self.location_id}"
                )

            if self.title_facet:
                finder += (
                    ",lastSelectedFacet=TITLES"
                    f",selectedTitlesFacet={self.title_facet}"
                )

            response = requests.get(
                api_url,
                params={
                    "onlyData": "true",
                    "expand": "requisitionList",
                    "finder": finder,
                },
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            data = response.json()

            page_jobs = []

            for item in data.get("items", []):
                page_jobs.extend(
                    item.get("requisitionList", [])
                )

            if not page_jobs:
                break

            for vacancy in page_jobs:
                job_id = str(
                    vacancy.get("Id", "")
                ).strip()

                title = str(
                    vacancy.get("Title", "")
                ).strip()

                location = str(
                    vacancy.get(
                        "PrimaryLocation",
                        "",
                    )
                ).strip()

                country = str(
                    vacancy.get(
                        "PrimaryLocationCountry",
                        "",
                    )
                ).strip().upper()

                if not job_id or not title:
                    continue

                # Netherlands only
                if (
                    self.countries
                    and country not in self.countries
                ):
                    continue

                # Mechanical OR Project OR Process
                if self.keywords and not any(
                    keyword in title.casefold()
                    for keyword in self.keywords
                ):
                    continue

                job_url = (
                    f"{self.host}/hcmUI/"
                    f"CandidateExperience/en/sites/"
                    f"{self.site}/job/{job_id}"
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

            if len(page_jobs) < limit:
                break

            offset += limit

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )