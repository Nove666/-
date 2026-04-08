"""
数据库迁移管理 - 同时支持 SQLite 和 MySQL
"""
import os
from datetime import datetime
from typing import List, Tuple
from sqlalchemy import text


class SimpleMigrationManager:
    """简单迁移管理器"""

    def __init__(self, db_manager):
        self.db = db_manager
        self.migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
        self._ensure_dirs()
        self.db_type = self._get_db_type()

    def _get_db_type(self):
        """获取数据库类型"""
        db_url = str(self.db.engine.url)
        if 'mysql' in db_url:
            return 'mysql'
        elif 'postgresql' in db_url:
            return 'postgresql'
        else:
            return 'sqlite'

    def _ensure_dirs(self):
        """确保目录存在"""
        if not os.path.exists(self.migrations_dir):
            os.makedirs(self.migrations_dir)

        versions_dir = os.path.join(self.migrations_dir, 'versions')
        if not os.path.exists(versions_dir):
            os.makedirs(versions_dir)

    def _get_migration_table(self):
        """获取或创建迁移记录表"""
        with self.db.get_session() as session:
            try:
                session.execute(text("SELECT 1 FROM schema_migrations LIMIT 1"))
            except:
                # 根据数据库类型创建不同的表
                if self.db_type == 'mysql':
                    session.execute(text("""
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            version VARCHAR(255) PRIMARY KEY,
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            description TEXT
                        )
                    """))
                else:
                    session.execute(text("""
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            version VARCHAR(255) PRIMARY KEY,
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            description TEXT
                        )
                    """))
                session.commit()

    def create_migration(self, name: str, sql_content: str = None):
        """创建迁移文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{name}.sql"
        filepath = os.path.join(self.migrations_dir, 'versions', filename)

        if sql_content is None:
            sql_content = self._get_migration_template(name)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(sql_content)

        print(f"✓ 创建迁移文件: {filename}")
        return filepath

    def _get_migration_template(self, name):
        """获取迁移模板"""
        if self.db_type == 'mysql':
            return f"""-- Migration: {name}
-- Database: MySQL
-- Created at: {datetime.now()}

-- UP migration
-- 在这里写你的迁移SQL


-- DOWN migration (rollback)
-- 在这里写回滚SQL

"""
        else:
            return f"""-- Migration: {name}
-- Database: SQLite
-- Created at: {datetime.now()}

-- UP migration
-- 在这里写你的迁移SQL


-- DOWN migration (rollback)
-- 在这里写回滚SQL

"""

    def migrate(self, target_version: str = None):
        """执行迁移"""
        self._get_migration_table()

        applied = self._get_applied_versions()
        migrations = self._get_migration_files()
        migrations.sort(key=lambda x: x[0])

        for version, name, path in migrations:
            if version in applied:
                continue

            if target_version and version > target_version:
                break

            print(f"执行迁移: {name} ({version})")
            self._apply_migration(path, version, name)

    def rollback(self, steps: int = 1):
        """回滚迁移"""
        self._get_migration_table()

        with self.db.get_session() as session:
            result = session.execute(text("""
                SELECT version, description FROM schema_migrations 
                ORDER BY applied_at DESC LIMIT :steps
            """), {'steps': steps})
            to_rollback = result.fetchall()

        for version, description in to_rollback:
            print(f"回滚迁移: {description} ({version})")
            self._rollback_migration(version)

    def _get_applied_versions(self) -> set:
        """获取已应用的版本"""
        with self.db.get_session() as session:
            try:
                result = session.execute(text("SELECT version FROM schema_migrations"))
                return {row[0] for row in result}
            except:
                return set()

    def _get_migration_files(self) -> List[Tuple[str, str, str]]:
        """获取迁移文件列表"""
        versions_dir = os.path.join(self.migrations_dir, 'versions')
        migrations = []

        if not os.path.exists(versions_dir):
            return migrations

        for filename in os.listdir(versions_dir):
            if filename.endswith('.sql'):
                parts = filename.split('_', 1)
                if len(parts) == 2:
                    version = parts[0]
                    name = parts[1].replace('.sql', '')
                    path = os.path.join(versions_dir, filename)
                    migrations.append((version, name, path))

        return migrations

    def _apply_migration(self, path: str, version: str, name: str):
        """应用迁移"""
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        if '-- DOWN' in content:
            up_sql = content.split('-- DOWN')[0]
        else:
            up_sql = content

        with self.db.get_session() as session:
            statements = self._split_sql(up_sql)
            for stmt in statements:
                if stmt.strip():
                    try:
                        session.execute(text(stmt))
                    except Exception as e:
                        print(f"  执行失败: {stmt[:100]}...")
                        print(f"  错误: {e}")
                        raise

            session.execute(text("""
                INSERT INTO schema_migrations (version, description)
                VALUES (:version, :description)
            """), {'version': version, 'description': name})

            session.commit()

        print(f"  ✓ 已应用")

    def _rollback_migration(self, version: str):
        """回滚迁移"""
        migrations = self._get_migration_files()

        for v, name, path in migrations:
            if v == version:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if '-- DOWN' in content:
                    down_sql = content.split('-- DOWN')[1]

                    with self.db.get_session() as session:
                        statements = self._split_sql(down_sql)
                        for stmt in statements:
                            if stmt.strip():
                                session.execute(text(stmt))

                        session.execute(text("""
                            DELETE FROM schema_migrations WHERE version = :version
                        """), {'version': version})

                        session.commit()

                    print(f"  ✓ 已回滚")
                break

    def _split_sql(self, sql: str) -> List[str]:
        """分割SQL语句"""
        statements = []
        current = []

        for line in sql.split('\n'):
            line = line.strip()
            if line.startswith('--') or not line:
                continue

            current.append(line)
            if line.endswith(';'):
                statements.append(' '.join(current))
                current = []

        return statements

    def show_history(self):
        """显示迁移历史"""
        self._get_migration_table()

        with self.db.get_session() as session:
            result = session.execute(text("""
                SELECT version, description, applied_at 
                FROM schema_migrations 
                ORDER BY applied_at DESC
            """))

            print("\n=== 迁移历史 ===")
            rows = result.fetchall()
            if rows:
                for row in rows:
                    print(f"  {row[0]}: {row[1]} ({row[2]})")
            else:
                print("  暂无迁移记录")

    def generate_initial_migration(self):
        """生成初始迁移（根据数据库类型生成正确的SQL）"""
        if self.db_type == 'mysql':
            initial_sql = """-- Initial schema for MySQL
