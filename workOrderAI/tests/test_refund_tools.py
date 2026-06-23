import json
import unittest
from unittest.mock import MagicMock, patch

from workOrderAI.agent.agent_context import reset_current_username, set_current_username
from workOrderAI.agent.refund_tools import evaluate_current_refund, fetch_current_user_orders


class RefundToolTests(unittest.TestCase):
    @patch("workOrderAI.agent.refund_tools.get_db_connection")
    def test_order_tool_uses_context_user_and_hides_owner(self, get_db_connection):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "order_no": "ORD-1",
                "status": "PAID",
                "paid_amount": "399.00",
                "created_at": "2026-06-22 10:00:00",
                "product_name": "扫拖一体机器人",
                "owner_username": "1004",
            }
        ]
        get_db_connection.return_value.cursor.return_value.__enter__.return_value = cursor

        token = set_current_username("1004")
        try:
            result = json.loads(
                fetch_current_user_orders.invoke({"order_hint": "ORD", "product_hint": ""})
            )
        finally:
            reset_current_username(token)

        params = cursor.execute.call_args.args[1]
        self.assertEqual(params[0], "1004")
        self.assertEqual(result[0]["order_no"], "ORD-1")
        self.assertNotIn("owner_username", result[0])

    @patch("workOrderAI.agent.refund_tools.get_db_connection")
    def test_order_tool_blocks_missing_user_context(self, get_db_connection):
        result = fetch_current_user_orders.invoke({"order_hint": "", "product_hint": ""})

        self.assertEqual(json.loads(result)["error"], "missing_user_context")
        get_db_connection.assert_not_called()

    @patch("workOrderAI.agent.refund_tools.httpx.Client")
    def test_evaluation_tool_injects_context_user_and_bypasses_proxy(self, client_class):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "code": 200,
            "data": {"eligible": True, "refundable_amount": "399.00"},
        }
        post = client_class.return_value.__enter__.return_value.post
        post.return_value = response

        token = set_current_username("1004")
        try:
            result = json.loads(
                evaluate_current_refund.invoke(
                    {"order_no": "ORD-1", "refund_type": "UNSHIPPED_REFUND"}
                )
            )
        finally:
            reset_current_username(token)

        payload = post.call_args.kwargs["json"]
        client_class.assert_called_once_with(trust_env=False, timeout=10.0)
        self.assertEqual(payload["owner_username"], "1004")
        self.assertEqual(result["refundable_amount"], "399.00")


if __name__ == "__main__":
    unittest.main()
