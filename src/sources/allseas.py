import re
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from src.models import Job
from src.sources.base import JobSource


class AllseasSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get("company", "Allseas")
        self.url = config["url"]

        self.keywords = [
            keyword.casefold()
            for keyword in config.get("keywords", [])
        ]

        self.timeout_ms = int(
            config.get("timeout_ms", 20000)
        )

    def fetch_jobs(self) -> list[Job]:
        jobs = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True
            )

            page = browser.new_page()

            try:
                page.goto(
                    self.url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )

                page.wait_for_timeout(3000)

                vacancies = page.evaluate(
                    """
                    () => {
                        const results = [];
                        const seen = new Set();

                        const links = Array.from(
                            document.querySelectorAll(
                                'a[href*="/careers/vacancy/"]'
                            )
                        );

                        for (const link of links) {
                            const href =
                                link.getAttribute("href") || "";

                            if (seen.has(href)) {
                                continue;
                            }

                            seen.add(href);

                            let card = link;

                            for (
                                let i = 0;
                                i < 8 && card;
                                i++
                            ) {
                                const text =
                                    card.innerText || "";

                                if (
                                    text.includes(
                                        "Field of Expertise:"
                                    ) &&
                                    text.includes(
                                        "Location:"
                                    )
                                ) {
                                    break;
                                }

                                card = card.parentElement;
                            }

                            if (!card) {
                                continue;
                            }

                            results.push({
                                href: href,
                                text: (
                                    card.innerText || ""
                                )
                            });
                        }

                        return results;
                    }
                    """
                )

                for vacancy in vacancies:
                    href = vacancy["href"]

                    text = " ".join(
                        vacancy["text"].split()
                    )

                    match = re.search(
                        r"/careers/vacancy/(\d+)/",
                        href,
                        flags=re.IGNORECASE,
                    )

                    if not match:
                        continue

                    job_id = match.group(1)

                    # Only Design & Engineering
                    expertise = self._field(
                        text,
                        "Field of Expertise",
                        "Category",
                    )

                    if (
                        expertise.casefold()
                        != "design & engineering"
                    ):
                        continue

                    title = self._title(text)

                    if not title:
                        continue

                    # Mechanical OR Project OR Process
                    if self.keywords and not any(
                        keyword in title.casefold()
                        for keyword in self.keywords
                    ):
                        continue

                    location = self._field(
                        text,
                        "Location",
                        "Read more",
                    )

                    jobs[job_id] = Job(
                        source_id=self.source_id,
                        source_name=self.source_name,
                        job_id=job_id,
                        title=title,
                        url=urljoin(
                            self.url,
                            href,
                        ),
                        company=self.company,
                        location=location,
                    )

            finally:
                browser.close()

        return list(jobs.values())

    @staticmethod
    def _title(text: str) -> str:
        if "Field of Expertise:" not in text:
            return ""

        return (
            text.split(
                "Field of Expertise:",
                1,
            )[0]
            .strip()
        )

    @staticmethod
    def _field(
        text: str,
        start: str,
        end: str,
    ) -> str:
        pattern = (
            rf"{re.escape(start)}:\s*"
            rf"(.*?)"
            rf"(?={re.escape(end)}:|"
            rf"{re.escape(end)}|$)"
        )

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            return ""

        return " ".join(
            match.group(1).split()
        ).strip()