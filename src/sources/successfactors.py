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


class SuccessfactorsSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config["company"]
        self.url = config["url"]

        self.keywords = [
            keyword.strip().casefold()
            for keyword in config.get("keywords", [])
            if keyword.strip()
        ]

        self.max_pages = int(
            config.get("max_pages", 30)
        )

        self.timeout_ms = int(
            config.get("timeout_ms", 45000)
        )

        self.default_location = config.get(
            "default_location",
            "",
        )

    def fetch_jobs(self) -> list[Job]:
        jobs: dict[str, Job] = {}
        seen_page_ids: set[str] = set()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True
            )

            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/127.0 Safari/537.36"
                )
            )

            try:
                for page_number in range(
                    self.max_pages
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
                            'a[href*="/job/"]',
                            timeout=self.timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        if page_number == 0:
                            raise RuntimeError(
                                "SuccessFactors loaded, "
                                "but no job links appeared."
                            )

                        break

                    page.wait_for_timeout(1000)

                    raw_jobs = page.evaluate(
                        """
                        () => {
                            const results = [];
                            const seen = new Set();

                            const links = Array.from(
                                document.querySelectorAll(
                                    'a[href*="/job/"]'
                                )
                            );

                            for (const link of links) {
                                const href =
                                    link.getAttribute("href") || "";

                                const match = href.match(
                                    /\\/job\\/[^/]+\\/(\\d+)-[a-z]{2}_[A-Z]{2}\\/?/i
                                );

                                if (!match) {
                                    continue;
                                }

                                const jobId = match[1];

                                if (seen.has(jobId)) {
                                    continue;
                                }

                                let title = (
                                    link.innerText ||
                                    link.textContent ||
                                    ""
                                )
                                    .replace(/\\s+/g, " ")
                                    .trim();

                                let current = link;

                                for (
                                    let level = 0;
                                    level < 8 && current;
                                    level++
                                ) {
                                    const heading =
                                        current.querySelector(
                                            "h1, h2, h3, h4, h5"
                                        );

                                    if (heading) {
                                        const value = (
                                            heading.innerText ||
                                            heading.textContent ||
                                            ""
                                        )
                                            .replace(/\\s+/g, " ")
                                            .trim();

                                        if (value) {
                                            title = value;
                                            break;
                                        }
                                    }

                                    current =
                                        current.parentElement;
                                }

                                if (!title) {
                                    continue;
                                }

                                seen.add(jobId);

                                results.push({
                                    job_id: jobId,
                                    title: title,
                                    href: href
                                });
                            }

                            return results;
                        }
                        """
                    )

                    page_ids: set[str] = set()

                    for raw_job in raw_jobs:
                        job_id = str(
                            raw_job.get("job_id", "")
                        ).strip()

                        title = str(
                            raw_job.get("title", "")
                        ).strip()

                        href = str(
                            raw_job.get("href", "")
                        ).strip()

                        if (
                            not job_id
                            or not title
                            or not href
                        ):
                            continue

                        page_ids.add(job_id)

                        if self.keywords and not any(
                            keyword in title.casefold()
                            for keyword in self.keywords
                        ):
                            continue

                        jobs[job_id] = Job(
                            source_id=self.source_id,
                            source_name=self.source_name,
                            job_id=job_id,
                            title=title,
                            url=urljoin(
                                page_url,
                                href,
                            ),
                            company=self.company,
                            location=self.default_location,
                        )

                    if not page_ids:
                        break

                    if page_ids.issubset(
                        seen_page_ids
                    ):
                        break

                    seen_page_ids.update(
                        page_ids
                    )

            finally:
                browser.close()

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

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

        query["pageNumber"] = [
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