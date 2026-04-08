"""
灵枢安 - AI健康助手
整合了爬虫、数据库、向量检索、聊天功能的完整应用
"""
import os
import re
import json
import asyncio
import threading
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from contextlib import contextmanager

# ==================== 数据库部分 ====================
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

Base = declarative_base()


# 数据库模型
class HealthArticle(Base):
    __tablename__ = 'health_articles'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text)
    source = Column(String(200))
    source_url = Column(String(500))
    category = Column(String(100))
    tags = Column(String(500))
    publish_date = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
    view_count = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)


class MedicalKnowledge(Base):
    __tablename__ = 'medical_knowledge'
    id = Column(Integer, primary_key=True, autoincrement=True)
    disease_name = Column(String(200))
    symptom = Column(Text)
    cause = Column(Text)
    treatment = Column(Text)
    prevention = Column(Text)
    diet_advice = Column(Text)
    medication = Column(Text)
    source = Column(String(200))
    created_at = Column(DateTime, default=datetime.now)


class CrawlTask(Base):
    __tablename__ = 'crawl_tasks'
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String(200))
    source = Column(String(200))
    status = Column(String(50), default='pending')
    total_items = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)


# 数据库管理器
class DatabaseManager:
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), 'lingshu_an.db')
        self.engine = create_engine(f'sqlite:///{db_path}', connect_args={'check_same_thread': False})
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        self._create_tables()

    def _create_tables(self):
        Base.metadata.create_all(self.engine)
        print("✓ 数据库初始化完成")

    @contextmanager
    def get_session(self):
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def save_article(self, article: dict):
        with self.get_session() as session:
            existing = session.query(HealthArticle).filter_by(source_url=article.get('source_url', '')).first()
            if not existing:
                new_article = HealthArticle(**article)
                session.add(new_article)
                return True
            return False

    def save_articles_batch(self, articles: List[dict]):
        count = 0
        for article in articles:
            if self.save_article(article):
                count += 1
        return count


db_manager = DatabaseManager()


# ==================== 向量存储部分 ====================
class VectorStore:
    def __init__(self):
        self.persist_path = os.path.join(os.path.dirname(__file__), 'vector_db')
        os.makedirs(self.persist_path, exist_ok=True)
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            print("✓ 向量模型加载成功")
        except Exception as e:
            print(f"⚠ 向量模型加载失败: {e}")

    def encode(self, text):
        if self.model:
            return self.model.encode(text).tolist()
        return [0.0] * 384

    def add(self, collection, documents, metadatas=None):
        file_path = os.path.join(self.persist_path, f"{collection}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []

        for i, doc in enumerate(documents):
            data.append({
                'id': hashlib.md5(doc.encode()).hexdigest(),
                'document': doc,
                'embedding': self.encode(doc),
                'metadata': metadatas[i] if metadatas else {}
            })

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def query(self, collection, query_text, n_results=3):
        file_path = os.path.join(self.persist_path, f"{collection}.json")
        if not os.path.exists(file_path):
            return {'documents': [[]], 'metadatas': [[]]}

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data:
            return {'documents': [[]], 'metadatas': [[]]}

        query_embedding = self.encode(query_text)
        results = []

        for item in data:
            if item.get('embedding'):
                similarity = self._cosine_similarity(query_embedding, item['embedding'])
                results.append({
                    'document': item['document'],
                    'metadata': item.get('metadata', {}),
                    'similarity': similarity
                })

        results.sort(key=lambda x: x['similarity'], reverse=True)
        top = results[:n_results]

        return {
            'documents': [[r['document'] for r in top]],
            'metadatas': [[r['metadata'] for r in top]]
        }

    def _cosine_similarity(self, a, b):
        import numpy as np
        a_np = np.array(a)
        b_np = np.array(b)
        return np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-8)


vector_store = VectorStore()

# ==================== 爬虫部分 ====================
import requests
from bs4 import BeautifulSoup


class HealthCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def crawl_dingxiang(self):
        """爬取丁香园数据"""
        articles = []

        # 内置健康知识数据（模拟爬取）
        health_data = [
            {"title": "感冒了怎么办",
             "content": "感冒通常由病毒引起，建议多喝水、休息，可服用感冒药缓解症状。如有高烧不退请及时就医。",
             "category": "symptom", "tags": "感冒,发烧"},
            {"title": "高血压注意事项",
             "content": "高血压患者应低盐饮食、规律作息、按时服药。建议每天测量血压，控制在140/90mmHg以下。",
             "category": "chronic", "tags": "高血压,血压"},
            {"title": "糖尿病饮食指南",
             "content": "糖尿病患者应注意控制饮食，少食多餐，避免高糖食物。定期监测血糖，遵医嘱用药。",
             "category": "chronic", "tags": "糖尿病,血糖"},
            {"title": "头痛的原因和缓解",
             "content": "头痛可能由疲劳、紧张、感冒等引起。建议休息、按摩太阳穴。如果剧烈或持续头痛请就医。",
             "category": "symptom", "tags": "头痛"},
            {"title": "发烧处理指南",
             "content": "发烧体温超过37.3℃为发热。轻度发热可物理降温，超过38.5℃建议服用退烧药。持续发热请就医。",
             "category": "symptom", "tags": "发烧"},
            {"title": "失眠的改善方法",
             "content": "失眠可尝试规律作息、睡前放松、避免咖啡因。严重时可咨询医生，不建议长期服用安眠药。",
             "category": "wellness", "tags": "失眠"},
            {"title": "健康饮食建议",
             "content": "健康饮食建议：多吃蔬菜水果，适量摄入蛋白质，减少油炸和高糖食物，每天饮水1.5-2升。",
             "category": "wellness", "tags": "饮食,营养"},
            {"title": "运动健身指南",
             "content": "运动建议：每周至少150分钟中等强度运动，如快走、慢跑、游泳。运动前热身，运动后拉伸。",
             "category": "wellness", "tags": "运动"},
            {"title": "焦虑情绪缓解",
             "content": "焦虑情绪可以通过深呼吸、冥想、规律运动来缓解。如果影响生活，建议寻求心理咨询。",
             "category": "emotion", "tags": "焦虑"},
            {"title": "胃痛怎么办",
             "content": "胃痛可能由饮食不当、胃炎等引起。建议清淡饮食，避免辛辣刺激。持续胃痛请就医。",
             "category": "symptom", "tags": "胃痛"},
            {"title": "运动损伤处理", "content": "运动损伤应遵循RICE原则：休息、冰敷、加压、抬高。严重损伤请及时就医。",
             "category": "symptom", "tags": "运动损伤"},
            {"title": "睡眠质量改善", "content": "睡眠建议：保持规律作息，睡前1小时远离电子设备，保持卧室安静、黑暗、凉爽。",
             "category": "wellness", "tags": "睡眠"},
        ]

        for data in health_data:
            articles.append({
                'title': data['title'],
                'content': data['content'],
                'summary': data['content'][:100],
                'source': '丁香园',
                'category': data['category'],
                'tags': data['tags'],
                'publish_date': datetime.now(),
                'is_verified': True
            })

        return articles

    def crawl_baidu(self, keywords=None):
        """爬取百度健康数据"""
        if keywords is None:
            keywords = ['感冒', '发烧', '头痛', '胃痛', '高血压', '糖尿病', '失眠']

        articles = []
        disease_info = {
            '感冒': '感冒是由病毒引起的常见呼吸道疾病，症状包括打喷嚏、流鼻涕、咳嗽、喉咙痛等。',
            '发烧': '发烧是指体温超过37.3℃，可能由感染引起。建议物理降温，体温超过38.5℃可服用退烧药。',
            '头痛': '头痛可由多种原因引起，如疲劳、紧张、感冒等。建议休息放松，如持续剧烈头痛请及时就医。',
            '胃痛': '胃痛可能由胃炎、胃溃疡、饮食不当等引起。建议清淡饮食，避免辛辣刺激。',
            '高血压': '高血压是指血压持续高于140/90mmHg。建议低盐饮食、规律作息、按时服药。',
            '糖尿病': '糖尿病是血糖代谢异常疾病。建议控制饮食、规律运动、监测血糖、遵医嘱用药。',
            '失眠': '失眠是指入睡困难或睡眠维持困难。建议规律作息、睡前放松、避免咖啡因。'
        }

        for keyword in keywords:
            if keyword in disease_info:
                articles.append({
                    'title': f'{keyword}的健康科普',
                    'content': disease_info[keyword],
                    'summary': disease_info[keyword][:100],
                    'source': '百度健康',
                    'category': 'symptom' if keyword in ['感冒', '发烧', '头痛', '胃痛'] else 'chronic',
                    'tags': keyword,
                    'publish_date': datetime.now(),
                    'is_verified': True
                })

        return articles

    def run(self, source='all'):
        """运行爬虫"""
        task = CrawlTask(task_name=f'crawl_{source}', source=source, status='running', started_at=datetime.now())
        with db_manager.get_session() as session:
            session.add(task)
            session.flush()
            task_id = task.id

        try:
            all_articles = []
            if source in ['all', 'dingxiang']:
                articles = self.crawl_dingxiang()
                all_articles.extend(articles)
                print(f"✓ 丁香园: 获取 {len(articles)} 条")

            if source in ['all', 'baidu']:
                articles = self.crawl_baidu()
                all_articles.extend(articles)
                print(f"✓ 百度健康: 获取 {len(articles)} 条")

            # 保存到数据库
            saved_count = db_manager.save_articles_batch(all_articles)

            # 更新任务状态
            with db_manager.get_session() as session:
                task = session.query(CrawlTask).get(task_id)
                task.status = 'completed'
                task.completed_at = datetime.now()
                task.total_items = saved_count
                session.commit()

            print(f"✓ 爬取完成，共保存 {saved_count} 条新数据")
            return saved_count

        except Exception as e:
            with db_manager.get_session() as session:
                task = session.query(CrawlTask).get(task_id)
                task.status = 'failed'
                task.error_message = str(e)
                session.commit()
            print(f"✗ 爬取失败: {e}")
            return 0


