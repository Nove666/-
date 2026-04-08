"""
配置文件
"""
import os
from typing import Dict, Any

# 尝试加载环境变量
try:
    from dotenv import load_dotenv

    load_dotenv()
except:
    pass


class Config:
    """基础配置"""

    # Flask配置
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

    # 数据库配置
    DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '3306')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME = os.getenv('DB_NAME', 'lingshu_an')

    # OpenAI配置
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')

    # 爬虫配置
    CRAWLER_DELAY = float(os.getenv('CRAWLER_DELAY', '1.0'))
    CRAWLER_TIMEOUT = int(os.getenv('CRAWLER_TIMEOUT', '30'))
    CRAWLER_MAX_RETRIES = int(os.getenv('CRAWLER_MAX_RETRIES', '3'))

    # 向量模型配置
    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')
    VECTOR_DB_PATH = os.getenv('VECTOR_DB_PATH', './vector_db')

    # API配置
    API_HOST = os.getenv('API_HOST', '0.0.0.0')
    API_PORT = int(os.getenv('API_PORT', '5000'))

    # 数据源配置
    DATA_SOURCES: Dict[str, Any] = {
        'dingxiang': {
            'enabled': True,
            'name': '丁香园',
            'urls': [
                'https://dxy.com/disease/list',
                'https://dxy.com/health/list'
            ]
        },
        'baidu_health': {
            'enabled': True,
            'name': '百度健康',
            'keywords': [
                '感冒', '发烧', '咳嗽', '头痛', '胃痛',
                '高血压', '糖尿病', '失眠', '焦虑', '运动损伤'
            ]
        },
        'wechat': {
            'enabled': False,
            'name': '微信公众号',
            'accounts': ['丁香医生', '健康中国', '医学界']
        },
        'pubmed': {
            'enabled': False,
            'name': 'PubMed',
            'keywords': ['common cold', 'hypertension', 'diabetes']
        }
    }

    # 定时任务配置
    SCHEDULED_TASKS = {
        'daily_crawl': {
            'enabled': True,
            'cron': 'daily 02:00',
            'crawler': 'dingxiang'
        },
        'weekly_search': {
            'enabled': True,
            'cron': 'weekly 03:00',
            'crawler': 'baidu'
        }
    }

    # 日志配置
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/app.log')

    @classmethod
    def get_db_url(cls) -> str:
        """获取数据库连接URL"""
        if cls.DB_TYPE == 'mysql':
            return f"mysql+pymysql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}?charset=utf8mb4"
        elif cls.DB_TYPE == 'postgresql':
            return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
        else:
            return f"sqlite:///{cls.DB_NAME}.db"

    @classmethod
    def get_enabled_sources(cls) -> list:
        """获取启用的数据源"""
        return [name for name, config in cls.DATA_SOURCES.items() if config.get('enabled')]


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'


def get_config():
    """获取当前环境配置"""
    env = os.getenv('ENV', 'development')
    if env == 'production':
        return ProductionConfig
    return DevelopmentConfig