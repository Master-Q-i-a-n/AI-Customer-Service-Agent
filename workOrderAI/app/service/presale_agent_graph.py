import json
import re
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from workOrderAI.agent.catalog_tools import get_product_details, search_products
from workOrderAI.app.model.customer_assistant import CustomerAssistantRequest, CustomerAssistantResponse
from workOrderAI.app.model.presale import (
    PresaleComparison,
    PresaleComparisonRow,
    PresaleNeedExtraction,
    PresaleProduct,
    PresaleState,
)
from workOrderAI.models.factory import router_model
from workOrderAI.utils.logger_handler import logger


PresaleAction = Literal["CLARIFY_NEED", "RECOMMEND", "COMPARE", "PRODUCT_QA"]
TARGET_BUDGET_TOLERANCE = 0.20
REQUIREMENT_FIELDS = (
    "budget_min",
    "budget_max",
    "budget_target",
    "budget_flexible",
    "budget_unlimited",
    "home_size_sqm",
    "home_size_level",
    "floor_types",
    "has_pet",
    "station_preference",
    "noise_sensitive",
)


class PresaleGraphState(TypedDict, total=False):
    request: CustomerAssistantRequest
    presale_state: PresaleState
    extraction: PresaleNeedExtraction
    action: PresaleAction
    response: CustomerAssistantResponse