# ==================== AI 对话部分 ====================
import openai

openai.api_key = os.getenv("OPENAI_API_KEY", "")


# 初始化向量知识库
def init_vector_knowledge():
    """初始化向量知识库"""
    with db_manager.get_session() as session:
        articles = session.query(HealthArticle).all()

        documents = []
        metadatas = []
        for article in articles:
            text = f"{article.title}\n{article.content}"
            documents.append(text)
            metadatas.append({
                'source': article.source,
                'category': article.category,
                'title': article.title
            })

        if documents:
            vector_store.add('health_knowledge', documents, metadatas)
            print(f"✓ 向量知识库初始化完成，共 {len(documents)} 条")
        else:
            # 添加默认知识
            default_knowledge = [
                "感冒通常由病毒引起，建议多喝水、休息，可服用感冒药缓解症状。如有高烧不退请及时就医。",
                "高血压患者应低盐饮食、规律作息、按时服药。建议每天测量血压。",
                "糖尿病患者应注意控制饮食，少食多餐，避免高糖食物。定期监测血糖。",
                "头痛可能由疲劳、紧张、感冒等引起。建议休息、按摩太阳穴。",
                "发烧体温超过37.3℃为发热。轻度发热可物理降温，超过38.5℃建议服用退烧药。",
                "失眠可尝试规律作息、睡前放松、避免咖啡因。严重时可咨询医生。",
                "健康饮食：多吃蔬菜水果，适量摄入蛋白质，减少油炸和高糖食物。",
                "运动建议：每周至少150分钟中等强度运动，运动前热身，运动后拉伸。"
            ]
            vector_store.add('health_knowledge', default_knowledge, [{'source': '内置知识'}] * len(default_knowledge))
            print(f"✓ 默认知识库初始化完成")


# ==================== 知识库内容（精确关键词匹配）====================

