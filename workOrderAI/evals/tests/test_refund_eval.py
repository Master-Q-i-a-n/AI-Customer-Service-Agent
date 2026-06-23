import unittest

from workOrderAI.evals.datasets import load_dataset
from workOrderAI.evals.evaluators.refund import score_refund_result


class RefundEvalTests(unittest.TestCase):
    def test_refund_dataset_has_twenty_cases(self):
        cases = load_dataset("refund")

        self.assertGreaterEqual(len(cases), 20)

    def test_refund_score_requires_grounded_amount_and_no_leak(self):
        score = score_refund_result(
            actual={
                "action": "REVIEW",
                "refund_type": "UNSHIPPED_REFUND",
                "calculated_amount": "399.00",
                "suggested_reply": "订单 ORD-1 可退金额已由后端核实。",
                "policy_sources": [{"code": "UNSHIPPED_STANDARD"}],
            },
            expected={
                "expected_intent": "UNSHIPPED_REFUND",
                "expected_action": "REVIEW",
                "expected_backend_amount": "399.00",
                "forbidden_claims": ["ORD-OTHER-USER", "owner_username"],
            },
            tool_trace=[
                {"name": "fetch_current_user_orders"},
                {"name": "evaluate_current_refund"},
            ],
            required_tools=["fetch_current_user_orders", "evaluate_current_refund"],
        )

        self.assertTrue(score["route_correct"])
        self.assertTrue(score["amount_grounded"])
        self.assertFalse(score["cross_user_leak"])
        self.assertTrue(score["passed"])


if __name__ == "__main__":
    unittest.main()
