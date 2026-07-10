import json
import os
import unittest

os.environ.setdefault("DASHSCOPE_API_KEY", "test")

from workOrderAI.app.model.customer_assistant import CustomerAssistantRequest
from workOrderAI.app.model.presale import PresaleNeedExtraction, PresaleState
from workOrderAI.app.service.presale_agent_graph import PresaleAgentGraph


class EmptyExtractionModel:
    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _prompt):
        return PresaleNeedExtraction()


class DummyTool:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def ainvoke(self, payload):
        self.calls.append(payload)
        return self.result


def product(
    sku_id: str,
    name: str,
    price: float,
    home_size: int,
    suction: int,
    station: str,
    noise: int,
):
    return {
        "productId": "product-" + sku_id,
        "skuId": sku_id,
        "name": name,
        "skuName": "标准版",
        "category": "扫拖机器人",
        "summary": "商品简介",
        "imageUrl": "/products/test.png",
        "price": price,
        "stock": 10,
        "attributes": {
            "home_size_max": home_size,
            "floor_types": ["木地板", "瓷砖"],
            "pet_friendly": True,
            "suction_pa": suction,
            "runtime_minutes": 150,
            "navigation": "激光导航",
            "obstacle_avoidance": "3D结构光",
            "mop_lift": True,
            "anti_tangle": True,
            "station_type": station,
            "noise_db": noise,
        },
        "highlights": [f"{suction}Pa 吸力"],
        "matchReasons": ["适合宠物家庭"],
        "warnings": [],
    }


class PresaleBudgetRuleTests(unittest.TestCase):
    def setUp(self):
        self.graph = PresaleAgentGraph.__new__(PresaleAgentGraph)

    def merged(self, text: str) -> PresaleState:
        return self.graph._merge_state(PresaleState(), self.graph._rule_updates(text))

    def test_budget_language_has_stable_semantics(self):
        hard_max = self.merged("最多2500元")
        self.assertEqual(hard_max.budget_max, 2500)
        self.assertFalse(hard_max.budget_flexible)

        hard_range = self.merged("预算2000到3000元")
        self.assertEqual((hard_range.budget_min, hard_range.budget_max), (2000, 3000))
        self.assertFalse(hard_range.budget_flexible)

        for text in ["预算3000", "预算3000左右", "大概3000上下"]:
            with self.subTest(text=text):
                target = self.merged(text)
                self.assertEqual(target.budget_target, 3000)
                self.assertEqual((target.budget_min, target.budget_max), (2400, 3600))
                self.assertFalse(target.budget_flexible)

    def test_explicit_new_budget_clears_old_budget_shape(self):
        current = PresaleState(budget_min=2000, budget_max=3000, budget_flexible=False)
        updated = self.graph._merge_state(current, self.graph._rule_updates("预算改成3500"))
        self.assertEqual(updated.budget_min, 2800)
        self.assertEqual(updated.budget_max, 4200)
        self.assertEqual(updated.budget_target, 3500)
        self.assertFalse(updated.budget_flexible)

    def test_legacy_target_state_is_normalized_to_hard_window(self):
        legacy = PresaleState(budget_target=2000, budget_flexible=True)
        normalized = self.graph._normalize_target_budget(legacy)
        self.assertEqual((normalized.budget_min, normalized.budget_max), (1600, 2400))
        self.assertFalse(normalized.budget_flexible)

    def test_specific_carpet_type_does_not_add_generic_hard_condition(self):
        state = self.merged("家里有木地板和短毛地毯")
        self.assertEqual(state.floor_types, ["木地板", "短毛地毯"])


