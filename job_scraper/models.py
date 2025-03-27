from typing import TypeAlias
from pydantic import BaseModel, TypeAdapter, computed_field
from pydantic.dataclasses import dataclass


@dataclass
class TenderOverview:
    title: str | None = None
    company: str | None = None
    description: str | None = None
    delivery_date: str | None = None
    tender_uri: str | None = None


class Tender(BaseModel):
    tender_overview: TenderOverview
    description: str
    platform: str | None = None

    @computed_field
    def tender_id(self) -> str:
        return self.tender_overview.tender_uri


TenderList: TypeAlias = list[Tender]
TenderListModel = TypeAdapter(TenderList)
