# 知识库管理
"""
知识库管理 - 整合向量检索和数据库查询
"""
from typing import List, Dict, Any, Optional
from .vector_store import vector_store


class KnowledgeBase:
    """知识库管理器"""

    def __init__(self, db_manager=None):
        self.db = db_manager
        self.vector_store = vector_store
        self.collection_name = "health_knowledge"

        # 确保集合存在
        self.vector_store.create_collection(self.collection_name)

    def add_knowledge(self, text: str, metadata: Dict = None) -> bool:
        """添加知识到向量库"""
        return self.vector_store.add(
            collection_name=self.collection_name,
            documents=[text],
            metadatas=[metadata or {}],
            ids=None
        )

    def add_batch(self, items: List[Dict]) -> int:
        """批量添加知识"""
        documents = []
        metadatas = []

        for item in items:
            documents.append(item.get('text', ''))
            metadatas.append({
                'source': item.get('source', ''),
                'category': item.get('category', ''),
                'tags': item.get('tags', '')
            })

        success = self.vector_store.add(
            collection_name=self.collection_name,
            documents=documents,
            metadatas=metadatas
        )

        return len(documents) if success else 0

    def search(self, query: str, n_results: int = 3) -> List[Dict]:
        """搜索知识"""
        results = self.vector_store.query(
            collection_name=self.collection_name,
            query_text=query,
            n_results=n_results
        )

        documents = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]

        return [
            {
                'text': doc,
                'metadata': meta,
                'score': 1 - dist
            }
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]

    def search_from_db(self, query: str, limit: int = 5) -> List[Dict]:
        """从关系数据库搜索"""
        if not self.db:
            return []

        from database.models import HealthArticle, MedicalKnowledge

        results = []

        with self.db.get_session() as session:
            # 搜索文章
            articles = session.query(HealthArticle).filter(
                HealthArticle.title.like(f'%{query}%') |
                HealthArticle.content.like(f'%{query}%')
            ).limit(limit).all()

            for article in articles:
                results.append({
                    'type': 'article',
                    'title': article.title,
                    'content': article.content[:500],
                    'source': article.source,
                    'score': 0.5
                })

            # 搜索医学知识
            medical = session.query(MedicalKnowledge).filter(
                MedicalKnowledge.disease_name.like(f'%{query}%') |
                MedicalKnowledge.symptom.like(f'%{query}%')
            ).limit(limit).all()

            for m in medical:
                results.append({
                    'type': 'medical',
                    'name': m.disease_name,
                    'symptom': m.symptom[:200] if m.symptom else '',
                    'treatment': m.treatment[:200] if m.treatment else '',
                    'score': 0.6
                })

        return results

    def hybrid_search(self, query: str, n_results: int = 5) -> List[Dict]:
        """混合搜索（向量+关键词）"""
        # 向量搜索
        vector_results = self.search(query, n_results)

        # 数据库搜索
        db_results = self.search_from_db(query, n_results)

        # 合并结果
        all_results = vector_results + db_results

        # 去重和排序
        seen_texts = set()
        unique_results = []

        for r in all_results:
            text = r.get('text', '') or r.get('content', '') or r.get('symptom', '')
            text_key = text[:100]

            if text_key not in seen_texts:
                seen_texts.add(text_key)
                unique_results.append(r)

        # 按分数排序
        unique_results.sort(key=lambda x: x.get('score', 0), reverse=True)

        return unique_results[:n_results]

    def index_database(self):
        """索引数据库中的内容到向量库"""
        if not self.db:
            print("未配置数据库，跳过索引")
            return

        from database.models import HealthArticle, MedicalKnowledge

        items = []

        with self.db.get_session() as session:
            # 索引文章
            articles = session.query(HealthArticle).limit(500).all()
            for article in articles:
                text = f"{article.title}\n{article.content}"
                items.append({
                    'text': text,
                    'source': article.source,
                    'category': article.category,
                    'tags': article.tags
                })

            # 索引医学知识
            medical = session.query(MedicalKnowledge).limit(500).all()
            for m in medical:
                text = f"疾病：{m.disease_name}\n症状：{m.symptom}\n治疗：{m.treatment}"
                items.append({
                    'text': text,
                    'source': m.source,
                    'category': 'medical',
                    'tags': m.keywords
                })

        # 批量添加
        count = self.add_batch(items)
        print(f"✓ 已索引 {count} 条知识")

    def get_stats(self) -> Dict:
        """获取知识库统计"""
        vector_stats = self.vector_store.get_stats()

        db_stats = {}
        if self.db:
            db_stats = self.db.get_statistics()

        return {
            'vector_store': vector_stats,
            'database': db_stats,
            'collection': self.collection_name
        }


# 全局实例
knowledge_base = None


def init_knowledge_base(db_manager=None):
    """初始化知识库"""
    global knowledge_base
    knowledge_base = KnowledgeBase(db_manager)
    return knowledge_base