"""
爬虫调度器 - 管理爬虫任务的执行
"""
import asyncio
import threading
import time
from datetime import datetime
from typing import List, Dict, Any, Callable
import logging
from queue import Queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CrawlerScheduler:
    """爬虫调度器"""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.crawlers = {}
        self.tasks = {}
        self.task_queue = Queue()
        self.is_running = False
        self.worker_thread = None

    def register_crawler(self, name: str, crawler):
        """注册爬虫"""
        self.crawlers[name] = crawler
        logger.info(f"已注册爬虫: {name}")

    def add_task(self, task_name: str, crawler_name: str, **kwargs):
        """添加爬取任务"""
        task = {
            'task_id': f"{task_name}_{int(time.time())}",
            'task_name': task_name,
            'crawler_name': crawler_name,
            'params': kwargs,
            'status': 'pending',
            'created_at': datetime.now()
        }
        self.task_queue.put(task)
        logger.info(f"添加任务: {task_name}")
        return task['task_id']

    def start(self):
        """启动调度器"""
        if self.is_running:
            logger.warning("调度器已在运行")
            return

        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logger.info("调度器已启动")

    def stop(self):
        """停止调度器"""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("调度器已停止")

    def _worker_loop(self):
        """工作循环"""
        while self.is_running:
            try:
                # 非阻塞获取任务
                task = self.task_queue.get(timeout=1)
                self._execute_task(task)
            except:
                pass

    def _execute_task(self, task: Dict):
        """执行任务"""
        task['status'] = 'running'
        task['started_at'] = datetime.now()

        try:
            crawler = self.crawlers.get(task['crawler_name'])
            if not crawler:
                raise Exception(f"爬虫不存在: {task['crawler_name']}")

            # 同步或异步执行
            if asyncio.iscoroutinefunction(crawler.crawl):
                # 异步执行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                results = loop.run_until_complete(crawler.crawl(**task['params']))
                loop.close()
            else:
                # 同步执行
                results = crawler.crawl(**task['params'])

            task['status'] = 'completed'
            task['completed_at'] = datetime.now()
            task['result_count'] = len(results) if results else 0

            # 保存结果到数据库
            if self.db_manager and results:
                self._save_results(results, task)

            logger.info(f"任务完成: {task['task_name']}, 获取 {len(results) if results else 0} 条数据")

        except Exception as e:
            task['status'] = 'failed'
            task['error'] = str(e)
            logger.error(f"任务失败: {task['task_name']}, {e}")

        task['finished_at'] = datetime.now()

    def _save_results(self, results: List[Dict], task: Dict):
        """保存结果到数据库"""
        # 这里需要根据实际数据库模型实现
        pass

    def get_task_status(self, task_id: str) -> Dict:
        """获取任务状态"""
        # 遍历队列查找任务
        temp_queue = []
        found = None

        while not self.task_queue.empty():
            task = self.task_queue.get()
            temp_queue.append(task)
            if task.get('task_id') == task_id:
                found = task

        # 放回队列
        for task in temp_queue:
            self.task_queue.put(task)

        return found or {'status': 'not_found'}

    def get_all_tasks(self) -> List[Dict]:
        """获取所有任务"""
        tasks = []
        temp_queue = []

        while not self.task_queue.empty():
            task = self.task_queue.get()
            temp_queue.append(task)
            tasks.append(task)

        for task in temp_queue:
            self.task_queue.put(task)

        return tasks

    def clear_completed_tasks(self):
        """清除已完成任务"""
        temp_queue = []

        while not self.task_queue.empty():
            task = self.task_queue.get()
            if task.get('status') not in ['completed', 'failed']:
                temp_queue.append(task)

        for task in temp_queue:
            self.task_queue.put(task)

        logger.info("已清除完成任务")


class CronScheduler:
    """定时任务调度器"""

    def __init__(self, crawler_scheduler: CrawlerScheduler):
        self.crawler_scheduler = crawler_scheduler
        self.schedules = {}
        self.is_running = False
        self.thread = None

    def add_schedule(self, name: str, crawler_name: str, cron: str, **kwargs):
        """添加定时任务"""
        self.schedules[name] = {
            'crawler_name': crawler_name,
            'cron': cron,
            'params': kwargs,
            'last_run': None
        }
        logger.info(f"添加定时任务: {name}, cron: {cron}")

    def start(self):
        """启动定时调度器"""
        self.is_running = True
        self.thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self.thread.start()
        logger.info("定时调度器已启动")

    def _schedule_loop(self):
        """调度循环"""
        while self.is_running:
            now = datetime.now()

            for name, schedule in self.schedules.items():
                if self._should_run(schedule, now):
                    # 执行任务
                    task_id = self.crawler_scheduler.add_task(
                        f"scheduled_{name}",
                        schedule['crawler_name'],
                        **schedule['params']
                    )
                    schedule['last_run'] = now
                    logger.info(f"执行定时任务: {name}, task_id: {task_id}")

            time.sleep(60)  # 每分钟检查一次

    def _should_run(self, schedule: Dict, now: datetime) -> bool:
        """判断是否应该执行"""
        cron = schedule['cron']
        last_run = schedule['last_run']

        # 简单实现，只支持每日定时
        if cron.startswith('daily'):
            hour, minute = map(int, cron.split()[1].split(':'))
            if (last_run is None or last_run.date() != now.date()) and \
                    now.hour == hour and now.minute >= minute:
                return True

        return False


# 使用示例
def create_default_scheduler(db_manager=None):
    """创建默认调度器"""
    from .health_crawler import DingXiangCrawler, BaiduHealthCrawler

    scheduler = CrawlerScheduler(db_manager)

    # 注册爬虫
    scheduler.register_crawler('dingxiang', DingXiangCrawler(db_manager))
    scheduler.register_crawler('baidu', BaiduHealthCrawler(db_manager))

    # 启动调度器
    scheduler.start()

    return scheduler