import json
import os

import httpx
from langchain_core.tools import tool

from workOrderAI.agent.agent_context import (
    get_current_username_value,
    record_tool_call,
)
from workOrderAI.app.model.database import get_db_connection
from workOrderAI.utils.config import config
from workOrderAI.utils.logger_handler import logger


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _missing_context() -> str | None:
    if get_current_username_value():
        return None
    return _json({"error": "missing_user_context"})


@tool(description="查询当前工单用户最多五条订单候选，不接受用户名参数。")
def fetch_current_user_orders(order_hint: str = "", product_hint: str = "") -> str:
    blocked = _missing_context()
    if blocked:
        return blocked
    username = get_current_username_value()
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select distinct o.order_no, o.status, o.paid_amount, o.created_at, i.product_name
                from ec_order o
                join ec_order_item i on i.order_id=o.id
                where o.owner_username=%s and o.order_no like %s and i.product_name like %s
                order by o.created_at desc
                limit 5
                """,
                (
                    username,
                    f"%{str(order_hint or '').strip()}%",
                    f"%{str(product_hint or '').strip()}%",
                ),
            )
            rows = cursor.fetchall()
        sanitized = [
            {
                "order_no": row.get("order_no", ""),
                "status": row.get("status", ""),
                "paid_amount": row.get("paid_amount"),
                "created_at": row.get("created_at", ""),
                "product_name": row.get("product_name", ""),
            }
            for row in rows[:5]
        ]
        record_tool_call(
            "fetch_current_user_orders",
            {"order_hint": order_hint, "product_hint": product_hint},
            {"candidate_count": len(sanitized)},
        )
        return _json(sanitized)
    except Exception as exc:
        logger.error("[refund] order candidates query failed: %s", exc)
        return _json({"error": "order_query_failed"})
    finally:
        if connection:
            connection.close()


def _fetch_owned_order(order_no: str, include_items: bool) -> str:
    blocked = _missing_context()
    if blocked:
        return blocked
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select o.id, o.order_no, o.status, o.paid_amount,
                       s.status shipment_status, s.shipped_at, s.delivered_at
                from ec_order o
                join ec_shipment s on s.order_id=o.id
                where o.owner_username=%s and o.order_no=%s
                """,
                (get_current_username_value(), str(order_no or "").strip()),
            )
            order = cursor.fetchone()
            if not order:
                return _json({"error": "order_not_found"})
            result = {
                "order_no": order.get("order_no", ""),
                "status": order.get("status", ""),
                "paid_amount": order.get("paid_amount"),
                "shipment_status": order.get("shipment_status", ""),
                "shipped_at": order.get("shipped_at", ""),
                "delivered_at": order.get("delivered_at", ""),
            }
            if include_items:
                cursor.execute(
                    """
                    select id item_id, product_name, sku_name, quantity, paid_amount, returnable
                    from ec_order_item where order_id=%s order by id
                    """,
                    (order["id"],),
                )
                result["items"] = cursor.fetchall()
        return _json(result)
    except Exception as exc:
        logger.error("[refund] owned order query failed: %s", exc)
        return _json({"error": "order_query_failed"})
    finally:
        if connection:
            connection.close()


@tool(description="读取当前工单用户指定订单的商品与支付摘要。")
def get_current_order_detail(order_no: str) -> str:
    result = _fetch_owned_order(order_no, include_items=True)
    record_tool_call("get_current_order_detail", {"order_no": order_no}, {"found": "error" not in result})
    return result


@tool(description="读取当前工单用户指定订单的发货和签收状态。")
def get_current_order_logistics(order_no: str) -> str:
    result = _fetch_owned_order(order_no, include_items=False)
    record_tool_call("get_current_order_logistics", {"order_no": order_no}, {"found": "error" not in result})
    return result


@tool(description="查询启用的退款政策，返回政策代码、标题和正文。")
def search_refund_policy(refund_type: str) -> str:
    blocked = _missing_context()
    if blocked:
        return blocked
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select code, title, content from ec_refund_policy
                where active=1 and refund_type=%s order by code
                """,
                (str(refund_type or "").strip(),),
            )
            rows = cursor.fetchall()
        record_tool_call("search_refund_policy", {"refund_type": refund_type}, {"policy_count": len(rows)})
        return _json(rows)
    except Exception as exc:
        logger.error("[refund] policy query failed: %s", exc)
        return _json({"error": "policy_query_failed"})
    finally:
        if connection:
            connection.close()


@tool(description="调用确定性 Java 服务校验退款资格并读取可退金额。")
def evaluate_current_refund(order_no: str, refund_type: str) -> str:
    blocked = _missing_context()
    if blocked:
        return blocked
    refund_config = config.get("refund", {})
    base_url = os.getenv(
        "WORKORDER_BACKEND_BASE_URL",
        refund_config.get("backend_base_url", "http://localhost:8080"),
    ).rstrip("/")
    token = os.getenv(
        "WORKORDER_AI_INTERNAL_TOKEN",
        refund_config.get("internal_token", "local-refund-agent"),
    )
    try:
        # 本地服务调用不能继承系统 HTTP 代理，否则 localhost 可能被转发为 502。
        with httpx.Client(trust_env=False, timeout=10.0) as client:
            response = client.post(
                f"{base_url}/api/internal/refund/evaluate",
                headers={"X-Internal-Agent-Token": token},
                json={
                    "owner_username": get_current_username_value(),
                    "order_no": str(order_no or "").strip(),
                    "refund_type": str(refund_type or "").strip(),
                },
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            result = {"error": "evaluation_rejected", "reason": payload.get("msg", "")}
        else:
            result = payload.get("data") or {}
        record_tool_call(
            "evaluate_current_refund",
            {"order_no": order_no, "refund_type": refund_type},
            {"code": result.get("code", result.get("error", "")), "eligible": result.get("eligible", False)},
        )
        return _json(result)
    except Exception as exc:
        logger.error("[refund] backend evaluation failed: %s", exc)
        return _json({"error": "evaluation_unavailable"})


REFUND_TOOLS = [
    fetch_current_user_orders,
    get_current_order_detail,
    get_current_order_logistics,
    search_refund_policy,
    evaluate_current_refund,
]
