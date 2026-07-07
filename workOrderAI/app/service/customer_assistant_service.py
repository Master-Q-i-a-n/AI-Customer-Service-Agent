from workOrderAI.agent.agent_context import (
    is_tool_trace_active,
    reset_current_username,
    reset_tool_trace,
    set_current_username,
    start_tool_trace,
)
from workOrderAI.app.model.customer_assistant import CustomerAssistantRequest, CustomerAssistantResponse
from workOrderAI.app.service.customer_assistant_graph import CustomerAssistantGraph


class CustomerAssistantService:
    def __init__(self, graph: CustomerAssistantGraph | None = None):
        self.graph = graph or CustomerAssistantGraph()

    async def chat(self, request: CustomerAssistantRequest) -> CustomerAssistantResponse:
        username_token = set_current_username(request.owner_username)
        owns_trace = not is_tool_trace_active()
        trace_token = start_tool_trace() if owns_trace else None
        try:
            return await self.graph.run(request)
        finally:
            reset_current_username(username_token)
            if trace_token is not None:
                reset_tool_trace(trace_token)
