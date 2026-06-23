from decimal import Decimal
import unittest

from workOrderAI.app.model.refund import RefundPlanRequest
from workOrderAI.app.service.refund_agent_graph import RefundAgentGraph


class RefundAgentGraphTests(unittest.IsolatedAsyncioTestCase):
    def request(self, description: str = "订单 ORD-1 还没发货，我不想要了"):
        return RefundPlanRequest(
            ticket_id="ticket-1",
            title="申请退款",
            description=description,
            owner_username="1004",
            history=[],
        )

    async def test_missing_order_returns_specific_clarification(self):
        async def intent_resolver(_request):
            return {
                "intent": "UNSHIPPED_REFUND",
                "order_hint": "",
                "reason": "不想要了",
                "missing_fields": ["order"],
                "confidence": 0.95,
            }

        graph = RefundAgentGraph(intent_resolver=intent_resolver, tool_runner=self.no_tools)
        result = await graph.run(self.request("我不想要了，帮我退款"))

        self.assertEqual(result.action, "CLARIFY")
        self.assertIn("订单", result.suggested_reply)

    async def test_multiple_orders_never_selects_one_automatically(self):
        async def intent_resolver(_request):
            return {
                "intent": "UNSHIPPED_REFUND",
                "order_hint": "扫地机器人",
                "reason": "不想要了",
                "missing_fields": [],
                "confidence": 0.95,
            }

        async def tool_runner(name, _args):
            if name == "fetch_current_user_orders":
                return [
                    {"order_no": "A", "product_name": "扫地机器人"},
                    {"order_no": "B", "product_name": "扫地机器人"},
                ]
            raise AssertionError(f"unexpected tool: {name}")

        result = await RefundAgentGraph(intent_resolver, tool_runner).run(self.request())

        self.assertEqual(result.action, "CLARIFY")
        self.assertEqual(result.order_no, "")
        self.assertIn("A", result.suggested_reply)
        self.assertIn("B", result.suggested_reply)

    async def test_review_plan_copies_backend_amount(self):
        async def intent_resolver(_request):
            return {
                "intent": "UNSHIPPED_REFUND",
                "order_hint": "ORD-1",
                "reason": "不想要了",
                "missing_fields": [],
                "confidence": 0.95,
            }

        async def tool_runner(name, _args):
            values = {
                "fetch_current_user_orders": [{"order_no": "ORD-1", "product_name": "扫地机器人"}],
                "get_current_order_detail": {"order_no": "ORD-1", "status": "PAID", "items": []},
                "get_current_order_logistics": {"order_no": "ORD-1", "status": "NOT_SHIPPED"},
                "search_refund_policy": [
                    {"code": "UNSHIPPED_STANDARD", "title": "未发货退款", "content": "可申请退款"}
                ],
                "evaluate_current_refund": {
                    "eligible": True,
                    "code": "ELIGIBLE",
                    "reason": "已支付且未发货",
                    "refundable_amount": "399.00",
                    "policy_sources": [{"code": "UNSHIPPED_STANDARD", "title": "未发货退款"}],
                },
            }
            return values[name]

        result = await RefundAgentGraph(intent_resolver, tool_runner).run(self.request())

        self.assertEqual(result.action, "REVIEW")
        self.assertEqual(result.calculated_amount, Decimal("399.00"))
        self.assertEqual(result.eligibility_code, "ELIGIBLE")

    async def test_ineligible_evaluation_never_promises_refund(self):
        async def intent_resolver(_request):
            return {
                "intent": "UNSHIPPED_REFUND",
                "order_hint": "ORD-1",
                "reason": "不想要了",
                "missing_fields": [],
                "confidence": 0.95,
            }

        async def tool_runner(name, _args):
            if name == "fetch_current_user_orders":
                return [{"order_no": "ORD-1", "product_name": "扫地机器人"}]
            if name == "get_current_order_detail":
                return {"order_no": "ORD-1", "status": "PAID"}
            if name == "get_current_order_logistics":
                return {"order_no": "ORD-1", "status": "SHIPPED"}
            if name == "search_refund_policy":
                return [{"code": "UNSHIPPED_STANDARD", "title": "未发货退款"}]
            return {
                "eligible": False,
                "code": "ORDER_ALREADY_SHIPPED",
                "reason": "订单已经发货",
                "refundable_amount": "0",
                "policy_sources": [],
            }

        result = await RefundAgentGraph(intent_resolver, tool_runner).run(self.request())

        self.assertEqual(result.action, "ESCALATE")
        self.assertNotIn("将为您退款", result.suggested_reply)

    async def no_tools(self, name, _args):
        raise AssertionError(f"tool should not be called: {name}")


if __name__ == "__main__":
    unittest.main()
