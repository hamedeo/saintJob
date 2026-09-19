import os
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.models import Job
from src.sources.base import JobSource


class HiltiSource(JobSource):
    def __init__(self, config: dict):
        self.source_id = config["id"]
        self.source_name = config["name"]
        self.company = config.get(
            "company",
            "Hilti",
        )

        self.url = config["url"]

        self.keywords = [
            value.strip().casefold()
            for value in config.get(
                "keywords",
                [],
            )
            if value.strip()
        ]

        self.timeout_ms = int(
            config.get(
                "timeout_ms",
                30000,
            )
        )

        self.cloudflare_wait_seconds = int(
            config.get(
                "cloudflare_wait_seconds",
                120,
            )
        )

        self.profile_dir = Path(
            config.get(
                "profile_dir",
                "data/hilti-browser-profile",
            )
        )

    def fetch_jobs(self) -> list[Job]:
        # Hilti uses Cloudflare verification.
        # A GitHub Actions runner will not have
        # the locally verified browser session.
        if os.getenv("GITHUB_ACTIONS") == "true":
            print(
                "Hilti skipped: requires a "
                "verified local browser session."
            )
            return []

        self.profile_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        jobs: dict[str, Job] = {}

        with sync_playwright() as p:
            context = (
                p.chromium.launch_persistent_context(
                    user_data_dir=str(
                        self.profile_dir
                    ),
                    headless=False,
                    viewport={
                        "width": 1440,
                        "height": 1000,
                    },
                )
            )

            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

            try:
                print(
                    "Hilti: opening filtered jobs page..."
                )

                try:
                    page.goto(
                        self.url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )

                except PlaywrightTimeoutError:
                    pass

                # ---------------------------------
                # Cloudflare verification
                # ---------------------------------

                if self._is_cloudflare(page):
                    print(
                        "Hilti: complete Cloudflare "
                        "verification in the browser."
                    )

                    verified = False

                    for _ in range(
                        self.cloudflare_wait_seconds
                    ):
                        page.wait_for_timeout(1000)

                        if not self._is_cloudflare(
                            page
                        ):
                            verified = True
                            break

                    if not verified:
                        print(
                            "Hilti: Cloudflare verification "
                            "not completed."
                        )
                        return []

                    # Re-open exact filtered URL after
                    # Cloudflare has accepted the session.
                    try:
                        page.goto(
                            self.url,
                            wait_until="domcontentloaded",
                            timeout=self.timeout_ms,
                        )

                    except PlaywrightTimeoutError:
                        pass

                # Let Hilti finish rendering results.
                page.wait_for_timeout(3000)

                print(
                    f"Hilti page: {page.title()}"
                )

                # ---------------------------------
                # Extract rendered job cards
                # ---------------------------------

                raw_jobs = page.evaluate(
                    """
                    () => {
                        const results = new Map();

                        const links = Array.from(
                            document.querySelectorAll(
                                'a[href]'
                            )
                        );

                        for (const link of links) {
                            const href =
                                link.getAttribute("href") || "";

                            const match = href.match(
                                /\\/jobs\\/(\\d+)-[a-z]{2}\\//i
                            );

                            if (!match) {
                                continue;
                            }

                            const jobId = match[1];

                            let card = link;
                            let cardText = "";

                            for (
                                let level = 0;
                                level < 10 && card;
                                level++
                            ) {
                                const text = (
                                    card.innerText || ""
                                )
                                    .replace(/\\s+/g, " ")
                                    .trim();

                                const isNetherlands =
                                    /The Netherlands|Nederland/i
                                        .test(text);

                                const isEngineering =
                                    /Engineering|Research & Development/i
                                        .test(text);

                                if (
                                    isNetherlands
                                    && isEngineering
                                ) {
                                    cardText = (
                                        card.innerText || ""
                                    );

                                    break;
                                }

                                card =
                                    card.parentElement;
                            }

                            if (!cardText) {
                                continue;
                            }

                            let title = (
                                link.innerText ||
                                link.textContent ||
                                ""
                            )
                                .replace(/\\s+/g, " ")
                                .trim();

                            if (
                                !title
                                || title.length > 200
                            ) {
                                const heading =
                                    card.querySelector(
                                        "h1, h2, h3, h4, h5"
                                    );

                                if (heading) {
                                    title = (
                                        heading.innerText ||
                                        heading.textContent ||
                                        ""
                                    )
                                        .replace(/\\s+/g, " ")
                                        .trim();
                                }
                            }

                            if (!title) {
                                continue;
                            }

                            results.set(
                                jobId,
                                {
                                    job_id: jobId,
                                    title: title,
                                    href: href,
                                    text: cardText
                                }
                            );
                        }

                        return Array.from(
                            results.values()
                        );
                    }
                    """
                )

                print(
                    f"Hilti: {len(raw_jobs)} "
                    "filtered cards found"
                )

                # ---------------------------------
                # Convert to Job objects
                # ---------------------------------

                for raw in raw_jobs:
                    job_id = str(
                        raw.get(
                            "job_id",
                            "",
                        )
                    ).strip()

                    title = " ".join(
                        str(
                            raw.get(
                                "title",
                                "",
                            )
                        ).split()
                    )

                    href = str(
                        raw.get(
                            "href",
                            "",
                        )
                    ).strip()

                    card_text = str(
                        raw.get(
                            "text",
                            "",
                        )
                    )

                    if (
                        not job_id
                        or not title
                        or not href
                    ):
                        continue

                    # Optional title filter.
                    # Leave keywords empty to accept
                    # everything selected by Hilti's URL.
                    if self.keywords and not any(
                        keyword in title.casefold()
                        for keyword in self.keywords
                    ):
                        continue

                    location = self._location(
                        card_text
                    )

                    jobs[job_id] = Job(
                        source_id=self.source_id,
                        source_name=self.source_name,
                        job_id=job_id,
                        title=title,
                        url=urljoin(
                            "https://careers.hilti.group",
                            href,
                        ),
                        company=self.company,
                        location=location,
                    )

            finally:
                context.close()

        return sorted(
            jobs.values(),
            key=lambda job: job.title.casefold(),
        )

    @staticmethod
    def _location(
        text: str,
    ) -> str:
        """
        Hilti card example:

        Design Engineer
        Save
        Berkel en Rodenrijs,
        South Holland,
        The Netherlands
        Engineering
        """

        text = " ".join(
            text.split()
        )

        match = re.search(
            r"\bSave\s+"
            r"(.+?,\s*.+?,\s*The Netherlands)\b",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return " ".join(
                match.group(1).split()
            )

        # Fallback if the Save label changes.
        match = re.search(
            r"([A-Za-zÀ-ÿ .'’\-]+,\s*"
            r"[A-Za-zÀ-ÿ .'’\-]+,\s*"
            r"The Netherlands)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            location = " ".join(
                match.group(1).split()
            )

            # Remove possible title text before Save.
            location = re.sub(
                r"^.*?\bSave\s+",
                "",
                location,
                flags=re.IGNORECASE,
            )

            return location.strip()

        return "The Netherlands"

    @staticmethod
    def _is_cloudflare(
        page,
    ) -> bool:
        try:
            title = (
                page.title()
                .casefold()
            )

            body = (
                page.locator("body")
                .inner_text(
                    timeout=3000
                )
                .casefold()
            )

        except Exception:
            return False

        return (
            "just a moment" in title
            or
            "performing security verification"
            in body
            or
            "verify you are human"
            in body
        )