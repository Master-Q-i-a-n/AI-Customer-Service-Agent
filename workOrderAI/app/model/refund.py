from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from workOrderAI.app.model.request import ReplyMessage


class RefundPlanRequest(BaseModel):
    ticket_id: str
    title: str
    description: str
    owner_username: str
    history: list[ReplyMessage] = Field(default_factory=list)


class RefundIntent(BaseModel):
    intent: Literal[
        "UNSHIPPED_REFUND", "RETURN_REFUND", "REFUND_STATUS", "UNKNOWN"
    ]
    order_hint: str = ""
    item_hints: list[str] = Field(default_factory=list)
    reason: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class RefundPlanResponse(BaseModel):
    action: Literal["CLARIFY", "REVIEW", "ESCALATE"]
    suggested_reply: str
    order_no: str = ""
    refund_type: str = ""
    reason: str = ""
    calculated_amount: Decimal | None = None
    eligibility_code: str = ""
    eligibility_reason: str = ""
    policy_sources: list[dict] = Field(default_factory=list)
    agent_plan: dict = Field(default_factory=dict)
