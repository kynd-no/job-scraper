import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.models.blocks import HeaderBlock, SectionBlock, DividerBlock
from slack_sdk.models.blocks.basic_components import PlainTextObject, MarkdownTextObject

from models import Job

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



