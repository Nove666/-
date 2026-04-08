"""
数据库模块初始化
"""
from .db_manager import DatabaseManager, db_manager
from .models import (
    Base, HealthArticle, MedicalKnowledge,
    Symptom, Drug, CrawlTask, VectorEmbedding
)
from .migrations import MigrationManager, SimpleMigrationManager

__all__ = [
    'DatabaseManager',
    'db_manager',
    'Base',
    'HealthArticle',
    'MedicalKnowledge',
    'Symptom',
    'Drug',
    'CrawlTask',
    'VectorEmbedding',
    'MigrationManager',
    'SimpleMigrationManager'
]