class PresaleAgentFlowTests(unittest.IsolatedAsyncioTestCase):
    def build_graph(self, search_result=None, detail_result=None):
        search = DummyTool(json.dumps(search_result if search_result is not None else [], ensure_ascii=False))
        details = DummyTool(json.dumps(detail_result if detail_result is not None else [], ensure_ascii=False))
        return PresaleAgentGraph(EmptyExtractionModel(), search, details), search, details

    async def test_vague_need_clarifies_budget_and_home_size(self):
        graph, search, _ = self.build_graph()
        result = await graph.run(CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="想买扫地机器人",
        ))

        self.assertEqual(result.action, "CLARIFY")
        self.assertIn("预算", result.reply)
        self.assertIn("户型面积", result.reply)
        self.assertEqual(search.calls, [])

    async def test_multi_slot_message_searches_and_persists_candidates(self):
        p2 = product("sku-p2-gray", "净巡 P2 Pet", 2299, 120, 5500, "自动集尘", 56)
        graph, search, _ = self.build_graph([p2])
        result = await graph.run(CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="90平，预算2500，有猫，木地板",
        ))

        self.assertEqual(result.action, "ANSWER")
        self.assertEqual(result.products[0].sku_id, "sku-p2-gray")
        self.assertEqual(result.presale_state.budget_target, 2500)
        self.assertEqual((result.presale_state.budget_min, result.presale_state.budget_max), (2000, 3000))
        self.assertFalse(result.presale_state.budget_flexible)
        self.assertEqual(result.presale_state.home_size_sqm, 90)
        self.assertTrue(result.presale_state.has_pet)
        self.assertEqual(result.presale_state.candidate_sku_ids, ["sku-p2-gray"])
        self.assertEqual(search.calls[0]["budget_target"], 2500)
        self.assertEqual((search.calls[0]["budget_min"], search.calls[0]["budget_max"]), (2000, 3000))
        self.assertFalse(search.calls[0]["budget_flexible"])

    async def test_compare_front_two_uses_stored_candidates(self):
        m3 = product("sku-m3-white", "净巡 M3 Station", 3299, 150, 6500, "集尘洗拖烘干基站", 54)
        x4 = product("sku-x4-black", "净巡 X4 Max", 4599, 220, 8000, "全能自清洁基站", 52)
        graph, _, details = self.build_graph(detail_result=[m3, x4])
        result = await graph.run(CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="前两款对比一下",
            presale_state=PresaleState(
                budget_min=3200,
                budget_max=4800,
                budget_target=4000,
                budget_flexible=False,
                home_size_sqm=90,
                candidate_sku_ids=["sku-m3-white", "sku-x4-black"],
                candidate_names=["净巡 M3 Station", "净巡 X4 Max"],
            ),
        ))

        self.assertEqual(result.action, "ANSWER")
        self.assertEqual(result.comparison.product_names, ["净巡 M3 Station", "净巡 X4 Max"])
        self.assertEqual(details.calls[0], {"sku_ids": ["sku-m3-white", "sku-x4-black"]})
        self.assertIn("更推荐", result.comparison.recommendation)

    async def test_no_match_requests_one_constraint_relaxation(self):
        graph, _, _ = self.build_graph([])
        result = await graph.run(CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="90平，最多1000元",
        ))

        self.assertEqual(result.action, "CLARIFY")
        self.assertIn("新的预算", result.reply)
        self.assertEqual(result.products, [])

    async def test_changed_budget_clears_stale_candidates_when_no_match(self):
        graph, _, _ = self.build_graph([])
        result = await graph.run(CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="预算改成3000",
            presale_state=PresaleState(
                budget_min=1600,
                budget_max=2400,
                budget_target=2000,
                budget_flexible=False,
                home_size_sqm=90,
                candidate_sku_ids=["sku-p2-gray"],
                candidate_names=["净巡 P2 Pet"],
            ),
        ))

        self.assertEqual(result.action, "CLARIFY")
        self.assertEqual((result.presale_state.budget_min, result.presale_state.budget_max), (2400, 3600))
        self.assertEqual(result.presale_state.candidate_sku_ids, [])
        self.assertIn("¥2400–¥3600", result.reply)

    async def test_legacy_target_state_clears_candidates_before_recommendation(self):
        graph, _, _ = self.build_graph([])
        result = await graph.run(CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="继续推荐",
            presale_state=PresaleState(
                budget_target=2000,
                budget_flexible=True,
                home_size_sqm=90,
                candidate_sku_ids=["sku-x4-black"],
                candidate_names=["净巡 X4 Max"],
            ),
        ))

        self.assertEqual((result.presale_state.budget_min, result.presale_state.budget_max), (1600, 2400))
        self.assertEqual(result.presale_state.candidate_sku_ids, [])

    async def test_catalog_failure_never_invents_product_facts(self):
        graph, _, _ = self.build_graph(search_result={"error": "catalog_unavailable"})
        result = await graph.run(CustomerAssistantRequest(
            session_id="as-1",
            owner_username="user",
            message="小户型，预算2000左右",
        ))

        self.assertEqual(result.action, "ANSWER")
        self.assertIn("暂时无法查询", result.reply)
        self.assertEqual(result.products, [])


if __name__ == "__main__":
    unittest.main()
