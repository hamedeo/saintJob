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


class SiemensSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config.get(
            "name",
            "Siemens Careers",
        )
        self.company = config.get(
            "company",
            "Siemens",
        )

        self.url = config["url"]

        self.keywords = [
            keyword.strip().casefold()
            for keyword in config.get("keywords", [])
            if keyword.strip()
        ]

        self.page_size = int(
            config.get("page_size", 6)
        )

        self.max_pages = int(
            config.get("max_pages", 100)
        )

        self.timeout_ms = int(
            config.get("timeout_ms", 45000)
        )

    def fetch_jobs(self) -> list[Job]:
        jobs: dict[str, Job] = {}

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
                offset = 0
                page_number = 0
                total_results = None

                while page_number < self.max_pages:
                    page_url = self._build_page_url(
                        offset
                    )

                    page.goto(
                        page_url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )

                    try:
                        page.wait_for_selector(
                            'a[href*="/externaljobs/JobDetail/"]',
                            timeout=self.timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        if offset == 0:
                            raise RuntimeError(
                                "Siemens loaded, but no job "
                                "links were rendered."
                            )

                        break

                    # Give Siemens JavaScript time to finish
                    # rendering the current result batch.
                    page.wait_for_timeout(1500)

                    if total_results is None:
                        total_results = (
                            self._extract_total_results(
                                page
                            )
                        )

                        if total_results is not None:
                            print(
                                f"Siemens search contains "
                                f"{total_results} total results"
                            )

                    raw_jobs = self._extract_dom_jobs(
                        page
                    )

                    if not raw_jobs:
                        break

                    for raw_job in raw_jobs:
                        job_id = raw_job.get(
                            "job_id",
                            "",
                        ).strip()

                        title = raw_job.get(
                            "title",
                            "",
                        ).strip()

                        href = raw_job.get(
                            "href",
                            "",
                        ).strip()

                        location = raw_job.get(
                            "location",
                            "",
                        ).strip()

                        if (
                            not job_id
                            or not title
                            or not href
                        ):
                            continue

                        # Relevant title keywords:
                        # mechanical OR project OR CFD etc.
                        if self.keywords and not any(
                            keyword in title.casefold()
                            for keyword in self.keywords
                        ):
                            continue

                        job_url = urljoin(
                            page_url,
                            href,
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

                    page_number += 1
                    offset += self.page_size

                    if (
                        total_results is not None
                        and offset >= total_results
                    ):
                        break

            finally:
                browser.close()

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    @staticmethod
    def _extract_dom_jobs(page) -> list[dict]:
        """
        Extract Siemens result cards directly from the
        rendered DOM.

        We locate every JobDetail link and walk upward
        through its HTML ancestors until we find the
        container containing that vacancy's Job ID.
        """

        return page.evaluate(
            """
            () => {
                const result = new Map();

                const links = Array.from(
                    document.querySelectorAll(
                        'a[href*="/externaljobs/JobDetail/"]'
                    )
                );

                for (const link of links) {
                    const href =
                        link.getAttribute("href") || "";

                    const idMatch = href.match(
                        /\\/JobDetail\\/(\\d+)/i
                    );

                    if (!idMatch) {
                        continue;
                    }

                    const jobId = idMatch[1];

                    let current = link;

                    for (
                        let level = 0;
                        level < 15 && current;
                        level++
                    ) {
                        const text = (
                            current.innerText ||
                            current.textContent ||
                            ""
                        )
                            .replace(/\\s+/g, " ")
                            .trim();

                        const exactJobId =
                            new RegExp(
                                "Job\\\\s*ID\\\\s*:\\\\s*" +
                                jobId +
                                "\\\\b",
                                "i"
                            );

                        if (exactJobId.test(text)) {
                            const headings =
                                Array.from(
                                    current.querySelectorAll(
                                        "h1, h2, h3, h4, h5"
                                    )
                                );

                            let title = "";

                            for (
                                const heading
                                of headings
                            ) {
                                const value = (
                                    heading.innerText ||
                                    heading.textContent ||
                                    ""
                                )
                                    .replace(/\\s+/g, " ")
                                    .trim();

                                if (
                                    value &&
                                    ![
                                        "open jobs",
                                        "jobs",
                                        "search jobs"
                                    ].includes(
                                        value.toLowerCase()
                                    )
                                ) {
                                    title = value;
                                    break;
                                }
                            }

                            // Fallback if Siemens does
                            // not use a heading element.
                            if (!title) {
                                const detailLinks =
                                    Array.from(
                                        current.querySelectorAll(
                                            'a[href*="/externaljobs/JobDetail/"]'
                                        )
                                    );

                                for (
                                    const item
                                    of detailLinks
                                ) {
                                    const value = (
                                        item.innerText ||
                                        item.textContent ||
                                        ""
                                    )
                                        .replace(/\\s+/g, " ")
                                        .trim();

                                    if (
                                        value &&
                                        ![
                                            "learn more",
                                            "apply",
                                            "view job"
                                        ].includes(
                                            value.toLowerCase()
                                        )
                                    ) {
                                        title = value;
                                        break;
                                    }
                                }
                            }

                            /*
                            Siemens cards look like:

                            CFD Software Developer
                            Multiple Locations
                            • Job ID: 508065
                            • Research & Development
                            */

                            let location = "";

                            const beforeId =
                                text.split(
                                    new RegExp(
                                        "Job\\\\s*ID\\\\s*:\\\\s*" +
                                        jobId,
                                        "i"
                                    )
                                )[0] || "";

                            if (
                                /Multiple Locations/i.test(
                                    beforeId
                                )
                            ) {
                                location =
                                    "Multiple Locations";
                            } else {
                                /*
                                Try Siemens elements whose
                                class refers to location.
                                */
                                const locationElement =
                                    current.querySelector(
                                        '[class*="location" i]'
                                    );

                                if (locationElement) {
                                    location = (
                                        locationElement
                                            .innerText ||
                                        locationElement
                                            .textContent ||
                                        ""
                                    )
                                        .replace(/\\s+/g, " ")
                                        .trim();
                                }
                            }

                            if (title) {
                                result.set(
                                    jobId,
                                    {
                                        job_id: jobId,
                                        title: title,
                                        href: href,
                                        location: location
                                    }
                                );

                                break;
                            }
                        }

                        current =
                            current.parentElement;
                    }
                }

                return Array.from(
                    result.values()
                );
            }
            """
        )

    @staticmethod
    def _extract_total_results(
        page,
    ) -> int | None:
        text = " ".join(
            page.locator("body")
            .inner_text()
            .split()
        )

        # Siemens displays:
        # 55 - 60 of 130 results
        match = re.search(
            r"\bof\s+([\d,]+)\s+results\b",
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            return None

        try:
            return int(
                match.group(1).replace(
                    ",",
                    "",
                )
            )
        except ValueError:
            return None

    def _build_page_url(
        self,
        offset: int,
    ) -> str:
        parsed = urlparse(
            self.url
        )

        query = parse_qs(
            parsed.query,
            keep_blank_values=True,
        )

        # Ignore whatever offset was copied
        # from the browser.
        query["folderOffset"] = [
            str(offset)
        ]

        query["folderRecordsPerPage"] = [
            str(self.page_size)
        ]

        return urlunparse(
            parsed._replace(
                query=urlencode(
                    query,
                    doseq=True,
                )
            )
        )