class PresaleAgentGraph:
    def __init__(self, model=None, search_tool=None, detail_tool=None):
        self.model = model or router_model
        self.search_tool = search_tool or search_products
        self.detail_tool = detail_tool or get_product_details
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(PresaleGraphState)
        graph.add_node("extract_need", self.extract_need)
        graph.add_node("decide_action", self.decide_action)
        graph.add_node("clarify_need", self.clarify_need)
        graph.add_node("recommend", self.recommend)
        graph.add_node("compare", self.compare)
        graph.add_node("product_qa", self.product_qa)
        graph.add_edge(START, "extract_need")
        graph.add_edge("extract_need", "decide_action")
        graph.add_conditional_edges(
            "decide_action",
            lambda state: state["action"],
            {
                "CLARIFY_NEED": "clarify_need",
                "RECOMMEND": "recommend",
                "COMPARE": "compare",
                "PRODUCT_QA": "product_qa",
            },
        )
        graph.add_edge("clarify_need", END)
        graph.add_edge("recommend", END)
        graph.add_edge("compare", END)
        graph.add_edge("product_qa", END)
        return graph.compile()

    async def run(self, request: CustomerAssistantRequest) -> CustomerAssistantResponse:
        result = await self.graph.ainvoke({"request": request})
        return result["response"]

    async def extract_need(self, state: PresaleGraphState) -> dict:
        request = state["request"]
        original = PresaleState.model_validate(request.presale_state or {})
        current = self._normalize_target_budget(original)
        extraction = await self._extract_with_model(request, current)
        model_updates = extraction.model_dump(exclude_none=True, exclude={"intent"})
        if any(key in model_updates for key in ["budget_min", "budget_max", "budget_target", "budget_unlimited"]):
            model_updates["_budget_mentioned"] = True
        merged = self._merge_state(current, model_updates)
        merged = self._merge_state(merged, self._rule_updates(request.message))
        merged = self._normalize_target_budget(merged)
        if self._requirements_changed(original, merged):
            merged.candidate_sku_ids = []
            merged.candidate_names = []
        return {"presale_state": merged, "extraction": extraction}

    async def decide_action(self, state: PresaleGraphState) -> dict:
        request = state["request"]
        presale_state = state["presale_state"]
        latest = request.message
        extraction_intent = state.get("extraction", PresaleNeedExtraction()).intent

        if self._is_compare_request(latest) or extraction_intent == "COMPARE":
            action: PresaleAction = "COMPARE"
        elif self._is_product_question(latest, presale_state) or extraction_intent == "PRODUCT_QA":
            action = "PRODUCT_QA"
        elif self._ready_to_recommend(presale_state):
            action = "RECOMMEND"
        else:
            action = "CLARIFY_NEED"
        return {"action": action}

    async def clarify_need(self, state: PresaleGraphState) -> dict:
        presale_state = state["presale_state"]
        missing = []
        if not self._has_budget(presale_state):
            missing.append("预算范围或目标价")
        if presale_state.home_size_sqm is None and presale_state.home_size_level is None:
            missing.append("大致户型面积")
        if not missing:
            missing.append("更关注的使用场景")
        reply = "为了帮你筛出真正合适的型号，请补充" + "和".join(missing[:2]) + "。"
        return {
            "response": CustomerAssistantResponse(
                action="CLARIFY",
                route="PRESALE",
                reply=reply,
                presale_state=presale_state,
            )
        }

    async def recommend(self, state: PresaleGraphState) -> dict:
        presale_state = state["presale_state"]
        raw = await self.search_tool.ainvoke(self._search_args(presale_state))
        payload = self._parse_tool_payload(raw)
        if isinstance(payload, dict) and payload.get("error"):
            return {"response": self._tool_failure_response(presale_state)}

        products = [self._normalize_product(item) for item in payload[:3] if isinstance(item, dict)]
        products = [item for item in products if item is not None]
        if not products:
            presale_state.candidate_sku_ids = []
            presale_state.candidate_names = []
            return {
                "response": CustomerAssistantResponse(
                    action="CLARIFY",
                    route="PRESALE",
                    reply=self._no_match_reply(presale_state),
                    presale_state=presale_state,
                )
            }

        presale_state.candidate_sku_ids = [item.sku_id for item in products]
        presale_state.candidate_names = [item.name for item in products]
        overspend = [warning for item in products for warning in item.warnings]
        if presale_state.budget_target is not None:
            budget_range = self._budget_range_text(presale_state)
            reply = f"已按目标预算上下浮动 20%（{budget_range}）筛选出 {len(products)} 款在售且有库存的型号。"
        else:
            reply = f"根据你目前的预算和使用场景，筛选出 {len(products)} 款在售且有库存的型号。"
        if overspend:
            reply += "其中有商品略高于目标价，差额已在商品卡片中标明。"
        reply += "你可以查看详情，或者选择两款继续对比。"
        return {
            "response": CustomerAssistantResponse(
                action="ANSWER",
                route="PRESALE",
                reply=reply,
                products=products,
                presale_state=presale_state,
            )
        }

    async def compare(self, state: PresaleGraphState) -> dict:
        presale_state = state["presale_state"]
        sku_ids = self._resolve_compare_skus(state["request"].message, presale_state)
        if len(sku_ids) != 2:
            return {
                "response": CustomerAssistantResponse(
                    action="CLARIFY",
                    route="PRESALE",
                    reply="请选择两款商品进行对比，例如“对比第一款和第二款”。",
                    presale_state=presale_state,
                )
            }

        raw = await self.detail_tool.ainvoke({"sku_ids": sku_ids})
        payload = self._parse_tool_payload(raw)
        if isinstance(payload, dict) and payload.get("error"):
            return {"response": self._tool_failure_response(presale_state)}
        products = [self._normalize_product(item) for item in payload if isinstance(item, dict)]
        products = [item for item in products if item is not None]
        if len(products) != 2:
            return {"response": self._tool_failure_response(presale_state)}

        comparison = self._build_comparison(products, presale_state)
        return {
            "response": CustomerAssistantResponse(
                action="ANSWER",
                route="PRESALE",
                reply="已按当前价格、库存和核心参数完成对比，结合你前面提供的需求给出了选择建议。",
                products=products,
                comparison=comparison,
                presale_state=presale_state,
            )
        }

    async def product_qa(self, state: PresaleGraphState) -> dict:
        presale_state = state["presale_state"]
        sku_id = self._resolve_single_sku(state["request"].message, presale_state)
        if not sku_id:
            return {
                "response": CustomerAssistantResponse(
                    action="CLARIFY",
                    route="PRESALE",
                    reply="请说明想了解哪一款商品，或先让我根据预算和户型为你推荐。",
                    presale_state=presale_state,
                )
            }
        raw = await self.detail_tool.ainvoke({"sku_ids": [sku_id]})
        payload = self._parse_tool_payload(raw)
        if isinstance(payload, dict) and payload.get("error"):
            return {"response": self._tool_failure_response(presale_state)}
        product = self._normalize_product(payload[0]) if isinstance(payload, list) and payload else None
        if product is None:
            return {"response": self._tool_failure_response(presale_state)}
        attrs = product.attributes
        reply = (
            f"{product.name} 当前售价 ¥{product.price:.0f}，库存 {product.stock} 件；"
            f"吸力 {attrs.get('suction_pa', '--')}Pa，续航约 {attrs.get('runtime_minutes', '--')} 分钟，"
            f"适用面积最高 {attrs.get('home_size_max', '--')}㎡。详细参数可以在商品卡片中查看。"
        )
        return {
            "response": CustomerAssistantResponse(
                action="ANSWER",
                route="PRESALE",
                reply=reply,
                products=[product],
                presale_state=presale_state,
            )
        }

    async def _extract_with_model(
        self,
        request: CustomerAssistantRequest,
        current: PresaleState,
    ) -> PresaleNeedExtraction:
        prompt = f"""你是扫拖机器人售前需求提取器。只提取用户最新消息明确表达的信息，不猜测。

预算规则：
- “最多/以内/不超过”是硬上限，budget_flexible=false。
- 明确区间是硬范围，budget_flexible=false。
- “预算3000/3000左右/大概3000”是目标价，提取 budget_target=3000；系统会将其转换为上下浮动 20% 的硬推荐范围。
- “预算不限”设置 budget_unlimited=true。
- 用户说没有宠物、不要基站、不在意噪音时，相应布尔值必须为 false。
- intent 只在用户明确要比较、询问具体型号参数、要求推荐时填写。

已有状态：{current.model_dump_json()}
用户最新消息：{request.message}
"""
        try:
            result = await self.model.with_structured_output(PresaleNeedExtraction).ainvoke(prompt)
            if isinstance(result, PresaleNeedExtraction):
                return result
            if isinstance(result, dict):
                return PresaleNeedExtraction(**result)
            if hasattr(result, "model_dump"):
                return PresaleNeedExtraction(**result.model_dump())
        except Exception as exc:
            logger.warning("[presale] structured extraction failed, use rules, error=%s", exc)
        return PresaleNeedExtraction()

    def _rule_updates(self, text: str) -> dict:
        normalized = re.sub(r"\s+", "", str(text or ""))
        updates: dict = {}
        range_match = re.search(r"(\d+(?:\.\d+)?)元?(?:到|至|[-~～])(\d+(?:\.\d+)?)元?", normalized)
        max_match = re.search(r"(?:最多|最高|不超过|不要超过)(\d+(?:\.\d+)?)元?", normalized)
        suffix_max_match = re.search(r"(\d+(?:\.\d+)?)元?(?:以内|以下)", normalized)
        target_match = re.search(r"(?:预算|大概|差不多)?(\d+(?:\.\d+)?)元?(?:左右|上下)", normalized)
        simple_budget_match = re.search(r"预算(?:改成|调整到|提高到|降到|大概|约)?(\d+(?:\.\d+)?)元?", normalized)
        if "预算不限" in normalized or "价格不限" in normalized:
            updates.update({
                "_budget_mentioned": True,
                "budget_min": None,
                "budget_max": None,
                "budget_target": None,
                "budget_flexible": True,
                "budget_unlimited": True,
            })
        elif range_match:
            updates.update({
                "_budget_mentioned": True,
                "budget_min": float(range_match.group(1)),
                "budget_max": float(range_match.group(2)),
                "budget_target": None,
                "budget_flexible": False,
                "budget_unlimited": False,
            })
        elif max_match or suffix_max_match:
            match = max_match or suffix_max_match
            updates.update({
                "_budget_mentioned": True,
                "budget_min": None,
                "budget_max": float(match.group(1)),
                "budget_target": None,
                "budget_flexible": False,
                "budget_unlimited": False,
            })
        elif target_match or simple_budget_match:
            match = target_match or simple_budget_match
            target = float(match.group(1))
            updates.update({
                "_budget_mentioned": True,
                "budget_min": round(target * (1 - TARGET_BUDGET_TOLERANCE), 2),
                "budget_max": round(target * (1 + TARGET_BUDGET_TOLERANCE), 2),
                "budget_target": target,
                "budget_flexible": False,
                "budget_unlimited": False,
            })

        size_match = re.search(r"(\d{2,3})\s*(?:平米|平|㎡)", str(text or ""))
        if size_match:
            updates.update({"home_size_sqm": int(size_match.group(1)), "home_size_level": None})
        elif "小户型" in normalized:
            updates["home_size_level"] = "SMALL"
        elif "大户型" in normalized:
            updates["home_size_level"] = "LARGE"
        elif "中等户型" in normalized or "中户型" in normalized:
            updates["home_size_level"] = "MEDIUM"

        floors = [item for item in ["木地板", "瓷砖"] if item in normalized]
        # 具体地毯类型优先，避免“短毛地毯”同时生成泛化的“地毯”硬条件。
        if "短毛地毯" in normalized:
            floors.append("短毛地毯")
        elif "地毯" in normalized:
            floors.append("地毯")
        if floors:
            updates["floor_types"] = list(dict.fromkeys(floors))
        if any(item in normalized for item in ["没有宠物", "不养宠物", "没养猫", "没养狗"]):
            updates["has_pet"] = False
        elif any(item in normalized for item in ["有猫", "养猫", "有狗", "养狗", "养宠物", "宠物家庭"]):
            updates["has_pet"] = True
        if any(item in normalized for item in ["不要基站", "不需要基站", "无需基站"]):
            updates["station_preference"] = False
        elif "基站" in normalized:
            updates["station_preference"] = True
        if any(item in normalized for item in ["不在意噪音", "噪音无所谓"]):
            updates["noise_sensitive"] = False
        elif any(item in normalized for item in ["静音", "安静", "噪音低", "在意噪音", "怕吵"]):
            updates["noise_sensitive"] = True
        return updates

    def _merge_state(self, current: PresaleState, updates: dict) -> PresaleState:
        data = current.model_dump()
        updates = dict(updates or {})
        if updates.pop("_budget_mentioned", False):
            budget_min = updates.pop("budget_min", None)
            budget_max = updates.pop("budget_max", None)
            budget_target = updates.pop("budget_target", None)
            budget_unlimited = updates.pop("budget_unlimited", False)
            data.update({
                "budget_min": budget_min,
                "budget_max": budget_max,
                "budget_target": budget_target,
                "budget_flexible": updates.pop(
                    "budget_flexible",
                    bool(budget_target is not None or budget_unlimited),
                ),
                "budget_unlimited": budget_unlimited,
            })
        for key, value in updates.items():
            if key not in data or value is None:
                continue
            data[key] = value
        return PresaleState.model_validate(data)

    def _normalize_target_budget(self, state: PresaleState) -> PresaleState:
        if state.budget_unlimited or state.budget_target is None or state.budget_target <= 0:
            return state
        if state.budget_min is not None or state.budget_max is not None:
            return state
        data = state.model_dump()
        data["budget_min"] = round(state.budget_target * (1 - TARGET_BUDGET_TOLERANCE), 2)
        data["budget_max"] = round(state.budget_target * (1 + TARGET_BUDGET_TOLERANCE), 2)
        data["budget_flexible"] = False
        return PresaleState.model_validate(data)

    def _requirements_changed(self, previous: PresaleState, current: PresaleState) -> bool:
        return any(getattr(previous, field) != getattr(current, field) for field in REQUIREMENT_FIELDS)

    def _ready_to_recommend(self, state: PresaleState) -> bool:
        has_home = state.home_size_sqm is not None or state.home_size_level is not None
        return has_home and self._has_budget(state)

    def _has_budget(self, state: PresaleState) -> bool:
        return state.budget_unlimited or any(
            value is not None for value in [state.budget_min, state.budget_max, state.budget_target]
        )

    def _search_args(self, state: PresaleState) -> dict:
        return {
            "budget_min": state.budget_min,
            "budget_max": state.budget_max,
            "budget_target": state.budget_target,
            "budget_flexible": state.budget_flexible,
            "home_size_sqm": state.home_size_sqm,
            "home_size_level": state.home_size_level,
            "floor_types": state.floor_types,
            "has_pet": state.has_pet,
            "station_preference": state.station_preference,
            "noise_sensitive": state.noise_sensitive,
        }

    def _normalize_product(self, item: dict) -> PresaleProduct | None:
        try:
            return PresaleProduct(
                product_id=str(item.get("productId") or item.get("product_id") or ""),
                sku_id=str(item.get("skuId") or item.get("sku_id") or ""),
                name=str(item.get("name") or ""),
                sku_name=str(item.get("skuName") or item.get("sku_name") or ""),
                category=str(item.get("category") or "扫拖机器人"),
                summary=str(item.get("summary") or ""),
                image_url=str(item.get("imageUrl") or item.get("image_url") or ""),
                price=float(item.get("price") or 0),
                stock=int(item.get("stock") or 0),
                attributes=item.get("attributes") if isinstance(item.get("attributes"), dict) else {},
                highlights=list(item.get("highlights") or []),
                match_reasons=list(item.get("matchReasons") or item.get("match_reasons") or []),
                warnings=list(item.get("warnings") or []),
            )
        except (TypeError, ValueError):
            return None

    def _resolve_compare_skus(self, text: str, state: PresaleState) -> list[str]:
        if len(state.candidate_sku_ids) < 2:
            return []
        normalized = str(text or "")
        selected: list[str] = []
        for name, sku_id in zip(state.candidate_names, state.candidate_sku_ids):
            if name and name in normalized:
                selected.append(sku_id)
        if len(selected) >= 2:
            return selected[:2]
        if "前两款" in normalized or "前2款" in normalized:
            return state.candidate_sku_ids[:2]
        index_map = {"一": 0, "二": 1, "三": 2, "1": 0, "2": 1, "3": 2}
        for value in re.findall(r"第([一二三123])款", normalized):
            index = index_map[value]
            if index < len(state.candidate_sku_ids):
                selected.append(state.candidate_sku_ids[index])
        return list(dict.fromkeys(selected))[:2]

    def _resolve_single_sku(self, text: str, state: PresaleState) -> str:
        normalized = str(text or "")
        for name, sku_id in zip(state.candidate_names, state.candidate_sku_ids):
            if name and name in normalized:
                return sku_id
        index_map = {"一": 0, "二": 1, "三": 2, "1": 0, "2": 1, "3": 2}
        match = re.search(r"第([一二三123])款", normalized)
        if match:
            index = index_map[match.group(1)]
            if index < len(state.candidate_sku_ids):
                return state.candidate_sku_ids[index]
        return state.candidate_sku_ids[0] if len(state.candidate_sku_ids) == 1 else ""

    def _build_comparison(self, products: list[PresaleProduct], state: PresaleState) -> PresaleComparison:
        rows = [
            self._comparison_row("当前价格", products, lambda item: f"¥{item.price:.0f}"),
            self._comparison_row("适用面积", products, lambda item: f"最高 {item.attributes.get('home_size_max', '--')}㎡"),
            self._comparison_row("吸力", products, lambda item: f"{item.attributes.get('suction_pa', '--')}Pa"),
            self._comparison_row("续航", products, lambda item: f"{item.attributes.get('runtime_minutes', '--')} 分钟"),
            self._comparison_row("导航", products, lambda item: str(item.attributes.get("navigation", "--"))),
            self._comparison_row("避障", products, lambda item: str(item.attributes.get("obstacle_avoidance", "--"))),
            self._comparison_row("基站", products, lambda item: str(item.attributes.get("station_type", "无"))),
            self._comparison_row("噪音", products, lambda item: f"约 {item.attributes.get('noise_db', '--')}dB"),
            self._comparison_row("防缠绕", products, lambda item: "支持" if item.attributes.get("anti_tangle") else "不支持"),
        ]
        preferred = max(products, key=lambda item: self._local_match_score(item, state))
        recommendation = f"结合当前预算和户型，更推荐 {preferred.name}；它与已确认需求的综合匹配度更高。"
        return PresaleComparison(
            product_names=[item.name for item in products],
            rows=rows,
            recommendation=recommendation,
        )

    def _comparison_row(self, label: str, products: list[PresaleProduct], formatter) -> PresaleComparisonRow:
        return PresaleComparisonRow(label=label, values=[formatter(item) for item in products])

    def _local_match_score(self, product: PresaleProduct, state: PresaleState) -> float:
        attrs = product.attributes
        score = 0.0
        if state.budget_target and state.budget_target > 0:
            score += max(0, 40 - abs(product.price - state.budget_target) / state.budget_target * 40)
        if state.home_size_sqm and int(attrs.get("home_size_max") or 0) >= state.home_size_sqm:
            score += 25
        if state.has_pet and attrs.get("pet_friendly"):
            score += 20
        station = str(attrs.get("station_type") or "无")
        if state.station_preference is True and station != "无":
            score += 10
        if state.station_preference is False and station == "无":
            score += 10
        if state.noise_sensitive:
            score += max(0, 10 - max(0, int(attrs.get("noise_db") or 60) - 52))
        return score

    def _no_match_reply(self, state: PresaleState) -> str:
        if state.budget_target is not None and state.budget_min is not None and state.budget_max is not None:
            return (
                f"当前目标预算的推荐范围是 {self._budget_range_text(state)}，没有同时满足使用场景的在售商品。"
                "请提供新的预算上限或预算范围。"
            )
        if not state.budget_flexible and (state.budget_min is not None or state.budget_max is not None):
            return "当前没有同时满足明确预算和使用场景的在售商品。请提供新的预算上限或预算范围。"
        if state.station_preference is not None:
            return "当前没有同时满足户型和基站要求的在售商品。是否愿意调整基站偏好？"
        return "当前没有同时满足这些条件的在售商品。是否愿意调整其中一个使用条件？"

    def _budget_range_text(self, state: PresaleState) -> str:
        return f"¥{self._format_budget(state.budget_min)}–¥{self._format_budget(state.budget_max)}"

    def _format_budget(self, value: float | None) -> str:
        if value is None:
            return "--"
        return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")

    def _tool_failure_response(self, state: PresaleState) -> CustomerAssistantResponse:
        return CustomerAssistantResponse(
            action="ANSWER",
            route="PRESALE",
            reply="商品价格和库存暂时无法查询。为避免给出不准确的推荐，请稍后再试。",
            presale_state=state,
        )

    def _is_compare_request(self, text: str) -> bool:
        return any(keyword in str(text or "") for keyword in ["对比", "比较", "区别", "哪个更", "前两款"])

    def _is_product_question(self, text: str, state: PresaleState) -> bool:
        normalized = str(text or "")
        has_reference = any(name and name in normalized for name in state.candidate_names) or bool(
            re.search(r"第[一二三123]款", normalized)
        )
        asks_detail = any(keyword in normalized for keyword in ["详情", "参数", "吸力", "续航", "噪音", "导航", "避障", "基站"])
        return has_reference and asks_detail

    def _parse_tool_payload(self, raw: object):
        if isinstance(raw, (list, dict)):
            return raw
        try:
            value = json.loads(str(raw or ""))
            return value if isinstance(value, (list, dict)) else []
        except json.JSONDecodeError:
            return {"error": "invalid_tool_response"}
