import unittest
import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

os.environ.setdefault("DASHSCOPE_API_KEY", "test")

from workOrderAI.agent.agent_context import get_current_username_value, is_tool_trace_active
from workOrderAI.app.model.customer_assistant import (
    CustomerAssistantMessage,
    CustomerAssistantRequest,
    CustomerAssistantResponse,
)
from workOrderAI.app.service.customer_assistant_graph import CustomerAssistantGraph, FaultConversationAssessment
from workOrderAI.app.service.customer_assistant_service import CustomerAssistantService
from workOrderAI.main import app


class DummyRouterModel:
    def __init__(self, content: str | Exception):
        self.content = content

    async def ainvoke(self, _prompt):
        if isinstance(self.content, Exception):
            raise self.content
        return AIMessage(content=self.content)


class DummyFaultAssessmentModel:
    def __init__(self, assessment: FaultConversationAssessment | Exception):
        self.assessment = assessment

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _prompt):
        if isinstance(self.assessment, Exception):
            raise self.assessment
        return self.assessment


class CustomerAssistantRouteTests(unittest.TestCase):
    def test_rule_routes_core_user_intents(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)

        self.assertEqual(graph._classify_route_by_rules("你好"), "GENERAL_CHAT")
        self.assertEqual(graph._classify_route_by_rules("你会干什么"), "GENERAL_CHAT")
        self.assertEqual(graph._classify_route_by_rules("我想买扫拖机器人，哪个型号适合小户型"), "PRESALE")
        self.assertEqual(graph._classify_route_by_rules("帮我查一下 ORD-USER-PAID 的物流"), "ORDER_QUERY")
        self.assertEqual(graph._classify_route_by_rules("我有哪些订单"), "ORDER_QUERY")
        self.assertEqual(graph._classify_route_by_rules("帮我查订单列表"), "ORDER_QUERY")
        self.assertEqual(graph._classify_route_by_rules("我买过什么"), "ORDER_QUERY")
        self.assertEqual(graph._classify_route_by_rules("我2025年12月有什么使用记录"), "USER_RECORD")
        self.assertEqual(graph._classify_route_by_rules("机器人不出水，有报错"), "AFTER_SALES_FAULT")
        self.assertEqual(graph._classify_route_by_rules("ORD-USER-PAID 我想退款"), "REFUND_AFTER_SALES")
        self.assertEqual(graph._classify_route_by_rules("股票能买吗"), "OUT_OF_SCOPE")

    def test_presale_state_keeps_short_follow_up_in_presale(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="有猫，木地板",
            presale_state={"budget_target": 2500, "home_size_sqm": 90},
        )

        self.assertTrue(graph._should_continue_presale(request))

    def test_refund_ticket_draft_never_promises_amount(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)

        draft = graph._build_ticket_draft("退款售后", "ORD-USER-PAID 我想退款", "退款售后", "AFTER_SALES")

        self.assertNotIn("可退金额", draft.description)
        self.assertNotIn("执行退款", draft.description)
        self.assertEqual(draft.category, "退款售后")
        self.assertEqual(draft.service_group, "AFTER_SALES")


class CustomerAssistantLlmRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_model_can_override_keyword_fallback(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyRouterModel(
            '{"route":"ORDER_QUERY","confidence":0.91,"reason":"用户想查看购买过的商品，属于订单查询"}'
        )

        route = await graph._classify_route("我想看看我买过的东西")

        self.assertEqual(route, "ORDER_QUERY")

    async def test_router_model_low_confidence_uses_rule_fallback(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyRouterModel(
            '{"route":"KNOWLEDGE_QA","confidence":0.3,"reason":"不确定"}'
        )

        route = await graph._classify_route("机器人不出水怎么办")

        self.assertEqual(route, "AFTER_SALES_FAULT")

    async def test_router_model_invalid_json_uses_rule_fallback(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyRouterModel("not json")

        route = await graph._classify_route("我有哪些订单")

        self.assertEqual(route, "ORDER_QUERY")

    async def test_router_model_exception_uses_rule_fallback(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyRouterModel(RuntimeError("boom"))

        route = await graph._classify_route("你会干什么")

        self.assertEqual(route, "GENERAL_CHAT")


class CustomerAssistantBranchTests(unittest.IsolatedAsyncioTestCase):
    async def test_general_chat_has_no_sources(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="你会干什么",
            history=[],
        )

        result = await CustomerAssistantGraph._general_chat_branch(graph, {"request": request})

        self.assertEqual(result.route, "GENERAL_CHAT")
        self.assertEqual(result.sources, [])
        self.assertIn("订单物流", result.reply)

    async def test_fault_branch_uses_llm_assessment_for_multi_turn_details(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyFaultAssessmentModel(
            FaultConversationAssessment(
                has_fault_context=True,
                information_sufficient=True,
                wants_human=False,
                concise_issue="扫地机器人充不上电，并且有绿灯闪烁。",
                missing_fields=[],
                reason="用户多轮描述了具体充电故障现象。",
            )
        )
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="有绿灯闪烁",
            history=[
                CustomerAssistantMessage(role="user", content="我的扫地机器人充不上电了，怎么办"),
                CustomerAssistantMessage(role="assistant", content="请补充具体异常现象。"),
            ],
        )

        with patch("workOrderAI.app.service.customer_assistant_graph.RagService") as rag_service_cls:
            rag_service_cls.return_value.rag_summary_for_suggestion = AsyncMock(
                return_value={"summary": "请先检查充电座和电源连接。", "sources": []}
            )
            result = await CustomerAssistantGraph._fault_branch(graph, {"request": request})

        self.assertEqual(result.action, "CREATE_TICKET")
        self.assertEqual(result.route, "AFTER_SALES_FAULT")
        self.assertIn("充不上电", result.ticket_draft.description)
        self.assertIn("绿灯闪烁", result.ticket_draft.description)

    async def test_fault_branch_transfer_human_with_context_creates_ticket(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyFaultAssessmentModel(
            FaultConversationAssessment(
                has_fault_context=True,
                information_sufficient=False,
                wants_human=True,
                concise_issue="扫地机器人充不上电，插上电后没有反应。",
                missing_fields=["设备型号"],
                reason="用户已有故障描述，并明确要求转人工。",
            )
        )
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="转人工",
            history=[
                CustomerAssistantMessage(role="user", content="我的扫地机器人充不上电了，怎么办"),
                CustomerAssistantMessage(role="user", content="插上电后没有反应"),
            ],
        )

        result = await CustomerAssistantGraph._fault_branch(graph, {"request": request})

        self.assertEqual(result.action, "CREATE_TICKET")
        self.assertIn("充不上电", result.ticket_draft.description)
        self.assertIn("没有反应", result.ticket_draft.description)
        self.assertNotEqual(result.ticket_draft.title, "售后故障：转人工")

    async def test_fault_branch_transfer_human_without_context_clarifies(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyFaultAssessmentModel(
            FaultConversationAssessment(
                has_fault_context=False,
                information_sufficient=False,
                wants_human=True,
                concise_issue="",
                missing_fields=["具体问题"],
                reason="只有转人工，没有故障上下文。",
            )
        )
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="转人工",
            history=[],
        )

        result = await CustomerAssistantGraph._fault_branch(graph, {"request": request})

        self.assertEqual(result.action, "CLARIFY")
        self.assertIsNone(result.ticket_draft)
        self.assertIn("具体问题", result.reply)

    async def test_fault_branch_never_creates_ticket_without_fault_context(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyFaultAssessmentModel(
            FaultConversationAssessment(
                has_fault_context=False,
                information_sufficient=True,
                wants_human=False,
                concise_issue="",
                missing_fields=["具体问题"],
                reason="没有故障上下文。",
            )
        )
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="帮我处理一下",
            history=[],
        )

        result = await CustomerAssistantGraph._fault_branch(graph, {"request": request})

        self.assertEqual(result.action, "CLARIFY")
        self.assertIsNone(result.ticket_draft)

    async def test_fault_branch_clarify_reply_uses_missing_fields(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyFaultAssessmentModel(
            FaultConversationAssessment(
                has_fault_context=True,
                information_sufficient=False,
                wants_human=False,
                concise_issue="机器人不好用。",
                missing_fields=["设备型号", "出现时间"],
                reason="缺少关键排查信息。",
            )
        )
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="机器人不好用",
            history=[],
        )

        result = await CustomerAssistantGraph._fault_branch(graph, {"request": request})

        self.assertEqual(result.action, "CLARIFY")
        self.assertIn("设备型号", result.reply)
        self.assertIn("出现时间", result.reply)
        self.assertNotEqual(
            result.reply,
            "为了更准确地帮您排查，请补充设备型号、具体异常现象、出现时间，以及是否有报错提示。",
        )

    async def test_fault_branch_model_exception_uses_safe_clarify(self):
        graph = CustomerAssistantGraph.__new__(CustomerAssistantGraph)
        graph.router_model = DummyFaultAssessmentModel(RuntimeError("boom"))
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="有绿灯闪烁",
            history=[
                CustomerAssistantMessage(role="user", content="我的扫地机器人充不上电了，怎么办"),
            ],
        )

        result = await CustomerAssistantGraph._fault_branch(graph, {"request": request})

        self.assertEqual(result.action, "CLARIFY")
        self.assertIsNone(result.ticket_draft)


class CustomerAssistantApiTests(unittest.TestCase):
    def test_customer_assistant_api_returns_structured_response(self):
        response_value = CustomerAssistantResponse(
            action="CLARIFY",
            route="REFUND_AFTER_SALES",
            reply="请提供订单号。",
        )
        with patch("workOrderAI.app.api.customer_assistant.CustomerAssistantService") as service_cls:
            service_cls.return_value.chat = AsyncMock(return_value=response_value)
            response = TestClient(app).post(
                "/ai/customer-assistant/chat",
                json={
                    "session_id": "as-1",
                    "owner_username": "user",
                    "message": "我要退款",
                    "history": [],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "CLARIFY")
        self.assertEqual(response.json()["route"], "REFUND_AFTER_SALES")


class CustomerAssistantServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_sets_and_resets_request_context(self):
        graph = AsyncMock()

        async def run(_request):
            self.assertEqual(get_current_username_value(), "user")
            self.assertTrue(is_tool_trace_active())
            return CustomerAssistantResponse(action="ANSWER", route="KNOWLEDGE_QA", reply="可以。")

        graph.run.side_effect = run
        request = CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="怎么保养？",
            history=[],
        )

        result = await CustomerAssistantService(graph=graph).chat(request)

        self.assertEqual(result.action, "ANSWER")
        self.assertEqual(get_current_username_value(), "")
        self.assertFalse(is_tool_trace_active())


if __name__ == "__main__":
    unittest.main()
