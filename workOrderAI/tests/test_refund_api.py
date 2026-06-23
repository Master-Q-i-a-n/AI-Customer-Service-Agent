import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from workOrderAI.agent.agent_context import get_current_username_value, is_tool_trace_active
from workOrderAI.app.model.refund import RefundPlanRequest, RefundPlanResponse
from workOrderAI.app.service.refund_service import RefundService
from workOrderAI.main import app


class RefundApiTests(unittest.TestCase):
    def test_refund_plan_api_returns_structured_result(self):
        response_value = RefundPlanResponse(
            action="CLARIFY",
            suggested_reply="请提供订单号。",
        )
        with patch("workOrderAI.app.api.refund.RefundService") as service_cls:
            service_cls.return_value.create_plan = AsyncMock(return_value=response_value)
            response = TestClient(app).post(
                "/ai/refund/plan",
                json={
                    "ticket_id": "ticket-1",
                    "title": "退款",
                    "description": "我想退款",
                    "owner_username": "1004",
                    "history": [],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "CLARIFY")


class RefundServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_sets_and_resets_request_context(self):
        graph = AsyncMock()

        async def run(_request):
            self.assertEqual(get_current_username_value(), "1004")
            self.assertTrue(is_tool_trace_active())
            return RefundPlanResponse(action="CLARIFY", suggested_reply="请提供订单号。")

        graph.run.side_effect = run
        request = RefundPlanRequest(
            ticket_id="ticket-1",
            title="退款",
            description="我想退款",
            owner_username="1004",
            history=[],
        )

        result = await RefundService(graph=graph).create_plan(request)

        self.assertEqual(result.action, "CLARIFY")
        self.assertEqual(get_current_username_value(), "")
        self.assertFalse(is_tool_trace_active())


if __name__ == "__main__":
    unittest.main()
