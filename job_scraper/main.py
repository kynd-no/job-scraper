import asyncio
import logging
from playwright.async_api import Browser, async_playwright
from typing import List
from dotenv import load_dotenv

from models import Job

from scrapers.folq import FolqScraper
from scrapers.verama import VeramaScraper
from scrapers.mercell import MercellScraper
from scrapers.emagine import EmagineScraper
from scrapers.witted import WittedScraper

from summarizer import JobDescriptionSummarizer
from slack_poster import SlackPoster
from new_job_detector import NewJobPostDetector

logging.basicConfig(level=logging.INFO)

async def run_scrapers() -> List[Job]:
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch()
        scrapers = [
            MercellScraper(browser),
            VeramaScraper(browser),
            FolqScraper(browser),
            EmagineScraper(browser),
            WittedScraper(browser),
        ]

        tasks = [scraper.scrape_jobs() for scraper in scrapers]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        scraped_jobs = []
        for scraper, result in zip(scrapers, results):
            if isinstance(result, Exception):
                logging.error(
                    f"Could not scrape {scraper.job_platform}: error {result}"
                )
            else:
                scraped_jobs.extend(result)
        await browser.close()
        return scraped_jobs


async def main():
    load_dotenv()

    summarizer = JobDescriptionSummarizer()
    scraped_jobs: List[Job] = await run_scrapers()

    slack_poster = SlackPoster()

    change_detector = NewJobPostDetector("jobs.json")

    new_jobs = change_detector.detect_new_jobs(scraped_jobs)
    logging.info(f"Found {len(scraped_jobs)} jobs in total, {len(new_jobs)} are new.")

    for job in new_jobs:
        job.description_summarised = summarizer.summarize(job.description)
        slack_poster.post_job(job)

    change_detector.update_known_jobs(new_jobs)


if __name__ == "__main__":
    asyncio.run(main())
