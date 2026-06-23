from fastapi import APIRouter

from workOrderAI.app.model.refund import RefundPlanRequest, RefundPlanResponse
from workOrderAI.app.service.refund_service import RefundService
from workOrderAI.utils.config import config


api = APIRouter(prefix=config["router"]["prefix"], tags=["refund"])


@api.post("/refund/plan", response_model=RefundPlanResponse)
async def create_refund_plan(request: RefundPlanRequest):
    return await RefundService().create_plan(request)