# 结构化知识库 - 每个知识有明确的关键词
KNOWLEDGE_BASE = [
    {
        "text": "感冒通常由病毒引起，建议多喝水、休息，可服用感冒药缓解症状。如有高烧不退请及时就医。",
        "keywords": ["感冒", "流感", "伤风", "打喷嚏", "流鼻涕", "鼻塞", "喉咙痛", "嗓子疼"],
        "category": "symptom"
    },
    {
        "text": "发烧体温超过37.3℃为发热。轻度发热可物理降温，超过38.5℃建议服用退烧药。持续发热请就医。",
        "keywords": ["发烧", "发热", "高热", "低烧", "体温高", "发高烧"],
        "category": "symptom"
    },
    {
        "text": "头痛可能由疲劳、紧张、感冒等引起。建议休息、按摩太阳穴。如果剧烈或持续头痛请就医。",
        "keywords": ["头痛", "头疼", "偏头痛", "头晕", "头胀", "脑袋疼"],
        "category": "symptom"
    },
    {
        "text": "胃痛可能由饮食不当、胃炎等引起。建议清淡饮食，避免辛辣刺激。持续胃痛请就医。",
        "keywords": ["胃痛", "胃疼", "肚子疼", "腹痛", "胃胀", "消化不良", "胃不舒服"],
        "category": "symptom"
    },
    {
        "text": "高血压患者应低盐饮食、规律作息、按时服药。建议每天测量血压，控制在140/90mmHg以下。",
        "keywords": ["高血压", "血压高", "低压", "高压", "血压"],
        "category": "chronic"
    },
    {
        "text": "糖尿病患者应注意控制饮食，少食多餐，避免高糖食物。定期监测血糖，遵医嘱用药。",
        "keywords": ["糖尿病", "血糖高", "血糖", "胰岛素", "甜食"],
        "category": "chronic"
    },
    {
        "text": "失眠可尝试规律作息、睡前放松、避免咖啡因。严重时可咨询医生，不建议长期服用安眠药。",
        "keywords": ["失眠", "睡不着", "入睡困难", "睡眠不好", "熬夜", "睡眠质量", "睡不好"],
        "category": "wellness"
    },
    {
        "text": "焦虑情绪可以通过深呼吸、冥想、规律运动来缓解。如果影响生活，建议寻求心理咨询。",
        "keywords": ["焦虑", "紧张", "压力大", "心烦", "不安", "恐慌", "心慌"],
        "category": "emotion"
    },
    {
        "text": "运动损伤应遵循RICE原则：休息、冰敷、加压、抬高。严重损伤请及时就医。",
        "keywords": ["运动损伤", "扭伤", "拉伤", "肌肉拉伤", "韧带", "骨折", "崴脚"],
        "category": "symptom"
    },
    {
        "text": "健康饮食建议：多吃蔬菜水果，适量摄入蛋白质，减少油炸和高糖食物，每天饮水1.5-2升。",
        "keywords": ["饮食", "营养", "健康饮食", "吃什么", "减肥", "食谱", "吃饭"],
        "category": "wellness"
    },
    {
        "text": "运动建议：每周至少150分钟中等强度运动，如快走、慢跑、游泳。运动前热身，运动后拉伸。",
        "keywords": ["运动", "锻炼", "健身", "跑步", "游泳", "快走", "散步"],
        "category": "wellness"
    },
    {
        "text": "颈椎病预防：保持正确坐姿，定时活动颈部，做颈椎保健操，选择合适的枕头。",
        "keywords": ["颈椎", "脖子疼", "颈椎病", "肩颈", "脖子酸"],
        "category": "wellness"
    },
    {
        "text": "眼睛疲劳：遵循20-20-20法则（每20分钟看20英尺外20秒），做眼保健操，保证充足睡眠。",
        "keywords": ["眼睛", "视力", "眼疲劳", "近视", "眼干", "眼涩"],
        "category": "wellness"
    }
]

# ==================== 紧急情况关键词 ====================
EMERGENCY_KEYWORDS = {
    "crisis": ["想死", "自杀", "不想活了", "活不下去", "结束生命", "死了算了", "跳楼", "割腕", "轻生"],
    "emergency": ["急诊", "急救", "晕倒", "昏迷", "大出血", "剧烈疼痛", "呼吸困难", "胸痛", "心脏病发作", "中风", "120"]
}

