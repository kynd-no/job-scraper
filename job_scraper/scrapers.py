import os
from playwright.async_api import Browser, Page, async_playwright
from abc import ABC, abstractmethod
from typing import List

from models import Job, JobOverview


class JobScraper(ABC):

    def __init__(self): ...

    @abstractmethod
    async def scrape_jobs(self) -> List[Job]: ...


class FolqScraper(JobScraper):
    BASE_URL = "https://app.folq.com"
    job_platform: str = "Folq"

    def __init__(self):
        self.username = os.getenv("FOLQ_USERNAME")
        self.password = os.getenv("FOLQ_PASSWORD")

        if not self.username or not self.password:
            raise ValueError(
                "Missing FOLQ_USERNAME or FOLQ_PASSWORD environment variables. Check .env"
            )

    async def _login(self, page: Page) -> None:
        await page.goto("https://app.folq.com/login")
        await page.fill("input[type='email']", self.username)
        await page.fill("input[type='password']", self.password)
        await page.click("button[type='submit']")
        # Folq redirect is slow
        await page.wait_for_timeout(5000)

    async def scrape_jobs(self) -> List[Job]:
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch()
            page: Page = await browser.new_page()
            await self._login(page)
            job_overviews: List[JobOverview] = await self._parse_job_overview(page)

            jobs: List[Job] = await self._traverse_job_pages(page, job_overviews)

            await browser.close()
            return jobs

    async def _traverse_job_pages(
        self, page: Page, job_overviews: List[JobOverview]
    ) -> List[Job]:
        jobs: List[Job] = []

        for job_overview in job_overviews:
            await page.goto(
                job_overview.job_uri,
                wait_until="networkidle",
            )

            description_el = await page.query_selector(
                'div[class="hc spacing-8-8 s c wf ct cl"]'
            )
            description_text = await description_el.text_content()

            jobs.append(
                Job(
                    job_overview=job_overview,
                    description=description_text,
                    platform=self.job_platform,
                )
            )

        return jobs

    async def _parse_job_overview(self, page: Page) -> List[JobOverview]:
        await page.goto(
            f"{self.BASE_URL}/assignments/all?sorting=by-deadline",
            wait_until="domcontentloaded",
        )

        # Filter on jobs in Norway
        await page.select_option(
            '//*[@id="main-content"]/div/div[2]/div/div[2]/div/div[1]/div[1]/div[2]/div[2]/select',
            "norge",
        )

        job_list_el = await page.query_selector_all(
            '//*[@id="main-content"]/div/div[2]/div/div[2]/div/div[2]/div'
        )

        jobs: List[JobOverview] = []
        for job_listing in job_list_el:
            job_title_and_href_el = await job_listing.query_selector("a")
            job_href = await job_title_and_href_el.get_attribute("href")

            job_title = await job_title_and_href_el.text_content()

            company = await job_listing.query_selector(
                'div[class="spacing-5-5 font-size-14 ff-helvetica-neuehelveticaarialsans-serif fc-60-60-60-255 w3 s p wf"]'
            )

            company_text = await company.text_content()

            due_date_el = await job_listing.query_selector(
                'div[class="hc cptr fc-66-156-218-255 s e wf ccx ccy sbt notxt focusable"]'
            )
            due_date_text = (
                await due_date_el.text_content() if due_date_el else "Snarest"
            )

            jobs.append(
                JobOverview(
                    title=job_title,
                    job_uri=self.BASE_URL + job_href,
                    company=company_text,
                    delivery_date=due_date_text,
                )
            )

        return jobs


