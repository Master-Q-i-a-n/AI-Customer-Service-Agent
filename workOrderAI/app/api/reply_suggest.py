from workOrderAI.app.model.request import ReplySuggestRequest, ReplyMessage
from workOrderAI.app.model.response import ReplySuggestResponse
from workOrderAI.app.service.suggest_service import SuggestService
from workOrderAI.app.service.vision_evidence_service import VisionEvidenceService
from workOrderAI.utils.logger_handler import logger
from workOrderAI.utils.config import config
from fastapi import APIRouter


api = APIRouter(prefix=config['router']['prefix'], tags=['reply_suggest'])

@api.post('/suggestion', response_model=ReplySuggestResponse)
async def get_suggestion(request: ReplySuggestRequest):

    logger.info(f"建议服务调用，工单ID: {request.id}")
    try:
        if request.images:
            evidence = await VisionEvidenceService().analyze(
                request.images,
                f"{request.title}\n{request.description}",
            )
            if evidence:
                evidence_text = "；".join(
                    item
                    for item in [evidence.summary, *evidence.observations, *evidence.visible_text]
                    if item
                )
                request = request.model_copy(
                    update={
                        "description": request.description + "\n【图片证据摘要，仅作辅助】" + evidence_text,
                        "images": [],
                    }
                )
        suggest_service = SuggestService()
        suggestion = await suggest_service.get_suggestion_result(request)
        logger.debug(f"建议服务返回: {suggestion.suggested_reply}")

        return suggestion

    except Exception as e:
        logger.error(f"建议服务调用失败: {e}", exc_info=True)






