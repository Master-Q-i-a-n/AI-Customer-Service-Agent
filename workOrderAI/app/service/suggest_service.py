from workOrderAI.utils.prompt_builder import REPLY_SUGGESTION_AGENT_PROMPT
from workOrderAI.models.factory import chat_model
from workOrderAI.agent.agent import ReactAgent
import json

from workOrderAI.agent.agent_context import (
    get_tool_trace,
    is_tool_trace_active,
    reset_current_username,
    reset_tool_trace,
    set_current_username,
    start_tool_trace,
)
from workOrderAI.app.model.request import ReplySuggestRequest, ReplyMessage
from workOrderAI.app.model.response import ReplySuggestResponse, SourceTemplate
from workOrderAI.app.service.case_memory_service import CaseMemoryService
from workOrderAI.utils.logger_handler import logger



class SuggestService:
    def __init__(self):
        self.agent = ReactAgent(REPLY_SUGGESTION_AGENT_PROMPT)

    async def get_suggestion(self, work_order: ReplySuggestRequest):
        return (await self.get_suggestion_result(work_order)).suggested_reply

    async def get_suggestion_result(self, work_order: ReplySuggestRequest) -> ReplySuggestResponse:
        """
        获取工单建议，并返回本轮可参考的历史案例来源。
        """
        try:
            prefetched_cases = await CaseMemoryService().search_similar_cases(
                self._build_case_query(work_order)
            )
        except Exception as exc:
            logger.error("[suggestion] prefetch similar cases failed: %s", exc, exc_info=True)
            prefetched_cases = []

        input = f'标题：{work_order.title}\n内容：{work_order.description}\n'
        input += self._format_prefetched_cases(prefetched_cases)
        input += '用户(user)和客服(service)的对话记录：\n'
        for reply in work_order.history:
            input += f'{reply.role}：{reply.content}\n'

        username_token = set_current_username(work_order.owner_username)
        owns_trace = not is_tool_trace_active()
        trace_token = start_tool_trace() if owns_trace else None
        try:
            suggestion_reply = await self.agent.execute_invoke(input)
            source_templates = self._merge_case_sources(
                self._build_case_sources(prefetched_cases),
                self._extract_case_sources(get_tool_trace()),
            )
        finally:
            reset_current_username(username_token)
            if trace_token is not None:
                reset_tool_trace(trace_token)

        return ReplySuggestResponse(
            suggested_reply=suggestion_reply,
            source_templates=source_templates,
        )

    def _build_case_query(self, work_order: ReplySuggestRequest) -> str:
        return f"{work_order.title}\n{work_order.description}".strip()

    def _format_prefetched_cases(self, cases: list[dict]) -> str:
        if not cases:
            return ""

        lines = ["可参考的历史案例："]
        for index, case in enumerate(cases, 1):
            lines.append(
                f"{index}. 编号：{case.get('ticket_code') or case.get('ticket_id') or '--'}；"
                f"标题：{case.get('title') or '--'}；"
                f"最终客服回复：{case.get('final_reply') or ''}"
            )
        return "\n".join(lines) + "\n"

    def _build_case_sources(self, cases: list[dict]) -> list[SourceTemplate]:
        sources = []
        for case in cases:
            ticket_id = str(case.get("ticket_id") or "").strip()
            if not ticket_id:
                continue
            sources.append(self._to_source_template(case))
        return sources

    def _extract_case_sources(self, tool_trace: list[dict]) -> list[SourceTemplate]:
        sources = []
        for item in tool_trace:
            if item.get("name") != "fetch_similar_cases":
                continue
            try:
                cases = json.loads(item.get("output") or "[]")
            except json.JSONDecodeError:
                continue
            for case in cases if isinstance(cases, list) else []:
                ticket_id = str(case.get("ticket_id") or "").strip()
                if not ticket_id:
                    continue
                sources.append(self._to_source_template(case))
        return sources

    def _merge_case_sources(self, *groups: list[SourceTemplate]) -> list[SourceTemplate]:
        merged = []
        seen = set()
        for group in groups:
            for source in group:
                if source.ticket_id in seen:
                    continue
                seen.add(source.ticket_id)
                merged.append(source)
        return merged

    def _to_source_template(self, case: dict) -> SourceTemplate:
        return SourceTemplate(
            ticket_id=str(case.get("ticket_id") or ""),
            ticket_code=str(case.get("ticket_code") or ""),
            title=str(case.get("title") or ""),
            final_reply=str(case.get("final_reply") or ""),
            similarity_score=float(case.get("similarity_score") or 0.0),
        )

if __name__ == '__main__':
    import asyncio
    async def main():
        suggest_service = SuggestService()
        work_order = ReplySuggestRequest(
            id='123456',
            title='扫地机器人坏了',
            description='扫地机器人不能工作，怎么办？',
            category='咨询',
            emotion='愤怒',
            history=[
                ReplyMessage(role='service', content='我也不知道'),
                ReplyMessage(role='user', content='怎么当客服的？？？'),
            ]
        )
        suggestion = await suggest_service.get_suggestion(work_order)
        print(suggestion)

    asyncio.run(main())