class VeramaScraper(JobScraper):
    BASE_URL = "https://app.verama.com/app"
    job_platform: str = "Verama"

    def __init__(self):
        self.username = os.getenv("VERAMA_USERNAME")
        self.password = os.getenv("VERAMA_PASSWORD")

        if not self.username or not self.password:
            raise ValueError(
                "Missing VERAMA_USERNAME or VERAMA_PASSWORD environment variables. Check .env"
            )

    async def _login(self, page: Page) -> None:
        await page.goto("https://app.verama.com/auth?tab=login")
        await page.fill("input[name='username']", self.username)
        await page.fill("input[name='password']", self.password)
        await page.get_by_role("button", name="Log in").click()

    async def scrape_jobs(self) -> List[Job]:
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch()
            page: Page = await browser.new_page()
            await self._login(page)
            job_overviews: List[JobOverview] = await self._parse_job_overview(
                page
            )

            jobs: List[Job] = await self._traverse_job_pages(
                page, job_overviews
            )

            await browser.close()
            return jobs

    async def _traverse_job_pages(
        self, page: Page, job_overviews: List[JobOverview]
    ) -> List[Job]:
        jobs: List[Job] = []
        for job_overview in job_overviews:
            await page.goto(
                job_overview.job_uri,
                wait_until="domcontentloaded",
            )
            deadline_locator = page.locator(
                "//span[text()='Application deadline']/following-sibling::span[1]"
            )

            deadline_text = await deadline_locator.inner_text()
            deadline = deadline_text.split("(")[0].strip()
            job_overview.delivery_date = deadline

            company_locator = page.locator(
                "//span[text()='Client']/following-sibling::span[1]"
            )
            company = await company_locator.text_content()
            job_overview.company = company

            assignment_description_locator = await page.query_selector(
                "div.job-request-detail__section"
            )
            description = await assignment_description_locator.text_content()

            jobs.append(
                Job(
                    job_overview=job_overview,
                    description=description,
                    platform=self.job_platform,
                )
            )

        return jobs

    async def _parse_job_overview(self, page: Page) -> List[JobOverview]:
        # https://app.verama.com/app/job-requests
        await page.goto(
            f"{self.BASE_URL}/job-requests?page=0&size=20&sortConfig=%5B%7B%22sortBy%22%3A%22firstDayOfApplications%22%2C%22order%22%3A%22DESC%22%7D%5D&filtersConfig=%7B%22location%22%3A%7B%22id%22%3Anull%2C%22signature%22%3A%22%22%2C%22city%22%3A%22Oslo%22%2C%22country%22%3A%22Norway%22%2C%22name%22%3A%22Oslo%2C%20Norway%22%2C%22locationId%22%3A%22here%3Acm%3Anamedplace%3A20421988%22%2C%22countryCode%22%3A%22NOR%22%2C%22suggestedPhoneCode%22%3A%22NO%22%7D%2C%22remote%22%3A%5B%5D%2C%22query%22%3A%22%22%2C%22skillRoleCategories%22%3A%5B%5D%2C%22frequency%22%3A%22DAILY%22%2C%22radius%22%3A20000%2C%22dedicated%22%3Afalse%2C%22originIds%22%3A%5B%5D%2C%22favouritesOnly%22%3Afalse%2C%22recommendedOnly%22%3Afalse%2C%22languages%22%3A%5B%5D%2C%22level%22%3A%5B%5D%2C%22skillIds%22%3A%5B%5D%2C%22skills%22%3A%5B%5D%7D",
            wait_until="networkidle",
        )

        job_sections = await page.query_selector_all('a[class="route-section"]')

        if not job_sections:
            print("Could not find any job listings")
            return []

        jobs: List[JobOverview] = []
        for job_section in job_sections:
            job_uri = await job_section.get_attribute("href")

            job_title_el = await job_section.query_selector(
                "span.job-request-record__header"
            )
            job_title = await job_title_el.text_content()

            jobs.append(
                JobOverview(title=job_title, job_uri=self.BASE_URL + job_uri)
            )

        print(f"Found {len(jobs)} jobs")
        return jobs


