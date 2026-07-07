"""
Pydantic数据模型 - 响应体
定义所有API接口的响应数据结构
"""
from pydantic import BaseModel, Field
from typing import List, Optional


# ==========================================
# AI分类接口响应模型
# ==========================================
class ClassifyResponse(BaseModel):
    """AI工单分类响应"""
    problem_type: str                                   # 问题类型: 技术故障/产品咨询/功能需求/投诉建议/账单问题/退款售后
    priority: str                                       # 优先级: P0/P1/P2/P3
    user_sentiment: str                                 # 用户情绪: 正面/中性/负面/愤怒
    confidence_score: float                             # AI置信度 (0.0-1.0)
    analysis_reasoning: str                             # AI分析依据


# ==========================================
# 知识库引用来源模型
# ==========================================
class SourceDocument(BaseModel):
    """知识库引用文档"""
    id: str                                             # 知识库文档ID
    title: str                                          # 文档标题
    relevance_score: float                              # 相关度分数


class SourceTemplate(BaseModel):
    """历史工单模板引用"""
    ticket_id: str                                      # 历史工单ID
    ticket_code: str = ""                               # 历史工单编号
    title: str = ""                                     # 历史工单标题
    final_reply: str = ""                               # 历史工单最终客服回复
    similarity_score: float                             # 相似度分数


# ==========================================
# AI回复建议接口响应模型
# ==========================================
class ReplySuggestResponse(BaseModel):
    """AI智能回复建议响应"""
    suggested_reply: str                                # AI建议回复内容
    source_documents: List[SourceDocument] = []         # 引用知识库文档列表
    source_templates: List[SourceTemplate] = []         # 引用历史案例列表


# ==========================================
# 知识库管理响应模型
# ==========================================
class KnowledgeResponse(BaseModel):
    """知识库文档响应"""
    id: str                                             # 文档ID
    title: str                                          # 文档标题
    file_name: str                                      # 原始文件名
    file_ext: str                                       # 文件扩展名
    file_size: int                                      # 文件大小
    created_by: str                                     # 创建者
    status: str                                         # 状态: active/archived/draft
    created_at: str                                     # 创建时间


class KnowledgeListResponse(BaseModel):
    """知识库列表响应"""
    total: int                                          # 总记录数
    items: List[KnowledgeResponse]                      # 文档列表


class KnowledgeQAResponse(BaseModel):
    """知识库问答响应"""
    answer: str                                         # AI回答内容
    source_documents: List[SourceDocument] = []         # 引用来源
