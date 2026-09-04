import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import Job
from src.sources.base import JobSource


class VarbiSource(JobSource):
    def __init__(self, config):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.url = config["url"]
        self.department = config.get("department", "").casefold()

    def fetch_jobs(self):
        response = requests.get(
            self.url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        jobs = {}

        for link in soup.select("a[href]"):
            href = link.get("href", "")

            if "/what:job/" not in href:
                continue

            row = link.find_parent("tr")
            if not row:
                continue

            text = " ".join(row.get_text(" ", strip=True).split())

            if self.department and self.department not in text.casefold():
                continue

            title = " ".join(link.get_text(" ", strip=True).split())

            job_url = urljoin(self.url, href)

            match = re.search(r"/what:job/jobID:(\d+)", href)
            job_id = match.group(1) if match else job_url

            jobs[job_id] = Job(
                source_id=self.source_id,
                source_name=self.source_name,
                job_id=job_id,
                title=title,
                url=job_url,
                company=self.company,
                location="Eindhoven",
            )

        return list(jobs.values())