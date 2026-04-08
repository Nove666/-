"""
数据库管理 - 连接、会话、CRUD操作
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os
from typing import List, Dict, Any, Optional

# 尝试加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass


class DatabaseManager:
    """数据库管理器"""

   def __init__(self):
    import tempfile
    temp_dir = tempfile.gettempdir()
    db_path = os.path.join(temp_dir, 'lingshu_an.db')
    self.engine = create_engine(f'sqlite:///{db_path}', connect_args={'check_same_thread': False})
    self.Session = scoped_session(sessionmaker(bind=self.engine))
    self._create_tables()

    def _get_default_url(self) -> str:
        """获取默认数据库URL"""
        db_type = os.getenv('DB_TYPE', 'sqlite')

        if db_type == 'mysql':
            host = os.getenv('DB_HOST', 'localhost')
            port = os.getenv('DB_PORT', '3306')
            user = os.getenv('DB_USER', 'root')
            password = os.getenv('DB_PASSWORD', '')
            database = os.getenv('DB_NAME', 'lingshu_an')
            return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

        elif db_type == 'postgresql':
            host = os.getenv('DB_HOST', 'localhost')
            port = os.getenv('DB_PORT', '5432')
            user = os.getenv('DB_USER', 'postgres')
            password = os.getenv('DB_PASSWORD', '')
            database = os.getenv('DB_NAME', 'lingshu_an')
            return f"postgresql://{user}:{password}@{host}:{port}/{database}"

        else:
            # SQLite作为默认
            db_path = os.getenv('DB_PATH', 'lingshu_an.db')
            return f"sqlite:///{db_path}"

    def _init_engine(self):
        """初始化数据库引擎"""
        try:
            # SQLite特殊处理
            if self.db_url.startswith('sqlite'):
                self.engine = create_engine(
                    self.db_url,
                    connect_args={'check_same_thread': False},
                    echo=False
                )
            else:
                self.engine = create_engine(
                    self.db_url,
                    poolclass=QueuePool,
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    echo=False
                )

            self.Session = scoped_session(sessionmaker(bind=self.engine))
            print(f"✓ 数据库连接成功: {self.db_url.split('@')[-1] if '@' in self.db_url else self.db_url}")

        except Exception as e:
            print(f"✗ 数据库连接失败: {e}")
            # 降级到SQLite
            if not self.db_url.startswith('sqlite'):
                print("降级使用SQLite数据库")
                self.db_url = "sqlite:///lingshu_an.db"
                self._init_engine()

    @contextmanager
    def get_session(self):
        """获取数据库会话（上下文管理器）"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def create_tables(self, base):
        """创建所有表"""
        with self.engine.connect() as conn:
            base.metadata.create_all(self.engine)
        print("✓ 数据库表创建成功")

    def drop_tables(self, base):
        """删除所有表"""
        with self.engine.connect() as conn:
            base.metadata.drop_all(self.engine)
        print("✓ 数据库表已删除")

    def execute_raw(self, sql: str, params: Dict = None):
        """执行原始SQL"""
        with self.get_session() as session:
            result = session.execute(text(sql), params or {})
            return result

    def bulk_insert(self, model, items: List[Dict], batch_size: int = 100):
        """批量插入"""
        if not items:
            return 0

        with self.get_session() as session:
            for i in range(0, len(items), batch_size):
                batch = items[i:i+batch_size]
                objects = [model(**item) for item in batch]
                session.bulk_save_objects(objects)
                session.flush()

            session.commit()

        return len(items)

    def get_count(self, model, filters: Dict = None) -> int:
        """获取记录数"""
        with self.get_session() as session:
            query = session.query(model)
            if filters:
                for key, value in filters.items():
                    if hasattr(model, key):
                        query = query.filter(getattr(model, key) == value)
            return query.count()

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        from .models import HealthArticle, MedicalKnowledge, Drug, Symptom, CrawlTask

        with self.get_session() as session:
            return {
                'articles': session.query(HealthArticle).count(),
                'medical_knowledge': session.query(MedicalKnowledge).count(),
                'drugs': session.query(Drug).count(),
                'symptoms': session.query(Symptom).count(),
                'crawl_tasks': session.query(CrawlTask).count(),
                'db_type': self.db_url.split(':')[0]
            }

    def close(self):
        """关闭数据库连接"""
        if self.Session:
            self.Session.remove()
        if self.engine:
            self.engine.dispose()
        print("✓ 数据库连接已关闭")


# 全局数据库实例
db_manager = DatabaseManager()
