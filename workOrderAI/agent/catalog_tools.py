import json
import os

import httpx
from langchain_core.tools import tool

from workOrderAI.agent.agent_context import record_tool_call
from workOrderAI.utils.config import config
from workOrderAI.utils.logger_handler import logger


def _backend_settings() -> tuple[str, str]:
    backend_config = config.get("refund", {})
    base_url = os.getenv(
        "WORKORDER_BACKEND_BASE_URL",
        backend_config.get("backend_base_url", "http://localhost:8080"),
    ).rstrip("/")
    token = os.getenv(
        "WORKORDER_AI_INTERNAL_TOKEN",
        backend_config.get("internal_token", "local-refund-agent"),
    )
    return base_url, token


async def _post_catalog(path: str, body: dict) -> list[dict] | dict:
    base_url, token = _backend_settings()
    try:
        # 本地内部调用不继承系统代理，避免 localhost 被代理转发。
        async with httpx.AsyncClient(trust_env=False, timeout=10.0) as client:
            response = await client.post(
                f"{base_url}/api/internal/catalog/{path}",
                headers={"X-Internal-Agent-Token": token},
                json=body,
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            return {"error": "catalog_rejected", "reason": payload.get("msg", "")}
        data = payload.get("data")
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("[presale] catalog request failed path=%s error=%s", path, exc)
        return {"error": "catalog_unavailable"}


@tool(description="按预算、户型、地面、宠物、基站和噪音需求查询当前在售且有库存的扫拖机器人。")
async def search_products(
    budget_min: float | None = None,
    budget_max: float | None = None,
    budget_target: float | None = None,
    budget_flexible: bool = True,
    home_size_sqm: int | None = None,
    home_size_level: str | None = None,
    floor_types: list[str] | None = None,
    has_pet: bool | None = None,
    station_preference: bool | None = None,
    noise_sensitive: bool | None = None,
) -> str:
    body = {
        "budgetMin": budget_min,
        "budgetMax": budget_max,
        "budgetTarget": budget_target,
        "budgetFlexible": budget_flexible,
        "homeSizeSqm": home_size_sqm,
        "homeSizeLevel": home_size_level,
        "floorTypes": floor_types or [],
        "hasPet": has_pet,
        "stationPreference": station_preference,
        "noiseSensitive": noise_sensitive,
    }
    data = await _post_catalog("search", body)
    record_tool_call(
        "search_products",
        {key: value for key, value in body.items() if value not in (None, [], "")},
        {"product_count": len(data) if isinstance(data, list) else 0, "error": data.get("error") if isinstance(data, dict) else ""},
    )
    return json.dumps(data, ensure_ascii=False)


@tool(description="按SKU读取最多三款扫拖机器人的当前价格、库存和完整参数。")
async def get_product_details(sku_ids: list[str]) -> str:
    normalized = [str(item or "").strip() for item in (sku_ids or []) if str(item or "").strip()][:3]
    data = await _post_catalog("details", {"skuIds": normalized})
    record_tool_call(
        "get_product_details",
        {"sku_ids": normalized},
        {"product_count": len(data) if isinstance(data, list) else 0, "error": data.get("error") if isinstance(data, dict) else ""},
    )
    return json.dumps(data, ensure_ascii=False)
