import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from workOrderAI.app.service.rag_service import (
    HYDE_MAX_TOKENS,
    KNOWLEDGE_NO_ANSWER_SUMMARY,
    RagService,
)
from workOrderAI.utils.prompt_builder import QUESTION_HYDE_PROMPT, STATEMENT_HYDE_PROMPT
from workOrderAI.utils.file_handler import listdir_allowed_type
from workOrderAI.utils.vector_store import VectorStoreService


class _DummyVectorStore:
    def __init__(self):
        self.as_retriever_calls = 0

    def as_retriever(self, **_kwargs):
        self.as_retriever_calls += 1
        return "vector"


class VectorStoreCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await VectorStoreService.invalidate_retriever_cache()

    async def test_base_retrievers_are_built_once(self):
        service = VectorStoreService.__new__(VectorStoreService)
        service.vectors_store = _DummyVectorStore()
        service._build_bm25_retriever = AsyncMock(return_value="bm25")

        first = await service._get_cached_base_retrievers()
        second = await service._get_cached_base_retrievers()

        self.assertEqual(first, ("vector", "bm25"))
        self.assertEqual(second, ("vector", "bm25"))
        self.assertEqual(service.vectors_store.as_retriever_calls, 1)
        service._build_bm25_retriever.assert_awaited_once()

    async def test_invalidate_retriever_cache_clears_cached_retrievers(self):
        VectorStoreService._cached_vector_retriever = "vector"
        VectorStoreService._cached_bm25_retriever = "bm25"
        VectorStoreService._retriever_cache_initialized = True

        await VectorStoreService.invalidate_retriever_cache()

        self.assertIsNone(VectorStoreService._cached_vector_retriever)
        self.assertIsNone(VectorStoreService._cached_bm25_retriever)
        self.assertFalse(VectorStoreService._retriever_cache_initialized)


class KnowledgeFileSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_listdir_allowed_type_skips_excluded_paths(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            root.joinpath("knowledge.txt").write_text("knowledge", encoding="utf-8")
            root.joinpath("knowledge_docs").mkdir()
            root.joinpath("knowledge_docs", "uploaded.txt").write_text("uploaded", encoding="utf-8")
            root.joinpath("external").mkdir()
            root.joinpath("external", "records.txt").write_text("records", encoding="utf-8")
            root.joinpath("md5_hex_store").mkdir()
            root.joinpath("md5_hex_store", "md5_hex_store.txt").write_text("hash", encoding="utf-8")

            files = await listdir_allowed_type(
                str(root),
                ("txt",),
                (str(root / "external"), str(root / "md5_hex_store")),
            )

            self.assertEqual(
                {Path(file_path).name for file_path in files},
                {"knowledge.txt", "uploaded.txt"},
            )


class DynamicWeightTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_chinese_query_prefers_vector_search(self):
        self.assertEqual(
            await VectorStoreService.get_dynamic_weights("扫地机器人如何保养"),
            [0.7, 0.3],
        )

    async def test_short_english_query_still_prefers_bm25(self):
        self.assertEqual(
            await VectorStoreService.get_dynamic_weights("brush"),
            [0.3, 0.7],
        )

    async def test_long_chinese_query_keeps_existing_vector_bias(self):
        query = "扫地机器人长期使用后应该如何维护主刷边刷滤网拖布和水箱以保持清洁效果稳定" * 2
        self.assertEqual(
            await VectorStoreService.get_dynamic_weights(query),
            [0.7, 0.3],
        )


class RagLightPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieve_direct_documents_respects_limit(self):
        service = RagService.__new__(RagService)

        class _DummyRetriever:
            async def ainvoke(self, _query):
                return [
                    Document(page_content="doc-1"),
                    Document(page_content="doc-2"),
                    Document(page_content="doc-3"),
                ]

        class _DummyVectorStoreService:
            async def get_retriever(self, _query):
                return _DummyRetriever()

        service.vector_store = _DummyVectorStoreService()

        documents = await RagService.retrieve_direct_documents(service, "query", limit=2)

        self.assertEqual([doc.page_content for doc in documents], ["doc-1", "doc-2"])

    async def test_rag_summary_for_suggestion_uses_direct_top2_documents(self):
        service = RagService.__new__(RagService)
        service.retrieve_direct_documents = AsyncMock(
            return_value=[
                Document(page_content="doc-1"),
                Document(page_content="doc-2"),
            ]
        )

        class _DummyChain:
            def __init__(self):
                self.payload = None

            async def ainvoke(self, payload):
                self.payload = payload
                return "summary"

        service.chain = _DummyChain()

        result = await RagService.rag_summary_for_suggestion(service, "query")

        self.assertEqual(result, "summary")
        service.retrieve_direct_documents.assert_awaited_once_with("query", limit=2)
        self.assertIn("doc-1", service.chain.payload["context"])
        self.assertIn("doc-2", service.chain.payload["context"])

    async def test_chitchat_invalid_returns_knowledge_refusal(self):
        service = RagService.__new__(RagService)
        service.hyde_pre = AsyncMock(return_value="Chitchat_Invalid")

        result = await RagService.get_documents_and_summary(service, "who is the boss")

        self.assertEqual(result["summary"], KNOWLEDGE_NO_ANSWER_SUMMARY)
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["source_documents"], [])


class HydePromptTests(unittest.TestCase):
    def test_hyde_prompts_are_short_retrieval_expansions(self):
        self.assertIn("60字以内", QUESTION_HYDE_PROMPT)
        self.assertIn("60字以内", STATEMENT_HYDE_PROMPT)
        self.assertNotIn("专业且详细", QUESTION_HYDE_PROMPT)
        self.assertNotIn("写一段诊断和排查指南", STATEMENT_HYDE_PROMPT)

    @patch("workOrderAI.app.service.rag_service.VectorStoreService")
    @patch("workOrderAI.app.service.rag_service.chat_model", new=RunnableLambda(lambda _input: "ok"))
    def test_hyde_model_limits_output_tokens(self, _vector_store_service):
        service = RagService()
        self.assertEqual(service.hyde_model.kwargs["max_tokens"], HYDE_MAX_TOKENS)


if __name__ == "__main__":
    unittest.main()