# ==================== 情绪困扰关键词 ====================
DISTRESS_KEYWORDS = ["好难过", "伤心", "痛苦", "崩溃", "绝望", "无助", "空虚", "难受", "不开心", "郁闷"]


def retrieve_knowledge(query):
    """
    精确知识检索 - 使用关键词匹配
    返回: (知识内容, 分类) 或 (None, None)
    """
    query_lower = query.lower()

    # 1. 检查是否是紧急情况
    for level, keywords in EMERGENCY_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                return None, level

    # 2. 检查情绪困扰
    for kw in DISTRESS_KEYWORDS:
        if kw in query_lower:
            return None, "distress"

    # 3. 关键词精确匹配
    best_match = None
    best_score = 0

    for knowledge in KNOWLEDGE_BASE:
        score = 0
        for keyword in knowledge["keywords"]:
            if keyword in query_lower:
                # 完全匹配加分
                score += 2
            elif len(keyword) >= 2 and keyword in query:
                score += 1

        if score > best_score:
            best_score = score
            best_match = knowledge

    if best_match and best_score > 0:
        return best_match["text"], best_match["category"]

    return None, None


def get_reply(user_input, knowledge, intent):
    """生成回复"""
    query_lower = user_input.lower()

    # 1. 心理危机 - 最高优先级
    for kw in EMERGENCY_KEYWORDS.get("crisis", []):
        if kw in query_lower:
            return handle_crisis()

    # 2. 紧急医疗情况
    for kw in EMERGENCY_KEYWORDS.get("emergency", []):
        if kw in query_lower:
            return handle_emergency()

    # 3. 情绪困扰
    for kw in DISTRESS_KEYWORDS:
        if kw in query_lower:
            return handle_emotional_distress(user_input)

    # 4. 如果有相关知识匹配
    if knowledge:
        return f"🌿 {knowledge}\n\n💚 祝您健康！"

    # 5. 根据意图返回默认回复
    replies = {
        "symptom": "🌿 我理解您的不适。建议您多休息、多喝水，观察症状变化。如果症状持续或加重，请及时就医。\n\n💚 祝您早日康复！",
        "medication": "🌿 关于用药问题，请务必遵医嘱，不要自行用药。如有疑问，建议咨询专业医生或药师。\n\n💚 安全用药最重要！",
        "chronic": "🌿 慢性病管理需要长期坚持。请按时服药、定期复查、保持良好生活习惯。\n\n💚 坚持就是胜利！",
        "wellness": "🌿 保持良好的生活习惯是健康的基础。均衡饮食、规律运动、充足睡眠都很重要。\n\n💚 健康生活每一天！",
        "emotion": "🌿 我理解您的感受。适当放松、与人倾诉、寻求专业帮助都是好方法。\n\n💚 照顾好自己，一切都会好起来的！",
        "chat": "🌿 我是灵枢安，您的健康助手。请问有什么健康问题我可以帮您解答？\n\n💚 随时为您服务！"
    }

    return replies.get(intent, replies["chat"])


def handle_emergency():
    """紧急情况响应"""
    return """⚠️ **紧急提醒** ⚠️

您描述的情况可能比较紧急！请立即：

1. 📞 拨打急救电话 **120**
2. 🏥 前往最近的医院急诊科
3. ⏰ 在等待救援时保持冷静

🌿 请尽快就医，不要耽误！"""


def handle_crisis():
    """心理危机响应"""
    return """❤️ **请先停下来，听我说** ❤️

我理解您现在可能正在经历非常痛苦的时刻。

**请立即联系专业人士：**

📞 **全国心理援助热线：400-161-9995**（24小时）
📞 **希望24热线：400-161-9995**
📞 **北京心理危机干预中心：010-82951332**

**或者：**
- 告诉身边的家人或朋友
- 去最近的医院急诊科
- 拨打 120 寻求帮助

🌿 **请记住：生命是宝贵的，您不是一个人。请现在就给上面的号码打电话，他们愿意倾听。**"""


