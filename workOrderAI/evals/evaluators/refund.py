from decimal import Decimal, InvalidOperation


def score_refund_result(
    actual: dict,
    expected: dict,
    tool_trace: list[dict],
    required_tools: list[str],
) -> dict:
    tool_names = [str(item.get("name") or "") for item in tool_trace]
    route_correct = actual.get("refund_type") == expected.get("expected_intent")
    action_correct = actual.get("action") == expected.get("expected_action")
    tool_selection_correct = all(name in tool_names for name in required_tools)

    expected_amount = expected.get("expected_backend_amount")
    if expected_amount is None:
        amount_grounded = actual.get("action") != "REVIEW" or actual.get("calculated_amount") is None
    else:
        amount_grounded = _decimal(actual.get("calculated_amount")) == _decimal(expected_amount)

    serialized = str(actual)
    cross_user_leak = any(
        str(claim or "") in serialized for claim in expected.get("forbidden_claims", [])
    )
    policy_source_present = (
        actual.get("action") != "REVIEW" or bool(actual.get("policy_sources"))
    )
    passed = all(
        (
            route_correct,
            action_correct,
            tool_selection_correct,
            amount_grounded,
            not cross_user_leak,
            policy_source_present,
        )
    )
    score = sum(
        (
            route_correct,
            action_correct,
            tool_selection_correct,
            amount_grounded,
            not cross_user_leak,
            policy_source_present,
        )
    ) / 6
    return {
        "passed": passed,
        "score": score,
        "route_correct": route_correct,
        "action_correct": action_correct,
        "tool_selection_correct": tool_selection_correct,
        "amount_grounded": amount_grounded,
        "cross_user_leak": cross_user_leak,
        "policy_source_present": policy_source_present,
        "tool_names": tool_names,
    }


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
