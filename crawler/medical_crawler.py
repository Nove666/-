# 医学知识爬虫
"""
医学知识爬虫 - 爬取专业医学数据
"""
import asyncio
import xml.etree.ElementTree as ET
from typing import List, Dict
from datetime import datetime
import re
from .base_crawler import BaseCrawler


class MedicalKnowledgeCrawler(BaseCrawler):
    """医学知识爬虫"""

    def __init__(self, db_manager=None):
        super().__init__(db_manager)
        self.source_name = "medical_knowledge"

    async def crawl(self, **kwargs) -> List[Dict]:
        """爬取医学知识"""
        results = []

        # 爬取PubMed数据（需要API）
        pubmed_results = await self.crawl_pubmed(kwargs.get('keywords', []))
        results.extend(pubmed_results)

        return results

    async def crawl_pubmed(self, keywords: List[str]) -> List[Dict]:
        """爬取PubMed数据"""
        if not keywords:
            keywords = ['common cold', 'hypertension', 'diabetes', 'headache']

        results = []
        for keyword in keywords:
            articles = await self.search_pubmed(keyword)
            results.extend(articles)
            await self.random_delay()

        return results

    async def search_pubmed(self, keyword: str, max_results: int = 10) -> List[Dict]:
        """搜索PubMed"""
        # E-utilities API
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

        # 搜索文章ID
        search_params = {
            'db': 'pubmed',
            'term': keyword,
            'retmax': max_results,
            'retmode': 'json',
            'tool': 'lingshuan_agent',
            'email': 'your_email@example.com'
        }

        from urllib.parse import urlencode
        search_response = await self.fetch(f"{search_url}?{urlencode(search_params)}")

        if not search_response:
            return []

        # 解析XML获取ID列表
        ids = self.parse_pubmed_ids(search_response)

        if not ids:
            return []

        # 获取摘要
        fetch_params = {
            'db': 'pubmed',
            'id': ','.join(ids[:20]),
            'retmode': 'xml'
        }

        fetch_response = await self.fetch(f"{fetch_url}?{urlencode(fetch_params)}")

        if not fetch_response:
            return []

        # 解析文章
        return self.parse_pubmed_articles(fetch_response, keyword)

    def parse_pubmed_ids(self, xml_content: str) -> List[str]:
        """解析PubMed ID列表"""
        try:
            root = ET.fromstring(xml_content)
            ids = []
            for id_elem in root.findall('.//Id'):
                if id_elem.text:
                    ids.append(id_elem.text)
            return ids
        except Exception as e:
            print(f"解析PubMed ID失败: {e}")
            return []

    def parse_pubmed_articles(self, xml_content: str, keyword: str) -> List[Dict]:
        """解析PubMed文章"""
        try:
            root = ET.fromstring(xml_content)
            articles = []

            for article in root.findall('.//PubmedArticle'):
                # 标题
                title_elem = article.find('.//ArticleTitle')
                title = title_elem.text if title_elem is not None else ''

                # 摘要
                abstract_texts = []
                for abstract in article.findall('.//AbstractText'):
                    if abstract.text:
                        abstract_texts.append(abstract.text)
                    elif abstract.get('Label') and abstract.text:
                        abstract_texts.append(f"{abstract.get('Label')}: {abstract.text}")

                abstract = ' '.join(abstract_texts)

                # 期刊
                journal_elem = article.find('.//Title')
                journal = journal_elem.text if journal_elem is not None else ''

                # 日期
                pub_date_elem = article.find('.//PubDate')
                pub_date = self.parse_pubmed_date(pub_date_elem) if pub_date_elem is not None else datetime.now()

                if title and abstract:
                    articles.append({
                        'disease_name': keyword,
                        'title': title,
                        'content': abstract,
                        'symptom': self.extract_symptom_from_abstract(abstract),
                        'treatment': self.extract_treatment_from_abstract(abstract),
                        'source': 'PubMed',
                        'journal': journal,
                        'publish_date': pub_date,
                        'confidence_score': 0.8,
                        'is_verified': True
                    })

            return articles

        except Exception as e:
            print(f"解析PubMed文章失败: {e}")
            return []

    def parse_pubmed_date(self, date_elem) -> datetime:
        """解析PubMed日期"""
        try:
            year = date_elem.find('Year')
            month = date_elem.find('Month')
            day = date_elem.find('Day')

            year_val = int(year.text) if year is not None else 2000
            month_val = self.parse_month(month.text) if month is not None else 1
            day_val = int(day.text) if day is not None else 1

            return datetime(year_val, month_val, day_val)
        except:
            return datetime.now()

    def parse_month(self, month_str: str) -> int:
        """解析月份"""
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
            'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
            'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        if month_str in month_map:
            return month_map[month_str]
        try:
            return int(month_str)
        except:
            return 1

    def extract_symptom_from_abstract(self, abstract: str) -> str:
        """从摘要提取症状"""
        # 简单的关键词提取
        symptom_patterns = [
            r'症状包括[：:](.*?)[。.]',
            r'表现为(.*?)[。.]',
            r'临床特征(.*?)[。.]'
        ]

        for pattern in symptom_patterns:
            match = re.search(pattern, abstract)
            if match:
                return match.group(1)[:500]

        # 如果没有找到，返回前200字符
        return abstract[:200]

    def extract_treatment_from_abstract(self, abstract: str) -> str:
        """从摘要提取治疗方法"""
        treatment_patterns = [
            r'治疗[：:](.*?)[。.]',
            r'疗法(.*?)[。.]',
            r'采用(.*?)治疗'
        ]

        for pattern in treatment_patterns:
            match = re.search(pattern, abstract)
            if match:
                return match.group(1)[:500]

        return ''


class CNKICrawler(BaseCrawler):
    """中国知网爬虫（需要权限）"""

    def __init__(self, db_manager=None):
        super().__init__(db_manager)
        self.base_url = "https://kns.cnki.net"

    async def crawl(self, **kwargs) -> List[Dict]:
        """爬取知网数据"""
        # 注意：知网需要授权访问
        # 这里提供框架，实际使用需要配置API key或使用开放接口
        print("知网爬虫需要配置访问权限")
        return []