def handle_emotional_distress(query):
    """情绪困扰响应"""
    return """🌿 **我能感受到您现在的情绪**

每个人都会有难过的时候，这很正常。您可以试试：

1. 💬 **找人倾诉** - 和信任的朋友或家人聊聊
2. 🧘 **深呼吸放松** - 慢慢吸气4秒，呼气6秒
3. 🚶 **换个环境** - 出去走走，呼吸新鲜空气
4. 📞 **寻求帮助** - 心理援助热线：**400-161-9995**

如果这些情绪持续很久，建议咨询心理医生。

💚 **照顾好自己，一切都会慢慢好起来！**"""


def classify_intent(text):
    """意图识别"""
    text_lower = text.lower()

    # 紧急情况
    if any(kw in text_lower for kw in ["急诊", "急救", "晕倒", "昏迷", "大出血", "剧烈疼痛", "呼吸困难", "胸痛"]):
        return "emergency"

    # 心理危机
    if any(kw in text_lower for kw in ["想死", "自杀", "不想活了", "活不下去"]):
        return "crisis"

    # 症状类
    symptom_keywords = ["头疼", "头痛", "发烧", "发热", "感冒", "咳嗽", "胃痛", "胃疼", "肚子疼"]
    if any(kw in text_lower for kw in symptom_keywords):
        return "symptom"

    # 用药类
    medication_keywords = ["药", "吃药", "用药", "剂量", "服用", "药品"]
    if any(kw in text_lower for kw in medication_keywords):
        return "medication"

    # 慢性病类
    chronic_keywords = ["血压", "血糖", "高血压", "糖尿病", "慢病"]
    if any(kw in text_lower for kw in chronic_keywords):
        return "chronic"

    # 养生类
    wellness_keywords = ["养生", "调理", "保健", "饮食", "运动", "睡眠", "熬夜"]
    if any(kw in text_lower for kw in wellness_keywords):
        return "wellness"

    # 情绪类
    emotion_keywords = ["焦虑", "抑郁", "压力", "紧张", "心情", "情绪", "难过", "伤心"]
    if any(kw in text_lower for kw in emotion_keywords):
        return "emotion"

    return "chat"


def classify_intent(text):
    """意图识别 - 增加对情绪问题的识别"""
    text_lower = text.lower()

    # 紧急情况（最高优先级）
    emergency_keywords = ["急诊", "急救", "晕倒", "昏迷", "大出血", "剧烈疼痛", "呼吸困难", "胸痛", "心脏病发作"]
    if any(kw in text_lower for kw in emergency_keywords):
        return "emergency"

    # 严重情绪问题
    crisis_keywords = ["想死", "自杀", "不想活了", "活不下去", "结束生命", "死了"]
    if any(kw in text_lower for kw in crisis_keywords):
        return "crisis"

    # 情绪困扰
    emotion_distress = ["好难过", "伤心", "痛苦", "崩溃", "绝望", "无助", "空虚"]
    if any(kw in text_lower for kw in emotion_distress):
        return "emotion"

    # 症状类
    symptom_keywords = ["头疼", "头痛", "发烧", "发热", "感冒", "咳嗽", "流鼻涕", "喉咙痛", "胃痛", "胃疼", "肚子疼",
                        "腹泻", "呕吐"]
    if any(kw in text_lower for kw in symptom_keywords):
        return "symptom"

    # 用药类
    medication_keywords = ["药", "吃药", "用药", "剂量", "服用", "药品", "能不能吃"]
    if any(kw in text_lower for kw in medication_keywords):
        return "medication"

    # 慢性病类
    chronic_keywords = ["血压", "血糖", "高血压", "糖尿病", "慢病", "高血脂", "尿酸"]
    if any(kw in text_lower for kw in chronic_keywords):
        return "chronic"

    # 养生类
    wellness_keywords = ["养生", "调理", "保健", "饮食", "运动", "睡眠", "熬夜", "减压", "锻炼"]
    if any(kw in text_lower for kw in wellness_keywords):
        return "wellness"

    # 情绪类
    emotion_keywords = ["焦虑", "抑郁", "压力", "紧张", "心情", "情绪", "烦躁", "难过", "伤心"]
    if any(kw in text_lower for kw in emotion_keywords):
        return "emotion"

    return "chat"

