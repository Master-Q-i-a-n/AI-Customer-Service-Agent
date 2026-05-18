from fastapi import APIRouter

from workOrderAI.app.model.request import CaseMemoryUpsertRequest
from workOrderAI.app.service.case_memory_service import CaseMemoryService
from workOrderAI.utils.config import config


api = APIRouter(prefix=config["router"]["prefix"], tags=["case_memory"])


@api.post("/case-memory")
async def upsert_case_memory(request: CaseMemoryUpsertRequest):
    stored = await CaseMemoryService().upsert_case(request)
    return {
        "stored": stored is not None,
        "case_id": stored["id"] if stored else "",
    }
