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


class CustomerAssistantImage(BaseModel):
    name: str
    content_type: str
    content_base64: str


class VisionEvidence(BaseModel):
    image_count: int = 0
    summary: str = ""
    observations: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CustomerAssistantTicketDraft(BaseModel):
    title: str
    description: str
    category: str
    service_group: str


class CustomerAssistantRequest(BaseModel):
    session_id: str
    owner_username: str
    message: str = ""
    history: list[CustomerAssistantMessage] = Field(default_factory=list)
    presale_state: PresaleState = Field(default_factory=PresaleState)
    images: list[CustomerAssistantImage] = Field(default_factory=list)


class CustomerAssistantResponse(BaseModel):
    action: CustomerAssistantAction
    route: CustomerAssistantRoute
    reply: str
    sources: list[SourceDocument] = Field(default_factory=list)
    ticket_draft: CustomerAssistantTicketDraft | None = None
    products: list[PresaleProduct] = Field(default_factory=list)
    comparison: PresaleComparison | None = None
    presale_state: PresaleState | None = None
    vision_evidence: VisionEvidence | None = None
