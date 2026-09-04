import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class UtwenteSource(JobSource):
    def __init__(self, config):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.url = config["url"]

        self.keywords = [
            x.casefold()
            for x in config.get("keywords", [])
        ]

    def fetch_jobs(self):
        response = requests.get(
            self.url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        jobs = {}

        for link in soup.select('a[href*="/en/vacancies/"]'):
            href = link.get("href", "")

            match = re.search(
                r"/en/vacancies/(\d+)/",
                href,
            )

            if not match:
                continue

            title_element = link.find(["h3", "h4"])

            title = (
                title_element.get_text(" ", strip=True)
                if title_element
                else link.get_text(" ", strip=True)
            )

            title = " ".join(title.split())

            if self.keywords and not any(
                keyword in title.casefold()
                for keyword in self.keywords
            ):
                continue

            job_id = match.group(1)

            jobs[job_id] = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=job_id,
                title=title,
                url=urljoin(self.url, href),
                company=self.company,
                location="Enschede",
            )

        return list(jobs.values())