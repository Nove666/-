"""
知识库模块初始化
"""
from .vector_store import VectorStore, vector_store
from .knowledge_base import KnowledgeBase

__all__ = [
    'VectorStore',
    'vector_store',
    'KnowledgeBase'
]