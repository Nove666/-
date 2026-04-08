# 基础爬虫类
"""
基础爬虫类 - 所有爬虫的基类
"""
import asyncio
import aiohttp
import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime
import random
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    """基础爬虫抽象类"""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        self.delay = 1.0  # 请求延迟（秒）
        self.max_retries = 3
        self.timeout = 30

    async def get_session(self):
        """获取或创建aiohttp会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session

    async def fetch(self, url: str, retry: int = 0) -> Optional[str]:
        """异步获取网页内容"""
        try:
            session = await self.get_session()
            async with session.get(url, timeout=self.timeout) as response:
                if response.status == 200:
                    return await response.text()
                elif response.status == 429:  # Too Many Requests
                    wait_time = self.delay * (retry + 1)
                    logger.warning(f"请求被限流，等待 {wait_time} 秒后重试: {url}")
                    await asyncio.sleep(wait_time)
                    return await self.fetch(url, retry + 1)
                else:
                    logger.warning(f"请求失败 {response.status}: {url}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"请求超时: {url}")
            if retry < self.max_retries:
                await asyncio.sleep(self.delay)
                return await self.fetch(url, retry + 1)
        except Exception as e:
            logger.error(f"请求异常: {url}, {e}")
            if retry < self.max_retries:
                await asyncio.sleep(self.delay)
                return await self.fetch(url, retry + 1)
        return None

    async def fetch_json(self, url: str, retry: int = 0) -> Optional[Dict]:
        """获取JSON数据"""
        try:
            session = await self.get_session()
            async with session.get(url, timeout=self.timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"JSON请求失败 {response.status}: {url}")
                    return None
        except Exception as e:
            logger.error(f"JSON请求异常: {url}, {e}")
            if retry < self.max_retries:
                await asyncio.sleep(self.delay)
                return await self.fetch_json(url, retry + 1)
        return None

    async def post(self, url: str, data: Dict = None, retry: int = 0) -> Optional[str]:
        """POST请求"""
        try:
            session = await self.get_session()
            async with session.post(url, json=data, timeout=self.timeout) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception as e:
            logger.error(f"POST请求异常: {url}, {e}")
            if retry < self.max_retries:
                await asyncio.sleep(self.delay)
                return await self.post(url, data, retry + 1)
        return None

    async def random_delay(self):
        """随机延迟，避免被反爬"""
        await asyncio.sleep(random.uniform(self.delay, self.delay * 2))

    @abstractmethod
    async def crawl(self, **kwargs) -> List[Dict]:
        """爬取数据的主方法，子类必须实现"""
        pass

    async def close(self):
        """关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()

    def clean_text(self, text: str) -> str:
        """清洗文本"""
        if not text:
            return ""
        import re
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()

    def extract_emails(self, text: str) -> List[str]:
        """提取邮箱"""
        import re
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        return re.findall(pattern, text)

    def extract_urls(self, text: str) -> List[str]:
        """提取URL"""
        import re
        pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        return re.findall(pattern, text)