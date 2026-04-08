"""
健康数据爬虫实现
"""
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict
from datetime import datetime
import json
import re
from .base_crawler import BaseCrawler


class HealthDataCrawler(BaseCrawler):
    """通用健康数据爬虫"""

    def __init__(self, db_manager=None):
        super().__init__(db_manager)
        self.source_name = "health_general"

    async def crawl(self, urls: List[str] = None, **kwargs) -> List[Dict]:
        """爬取健康数据"""
        if urls is None:
            urls = kwargs.get('urls', [])

        results = []
        for url in urls:
            html = await self.fetch(url)
            if html:
                articles = self.parse_page(html, url)
                results.extend(articles)
            await self.random_delay()

        return results

    def parse_page(self, html: str, url: str) -> List[Dict]:
        """解析页面"""
        soup = BeautifulSoup(html, 'html.parser')
        articles = []

        # 查找文章容器（常见选择器）
        selectors = [
            'article', '.article', '.post', '.content',
            '.news-item', '.list-item', '.item'
        ]

        for selector in selectors:
            items = soup.select(selector)
            for item in items:
                article = self.parse_article_item(item, url)
                if article and article.get('title') and article.get('content'):
                    articles.append(article)

        return articles

    def parse_article_item(self, item, base_url: str) -> Dict:
        """解析单个文章项"""
        # 提取标题
        title_elem = item.find(['h1', 'h2', 'h3', '.title', '.headline'])
        title = title_elem.get_text(strip=True) if title_elem else ''

        # 提取内容
        content_elem = item.find(['.content', '.article-content', '.post-content', 'p'])
        content = ''
        if content_elem:
            content = content_elem.get_text(strip=True)
        else:
            # 尝试获取所有段落
            paragraphs = item.find_all('p')
            content = ' '.join([p.get_text(strip=True) for p in paragraphs[:10]])

        # 提取链接
        link_elem = item.find('a', href=True)
        url = link_elem['href'] if link_elem else ''
        if url and not url.startswith('http'):
            url = base_url.rstrip('/') + '/' + url.lstrip('/')

        # 提取时间
        time_elem = item.find(['time', '.date', '.time'])
        publish_date = None
        if time_elem:
            date_text = time_elem.get_text(strip=True)
            publish_date = self.parse_date(date_text)

        return {
            'title': self.clean_text(title),
            'content': self.clean_text(content),
            'source': self.source_name,
            'source_url': url,
            'publish_date': publish_date or datetime.now(),
            'category': self.guess_category(title + content)
        }

    def guess_category(self, text: str) -> str:
        """猜测文章分类"""
        categories = {
            'symptom': ['感冒', '发烧', '咳嗽', '头痛', '胃痛', '腹泻', '呕吐'],
            'chronic': ['高血压', '糖尿病', '心脏病', '慢病', '长期'],
            'medication': ['药', '用药', '服药', '剂量', '药品'],
            'wellness': ['养生', '保健', '饮食', '运动', '睡眠', '减压'],
            'emotion': ['焦虑', '抑郁', '压力', '情绪', '心理']
        }

        for category, keywords in categories.items():
            if any(kw in text for kw in keywords):
                return category
        return 'general'

    def parse_date(self, date_str: str) -> datetime:
        """解析日期字符串"""
        patterns = [
            r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})',
            r'(\d{1,2})[-/月](\d{1,2})[-/日]\s*(\d{4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    try:
                        year, month, day = map(int, groups)
                        if year < 100:
                            year += 2000
                        return datetime(year, month, day)
                    except ValueError:
                        pass
        return datetime.now()


class DingXiangCrawler(HealthDataCrawler):
    """丁香园爬虫"""

    def __init__(self, db_manager=None):
        super().__init__(db_manager)
        self.source_name = "丁香园"
        self.base_url = "https://dxy.com"

    async def crawl(self, **kwargs) -> List[Dict]:
        """爬取丁香园数据"""
        urls = [
            f"{self.base_url}/disease/list",
            f"{self.base_url}/health/list",
            f"{self.base_url}/drug/list"
        ]

        results = []
        for url in urls:
            html = await self.fetch(url)
            if html:
                articles = self.parse_dxy_page(html, url)
                results.extend(articles)
            await self.random_delay()

        return results

    def parse_dxy_page(self, html: str, url: str) -> List[Dict]:
        """解析丁香园页面"""
        soup = BeautifulSoup(html, 'html.parser')
        articles = []

        # 丁香园特有的选择器
        items = soup.select('.disease-item, .health-article, .drug-item')

        for item in items:
            title_elem = item.select_one('h3, .title, a')
            title = title_elem.get_text(strip=True) if title_elem else ''

            desc_elem = item.select_one('.desc, .summary, p')
            description = desc_elem.get_text(strip=True) if desc_elem else ''

            link_elem = item.select_one('a[href]')
            link = link_elem['href'] if link_elem else ''
            if link and not link.startswith('http'):
                link = self.base_url + link

            if title:
                articles.append({
                    'title': self.clean_text(title),
                    'content': self.clean_text(description) or title,
                    'summary': self.clean_text(description)[:200] if description else title[:200],
                    'source': self.source_name,
                    'source_url': link,
                    'publish_date': datetime.now(),
                    'category': self.guess_category(title + description),
                    'tags': self.extract_tags(title + description)
                })

        return articles

    def extract_tags(self, text: str) -> str:
        """提取标签"""
        common_tags = ['感冒', '发烧', '咳嗽', '头痛', '高血压', '糖尿病', '失眠', '焦虑']
        found = [tag for tag in common_tags if tag in text]
        return ','.join(found[:5])