-- Created at: {}

-- 健康文章表
CREATE TABLE IF NOT EXISTS health_articles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    source VARCHAR(200),
    source_url VARCHAR(500),
    category VARCHAR(100),
    tags VARCHAR(500),
    author VARCHAR(100),
    publish_date DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    view_count INT DEFAULT 0,
    is_verified TINYINT(1) DEFAULT 0
);

-- 医学知识表
CREATE TABLE IF NOT EXISTS medical_knowledge (
    id INT PRIMARY KEY AUTO_INCREMENT,
    disease_name VARCHAR(200),
    symptom TEXT,
    cause TEXT,
    treatment TEXT,
    prevention TEXT,
    diet_advice TEXT,
    medication TEXT,
    when_to_see_doctor TEXT,
    keywords VARCHAR(500),
    confidence_score FLOAT DEFAULT 0.0,
    source VARCHAR(200),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 爬取任务表
CREATE TABLE IF NOT EXISTS crawl_tasks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    task_name VARCHAR(200),
    source VARCHAR(200),
    status VARCHAR(50) DEFAULT 'pending',
    total_items INT DEFAULT 0,
    processed_items INT DEFAULT 0,
    error_message TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- DOWN: 删除所有表
-- DROP TABLE IF EXISTS crawl_tasks;
-- DROP TABLE IF EXISTS medical_knowledge;
-- DROP TABLE IF EXISTS health_articles;
-- DROP TABLE IF EXISTS schema_migrations;
""".format(datetime.now())
        else:
            initial_sql = """-- Initial schema for SQLite
-- Created at: {}

-- 健康文章表
CREATE TABLE IF NOT EXISTS health_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    source VARCHAR(200),
    source_url VARCHAR(500),
    category VARCHAR(100),
    tags VARCHAR(500),
    author VARCHAR(100),
    publish_date DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    view_count INTEGER DEFAULT 0,
    is_verified BOOLEAN DEFAULT 0
);

-- 医学知识表
CREATE TABLE IF NOT EXISTS medical_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    disease_name VARCHAR(200),
    symptom TEXT,
    cause TEXT,
    treatment TEXT,
    prevention TEXT,
    diet_advice TEXT,
    medication TEXT,
    when_to_see_doctor TEXT,
    keywords VARCHAR(500),
    confidence_score FLOAT DEFAULT 0.0,
    source VARCHAR(200),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 爬取任务表
CREATE TABLE IF NOT EXISTS crawl_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name VARCHAR(200),
    source VARCHAR(200),
    status VARCHAR(50) DEFAULT 'pending',
    total_items INTEGER DEFAULT 0,
    processed_items INTEGER DEFAULT 0,
    error_message TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- DOWN: 删除所有表
-- DROP TABLE IF EXISTS crawl_tasks;
-- DROP TABLE IF EXISTS medical_knowledge;
-- DROP TABLE IF EXISTS health_articles;
-- DROP TABLE IF EXISTS schema_migrations;
""".format(datetime.now())

        return self.create_migration("initial_schema", initial_sql)


