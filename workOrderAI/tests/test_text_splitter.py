import unittest

from langchain_core.documents import Document

from workOrderAI.utils.text_spliter import AsyncTextSplitter


class StructuredTextSplitterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.splitter = AsyncTextSplitter(chunk_size=50, chunk_overlap=0)

    async def test_faq_keeps_question_and_answer_together(self):
        docs = await self.splitter.split_documents(
            [
                Document(
                    page_content="""# 扫拖一体机器人常见问题
### 拖扫功能融合类
1. **扫拖一体机器人可以只扫地不拖地吗？**
- 可以，在APP中关闭拖地功能，仅保留吸尘模式。
2. **如何设置先扫后拖？**
- 打开自定义清扫，选择先扫后拖模式。""",
                    metadata={"source": "faq.txt"},
                )
            ]
        )

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].metadata["splitter_type"], "faq")
        self.assertEqual(docs[0].metadata["item_no"], "1")
        self.assertEqual(docs[0].metadata["section"], "拖扫功能融合类")
        self.assertEqual(docs[0].metadata["question"], "扫拖一体机器人可以只扫地不拖地吗？")
        self.assertIn("问题：扫拖一体机器人可以只扫地不拖地吗？", docs[0].page_content)
        self.assertIn("答案：可以", docs[0].page_content)
        self.assertNotIn("如何设置先扫后拖", docs[0].page_content)

    async def test_fault_entry_keeps_symptom_check_and_fix_together(self):
        docs = await self.splitter.split_documents(
            [
                Document(
                    page_content="""扫地/扫拖一体机器人故障检测与修复
1. 故障现象：机器人无法连接WiFi；检测：确认手机与机器人连同一2.4G网络；修复：重启路由器和机器人。
2. 故障现象：主刷不旋转；检测：检查主刷是否被异物卡死；修复：清理主刷杂物。""",
                    metadata={"source": "fault.txt"},
                )
            ]
        )

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].metadata["splitter_type"], "fault")
        self.assertEqual(docs[0].metadata["item_no"], "1")
        self.assertIn("故障现象：机器人无法连接WiFi", docs[0].page_content)
        self.assertIn("检测：确认手机与机器人连同一2.4G网络", docs[0].page_content)
        self.assertIn("修复：重启路由器和机器人", docs[0].page_content)

    async def test_numbered_knowledge_uses_one_item_per_chunk(self):
        docs = await self.splitter.split_documents(
            [
                Document(
                    page_content="""扫地/扫拖一体机器人选购指南
1. 选购核心：优先明确使用场景。
2. 吸力参数：家用建议选择3000Pa以上。
3. 导航技术：激光导航定位精准。""",
                    metadata={"source": "buying.txt"},
                )
            ]
        )

        self.assertEqual(len(docs), 3)
        self.assertEqual(docs[0].metadata["splitter_type"], "numbered")
        self.assertEqual(docs[0].metadata["section"], "扫地/扫拖一体机器人选购指南")
        self.assertIn("1. 选购核心", docs[0].page_content)
        self.assertNotIn("2. 吸力参数", docs[0].page_content)

    async def test_care_entry_merges_wash_and_maintenance(self):
        docs = await self.splitter.split_documents(
            [
                Document(
                    page_content="""一、春季服装
1. 纯棉材质（春季衬衫、T恤）
洗涤：可机洗或手洗，水温不超过30℃。
养护：阴凉通风处阴干，避免暴晒。
2. 薄牛仔材质（春季牛仔裤）
洗涤：翻面清洗减少褪色。
养护：翻面阴干，避免阳光直射。""",
                    metadata={"source": "care.txt"},
                )
            ]
        )

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].metadata["splitter_type"], "care")
        self.assertEqual(docs[0].metadata["section"], "一、春季服装")
        self.assertIn("条目：纯棉材质", docs[0].page_content)
        self.assertIn("洗涤：可机洗或手洗", docs[0].page_content)
        self.assertIn("养护：阴凉通风处阴干", docs[0].page_content)

    async def test_plain_text_falls_back_to_recursive_splitter(self):
        docs = await self.splitter.split_documents(
            [
                Document(
                    page_content="这是一段普通说明文档，没有编号结构，也没有问答格式。" * 10,
                    metadata={"source": "plain.txt"},
                )
            ]
        )

        self.assertGreater(len(docs), 1)
        self.assertNotIn("splitter_type", docs[0].metadata)


if __name__ == "__main__":
    unittest.main()
