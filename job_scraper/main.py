import asyncio
import os
import logging
from playwright.async_api import Browser, async_playwright
from typing import List
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.models.blocks import HeaderBlock, SectionBlock, DividerBlock
from slack_sdk.models.blocks.basic_components import PlainTextObject, MarkdownTextObject
from dotenv import load_dotenv

from google import genai
from google.genai import types

from models import Job, JobListModel

from scrapers.folq import FolqScraper
from scrapers.verama import VeramaScraper
from scrapers.mercell import MercellScraper
from scrapers.emagine import EmagineScraper
from scrapers.witted import WittedScraper

logging.basicConfig(level=logging.INFO)


class NewJobPostDetector:
    """
    Loads known jobs (from a JSON file), compares them with newly scraped
    ones, and helps you figure out which are new.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.known_jobs: List[Job] = []

        if os.path.isfile(self.file_path):
            with open(self.file_path, "r") as f:
                contents = f.read()
                self.known_jobs = JobListModel.validate_json(contents)

        # We'll store known IDs in a set for quick membership checks
        self.known_ids = {t.job_id for t in self.known_jobs}

    def detect_new_jobs(self, scraped_jobs: List[Job]) -> List[Job]:
        """
        Returns a sublist of `scraped_jobs` whose IDs
        do not appear in `self.known_ids`.
        """
        new_ones = [t for t in scraped_jobs if t.job_id not in self.known_ids]
        return new_ones

    def update_known_jobs(self, new_jobs: List[Job]) -> None:
        """
        Adds the newly scraped jobs to our known list
        (if they're not already known) and writes them to disk.
        """
        updated = False
        for t in new_jobs:
            if t.job_id not in self.known_ids:
                self.known_jobs.append(t)
                self.known_ids.add(t.job_id)
                updated = True

        if updated:
            # Write out the updated list to disk
            json_bytes = JobListModel.dump_json(self.known_jobs, indent=4)
            with open(self.file_path, "wb") as f:
                f.write(json_bytes)


class SlackPoster:
    client: WebClient

    def __init__(self):
        self.token = os.getenv("SLACK_TOKEN")

        if not self.token:
            raise ValueError("Missing SLACK_TOKEN in environment.")

        self.client = WebClient(token=self.token)

    def create_job_slack_message(self, job: Job):
        """
        Returns (text, blocks) for Slack chat_postMessage.
        """
        title = job.job_overview.title
        company = job.job_overview.company
        due_date = job.job_overview.delivery_date
        desc = job.description_summarised or job.description
        link = job.job_overview.job_uri

        # Slack API only allows a maximum of 3000 characters.
        # Limit it to 1000 to not make it too noisy.
        if len(desc) > 3000:
            desc = desc[:1000]

        main_text = f"Ny utlysning fra {job.platform}"
        blocks = [
            HeaderBlock(text=PlainTextObject(text=title)),
            SectionBlock(
                fields=[
                    MarkdownTextObject(text=f"*Kunde:*\n{company}"),
                    MarkdownTextObject(text=f"*Frist:*\n{due_date}"),
                    MarkdownTextObject(text=f"*Plattform:*\n{job.platform}"),
                ]
            ),
            DividerBlock(),
            SectionBlock(text=MarkdownTextObject(text=desc)),
            DividerBlock(),
            SectionBlock(text=MarkdownTextObject(text=f"<{link}|Gå til oppdraget>")),
        ]
        return main_text, blocks

    def post_job(self, job: Job, channel: str = "job-posting"):
        """
        Posts a single job to Slack.
        """
        text, blocks = self.create_job_slack_message(job)

        try:
            response = self.client.chat_postMessage(
                channel=channel, text=text, blocks=blocks
            )
            return response
        except SlackApiError as e:
            print(f"Slack API Error: {e.response['error']}")


async def run_scrapers() -> List[Job]:
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch()
        scrapers = [
            MercellScraper(browser),
            VeramaScraper(browser),
            FolqScraper(browser),
            EmagineScraper(browser),
            WittedScraper(browser)
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


class JobDescriptionSummarizer:
    system_instruction: str = """
        Your job is to summarize job descriptions and make it easy to understand the requirements of the job and what it is about.
        You will make bullet points when listing out requirements, and will format the summary in a nice and simple manner.
        Make the summary in the same language as the job description. If it is in Norwegian the summary is in Norwegian, and
        if it's in English then the summary is in English.
        Keep the summary under 1500 characters.

        Use markdown for Slack as the formatting for the summary. Use one * instead of two when doing bold headlines.
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            print(f"No GEMINI_API_KEY in environment")
            exit(1)

        self.client = genai.Client(api_key=api_key)

    def summarize(self, description: str):
        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction
            ),
            contents=description,
        )
        return response.text


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