def handle_emergency():
    return "⚠️ **紧急提醒** ⚠️\n\n您描述的情况可能比较紧急！请立即：\n\n1. 拨打急救电话（如 120）\n2. 前往最近的医院急诊科\n3. 在等待救援时保持冷静\n\n🌿 请尽快就医，不要耽误！"


def get_reply(user_input, knowledge, intent):
    """生成回复"""
    query_lower = user_input.lower()

    # 1. 心理危机 - 最高优先级
    for kw in EMERGENCY_KEYWORDS.get("crisis", []):
        if kw in query_lower:
            return handle_crisis()

    # 2. 紧急医疗情况
    for kw in EMERGENCY_KEYWORDS.get("emergency", []):
        if kw in query_lower:
            return handle_emergency()

    # 3. 情绪困扰
    for kw in DISTRESS_KEYWORDS:
        if kw in query_lower:
            return handle_emotional_distress(user_input)

    # 4. 非健康问题识别（日期、天气、人名等）
    non_health_indicators = [
        "今天是几号", "现在几点", "什么时间", "日期", "星期", "天气", "温度",
        "谁", "名字", "叫什么", "曹硕", "张三", "李四", "王五",  # 人名
        "股票", "房价", "新闻", "电影", "游戏", "明星"
    ]
    for indicator in non_health_indicators:
        if indicator in query_lower:
            return "🌿 我是灵枢安，专业的健康助手。\n\n我只回答健康相关问题（如症状、用药、养生、疾病等）。\n\n如果您有健康方面的疑问，请随时告诉我！\n\n💚 祝您身体健康！"

    # 5. 如果有相关知识匹配
    if knowledge:
        return f"🌿 {knowledge}\n\n💚 祝您健康！"

    # 6. 兜底回复 - 引导用户提问健康问题
    return """🌿 我是灵枢安，您的AI健康助手。

我可以帮您解答以下类型的问题：
• 🤒 **症状分析** - 头疼、发烧、胃痛等
• 💊 **用药建议** - 感冒药、降压药等
• ❤️ **慢病管理** - 高血压、糖尿病等
• 🌱 **养生建议** - 饮食、运动、睡眠等
• 😊 **情绪疏导** - 焦虑、压力等

请告诉我您具体的健康问题，我会尽力帮您！

💚 祝您健康！"""


def get_local_reply(user_input, knowledge):
    """本地回复（不依赖API）"""
    intent = classify_intent(user_input)

    if intent == "emergency":
        return handle_emergency()

    if knowledge:
        return f"🌿 {knowledge}\n\n💚 祝您健康！"

    # 默认回复
    default_replies = {
        "symptom": "🌿 我理解您的不适。建议您多休息，观察症状变化。如果症状持续或加重，请及时就医。\n\n💚 祝您早日康复！",
        "medication": "🌿 关于用药问题，请务必遵医嘱，不要自行用药。如有疑问，建议咨询专业医生或药师。\n\n💚 安全用药最重要！",
        "chronic": "🌿 慢性病管理需要长期坚持。请按时服药、定期复查、保持良好生活习惯。\n\n💚 坚持就是胜利！",
        "wellness": "🌿 保持良好的生活习惯是健康的基础。均衡饮食、规律运动、充足睡眠都很重要。\n\n💚 健康生活每一天！",
        "emotion": "🌿 我理解您的感受。适当放松、与人倾诉、寻求专业帮助都是好方法。\n\n💚 照顾好自己，一切都会好起来的！",
        "chat": "🌿 我是灵枢安，您的健康助手。请问有什么健康问题我可以帮您解答？\n\n💚 随时为您服务！"
    }

    return default_replies.get(intent, default_replies["chat"])


# ==================== Flask 应用 ====================
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# 对话历史
conversation_history = {}


