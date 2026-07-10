import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from workOrderAI.agent.agent_tools import fetch_current_user_records
from workOrderAI.agent.refund_tools import fetch_current_user_orders
from workOrderAI.app.model.customer_assistant import (
    CustomerAssistantRequest,
    CustomerAssistantResponse,
    CustomerAssistantRoute,
    CustomerAssistantTicketDraft,
)
from workOrderAI.app.service.rag_service import RagService
from workOrderAI.app.service.presale_agent_graph import PresaleAgentGraph
from workOrderAI.models.factory import router_model
from workOrderAI.utils.logger_handler import logger


VALID_ROUTES = {
    "GENERAL_CHAT",
    "PRESALE",
    "KNOWLEDGE_QA",
    "ORDER_QUERY",
    "USER_RECORD",
    "AFTER_SALES_FAULT",
    "REFUND_AFTER_SALES",
    "CLARIFY",
    "OUT_OF_SCOPE",
}
ROUTER_CONFIDENCE_THRESHOLD = 0.6


class FaultConversationAssessment(BaseModel):
    has_fault_context: bool = Field(default=False, description="对话是否已经包含设备故障或异常使用场景")
    information_sufficient: bool = Field(default=False, description="是否足够进入初步排查或整理售后工单")
    wants_human: bool = Field(default=False, description="用户最新消息是否明确要求人工客服或转人工")
    concise_issue: str = Field(default="", description="合并上下文后的简短故障描述")
    missing_fields: list[str] = Field(default_factory=list, description="仍需用户补充的关键信息")
    reason: str = Field(default="", description="判断原因")


class CustomerAssistantState(TypedDict, total=False):
    request: CustomerAssistantRequest
    query_text: str
    route: CustomerAssistantRoute
    response: CustomerAssistantResponse


