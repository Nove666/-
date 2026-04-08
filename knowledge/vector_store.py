"""
向量数据库管理
"""
import os
import json
import numpy as np
from typing import List, Dict, Any, Optional


class VectorStore:
    """向量存储（使用本地文件存储，无需外部依赖）"""

    def __init__(self, persist_path: str = "./vector_db"):
        self.persist_path = persist_path
        self.collections = {}
        self.model = None

        # 确保目录存在
        if not os.path.exists(persist_path):
            os.makedirs(persist_path)

        # 尝试加载向量模型
        self._load_model()

        # 加载已有集合
        self._load_collections()

    def _load_model(self):
        """加载向量模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            print("✓ 向量模型加载成功")
        except Exception as e:
            print(f"⚠ 向量模型加载失败: {e}")
            self.model = None

    def _load_collections(self):
        """加载已有集合"""
        collection_file = os.path.join(self.persist_path, 'collections.json')
        if os.path.exists(collection_file):
            with open(collection_file, 'r', encoding='utf-8') as f:
                self.collections = json.load(f)

    def _save_collections(self):
        """保存集合信息"""
        collection_file = os.path.join(self.persist_path, 'collections.json')
        with open(collection_file, 'w', encoding='utf-8') as f:
            json.dump(self.collections, f, ensure_ascii=False, indent=2)

    def create_collection(self, name: str) -> bool:
        """创建集合"""
        if name in self.collections:
            return False

        self.collections[name] = {
            'name': name,
            'created_at': __import__('datetime').datetime.now().isoformat(),
            'count': 0
        }

        # 创建集合文件
        collection_file = os.path.join(self.persist_path, f"{name}.json")
        with open(collection_file, 'w', encoding='utf-8') as f:
            json.dump([], f)

        self._save_collections()
        return True

    def get_collection(self, name: str) -> Optional[Dict]:
        """获取集合"""
        return self.collections.get(name)

    def add(self, collection_name: str, documents: List[str],
            embeddings: List[List[float]] = None,
            metadatas: List[Dict] = None,
            ids: List[str] = None) -> bool:
        """添加向量到集合"""
        if collection_name not in self.collections:
            self.create_collection(collection_name)

        # 生成嵌入向量
        if embeddings is None and self.model:
            embeddings = self.model.encode(documents).tolist()
        elif embeddings is None:
            # 使用随机向量作为降级
            embeddings = [[0.0] * 384 for _ in documents]

        # 加载现有数据
        collection_file = os.path.join(self.persist_path, f"{collection_name}.json")
        with open(collection_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 添加新数据
        for i, doc in enumerate(documents):
            item = {
                'id': ids[i] if ids and i < len(ids) else f"doc_{len(data)}",
                'document': doc,
                'embedding': embeddings[i] if i < len(embeddings) else [],
                'metadata': metadatas[i] if metadatas and i < len(metadatas) else {}
            }
            data.append(item)

        # 保存
        with open(collection_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

        self.collections[collection_name]['count'] = len(data)
        self._save_collections()

        return True

    def query(self, collection_name: str, query_text: str, n_results: int = 3) -> Dict:
        """查询相似向量"""
        if collection_name not in self.collections:
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}

        # 加载数据
        collection_file = os.path.join(self.persist_path, f"{collection_name}.json")
        with open(collection_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data:
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}

        # 生成查询向量
        if self.model:
            query_embedding = self.model.encode(query_text).tolist()
        else:
            query_embedding = [0.0] * 384

        # 计算相似度
        results = []
        for item in data:
            if item.get('embedding'):
                similarity = self._cosine_similarity(query_embedding, item['embedding'])
                results.append({
                    'document': item['document'],
                    'metadata': item.get('metadata', {}),
                    'distance': 1 - similarity,
                    'similarity': similarity
                })

        # 排序
        results.sort(key=lambda x: x['similarity'], reverse=True)
        top_results = results[:n_results]

        return {
            'documents': [[r['document'] for r in top_results]],
            'metadatas': [[r['metadata'] for r in top_results]],
            'distances': [[r['distance'] for r in top_results]]
        }

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        try:
            a_np = np.array(a)
            b_np = np.array(b)
            return np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-8)
        except:
            return 0.0

    def delete_collection(self, name: str):
        """删除集合"""
        if name in self.collections:
            del self.collections[name]
            collection_file = os.path.join(self.persist_path, f"{name}.json")
            if os.path.exists(collection_file):
                os.remove(collection_file)
            self._save_collections()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'collections': len(self.collections),
            'model_loaded': self.model is not None,
            'persist_path': self.persist_path,
            'collection_details': self.collections
        }


# 全局实例
vector_store = VectorStore()