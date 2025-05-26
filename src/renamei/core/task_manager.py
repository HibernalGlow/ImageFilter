"""统计和进度管理器"""
from threading import Lock
from typing import List, Callable, Any
from concurrent.futures import ProcessPoolExecutor, as_completed
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from rich.table import Table
from rich import box
from loguru import logger


class ProcessStats:
    """处理统计类"""
    
    def __init__(self):
        self.lock = Lock()
        self.processed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
    
    def increment_processed(self):
        """增加处理成功计数"""
        with self.lock:
            self.processed_count += 1
            logger.debug("处理计数增加")
    
    def increment_failed(self):
        """增加处理失败计数"""
        with self.lock:
            self.failed_count += 1
            logger.debug("失败计数增加")
    
    def increment_skipped(self):
        """增加跳过计数"""
        with self.lock:
            self.skipped_count += 1
            logger.debug("跳过计数增加")
    
    def get_counts(self) -> tuple:
        """获取当前计数"""
        with self.lock:
            return self.processed_count, self.failed_count, self.skipped_count


class TaskManager:
    """任务管理器 - 负责并行处理任务"""
    
    def __init__(self, console: Console, max_workers: int = None):
        self.console = console
        self.max_workers = max_workers or self._get_default_workers()
    
    def _get_default_workers(self) -> int:
        """获取默认线程数"""
        import os
        return os.cpu_count() * 2 or 4
    
    def process_with_threadpool(self, items: List[Any], worker_func: Callable, 
                              task_description: str = "处理任务") -> ProcessStats:
        """
        使用线程池处理任务
        
        Args:
            items: 要处理的项目列表
            worker_func: 工作函数，应该接受(item, stats)参数
            task_description: 任务描述
        
        Returns:
            ProcessStats: 处理统计结果
        """
        if not items:
            logger.warning("没有项目需要处理")
            return ProcessStats()
        
        logger.info(f"使用线程池处理 {len(items)} 个项目，线程数: {self.max_workers}")
        
        stats = ProcessStats()
        total = len(items)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        ) as progress:
            task = progress.add_task(task_description, total=total)
            
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_item = {
                    executor.submit(worker_func, item, stats): item 
                    for item in items
                }
                
                # 处理完成的任务
                for future in as_completed(future_to_item):
                    item = future_to_item[future]
                    try:
                        future.result()  # 获取结果，如果有异常会抛出
                        progress.update(task, description=f"已完成: {self._get_item_name(item)[:30]}...")
                    except Exception as e:
                        logger.error(f"任务执行异常 {self._get_item_name(item)}: {e}")
                        stats.increment_failed()
                    finally:
                        progress.advance(task)
        
        # 显示最终统计
        self._show_final_stats(stats)
        
        processed, failed, skipped = stats.get_counts()
        logger.info(f"线程池处理完成 - 成功:{processed}, 失败:{failed}, 跳过:{skipped}")
        
        return stats
    
    def _get_item_name(self, item: Any) -> str:
        """获取项目名称用于显示"""
        if isinstance(item, str):
            import os
            return os.path.basename(item)
        elif hasattr(item, '__iter__') and not isinstance(item, str):
            # 如果是元组或列表，尝试获取第一个元素
            try:
                first_item = next(iter(item))
                if isinstance(first_item, str):
                    import os
                    return os.path.basename(first_item)
            except:
                pass
        
        return str(item)
    
    def _show_final_stats(self, stats: ProcessStats):
        """显示最终统计"""
        processed, failed, skipped = stats.get_counts()
        
        final_table = Table(title="最终统计", box=box.ROUNDED)
        final_table.add_column("状态", style="cyan")
        final_table.add_column("数量", style="green", justify="right")
        
        final_table.add_row("✅ 成功处理", str(processed))
        final_table.add_row("❌ 处理失败", str(failed))
        final_table.add_row("⏭️ 跳过处理", str(skipped))
        
        self.console.print(final_table)
