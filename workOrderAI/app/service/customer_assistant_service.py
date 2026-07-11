from workOrderAI.agent.agent_context import (
    is_tool_trace_active,
    reset_current_username,
    reset_tool_trace,
    set_current_username,
    start_tool_trace,
)
from workOrderAI.app.model.customer_assistant import CustomerAssistantRequest, CustomerAssistantResponse
from workOrderAI.app.service.customer_assistant_graph import CustomerAssistantGraph
from workOrderAI.app.service.vision_evidence_service import VisionEvidenceService


class CustomerAssistantService:
    def __init__(
        self,
        graph: CustomerAssistantGraph | None = None,
        vision_service: VisionEvidenceService | None = None,
    ):
        self.graph = graph or CustomerAssistantGraph()
        self.vision_service = vision_service or VisionEvidenceService()

    async def chat(self, request: CustomerAssistantRequest) -> CustomerAssistantResponse:
        if not str(request.message or "").strip() and not request.images:
            raise ValueError("message or images is required")
        username_token = set_current_username(request.owner_username)
        owns_trace = not is_tool_trace_active()
        trace_token = start_tool_trace() if owns_trace else None
        try:
            evidence = None
            graph_request = request
            if request.images:
                evidence = await self.vision_service.analyze(request.images, request.message)
                if evidence:
                    evidence_lines = [evidence.summary, *evidence.observations, *evidence.visible_text]
                    evidence_context = "；".join(item for item in evidence_lines if item)
                    original_message = str(request.message or "").strip()
                    enriched_message = (
                        (original_message + "\n") if original_message else ""
                    ) + "【图片证据摘要，仅作辅助】" + evidence_context
                    graph_request = request.model_copy(
                        update={"message": enriched_message, "images": []}
                    )
                elif not str(request.message or "").strip():
                    return CustomerAssistantResponse(
                        action="CLARIFY",
                        route="AFTER_SALES_FAULT",
                        reply="图片暂时无法识别，请重新上传清晰图片，或补充设备型号、故障现象和报错提示。",
                    )

            result = await self.graph.run(graph_request)
            if evidence:
                result.vision_evidence = evidence
            return result
        finally:
            reset_current_username(username_token)
            if trace_token is not None:
                reset_tool_trace(trace_token)
