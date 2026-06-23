from workOrderAI.agent.agent_context import (
    reset_current_username,
    reset_tool_trace,
    set_current_username,
    start_tool_trace,
)
from workOrderAI.app.model.refund import RefundPlanRequest, RefundPlanResponse
from workOrderAI.app.service.refund_agent_graph import RefundAgentGraph


class RefundService:
    def __init__(self, graph: RefundAgentGraph | None = None):
        self.graph = graph or RefundAgentGraph()

    async def create_plan(self, request: RefundPlanRequest) -> RefundPlanResponse:
        username_token = set_current_username(request.owner_username)
        trace_token = start_tool_trace()
        try:
            return await self.graph.run(request)
        finally:
            reset_tool_trace(trace_token)
            reset_current_username(username_token)