class BaiduHealthCrawler(HealthDataCrawler):
    """百度健康爬虫"""

    def __init__(self, db_manager=None):
        super().__init__(db_manager)
        self.source_name = "百度健康"
        self.base_url = "https://health.baidu.com"

    async def crawl(self, keywords: List[str] = None, **kwargs) -> List[Dict]:
        """搜索爬取"""
        if keywords is None:
            keywords = ['感冒', '发烧', '头痛', '胃痛', '高血压', '糖尿病', '失眠']

        results = []
        for keyword in keywords:
            search_results = await self.search_disease(keyword)
            results.extend(search_results)
            await self.random_delay()

        return results

    async def search_disease(self, keyword: str) -> List[Dict]:
        """搜索疾病"""
        search_url = f"{self.base_url}/search"
        params = {'q': keyword}

        # 构建URL
        from urllib.parse import urlencode
        url = f"{search_url}?{urlencode(params)}"

        html = await self.fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # 解析搜索结果
        items = soup.select('.result-item, .search-item, .disease-item')

        for item in items:
            title_elem = item.select_one('a, .title, h3')
            title = title_elem.get_text(strip=True) if title_elem else ''

            desc_elem = item.select_one('.desc, .summary, .content')
            description = desc_elem.get_text(strip=True) if desc_elem else ''

            link_elem = item.select_one('a[href]')
            link = link_elem['href'] if link_elem else ''

            if title:
                results.append({
                    'title': self.clean_text(title),
                    'content': self.clean_text(description) or self.get_disease_info(keyword),
                    'summary': self.clean_text(description)[:200] if description else '',
                    'source': self.source_name,
                    'source_url': link,
                    'publish_date': datetime.now(),
                    'category': 'symptom',
                    'tags': keyword
                })

        return results

    def get_disease_info(self, disease: str) -> str:
        """获取疾病基本信息"""
        disease_info = {
            '感冒': '感冒是由病毒引起的常见呼吸道疾病，症状包括打喷嚏、流鼻涕、咳嗽、喉咙痛等。建议多休息、多喝水，症状严重时及时就医。',
            '发烧': '发烧是指体温超过37.3℃，可能由感染引起。建议物理降温，体温超过38.5℃可服用退烧药，持续发烧请就医。',
            '头痛': '头痛可由多种原因引起，如疲劳、紧张、感冒等。建议休息放松，如持续剧烈头痛请及时就医。',
            '高血压': '高血压是指血压持续高于140/90mmHg。建议低盐饮食、规律作息、按时服药，定期监测血压。',
            '糖尿病': '糖尿病是血糖代谢异常疾病。建议控制饮食、规律运动、监测血糖、遵医嘱用药。'
        }
        return disease_info.get(disease, f"关于{disease}的健康信息，建议咨询专业医生。")


class WeChatPublicCrawler(HealthDataCrawler):
    """微信公众号爬虫"""

    def __init__(self, db_manager=None):
        super().__init__(db_manager)
        self.source_name = "微信公众号"
        self.search_url = "https://weixin.sogou.com/weixin"

    async def crawl(self, accounts: List[str] = None, **kwargs) -> List[Dict]:
        """爬取公众号文章"""
        if accounts is None:
            accounts = ['丁香医生', '健康中国', '医学界']

        results = []
        for account in accounts:
            articles = await self.search_account_articles(account)
            results.extend(articles)
            await self.random_delay()

        return results

    async def search_account_articles(self, account: str) -> List[Dict]:
        """搜索公众号文章"""
        params = {'type': '2', 'query': account}
        from urllib.parse import urlencode
        url = f"{self.search_url}?{urlencode(params)}"

        html = await self.fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        items = soup.select('.news-list li, .wx-rb')
        for item in items:
            title_elem = item.select_one('a')
            title = title_elem.get_text(strip=True) if title_elem else ''

            link = title_elem['href'] if title_elem and title_elem.get('href') else ''

            desc_elem = item.select_one('.txt-info, .abstract')
            description = desc_elem.get_text(strip=True) if desc_elem else ''

            if title:
                results.append({
                    'title': self.clean_text(title),
                    'content': self.clean_text(description) or title,
                    'summary': self.clean_text(description)[:200] if description else '',
                    'source': f"{self.source_name}-{account}",
                    'source_url': link,
                    'publish_date': datetime.now(),
                    'category': 'general'
                })

        return results