class CustomerAssistantGraph:
    def __init__(self):
        self.router_model = router_model
        self.presale_graph = PresaleAgentGraph(model=router_model)
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(CustomerAssistantState)
        graph.add_node("load_context", self.load_context)
        graph.add_node("route_query", self.route_query)
        graph.add_node("run_branch", self.run_branch)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "route_query")
        graph.add_edge("route_query", "run_branch")
        graph.add_edge("run_branch", END)
        return graph.compile()

    async def run(self, request: CustomerAssistantRequest) -> CustomerAssistantResponse:
        state = await self.graph.ainvoke({"request": request})
        return state["response"]

    async def load_context(self, state: CustomerAssistantState) -> dict:
        request = state["request"]
        history_lines = [
            f"{item.role}：{item.content}"
            for item in request.history[-6:]
            if str(item.content or "").strip()
        ]
        query_text = "\n".join([*history_lines, f"user：{request.message}"]).strip()
        return {"query_text": query_text}

    async def route_query(self, state: CustomerAssistantState) -> dict:
        request = state["request"]
        if self._should_continue_presale(request):
            route = "PRESALE"
        else:
            route = await self._classify_route(state.get("query_text") or "")
        logger.info("[customer-assistant] route=%s", route)
        return {"route": route}

    async def run_branch(self, state: CustomerAssistantState) -> dict:
        route = state.get("route") or "KNOWLEDGE_QA"
        handlers = {
            "GENERAL_CHAT": self._general_chat_branch,
            "PRESALE": self._presale_branch,
            "KNOWLEDGE_QA": self._knowledge_branch,
            "ORDER_QUERY": self._order_branch,
            "USER_RECORD": self._user_record_branch,
            "AFTER_SALES_FAULT": self._fault_branch,
            "REFUND_AFTER_SALES": self._refund_branch,
            "CLARIFY": self._clarify_branch,
            "OUT_OF_SCOPE": self._out_of_scope_branch,
        }
        handler = handlers.get(route, self._knowledge_branch)
        return {"response": await handler(state)}

    async def _classify_route(self, text: str) -> CustomerAssistantRoute:
        fallback_route = self._classify_route_by_rules(text)
        model = getattr(self, "router_model", None)
        if model is None:
            return fallback_route

        prompt = self._build_route_prompt(text)
        try:
            result = await model.ainvoke(prompt)
            payload = self._parse_json_object(self._message_content(result))
            route = str(payload.get("route") or "").strip()
            confidence = float(payload.get("confidence") or 0)
            reason = str(payload.get("reason") or "").strip()
            if route not in VALID_ROUTES:
                logger.warning("[customer-assistant] router returned invalid route=%s, fallback=%s", route, fallback_route)
                return fallback_route
            if confidence < ROUTER_CONFIDENCE_THRESHOLD:
                logger.info(
                    "[customer-assistant] router confidence too low route=%s confidence=%.2f, fallback=%s",
                    route,
                    confidence,
                    fallback_route,
                )
                return fallback_route
            logger.info("[customer-assistant] router model route=%s confidence=%.2f reason=%s", route, confidence, reason)
            return route
        except Exception as exc:
            logger.warning("[customer-assistant] router model failed, fallback=%s, error=%s", fallback_route, exc)
            return fallback_route

    def _classify_route_by_rules(self, text: str) -> CustomerAssistantRoute:
        normalized = str(text or "").lower()
        latest = normalized.rsplit("user：", 1)[-1].strip()
        if self._is_general_chat(latest):
            return "GENERAL_CHAT"
        if self._contains_any(latest, ["转人工", "人工客服", "找人工", "人工处理"]):
            return "AFTER_SALES_FAULT"
        if self._is_too_vague(latest):
            return "CLARIFY"
        if self._contains_any(latest, ["彩票", "股票", "考试答案", "写歌", "老板是谁", "无关"]):
            return "OUT_OF_SCOPE"
        if self._contains_any(latest, ["退款", "退货", "退钱", "取消订单", "申请退"]):
            return "REFUND_AFTER_SALES"
        if self._has_user_record_intent(latest):
            return "USER_RECORD"
        if self._contains_any(
            latest,
            [
                "物流", "快递", "发货", "签收", "订单状态", "我的订单", "有哪些订单",
                "订单列表", "订单记录", "历史订单", "查订单", "查询订单", "看订单",
                "订单号", "下过哪些单", "下了哪些单", "买过什么", "购买记录", "运单", "配送",
            ],
        ):
            return "ORDER_QUERY"
        if self._contains_any(latest, ["坏", "故障", "不能", "无法", "异常", "报错", "不出水", "回不了充", "乱跑", "卡住", "失灵", "异响"]):
            return "AFTER_SALES_FAULT"
        if self._contains_any(latest, ["买", "购买", "推荐", "适合", "型号", "区别", "价格", "优惠", "售前"]):
            return "PRESALE"
        return "KNOWLEDGE_QA"

    def _build_route_prompt(self, text: str) -> str:
        return f"""你是用户侧智能客服入口的意图路由器。请只判断用户最新诉求应进入哪条分支，不要回答问题。

可选 route：
1. GENERAL_CHAT：寒暄、问你是谁、你能做什么、功能介绍。
2. PRESALE：售前咨询、型号选择、购买建议、价格优惠、产品区别。
3. KNOWLEDGE_QA：产品使用方法、保养、功能说明、一般知识问答。
4. ORDER_QUERY：查询当前账号订单、订单列表、订单状态、物流、发货、签收、购买记录。
5. USER_RECORD：查询当前账号设备使用记录、清扫记录、清洁效率、清扫次数、耗材剩余。
6. AFTER_SALES_FAULT：设备故障、异常、不能使用、报错、异响、不出水、回不了充，需要排查或转售后。
7. REFUND_AFTER_SALES：退款、退货、取消订单、退款进度或退款售后诉求。
8. CLARIFY：用户只说“有问题/帮我/不好用”等，信息不足，必须先追问。
9. OUT_OF_SCOPE：明显超出扫地/扫拖机器人客服范围的问题。

判断要求：
- 只根据“最新 user 消息”定 route；历史消息只作为上下文辅助。
- 退款/退货/取消订单优先 REFUND_AFTER_SALES，不要承诺金额、资格或执行结果。
- 订单列表、有哪些订单、买过什么、物流和发货状态都属于 ORDER_QUERY。
- “使用记录/清扫次数/耗材剩余”属于 USER_RECORD；“怎么更换耗材/如何保养”属于 KNOWLEDGE_QA。
- 设备故障里提到“用过/换过/尝试过”不等于 USER_RECORD，仍按 AFTER_SALES_FAULT。
- confidence 表示你对 route 的置信度，范围 0 到 1。

只输出严格 JSON，不要输出 Markdown：
{{"route":"ORDER_QUERY","confidence":0.9,"reason":"一句话说明"}}

对话上下文：
{text}
"""

    async def _general_chat_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        query = state["request"].message
        if self._contains_any(query, ["会干什么", "能干什么", "你会什么", "有什么用", "功能"]):
            reply = (
                "我可以帮您查询商品和使用知识、订单物流、历史使用记录，也可以先追问售后故障或退款诉求；"
                "需要人工处理时，我会先整理工单草稿，等您确认后再生成工单。"
            )
        else:
            reply = "您好，我是 AI 客服。您可以直接描述商品咨询、订单物流、使用记录、售后故障或退款诉求。"
        return CustomerAssistantResponse(
            action="ANSWER",
            route="GENERAL_CHAT",
            reply=reply,
            sources=[],
        )

    async def _knowledge_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        request = state["request"]
        result = await RagService().rag_summary_for_suggestion(request.message)
        summary = str(result.get("summary") or "").strip() or "抱歉，当前知识库中没有相关信息。"
        sources = result.get("sources") if isinstance(result.get("sources"), list) else []
        return CustomerAssistantResponse(
            action="ANSWER",
            route=state.get("route") or "KNOWLEDGE_QA",
            reply=summary,
            sources=sources,
        )

    async def _presale_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        return await self.presale_graph.run(state["request"])

    async def _order_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        query = state["request"].message
        raw = await fetch_current_user_orders.ainvoke(
            {
                "order_hint": self._extract_order_hint(query),
                "product_hint": self._extract_product_hint(query),
            }
        )
        data = self._parse_json(raw, [])
        if isinstance(data, dict) and data.get("error"):
            reply = "您好，订单信息暂时无法查询。您可以稍后再试，或确认是否使用当前账号登录。"
        elif not data:
            reply = "您好，当前账号下暂未查询到匹配的订单。请补充订单号或商品名称，我再帮您核对。"
        else:
            lines = []
            for item in data[:3]:
                lines.append(
                    f"{item.get('order_no', '订单')}：{item.get('product_name', '商品')}，状态 {item.get('status', '未知')}。"
                )
            reply = "已为您查询到这些订单：\n" + "\n".join(lines)
        return CustomerAssistantResponse(action="ANSWER", route="ORDER_QUERY", reply=reply)

    async def _user_record_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        query = state["request"].message
        month = self._extract_month(query)
        raw = await fetch_current_user_records.ainvoke({"month": month})
        data = self._parse_json(raw, [])
        if isinstance(data, dict) and data.get("found") is False:
            target = f"{month} " if month else ""
            reply = f"您好，当前账号下未查到{target}对应的使用记录。您可以换一个月份，或确认设备是否已绑定当前账号。"
            return CustomerAssistantResponse(action="ANSWER", route="USER_RECORD", reply=reply)
        if not data:
            return CustomerAssistantResponse(
                action="ANSWER",
                route="USER_RECORD",
                reply="您好，使用记录暂时无法查询。请稍后再试，或转人工客服进一步核实。",
            )

        rows = data if isinstance(data, list) else []
        lines = []
        for row in rows[:3]:
            lines.append(
                f"{row.get('时间', '记录')}：特征 {row.get('特征', '未记录')}，清洁效率 {row.get('清洁效率', '未记录')}，耗材 {row.get('耗材', '未记录')}。"
            )
        reply = "已查询到您的使用记录：\n" + "\n".join(lines)
        return CustomerAssistantResponse(action="ANSWER", route="USER_RECORD", reply=reply)

    async def _fault_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        request = state["request"]
        fault_context = self._build_fault_context(request)
        try:
            assessment = await self._assess_fault_conversation(fault_context, request.message)
        except Exception as exc:
            logger.warning("[customer-assistant] fault assessment failed, error=%s", exc)
            return CustomerAssistantResponse(
                action="CLARIFY",
                route="AFTER_SALES_FAULT",
                reply="为了更准确地帮您排查，请补充设备型号、具体异常现象、出现时间，以及是否有报错提示。",
            )

        if not assessment.has_fault_context:
            return self._fault_clarify_response(assessment.missing_fields)

        if assessment.wants_human:
            issue_text = self._fault_issue_text(assessment, fault_context)
            draft = self._build_ticket_draft(
                title_prefix="售后故障",
                request_text=issue_text,
                category="技术故障",
                service_group="TECH_SUPPORT",
            )
            return CustomerAssistantResponse(
                action="CREATE_TICKET",
                route="AFTER_SALES_FAULT",
                reply="已根据您前面描述的问题整理售后工单草稿，请确认后生成工单，人工客服会继续跟进。",
                ticket_draft=draft,
            )

        if not assessment.information_sufficient:
            return self._fault_clarify_response(assessment.missing_fields)

        issue_text = self._fault_issue_text(assessment, fault_context)
        result = await RagService().rag_summary_for_suggestion("扫地机器人故障排查：" + issue_text)
        summary = str(result.get("summary") or "").strip()
        sources = result.get("sources") if isinstance(result.get("sources"), list) else []
        draft = self._build_ticket_draft(
            title_prefix="售后故障",
            request_text=issue_text,
            category="技术故障",
            service_group="TECH_SUPPORT",
        )
        reply = (
            (summary + "\n\n") if summary else ""
        ) + "如果这些排查后仍未恢复，我可以帮您生成售后工单，由人工客服继续跟进。"
        return CustomerAssistantResponse(
            action="CREATE_TICKET",
            route="AFTER_SALES_FAULT",
            reply=reply,
            sources=sources,
            ticket_draft=draft,
        )

    def _build_fault_context(self, request: CustomerAssistantRequest) -> str:
        user_messages = [
            str(item.content or "").strip()
            for item in request.history[-8:]
            if str(item.role or "").lower() == "user" and str(item.content or "").strip()
        ]
        current = str(request.message or "").strip()
        if current:
            user_messages.append(current)
        return "\n".join(user_messages).strip()

    async def _assess_fault_conversation(self, fault_context: str, latest_message: str) -> FaultConversationAssessment:
        model = getattr(self, "router_model", None)
        if model is None:
            raise RuntimeError("router model unavailable")
        prompt = f"""你是扫地/扫拖机器人售后客服的故障信息判断器。请只判断信息是否足够，不要给用户回复。

判断要求：
- has_fault_context：对话里是否已经出现设备故障、异常状态、无法使用、报错、指示灯异常等售后故障上下文；只有“转人工”不算故障上下文。
- information_sufficient：只要用户已经描述了可观察的具体故障现象，足够进入初步排查或整理售后工单，就返回 true；不要强制要求同时具备设备型号、时间和截图。
- wants_human：用户最新消息是否明确要求转人工、人工客服或人工处理。
- concise_issue：合并多轮用户消息，用一句话概括真实故障；不要只写“转人工”。
- missing_fields：信息不足时列出最值得补充的 1 到 4 项，例如设备型号、具体现象、出现时间、报错提示或截图。

最近用户消息：
{fault_context}

最新用户消息：
{latest_message}
"""
        # 用结构化输出避免在故障分支继续维护一组不断膨胀的关键词规则。
        structured_model = model.with_structured_output(FaultConversationAssessment)
        result = await structured_model.ainvoke(prompt)
        if isinstance(result, FaultConversationAssessment):
            return result
        if isinstance(result, dict):
            return FaultConversationAssessment(**result)
        if hasattr(result, "model_dump"):
            return FaultConversationAssessment(**result.model_dump())
        if hasattr(result, "dict"):
            return FaultConversationAssessment(**result.dict())
        return FaultConversationAssessment(**dict(result))

    def _fault_issue_text(self, assessment: FaultConversationAssessment, fault_context: str) -> str:
        issue = str(assessment.concise_issue or "").strip()
        return issue or re.sub(r"\s+", " ", str(fault_context or "")).strip()

    def _fault_clarify_response(self, missing_fields: list[str] | None = None) -> CustomerAssistantResponse:
        fields = [
            str(item).strip()
            for item in (missing_fields or [])[:4]
            if str(item or "").strip()
        ]
        if fields:
            reply = "为了继续排查，请补充" + "、".join(fields) + "。"
        else:
            reply = "为了继续排查，请补充设备型号、具体异常现象、出现时间，以及是否有报错提示。"
        return CustomerAssistantResponse(
            action="CLARIFY",
            route="AFTER_SALES_FAULT",
            reply=reply,
        )

    async def _refund_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        query = state["request"].message
        if not self._extract_order_hint(query):
            return CustomerAssistantResponse(
                action="CLARIFY",
                route="REFUND_AFTER_SALES",
                reply="您好，请提供需要退款或退货的订单号，或说明订单中的商品名称和具体诉求。我会先为您整理售后工单，后续由人工客服核实。",
            )
        draft = self._build_ticket_draft(
            title_prefix="退款售后",
            request_text=query,
            category="退款售后",
            service_group="AFTER_SALES",
        )
        return CustomerAssistantResponse(
            action="CREATE_TICKET",
            route="REFUND_AFTER_SALES",
            reply="已了解您的退款/退货诉求。我可以为您生成售后工单，后续由人工客服核实订单、政策和处理进度。",
            ticket_draft=draft,
        )

    async def _clarify_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        return CustomerAssistantResponse(
            action="CLARIFY",
            route="CLARIFY",
            reply="您好，请再补充一下您想咨询的具体问题，例如商品型号、订单号、故障现象或需要查询的时间范围。",
        )

    async def _out_of_scope_branch(self, state: CustomerAssistantState) -> CustomerAssistantResponse:
        return CustomerAssistantResponse(
            action="ANSWER",
            route="OUT_OF_SCOPE",
            reply="您好，这个问题超出了当前扫地/扫拖机器人客服范围。为了避免给您不准确的信息，建议联系人工客服确认其他事项。",
        )

    def _build_ticket_draft(
        self,
        title_prefix: str,
        request_text: str,
        category: str,
        service_group: str,
    ) -> CustomerAssistantTicketDraft:
        clean_text = re.sub(r"\s+", " ", str(request_text or "")).strip()
        title = f"{title_prefix}：{self._truncate(clean_text, 36)}"
        description = (
            "来源：用户侧 AI 客服对话\n"
            f"用户诉求：{clean_text}\n"
            "处理建议：请人工客服结合订单、设备状态和用户补充信息继续核实。"
        )
        return CustomerAssistantTicketDraft(
            title=title,
            description=description,
            category=category,
            service_group=service_group,
        )

    def _has_user_record_intent(self, text: str) -> bool:
        if "我" in text and self._contains_any(text, ["耗材还剩", "耗材剩余", "我的耗材"]):
            return True
        record_subject = self._contains_any(
            text,
            ["使用记录", "清扫记录", "清洁记录", "使用情况", "清洁效率", "清扫次数", "清洁次数"],
        )
        query_signal = self._contains_any(text, ["查", "看", "什么", "多少", "几次", "去年", "上个月", "这个月", "本月", "最近"])
        return record_subject and query_signal

    def _extract_order_hint(self, text: str) -> str:
        match = re.search(r"(ORD-[A-Za-z0-9-]+|\b\d{4,}\b)", str(text or ""), re.IGNORECASE)
        return match.group(1).upper() if match else ""

    def _extract_product_hint(self, text: str) -> str:
        for keyword in ["扫拖一体机器人", "无线吸尘器", "智能洗地机", "清洁耗材", "除螨仪"]:
            if keyword in text:
                return keyword
        return ""

    def _extract_month(self, text: str) -> str:
        match = re.search(r"(20\d{2})[年/-](\d{1,2})", str(text or ""))
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}"
        return ""

    def _is_too_vague(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", str(text or ""))
        if len(compact) <= 6 and self._contains_any(compact, ["坏了", "不好用", "有问题", "不行", "帮我"]):
            return True
        return compact in {"坏了", "有问题", "不好用", "不行", "帮我"}

    def _is_general_chat(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", str(text or "")).lower()
        if compact in {"你好", "您好", "hi", "hello", "在吗", "在不在"}:
            return True
        return self._contains_any(compact, ["你会干什么", "你能干什么", "你会什么", "有什么用", "功能介绍"])

    def _should_continue_presale(self, request: CustomerAssistantRequest) -> bool:
        latest = str(request.message or "")
        if self._contains_any(latest, ["退款", "退货", "订单", "物流", "故障", "报错", "不出水", "回不了充"]):
            return False
        current = request.presale_state
        has_context = bool(
            current.candidate_sku_ids
            or current.budget_min is not None
            or current.budget_max is not None
            or current.budget_target is not None
            or current.home_size_sqm is not None
            or current.home_size_level is not None
        )
        strong_signal = bool(
            re.search(r"\d{2,4}\s*(?:元|平米|平|㎡)", latest)
            or self._contains_any(latest, ["预算", "对比", "比较", "前两款", "净巡", "小户型", "大户型"])
        )
        contextual_signal = self._contains_any(
            latest,
            ["木地板", "瓷砖", "地毯", "有猫", "有狗", "宠物", "基站", "静音", "噪音"],
        )
        return strong_signal or (has_context and contextual_signal)

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _parse_json_object(self, content: str) -> dict:
        try:
            value = json.loads(content or "{}")
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", str(content or ""))
            if not match:
                return {}
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}

    def _message_content(self, result) -> str:
        return str(getattr(result, "content", result) or "").strip()

    def _parse_json(self, content: object, fallback):
        try:
            return json.loads(str(content or ""))
        except json.JSONDecodeError:
            return fallback

    def _truncate(self, text: str, limit: int) -> str:
        return text if len(text) <= limit else text[:limit] + "..."
