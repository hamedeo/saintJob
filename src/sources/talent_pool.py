import re
from urllib.parse import (
    parse_qs,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.models import Job
from src.sources.base import JobSource


class TalentPoolSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "Philips")
        self.url = config["url"]

        self.keywords = [
            keyword.strip().casefold()
            for keyword in config.get("keywords", [])
            if keyword.strip()
        ]

        self.max_pages = int(
            config.get("max_pages", 20)
        )

        self.timeout_ms = int(
            config.get("timeout_ms", 45000)
        )

    def fetch_jobs(self) -> list[Job]:
        jobs: dict[str, Job] = {}
        seen_ids: set[str] = set()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True
            )

            page = browser.new_page(
                viewport={
                    "width": 1440,
                    "height": 1200,
                },
                user_agent=(
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/127.0 Safari/537.36"
                ),
            )

            try:
                for page_number in range(
                    1,
                    self.max_pages + 1,
                ):
                    page_url = self._page_url(
                        page_number
                    )

                    page.goto(
                        page_url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )

                    try:
                        page.wait_for_selector(
                            'a[href*="/projects/"]',
                            timeout=self.timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        if page_number == 1:
                            raise RuntimeError(
                                "Philips loaded, but no "
                                "project links appeared."
                            )

                        break

                    page.wait_for_timeout(1000)

                    raw_jobs = page.evaluate(
                        """
                        () => {
                            const results = [];

                            const links = Array.from(
                                document.querySelectorAll(
                                    'a[href*="/projects/"]'
                                )
                            );

                            for (const link of links) {
                                const href =
                                    link.getAttribute("href") || "";

                                if (
                                    !/\\/projects\\/[^/]+\\/\\d+\\/?(?:\\?.*)?$/i
                                        .test(href)
                                ) {
                                    continue;
                                }

                                let text = (
                                    link.innerText ||
                                    link.textContent ||
                                    ""
                                )
                                    .replace(/\\s+/g, " ")
                                    .trim();

                                /*
                                Sometimes the anchor itself
                                contains little text, so walk
                                upward to the project card.
                                */
                                if (!text || text.length < 10) {
                                    let parent = link.parentElement;

                                    for (
                                        let level = 0;
                                        level < 6 && parent;
                                        level++
                                    ) {
                                        const parentText = (
                                            parent.innerText ||
                                            parent.textContent ||
                                            ""
                                        )
                                            .replace(/\\s+/g, " ")
                                            .trim();

                                        if (
                                            /Project posted:/i.test(
                                                parentText
                                            )
                                        ) {
                                            text = parentText;
                                            break;
                                        }

                                        parent =
                                            parent.parentElement;
                                    }
                                }

                                results.push({
                                    href,
                                    text
                                });
                            }

                            return results;
                        }
                        """
                    )

                    page_ids: set[str] = set()

                    for raw_job in raw_jobs:
                        href = raw_job.get(
                            "href",
                            "",
                        ).strip()

                        text = raw_job.get(
                            "text",
                            "",
                        ).strip()

                        if not href or not text:
                            continue

                        job_url = urljoin(
                            page_url,
                            href,
                        )

                        path = urlparse(
                            job_url
                        ).path.rstrip("/")

                        match = re.search(
                            r"/projects/([^/]+)/(\d+)$",
                            path,
                            flags=re.IGNORECASE,
                        )

                        if not match:
                            continue

                        job_id = match.group(2)
                        page_ids.add(job_id)

                        title = self._extract_title(
                            text
                        )

                        if not title:
                            continue

                        if self.keywords and not any(
                            keyword in title.casefold()
                            for keyword in self.keywords
                        ):
                            continue

                        location = (
                            self._extract_location(
                                text
                            )
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

                    if not page_ids:
                        break

                    if page_ids.issubset(
                        seen_ids
                    ):
                        break

                    seen_ids.update(
                        page_ids
                    )

            finally:
                browser.close()

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    @staticmethod
    def _extract_title(
        text: str,
    ) -> str:
        """
        Example card:

        Mechanical Development Engineer
        Eindhoven, NL (Hybrid)
        Project posted: ...
        """

        match = re.search(
            r"^(.*?)\s+"
            r"(Amsterdam|Best|Drachten|Ede|Eindhoven|Leusden)"
            r",\s*NL\b",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return " ".join(
                match.group(1).split()
            )

        return ""

    @staticmethod
    def _extract_location(
        text: str,
    ) -> str:
        match = re.search(
            r"\b("
            r"Amsterdam|Best|Drachten|Ede|Eindhoven|Leusden"
            r"),\s*NL\b",
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            return ""

        city = match.group(1)

        return f"{city}, NL"

    def _page_url(
        self,
        page_number: int,
    ) -> str:
        parsed = urlparse(
            self.url
        )

        query = parse_qs(
            parsed.query,
            keep_blank_values=True,
        )

        query["page"] = [
            str(page_number)
        ]

        return urlunparse(
            parsed._replace(
                query=urlencode(
                    query,
                    doseq=True,
                )
            )
        )