class MercellScraper(JobScraper):
    BASE_URL = "https://my.mercell.com"
    job_platform: str = "Mercell"

    def __init__(self) -> None:
        self.username = os.getenv("MERCELL_USERNAME")
        self.password = os.getenv("MERCELL_PASSWORD")

        if not self.username or not self.password:
            raise ValueError(
                "Missing MERCELL_USERNAME or MERCELL_PASSWORD in environment"
            )

    async def scrape_jobs(self) -> List[Job]:
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch()
            page: Page = await browser.new_page()
            await self._login(page)
            job_overviews: List[JobOverview] = await self._parse_job_overview(
                page
            )

            jobs: List[Job] = await self._traverse_job_pages(
                page, job_overviews
            )

            await browser.close()

            return jobs

    async def _login(self, page: Page) -> None:
        await page.goto(self.BASE_URL + "/en/m/logon/default.aspx?auth0done=true")
        await page.get_by_role("textbox").fill(self.username)
        await page.get_by_text("Continue").click()
        await page.locator('//*[@id="password"]').fill(self.password)
        await page.get_by_role("button", name="Continue").click()

    async def _parse_job_overview(self, page: Page) -> List[JobOverview]:
        for attempt in range(3):
            try:
                await page.goto(
                    f"{self.BASE_URL}/m/mts/MyTenders.aspx", wait_until="networkidle"
                )
                break
            except TimeoutError as e:
                print(f"Timeout error: {e} (attempt {attempt+1}/3)")
        else:
            raise TimeoutError("Cannot load MyTenders.aspx after 3 attempts")

        jobs: List[JobOverview] = []
        nxt_button_selector = 'a[class="nxt"]'
        while True:
            jobs.extend(await self._parse_job_overview_table(page))

            if await page.is_visible(nxt_button_selector, strict=True):
                await page.click(nxt_button_selector)
                await page.wait_for_timeout(2000)
            else:
                # No more pages
                break

        print(f"Found {len(jobs)} jobs")
        return jobs

    async def _parse_job_overview_table(self, page: Page) -> List[JobOverview]:
        """
        Parses each <tr> in the table's <tbody>, extracting the job data
        from known columns. Returns a list of JobOverview.
        """

        table_selector = "#ctl00_ctl00_commonContent_mainContent_ucTenderList_gwTenders_GridViewTop_GridView"
        table = await page.query_selector(table_selector)
        if not table:
            print("Could not find the table on this page.")
            return []

        # Get all <tr> inside <tbody>
        rows = await table.query_selector_all("tbody > tr")
        results: List[JobOverview] = []

        for row in rows:
            # Skip header rows if they contain <th>
            th_cells = await row.query_selector_all("th")
            if th_cells:
                continue

            # Some rows might be a "pager" or other control row with no data
            # So skip if it does not have 'roworder'
            roworder = await row.get_attribute("roworder")
            if roworder is None:
                continue

            # Grab all <td> in the row
            tds = await row.query_selector_all("td")
            if len(tds) < 7:
                # Not enough columns to parse the data we need
                continue

            # 1) The main column with link and company: column index 4
            main_col = tds[4]
            # - The "title" link is the <a class="hide100pct">
            title_a = await main_col.query_selector("a.hide100pct")
            title_text = ""
            job_href = ""
            if title_a:
                title_text = (await title_a.inner_text() or "").strip()
                job_href = await title_a.get_attribute("href") or ""

            # - The "company" link is the <a class="company-in-grid">
            company_a = await main_col.query_selector("a.company-in-grid")
            company_text = ""
            if company_a:
                # The text inside <a> might contain an icon <svg> plus the name,
                # so we might just do .inner_text() and strip it
                company_text = (await company_a.inner_text() or "").strip()

            # 3) Delivery date: column index 5
            date_el = tds[5]
            delivery_date = (await date_el.inner_text() or "").strip()

            results.append(
                JobOverview(
                    title=title_text,
                    company=company_text,
                    description="",  # or parse from tooltip if needed
                    delivery_date=delivery_date,
                    job_uri=self.BASE_URL + job_href,
                )
            )

        return results

    async def _traverse_job_pages(
        self, page: Page, job_overviews: List[JobOverview]
    ) -> List[Job]:
        jobs: List[Job] = []
        for job_overview in job_overviews:
            await page.goto(
                job_overview.job_uri,
                wait_until="domcontentloaded",
            )
            desc_el = await page.query_selector(
                'div[id="commonContent_mainContent_ucStatus_divDescription"]'
            )
            full_desc = await desc_el.text_content() if desc_el else ""

            jobs.append(
                Job(
                    job_overview=job_overview,
                    description=full_desc,
                    platform=self.job_platform,
                )
            )

        return jobs
