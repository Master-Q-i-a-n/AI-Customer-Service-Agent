import json
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from workOrderAI.agent.refund_tools import (
    evaluate_current_refund,
    fetch_current_user_orders,
    get_current_order_detail,
    get_current_order_logistics,
    search_refund_policy,
)
from workOrderAI.app.model.refund import RefundIntent, RefundPlanRequest, RefundPlanResponse
from workOrderAI.models.factory import router_model
from workOrderAI.utils.logger_handler import logger


class RefundState(TypedDict, total=False):
    request: RefundPlanRequest
    intent: dict
    order_candidates: list[dict]
    selected_order: dict
    evaluation: dict
    policy_sources: list[dict]
    order_detail: dict
    logistics: dict
    action: str
    suggested_reply: str
    agent_plan: dict
    check_result: dict


IntentResolver = Callable[[RefundPlanRequest], Awaitable[dict]]
ToolRunner = Callable[[str, dict], Awaitable[object]]


class RefundAgentGraph:
    def __init__(
        self,
        intent_resolver: IntentResolver | None = None,
        tool_runner: ToolRunner | None = None,
    ):
        self.intent_resolver = intent_resolver or self._resolve_intent_with_model
        self.tool_runner = tool_runner or self._run_tool
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(RefundState)
        graph.add_node("understand_refund_request", self.understand_refund_request)
        graph.add_node("resolve_order", self.resolve_order)
        graph.add_node("decide_next_action", self.decide_next_action)
        graph.add_node("evaluate_refund", self.evaluate_refund)
        graph.add_node("compose_refund_plan", self.compose_refund_plan)
        graph.add_node("self_check", self.self_check)
        graph.add_edge(START, "understand_refund_request")
        graph.add_edge("understand_refund_request", "resolve_order")
        graph.add_edge("resolve_order", "decide_next_action")
        graph.add_edge("decide_next_action", "evaluate_refund")
        graph.add_edge("evaluate_refund", "compose_refund_plan")
        graph.add_edge("compose_refund_plan", "self_check")
        graph.add_edge("self_check", END)
        return graph.compile()

    async def run(self, request: RefundPlanRequest) -> RefundPlanResponse:
        state = await self.graph.ainvoke({"request": request})
        return RefundPlanResponse(
            action=state.get("action", "ESCALATE"),
            suggested_reply=state.get("suggested_reply") or "退款信息暂时无法核实，请转人工处理。",
            order_no=(state.get("selected_order") or {}).get("order_no", ""),
            refund_type=(state.get("intent") or {}).get("intent", ""),
            reason=(state.get("intent") or {}).get("reason", ""),
            calculated_amount=self._decimal((state.get("evaluation") or {}).get("refundable_amount")),
            eligibility_code=(state.get("evaluation") or {}).get("code", ""),
            eligibility_reason=(state.get("evaluation") or {}).get("reason", ""),
            policy_sources=state.get("policy_sources") or [],
            agent_plan=state.get("agent_plan") or {},
        )

    async def understand_refund_request(self, state: RefundState) -> dict:
        try:
            raw = await self.intent_resolver(state["request"])
            intent = RefundIntent.model_validate(raw).model_dump()
        except Exception as exc:
            logger.warning("[refund-graph] intent extraction failed: %s", exc)
            intent = RefundIntent(intent="UNKNOWN", confidence=0.0).model_dump()
        if intent["intent"] == "UNKNOWN":
            return {
                "intent": intent,
                "action": "ESCALATE",
                "suggested_reply": "您好，目前还无法确认具体退款诉求，请由人工客服进一步核实。",
            }
        if intent["intent"] == "REFUND_STATUS":
            return {
                "intent": intent,
                "action": "ESCALATE",
                "suggested_reply": "您好，退款进度需要结合已有退款单核实，请由人工客服为您查询。",
            }
        return {"intent": intent}

    async def resolve_order(self, state: RefundState) -> dict:
        if state.get("action"):
            return {}
        intent = state["intent"]
        order_hint = str(intent.get("order_hint") or "").strip()
        if "order" in intent.get("missing_fields", []) or not order_hint:
            return {
                "action": "CLARIFY",
                "suggested_reply": "您好，请提供需要退款的订单号，或说明订单中的商品名称，以便准确核实。",
                "order_candidates": [],
            }
        candidates = await self._tool(
            "fetch_current_user_orders",
            {"order_hint": order_hint, "product_hint": " ".join(intent.get("item_hints") or [])},
        )
        if not isinstance(candidates, list) or not candidates:
            return {
                "action": "CLARIFY",
                "suggested_reply": "您好，暂未在您的订单中找到对应记录，请核对订单号或补充商品名称。",
                "order_candidates": [],
            }
        exact = [item for item in candidates if str(item.get("order_no")) == order_hint]
        if len(exact) == 1:
            return {"order_candidates": candidates, "selected_order": exact[0]}
        if len(candidates) == 1:
            return {"order_candidates": candidates, "selected_order": candidates[0]}
        choices = "、".join(
            f"{item.get('order_no', '')}（{item.get('product_name', '商品')}）" for item in candidates
        )
        return {
            "action": "CLARIFY",
            "suggested_reply": f"您好，查询到多个可能的订单：{choices}。请确认需要退款的订单号。",
            "order_candidates": candidates,
        }

    async def decide_next_action(self, state: RefundState) -> dict:
        if state.get("action") or not state.get("selected_order"):
            return {}
        order_no = state["selected_order"]["order_no"]
        detail = await self._tool("get_current_order_detail", {"order_no": order_no})
        logistics = await self._tool("get_current_order_logistics", {"order_no": order_no})
        if not isinstance(detail, dict) or detail.get("error"):
            return {
                "action": "ESCALATE",
                "suggested_reply": "您好，订单详情暂时无法核实，请由人工客服继续处理。",
            }
        return {
            "order_detail": detail,
            "logistics": logistics if isinstance(logistics, dict) else {},
        }

    async def evaluate_refund(self, state: RefundState) -> dict:
        if state.get("action"):
            return {}
        refund_type = state["intent"]["intent"]
        order_no = state["selected_order"]["order_no"]
        policies = await self._tool("search_refund_policy", {"refund_type": refund_type})
        evaluation = await self._tool(
            "evaluate_current_refund",
            {"order_no": order_no, "refund_type": refund_type},
        )
        return {
            "evaluation": evaluation if isinstance(evaluation, dict) else {},
            "policy_sources": policies if isinstance(policies, list) else [],
        }

    async def compose_refund_plan(self, state: RefundState) -> dict:
        if state.get("action"):
            return {}
        evaluation = state.get("evaluation") or {}
        if evaluation.get("error"):
            return {
                "action": "ESCALATE",
                "suggested_reply": "您好，退款资格暂时无法核实，请由人工客服继续处理。",
            }
        if not evaluation.get("eligible"):
            reason = evaluation.get("reason") or "当前订单不符合该退款路径的条件"
            return {
                "action": "ESCALATE",
                "suggested_reply": f"您好，经核实，{reason}。客服会继续协助您确认其他可行的售后方式。",
            }
        policies = evaluation.get("policy_sources") or state.get("policy_sources") or []
        if not policies:
            return {
                "action": "ESCALATE",
                "suggested_reply": "您好，当前未找到可引用的退款政策，请由人工客服进一步核实。",
            }
        amount = self._decimal(evaluation.get("refundable_amount"))
        if amount is None:
            return {
                "action": "ESCALATE",
                "suggested_reply": "您好，可退金额暂时无法核实，请由人工客服进一步处理。",
            }
        order_no = state["selected_order"]["order_no"]
        plan = {
            "request_summary": state["intent"].get("reason") or "用户申请退款",
            "order_no": order_no,
            "refund_type": state["intent"]["intent"],
            "backend_eligibility": evaluation.get("code", ""),
            "refundable_amount": str(amount),
            "policy_codes": [item.get("code", "") for item in policies],
            "risks": ["管理员批准前不会执行退款"],
        }
        return {
            "action": "REVIEW",
            "policy_sources": policies,
            "agent_plan": plan,
            "suggested_reply": (
                f"您好，已核实订单 {order_no} 的退款申请，后端计算可退金额为 ¥{amount:.2f}。"
                "当前方案需管理员审核，审核通过后再执行退款。"
            ),
        }

    async def self_check(self, state: RefundState) -> dict:
        action = state.get("action") or "ESCALATE"
        issues: list[str] = []
        selected = state.get("selected_order") or {}
        candidates = state.get("order_candidates") or []
        if selected and selected.get("order_no") not in {item.get("order_no") for item in candidates}:
            issues.append("订单不在当前用户候选中")
        if action == "REVIEW":
            evaluation = state.get("evaluation") or {}
            if not evaluation.get("eligible"):
                issues.append("后端未确认退款资格")
            if self._decimal(evaluation.get("refundable_amount")) is None:
                issues.append("后端金额缺失")
            if not state.get("policy_sources"):
                issues.append("政策来源缺失")
        reply = state.get("suggested_reply") or ""
        if any(term in reply for term in ("owner_username", "ticket_id", "transaction_no", "数据库字段")):
            issues.append("回复包含内部或敏感信息")
        if issues:
            return {
                "action": "ESCALATE",
                "suggested_reply": "您好，退款方案校验未通过，请由人工客服进一步核实。",
                "check_result": {"status": "ESCALATE", "issues": issues},
            }
        return {"check_result": {"status": "PASS", "issues": []}}

    async def _resolve_intent_with_model(self, request: RefundPlanRequest) -> dict:
        prompt = f"""请抽取退款诉求并严格输出结构化结果。
意图只能是 UNSHIPPED_REFUND、RETURN_REFUND、REFUND_STATUS、UNKNOWN。
不得猜测订单号；缺少订单线索时把 order 放入 missing_fields。

标题：{request.title}
内容：{request.description}
最近消息：{request.history[-4:]}
"""
        structured = router_model.with_structured_output(RefundIntent)
        result = await structured.ainvoke(prompt)
        return result.model_dump() if isinstance(result, RefundIntent) else dict(result)

    async def _run_tool(self, name: str, args: dict):
        tools = {
            "fetch_current_user_orders": fetch_current_user_orders,
            "get_current_order_detail": get_current_order_detail,
            "get_current_order_logistics": get_current_order_logistics,
            "search_refund_policy": search_refund_policy,
            "evaluate_current_refund": evaluate_current_refund,
        }
        return await tools[name].ainvoke(args)

    async def _tool(self, name: str, args: dict):
        raw = await self.tool_runner(name, args)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"error": "invalid_tool_response"}
        return raw

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
