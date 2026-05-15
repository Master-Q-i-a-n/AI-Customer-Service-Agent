import datetime
import json

import httpx
from langchain_core.tools import tool

from workOrderAI.agent.agent_context import get_current_username_value
from workOrderAI.app.model.database import get_db_connection
from workOrderAI.app.service.rag_service import RagService
from workOrderAI.utils.logger_handler import logger


@tool(description="Summarize related knowledge base content for the current question.")
async def rag_summarize(query: str) -> str:
    result = await RagService().rag_summary(query)
    return result


@tool(description="Get the current local time.")
async def get_time_now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


@tool(description="Get the current city from the public IP address.")
async def get_current_city() -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://myip.ipip.net/json", timeout=5.0)
            data = response.json()
            city = data.get("data", {}).get("location", [])[2] if data.get("data") else "unknown"
            return f"current city: {city}"
    except Exception as e:
        return f"failed to get current city: {e}"


@tool(description="Get current weather information.")
async def get_weather(city: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast"
                "?latitude=31.23&longitude=121.47"
                "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                "&timezone=Asia/Shanghai",
                timeout=15.0,
            )
            data = response.json()
            current = data.get("current", {})
            temp = current.get("temperature_2m", "unknown")
            humidity = current.get("relative_humidity_2m", "unknown")
            wind_speed = current.get("wind_speed_10m", "unknown")
            return f"{city} weather: temperature {temp}C, humidity {humidity}%, wind speed {wind_speed}km/h"
    except Exception as e:
        return f"failed to get weather: {e}"


def _format_user_records(rows: list[dict]) -> str:
    records = [
        {
            "\u65f6\u95f4": row.get("record_month") or "",
            "\u7279\u5f81": row.get("feature") or "",
            "\u6e05\u6d01\u6548\u7387": row.get("clean_efficiency") or "",
            "\u8017\u6750": row.get("consumable") or "",
            "\u5bf9\u6bd4": row.get("comparison") or "",
        }
        for row in rows
    ]
    return json.dumps(records, ensure_ascii=False)


@tool(description="Get the username of the current work order owner.")
def get_current_username() -> str:
    return get_current_username_value()


@tool(description="Fetch user records from the user_records database table by user id and optional month.")
def fetch_external_data(user_id: str, month: str = "") -> str:
    user_id = str(user_id or "").strip()
    month = str(month or "").strip()
    if not user_id:
        logger.warning("[fetch_external_data] user_id is empty")
        return ""

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            if month:
                cursor.execute(
                    """
                    select record_month, feature, clean_efficiency, consumable, comparison
                    from user_records
                    where owner_username = %s and record_month = %s
                    order by record_month asc
                    """,
                    (user_id, month),
                )
            else:
                cursor.execute(
                    """
                    select record_month, feature, clean_efficiency, consumable, comparison
                    from user_records
                    where owner_username = %s
                    order by record_month asc
                    """,
                    (user_id,),
                )
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"[fetch_external_data] database query failed: {e}", exc_info=True)
        return ""
    finally:
        if conn:
            conn.close()

    if not rows:
        logger.warning(f"[fetch_external_data] no records found for user_id={user_id}, month={month or '*'}")
        return ""

    return _format_user_records(rows)


def get_tools():
    return [
        rag_summarize,
        get_time_now,
        get_current_city,
        get_weather,
        get_current_username,
        fetch_external_data,
    ]


if __name__ == "__main__":
    import asyncio

    async def test():
        city_result = await get_current_city.ainvoke({})
        print(city_result)
        city = city_result.replace("current city:", "").strip()
        weather_result = await get_weather.ainvoke({"city": city})
        print(weather_result)

    asyncio.run(test())
