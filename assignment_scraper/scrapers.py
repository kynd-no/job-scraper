import os
from playwright.async_api import Browser, Page, async_playwright
from abc import ABC, abstractmethod
from typing import List

from models import Tender, TenderOverview

class JobScraper(ABC):

    def __init__(self): ...

    @abstractmethod
    async def scrape_tenders(self) -> List[Tender]: ...


class MercellScraper(JobScraper):
    BASE_URL = "https://my.mercell.com"

    def __init__(self) -> None:
        self.username = os.getenv("MERCELL_USERNAME")
        self.password = os.getenv("MERCELL_PASSWORD")

        if not self.username or not self.password:
            raise ValueError(
                "Missing MERCELL_USERNAME or MERCELL_PASSWORD in environment"
            )

    async def scrape_tenders(self) -> List[Tender]:
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch()
            page: Page = await browser.new_page()
            await self._login(page)
            tender_overviews: List[TenderOverview] = await self._parse_tender_overview(
                page
            )

            tenders: List[Tender] = await self._traverse_tender_pages(
                page, tender_overviews
            )

            await browser.close()

            return tenders

    async def _login(self, page: Page) -> None:
        await page.goto("https://my.mercell.com/en/m/logon/default.aspx?auth0done=true")
        await page.get_by_role("textbox").fill(self.username)
        await page.get_by_text("Continue").click()
        await page.locator('//*[@id="password"]').fill(self.password)
        await page.get_by_role("button", name="Continue").click()

    async def _parse_tender_overview(self, page: Page) -> List[TenderOverview]:
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

        tenders: List[TenderOverview] = []
        nxt_button_selector = 'a[class="nxt"]'
        while True:
            tenders.extend(await self._parse_tender_overview_table(page))

            if await page.is_visible(nxt_button_selector, strict=True):
                await page.click(nxt_button_selector)
                await page.wait_for_timeout(2000)
            else:
                # No more pages
                break

        print(f"Found {len(tenders)} tenders")
        return tenders

    async def _parse_tender_overview_table(self, page: Page) -> List[TenderOverview]:
        """
        Parses each <tr> in the table's <tbody>, extracting the tender data
        from known columns. Returns a list of TenderOverview.
        """

        table_selector = "#ctl00_ctl00_commonContent_mainContent_ucTenderList_gwTenders_GridViewTop_GridView"
        table = await page.query_selector(table_selector)
        if not table:
            print("Could not find the table on this page.")
            return []

        # Get all <tr> inside <tbody>
        rows = await table.query_selector_all("tbody > tr")
        results: List[TenderOverview] = []

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

            # 1) job_type: column index 3
            job_type_el = tds[3]
            job_type = (await job_type_el.inner_text() or "").strip()

            # 2) The main column with link and company: column index 4
            main_col = tds[4]
            # - The "title" link is the <a class="hide100pct">
            title_a = await main_col.query_selector("a.hide100pct")
            title_text = ""
            tender_href = ""
            if title_a:
                title_text = (await title_a.inner_text() or "").strip()
                tender_href = await title_a.get_attribute("href") or ""

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

            # 4) Status: column index 6
            status_el = tds[6]
            status_text = (await status_el.inner_text() or "").strip()

            results.append(
                TenderOverview(
                    job_type=job_type,
                    title=title_text,
                    company=company_text,
                    description="",  # or parse from tooltip if needed
                    delivery_date=delivery_date,
                    status=status_text,
                    tender_uri=tender_href,
                )
            )

        return results

    async def _traverse_tender_pages(
        self, page: Page, tender_overviews: List[TenderOverview]
    ) -> List[Tender]:
        tenders: List[Tender] = []
        for tender_overview in tender_overviews:
            await page.goto(
                self.BASE_URL + tender_overview.tender_uri,
                wait_until="domcontentloaded",
            )
            desc_el = await page.query_selector(
                'div[id="commonContent_mainContent_ucStatus_divDescription"]'
            )
            full_desc = await desc_el.text_content() if desc_el else ""

            tenders.append(
                Tender(tender_overview=tender_overview, description=full_desc)
            )

        return tenders