@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory('.', 'index.html')


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_id = data.get('user_id', 'default')
    user_input = data.get('message', '').strip()

    if not user_input:
        return jsonify({"reply": "请输入内容"})

    intent = classify_intent(user_input)

    if intent == "emergency":
        return jsonify({"reply": handle_emergency(), "intent": intent})

    knowledge = retrieve_knowledge(user_input)
    reply = get_reply(user_input, knowledge, intent)

    # 保存历史
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({"user": user_input, "assistant": reply})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    return jsonify({
        "reply": reply,
        "intent": intent,
        "has_knowledge": knowledge is not None
    })


@app.route('/clear', methods=['POST'])
def clear():
    data = request.json
    user_id = data.get('user_id', 'default')
    conversation_history[user_id] = []
    return jsonify({"status": "cleared"})


@app.route('/health', methods=['GET'])
def health():
    stats = db_manager.get_session().__enter__().query(HealthArticle).count()
    return jsonify({
        "status": "ok",
        "message": "灵枢安智能体运行正常",
        "knowledge_count": stats,
        "vector_loaded": vector_store.model is not None
    })


@app.route('/suggestions', methods=['GET'])
def suggestions():
    suggestions_list = [
        "我头疼怎么办？",
        "感冒了吃什么药？",
        "高血压要注意什么？",
        "最近总是失眠",
        "怎么缓解焦虑？",
        "健康饮食建议",
        "运动损伤怎么处理？",
        "胃痛怎么办？"
    ]
    return jsonify({"suggestions": suggestions_list})


@app.route('/api/crawl', methods=['POST'])
def run_crawl():
    """手动触发爬虫"""
    data = request.json or {}
    source = data.get('source', 'all')

    crawler = HealthCrawler()

    # 在后台线程中运行
    def run():
        crawler.run(source)
        init_vector_knowledge()  # 更新向量库

    thread = threading.Thread(target=run)
    thread.start()

    return jsonify({"status": "started", "message": f"爬虫已启动，正在爬取 {source} 数据"})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取数据统计"""
    with db_manager.get_session() as session:
        article_count = session.query(HealthArticle).count()
        task_count = session.query(CrawlTask).count()
        completed_tasks = session.query(CrawlTask).filter(CrawlTask.status == 'completed').count()

    return jsonify({
        'articles': article_count,
        'crawl_tasks': task_count,
        'completed_tasks': completed_tasks,
        'vector_collections': len(os.listdir(vector_store.persist_path)) if os.path.exists(
            vector_store.persist_path) else 0
    })


@app.route('/api/articles', methods=['GET'])
def get_articles():
    """获取文章列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    with db_manager.get_session() as session:
        query = session.query(HealthArticle)
        total = query.count()
        articles = query.order_by(HealthArticle.created_at.desc()) \
            .offset((page - 1) * per_page) \
            .limit(per_page) \
            .all()

        return jsonify({
            'total': total,
            'page': page,
            'per_page': per_page,
            'items': [{
                'id': a.id,
                'title': a.title,
                'summary': a.summary or a.content[:100],
                'category': a.category,
                'source': a.source,
                'created_at': a.created_at.isoformat() if a.created_at else None
            } for a in articles]
        })


# ==================== 启动 ====================
if __name__ == '__main__':
    print("=" * 50)
    print("🌿 灵枢安智能体启动中...")
    print("=" * 50)

    # 初始化数据库
    print("📦 初始化数据库...")
    # 数据库已在 DatabaseManager 中初始化

    # 初始化向量知识库
    print("🔍 初始化向量知识库...")
    init_vector_knowledge()

    # 可选：自动运行一次爬虫获取数据
    print("🕷️ 检查数据...")
    with db_manager.get_session() as session:
        count = session.query(HealthArticle).count()
        if count == 0:
            print("📡 首次运行，自动爬取数据...")
            crawler = HealthCrawler()
            crawler.run('all')
            init_vector_knowledge()

    print("=" * 50)
    print("🚀 服务已启动，访问 http://localhost:5000")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5000, debug=True)