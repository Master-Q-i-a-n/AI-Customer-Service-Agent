import asyncio
import math
import re
from typing import Any, List, Optional

from langchain.embeddings.base import Embeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from workOrderAI.utils.config import config


class AsyncTextSplitter:
    """Async wrapper around recursive splitting with structured knowledge support."""

    MAX_STRUCTURED_CHUNK_CHARS = 60000

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None,
        embedding_model: Optional[Embeddings] = None,
    ):
        default_separators = config["vector_store"]["separators"]

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or default_separators
        self.embedding_model = embedding_model
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=self.separators,
        )

    async def split_text(self, text: str) -> List[str]:
        chunks = await asyncio.to_thread(self.splitter.split_text, text)
        if self.embedding_model:
            chunks = await self._optimize_chunks(chunks)
        return chunks

    async def split_documents(self, documents: List[Any]) -> List[Any]:
        structured_docs = self._split_structured_documents(documents)
        if structured_docs:
            return structured_docs

        return await asyncio.to_thread(self.splitter.split_documents, documents)

    def _split_structured_documents(self, documents: List[Any]) -> List[Document]:
        structured_docs = []
        for text, metadata in self._merge_document_groups(documents):
            splitter_type = self._detect_structure(text)
            if splitter_type == "faq":
                docs = self._split_faq(text, metadata)
            elif splitter_type == "fault":
                docs = self._split_fault(text, metadata)
            elif splitter_type == "care":
                docs = self._split_care(text, metadata)
            elif splitter_type == "numbered":
                docs = self._split_numbered(text, metadata)
            else:
                docs = []

            if not docs:
                return []
            structured_docs.extend(docs)
        return structured_docs

    def _merge_document_groups(self, documents: List[Any]) -> List[tuple[str, dict]]:
        groups = []
        current_key = object()
        current_parts = []
        current_metadata = {}

        for doc in documents or []:
            metadata = dict(getattr(doc, "metadata", {}) or {})
            key = metadata.get("source") or metadata.get("file_path") or id(doc)
            if current_parts and key != current_key:
                groups.append(("\n".join(current_parts).strip(), current_metadata))
                current_parts = []
                current_metadata = {}

            current_key = key
            current_parts.append(str(getattr(doc, "page_content", "") or ""))
            if not current_metadata:
                current_metadata = {k: v for k, v in metadata.items() if k != "page"}

        if current_parts:
            groups.append(("\n".join(current_parts).strip(), current_metadata))

        return [(text, metadata) for text, metadata in groups if text]

    def _detect_structure(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        if not lines:
            return "plain"

        faq_questions = sum(1 for line in lines if self._is_faq_question_line(line))
        faq_answers = sum(
            1
            for line in lines
            if re.match(r"^[-－]\s*\S+", line) or re.match(r"^答[:：]", line)
        )
        fault_entries = sum(
            1
            for line in lines
            if "故障现象" in line and "检测" in line and "修复" in line
        )
        care_entries = min(
            sum(1 for line in lines if "洗涤：" in line or "洗涤:" in line),
            sum(1 for line in lines if "养护：" in line or "养护:" in line),
        )
        numbered_entries = sum(1 for line in lines if re.match(r"^\d+[.、]\s+\S+", line))

        # Keep thresholds conservative so ordinary prose still falls back to recursive splitting.
        if fault_entries >= 2:
            return "fault"
        if faq_questions >= 2 and faq_answers >= max(1, faq_questions // 2):
            return "faq"
        if care_entries >= 2:
            return "care"
        if numbered_entries >= 3:
            return "numbered"
        return "plain"

    def _split_faq(self, text: str, base_metadata: dict) -> List[Document]:
        docs = []
        section = ""
        current_no = ""
        current_question = ""
        current_lines = []

        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            question_match = self._faq_question_match(line)
            if question_match:
                if current_question:
                    docs.extend(
                        self._build_structured_docs(
                            "\n".join(current_lines),
                            base_metadata,
                            "faq",
                            section,
                            current_no,
                            current_question,
                        )
                    )
                current_no = question_match.group("no")
                current_question = self._clean_inline_markup(question_match.group("question"))
                current_lines = [
                    item
                    for item in [
                        self._format_context_line("分类", section),
                        f"问题：{current_question}",
                    ]
                    if item
                ]
                continue

            if self._is_heading_line(line):
                if current_question:
                    docs.extend(
                        self._build_structured_docs(
                            "\n".join(current_lines),
                            base_metadata,
                            "faq",
                            section,
                            current_no,
                            current_question,
                        )
                    )
                    current_no, current_question, current_lines = "", "", []
                section = self._clean_heading(line)
                continue

            if current_question:
                current_lines.append(self._format_answer_line(line))

        if current_question:
            docs.extend(
                self._build_structured_docs(
                    "\n".join(current_lines),
                    base_metadata,
                    "faq",
                    section,
                    current_no,
                    current_question,
                )
            )
        return docs

    def _split_fault(self, text: str, base_metadata: dict) -> List[Document]:
        docs = []
        section = ""

        for line in [item.strip() for item in str(text or "").splitlines() if item.strip()]:
            if not re.match(r"^\d+[.、]\s+", line):
                section = self._clean_heading(line)
                continue

            match = re.match(r"^(?P<no>\d+)[.、]\s*(?P<body>.+)$", line)
            if not match or "故障现象" not in match.group("body"):
                continue

            content = "\n".join(
                item
                for item in [
                    self._format_context_line("分类", section),
                    match.group("body").replace("；", "\n").replace(";", "\n"),
                ]
                if item
            )
            docs.extend(
                self._build_structured_docs(
                    content,
                    base_metadata,
                    "fault",
                    section,
                    match.group("no"),
                    "",
                )
            )
        return docs

    def _split_care(self, text: str, base_metadata: dict) -> List[Document]:
        docs = []
        section = ""
        current_no = ""
        current_lines = []

        for line in [item.strip() for item in str(text or "").splitlines() if item.strip()]:
            if self._is_heading_line(line):
                if current_lines:
                    docs.extend(
                        self._build_structured_docs(
                            "\n".join(current_lines),
                            base_metadata,
                            "care",
                            section,
                            current_no,
                            "",
                        )
                    )
                    current_no, current_lines = "", []
                section = self._clean_heading(line)
                continue

            item_match = re.match(r"^(?P<no>\d+)[.、]\s*(?P<title>.+)$", line)
            if item_match:
                if current_lines:
                    docs.extend(
                        self._build_structured_docs(
                            "\n".join(current_lines),
                            base_metadata,
                            "care",
                            section,
                            current_no,
                            "",
                        )
                    )
                current_no = item_match.group("no")
                current_lines = [
                    item
                    for item in [
                        self._format_context_line("分类", section),
                        f"条目：{item_match.group('title').strip()}",
                    ]
                    if item
                ]
                continue

            if current_lines:
                current_lines.append(line)

        if current_lines:
            docs.extend(
                self._build_structured_docs(
                    "\n".join(current_lines),
                    base_metadata,
                    "care",
                    section,
                    current_no,
                    "",
                )
            )
        return docs

    def _split_numbered(self, text: str, base_metadata: dict) -> List[Document]:
        docs = []
        section = ""
        current_no = ""
        current_lines = []

        for line in [item.strip() for item in str(text or "").splitlines() if item.strip()]:
            if self._is_heading_line(line):
                if current_lines:
                    docs.extend(
                        self._build_structured_docs(
                            "\n".join(current_lines),
                            base_metadata,
                            "numbered",
                            section,
                            current_no,
                            "",
                        )
                    )
                    current_no, current_lines = "", []
                section = self._clean_heading(line)
                continue

            item_match = re.match(r"^(?P<no>\d+)[.、]\s*(?P<body>.+)$", line)
            if item_match:
                if current_lines:
                    docs.extend(
                        self._build_structured_docs(
                            "\n".join(current_lines),
                            base_metadata,
                            "numbered",
                            section,
                            current_no,
                            "",
                        )
                    )
                current_no = item_match.group("no")
                current_lines = [
                    item
                    for item in [
                        self._format_context_line("分类", section),
                        f"{current_no}. {item_match.group('body').strip()}",
                    ]
                    if item
                ]
                continue

            if current_lines:
                current_lines.append(line)
            elif not section:
                section = self._clean_heading(line)

        if current_lines:
            docs.extend(
                self._build_structured_docs(
                    "\n".join(current_lines),
                    base_metadata,
                    "numbered",
                    section,
                    current_no,
                    "",
                )
            )
        return docs

    def _build_structured_docs(
        self,
        content: str,
        base_metadata: dict,
        splitter_type: str,
        section: str,
        item_no: str,
        question: str,
    ) -> List[Document]:
        content = str(content or "").strip()
        if not content:
            return []

        metadata = dict(base_metadata or {})
        metadata.update(
            {
                "splitter_type": splitter_type,
                "section": section or "",
                "item_no": item_no or "",
            }
        )
        if question:
            metadata["question"] = question

        if len(content) <= self.MAX_STRUCTURED_CHUNK_CHARS:
            return [Document(page_content=content, metadata=metadata)]

        return [
            Document(page_content=chunk, metadata={**metadata, "structured_overflow": True})
            for chunk in self.splitter.split_text(content)
        ]

    def _faq_question_match(self, line: str):
        return re.match(r"^(?P<no>\d+)[.、]\s*(?:\*\*)?(?P<question>.+?[？?])(?:\*\*)?\s*$", line)

    def _is_faq_question_line(self, line: str) -> bool:
        return bool(self._faq_question_match(line))

    def _is_heading_line(self, line: str) -> bool:
        return bool(
            re.match(r"^#{1,6}\s+\S+", line)
            or re.match(r"^[一二三四五六七八九十]+、\S+", line)
        )

    def _clean_heading(self, line: str) -> str:
        return re.sub(r"^#{1,6}\s*", "", self._clean_inline_markup(line)).strip()

    def _clean_inline_markup(self, text: str) -> str:
        return str(text or "").replace("**", "").strip()

    def _format_answer_line(self, line: str) -> str:
        answer = re.sub(r"^[-－]\s*", "", line).strip()
        answer = re.sub(r"^答[:：]\s*", "", answer)
        return f"答案：{answer}" if answer else ""

    def _format_context_line(self, label: str, value: str) -> str:
        return f"{label}：{value}" if value else ""

    async def _optimize_chunks(self, chunks: List[str]) -> List[str]:
        if not chunks:
            return []

        optimized_chunks = []
        current_chunk = chunks[0]

        for index in range(1, len(chunks)):
            similarity = await self._calculate_similarity(current_chunk, chunks[index])
            if similarity > 0.7:
                current_chunk += " " + chunks[index]
            else:
                optimized_chunks.append(current_chunk)
                current_chunk = chunks[index]

        optimized_chunks.append(current_chunk)
        return optimized_chunks

    async def _calculate_similarity(self, text1: str, text2: str) -> float:
        if not self.embedding_model:
            return 0.0

        embedding1 = self.embedding_model.embed_query(text1)
        embedding2 = self.embedding_model.embed_query(text2)
        return self._cosine_similarity(embedding1, embedding2)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(a * a for a in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)
