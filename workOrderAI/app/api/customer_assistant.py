from fastapi import APIRouter, HTTPException

from workOrderAI.app.model.customer_assistant import CustomerAssistantRequest, CustomerAssistantResponse
from workOrderAI.app.service.customer_assistant_service import CustomerAssistantService
from workOrderAI.utils.config import config


api = APIRouter(prefix=config["router"]["prefix"], tags=["customer_assistant"])


@api.post("/customer-assistant/chat", response_model=CustomerAssistantResponse)
async def customer_assistant_chat(request: CustomerAssistantRequest):
    try:
        return await CustomerAssistantService().chat(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
