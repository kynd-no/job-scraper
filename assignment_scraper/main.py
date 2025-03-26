import asyncio
import os
from typing import List
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.models.blocks import HeaderBlock, SectionBlock, DividerBlock
from slack_sdk.models.blocks.basic_components import PlainTextObject, MarkdownTextObject
from dotenv import load_dotenv

from models import Tender, TenderListModel

from scrapers import MercellScraper


class TenderChangeDetector:
    """
    Loads known tenders (from a JSON file), compares them with newly scraped
    ones, and helps you figure out which are new.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.known_tenders: List[Tender] = []

        if os.path.isfile(self.file_path):
            with open(self.file_path, "r") as f:
                contents = f.read()
                self.known_tenders = TenderListModel.validate_json(contents)

        # We'll store known IDs in a set for quick membership checks
        self.known_ids = {t.tender_id for t in self.known_tenders}

    def detect_new_tenders(self, scraped_tenders: List[Tender]) -> List[Tender]:
        """
        Returns a sublist of `scraped_tenders` whose IDs
        do not appear in `self.known_ids`.
        """
        new_ones = [t for t in scraped_tenders if t.tender_id not in self.known_ids]
        return new_ones

    def update_known_tenders(self, new_tenders: List[Tender]) -> None:
        """
        Adds the newly scraped tenders to our known list
        (if they're not already known) and writes them to disk.
        """
        updated = False
        for t in new_tenders:
            if t.tender_id not in self.known_ids:
                self.known_tenders.append(t)
                self.known_ids.add(t.tender_id)
                updated = True

        if updated:
            # Write out the updated list to disk
            json_bytes = TenderListModel.dump_json(self.known_tenders, indent=4)
            with open(self.file_path, "wb") as f:
                f.write(json_bytes)


class SlackPoster:
    client: WebClient

    def __init__(self):
        self.token = os.getenv("SLACK_TOKEN")

        if not self.token:
            raise ValueError("Missing SLACK_TOKEN in environment.")

        self.client = WebClient(token=self.token)

    def create_tender_slack_message(self, tender: Tender):
        """
        Returns (text, blocks) for Slack chat_postMessage.
        """
        title = tender.tender_overview.title
        company = tender.tender_overview.company
        due_date = tender.tender_overview.delivery_date
        desc = tender.description
        link = tender.full_tender_uri

        main_text = f"Ny utlysning fra {company}"
        blocks = [
            HeaderBlock(text=PlainTextObject(text=title)),
            SectionBlock(
                fields=[
                    MarkdownTextObject(text=f"*Kunde:*\n{company}"),
                    MarkdownTextObject(text=f"*Frist:*\n{due_date}"),
                ]
            ),
            DividerBlock(),
            SectionBlock(text=MarkdownTextObject(text=desc)),
            DividerBlock(),
            SectionBlock(text=MarkdownTextObject(text=f"<{link}|Gå til oppdraget>")),
        ]
        return main_text, blocks

    def post_tender(self, tender: Tender, channel: str = "job-posting-testing-dev"):
        """
        Posts a single tender to Slack.
        """
        text, blocks = self.create_tender_slack_message(tender)

        try:
            response = self.client.chat_postMessage(
                channel=channel, text=text, blocks=blocks
            )
            print("Slack response:", response)
            return response
        except SlackApiError as e:
            print(f"Slack API Error: {e.response['error']}")


async def main():
    load_dotenv()
    mercell_scraper = MercellScraper()

    slack_poster = SlackPoster()

    scraped_tenders = await mercell_scraper.scrape_tenders()

    change_detector = TenderChangeDetector("tenders.json")

    new_tenders = change_detector.detect_new_tenders(scraped_tenders)
    print(f"Found {len(scraped_tenders)} tenders in total, {len(new_tenders)} are new.")

    for tender in new_tenders:
        slack_poster.post_tender(tender)

    change_detector.update_known_tenders(new_tenders)


if __name__ == "__main__":
    asyncio.run(main())
