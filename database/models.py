# 数据库模型
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json

Base = declarative_base()


class HealthArticle(Base):
    """健康文章表"""
    __tablename__ = 'health_articles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text)
    source = Column(String(200))  # 来源
    source_url = Column(String(500))  # 原始URL
    category = Column(String(100))  # 分类：疾病、养生、用药等
    tags = Column(String(500))  # 标签，JSON格式
    author = Column(String(100))
    publish_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    view_count = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)  # 是否审核通过

    __table_args__ = (
        Index('idx_category', 'category'),
        Index('idx_publish_date', 'publish_date'),
    )


class MedicalKnowledge(Base):
    """医学知识表"""
    __tablename__ = 'medical_knowledge'

    id = Column(Integer, primary_key=True, autoincrement=True)
    disease_name = Column(String(200))  # 疾病名称
    symptom = Column(Text)  # 症状描述
    cause = Column(Text)  # 病因
    treatment = Column(Text)  # 治疗方法
    prevention = Column(Text)  # 预防措施
    diet_advice = Column(Text)  # 饮食建议
    medication = Column(Text)  # 用药指导
    when_to_see_doctor = Column(Text)  # 何时就医
    keywords = Column(String(500))  # 关键词
    confidence_score = Column(Float, default=0.0)  # 置信度
    source = Column(String(200))
    created_at = Column(DateTime, default=datetime.now)


class Symptom(Base):
    """症状表"""
    __tablename__ = 'symptoms'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    common_causes = Column(Text)
    related_diseases = Column(String(500))  # 关联疾病，JSON
    first_aid = Column(Text)  # 急救措施
    severity_level = Column(Integer, default=1)  # 严重程度 1-5
    created_at = Column(DateTime, default=datetime.now)


class Drug(Base):
    """药品表"""
    __tablename__ = 'drugs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    generic_name = Column(String(200))  # 通用名
    category = Column(String(100))  # 药品分类
    indications = Column(Text)  # 适应症
    dosage = Column(Text)  # 用法用量
    contraindications = Column(Text)  # 禁忌
    side_effects = Column(Text)  # 副作用
    precautions = Column(Text)  # 注意事项
    price_range = Column(String(100))
    is_prescription = Column(Boolean, default=True)  # 是否处方药
    created_at = Column(DateTime, default=datetime.now)


class CrawlTask(Base):
    """爬取任务表"""
    __tablename__ = 'crawl_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String(200))
    source = Column(String(200))
    status = Column(String(50), default='pending')  # pending, running, completed, failed
    total_items = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)


class VectorEmbedding(Base):
    """向量嵌入表"""
    __tablename__ = 'vector_embeddings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer)  # 关联的文章ID或知识ID
    source_type = Column(String(50))  # article, knowledge, symptom
    embedding_vector = Column(Text)  # 存储为JSON字符串
    model_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)