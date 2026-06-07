import unittest

from langchain_community.chat_models.tongyi import ChatTongyi

from workOrderAI.models.factory import ChatModelFactory, judge_model, reranker_model, router_model
from workOrderAI.utils.config import config


class ModelFactoryTests(unittest.TestCase):
    def test_chat_model_factory_keeps_chat_tongyi(self):
        model = ChatModelFactory(model_name="qwen3-max").generator()
        self.assertIsInstance(model, ChatTongyi)

    def test_judge_model_uses_chat_tongyi(self):
        self.assertIsInstance(judge_model, ChatTongyi)
        self.assertEqual(judge_model.model_name, "qwen3-next-80b-a3b-instruct")

    def test_router_model_uses_chat_tongyi(self):
        self.assertIsInstance(router_model, ChatTongyi)
        self.assertEqual(router_model.model_name, "qwen3-32b")
        self.assertEqual(router_model.model_kwargs.get("enable_thinking"), False)

    def test_reranker_model_uses_configured_top_n(self):
        self.assertEqual(reranker_model.model, config["model"]["reranker_model"])
        self.assertEqual(reranker_model.top_n, config["vector_store"]["rerank_top_k"])


if __name__ == "__main__":
    unittest.main()
