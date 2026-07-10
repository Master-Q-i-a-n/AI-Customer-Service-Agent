from typing import Literal

from pydantic import BaseModel, Field

from workOrderAI.app.model.response import SourceDocument
from workOrderAI.app.model.presale import PresaleComparison, PresaleProduct, PresaleState


CustomerAssistantAction = Literal["ANSWER", "CLARIFY", "CREATE_TICKET", "TRANSFER_HUMAN"]
CustomerAssistantRoute = Literal[
    "GENERAL_CHAT",
    "PRESALE",
    "KNOWLEDGE_QA",
    "ORDER_QUERY",
    "USER_RECORD",
    "AFTER_SALES_FAULT",
    "REFUND_AFTER_SALES",
    "CLARIFY",
    "OUT_OF_SCOPE",
]


class CustomerAssistantMessage(BaseModel):
    role: str
    content: str


class CustomerAssistantTicketDraft(BaseModel):
    title: str
    description: str
    category: str
    service_group: str


class CustomerAssistantRequest(BaseModel):
    session_id: str
    owner_username: str
    message: str
    history: list[CustomerAssistantMessage] = Field(default_factory=list)
    presale_state: PresaleState = Field(default_factory=PresaleState)


class CustomerAssistantResponse(BaseModel):
    action: CustomerAssistantAction
    route: CustomerAssistantRoute
    reply: str
    sources: list[SourceDocument] = Field(default_factory=list)
    ticket_draft: CustomerAssistantTicketDraft | None = None
    products: list[PresaleProduct] = Field(default_factory=list)
    comparison: PresaleComparison | None = None
    presale_state: PresaleState | None = None
