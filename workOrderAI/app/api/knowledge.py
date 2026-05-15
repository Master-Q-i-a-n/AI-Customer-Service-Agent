from fastapi import APIRouter, HTTPException

from workOrderAI.app.model.request import KnowledgeQARequest, KnowledgeUploadRequest
from workOrderAI.app.model.response import KnowledgeListResponse, KnowledgeQAResponse, KnowledgeResponse
from workOrderAI.app.service.knowledge_service import KnowledgeService
from workOrderAI.utils.config import config


api = APIRouter(prefix=config["router"]["prefix"], tags=["knowledge"])


@api.post("/knowledge/qa", response_model=KnowledgeQAResponse)
async def ask_knowledge(request: KnowledgeQARequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is empty")
    return await KnowledgeService().answer(question)


@api.get("/knowledge/documents", response_model=KnowledgeListResponse)
def list_knowledge_documents():
    return KnowledgeService().list_documents()


@api.post("/knowledge/documents/upload", response_model=KnowledgeResponse)
async def upload_knowledge_document(request: KnowledgeUploadRequest):
    try:
        return await KnowledgeService().upload_document(
            request.file_name,
            request.content_base64,
            request.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api.delete("/knowledge/documents/{document_id}")
async def delete_knowledge_document(document_id: str):
    deleted = await KnowledgeService().delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="knowledge document not found")
    return {"deleted": True}
