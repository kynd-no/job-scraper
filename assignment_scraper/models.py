from typing import TypeAlias
from pydantic import BaseModel, TypeAdapter, computed_field
from pydantic.dataclasses import dataclass


@dataclass
class TenderOverview:
    job_type: str
    title: str
    company: str
    description: str
    delivery_date: str
    status: str
    tender_uri: str


class Tender(BaseModel):
    tender_overview: TenderOverview
    description: str

    @computed_field
    def full_tender_uri(self) -> str:
        return "https://my.mercell.com" + self.tender_overview.tender_uri

    @computed_field
    def tender_id(self) -> str:
        return self.tender_overview.tender_uri.split("/")[-1].split(".")[0]


TenderList: TypeAlias = list[Tender]
TenderListModel = TypeAdapter(TenderList)
