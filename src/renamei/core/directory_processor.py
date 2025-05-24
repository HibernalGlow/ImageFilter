"""目录处理器 - 负责处理图片目录的完整流程"""
import os
import shutil
from typing import Tuple
from loguru import logger
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from rich.table import Table
from rich import box
from loguru import logger

from .processors import AdImageDetector, FileRenamer


class DirectoryProcessor:
    """目录处理器"""
    
    def __init__(self, console: Console):
        self.console = console
        self.ad_detector = AdImageDetector()
        self.file_renamer = FileRenamer()
    
    def process_directory(self, dir_path: str) -> Tuple[int, int, int]:
        """
        处理目录中的图片文件
        返回: (处理成功数量, 删除广告数量, 跳过数量)
        """
        processed_count = 0
        skipped_count = 0
        removed_ads_count = 0
        
        logger.info(f"开始处理目录: {dir_path}")
        
        # 获取总文件数
        total_files = self._count_image_files(dir_path)
        logger.info(f"发现 {total_files} 个图片文件需要处理")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        ) as progress:
            task = progress.add_task("处理图片文件...", total=total_files)
            
            # 遍历目录中的所有文件
            for root, dirs, files in os.walk(dir_path):
                for filename in files:
                    if self._is_image_file(filename):
                        progress.update(task, description=f"处理: {filename[:30]}...")
                        
                        file_path = os.path.join(root, filename)
                        
                        # 检查是否为广告图片
                        if self.ad_detector.is_ad_image(filename):
                            if self._handle_ad_file(file_path, dir_path):
                                removed_ads_count += 1
                            progress.advance(task)
                            continue
                        
                        # 处理文件名重命名
                        result = self._process_file_rename(file_path, dir_path)
                        if result == "processed":
                            processed_count += 1
                        elif result == "skipped":
                            skipped_count += 1
                        
                        progress.advance(task)
        
        # 显示处理结果
        self._show_results(processed_count, removed_ads_count, skipped_count)
        
        logger.info(f"目录处理完成 - 成功:{processed_count}, 删除广告:{removed_ads_count}, 跳过:{skipped_count}")
        return processed_count, removed_ads_count, skipped_count
    
    def _count_image_files(self, dir_path: str) -> int:
        """统计目录中的图片文件数量"""
        count = 0
        for root, _, files in os.walk(dir_path):
            for f in files:
                if self._is_image_file(f):
                    count += 1
        return count
    
    def _is_image_file(self, filename: str) -> bool:
        """检查文件是否为图片文件"""
        return filename.lower().endswith(('.jpg', '.png', '.avif', '.jxl', 'webp'))
    
    def _handle_ad_file(self, file_path: str, input_base_path: str) -> bool:
        """处理广告文件：备份并删除"""
        try:
            filename = os.path.basename(file_path)
            logger.warning(f"处理广告图片: {filename}")
            self.console.print(f"[yellow]⚠️ 检测到广告图片: {filename}[/yellow]")
            
            # 备份文件
            self._backup_file(file_path, file_path, input_base_path)
            
            # 删除文件
            os.remove(file_path)
            logger.info(f"已删除广告图片: {filename}")
            self.console.print(f"[green]✅ 已删除广告图片[/green]")
            return True
        except Exception as e:
            logger.error(f"删除广告图片失败 {file_path}: {e}")
            self.console.print(f"[red]❌ 删除广告图片失败: {str(e)}[/red]")
            return False
    
    def _process_file_rename(self, file_path: str, input_base_path: str) -> str:
        """
        处理文件重命名
        返回: "processed", "skipped", "failed"
        """
        filename = os.path.basename(file_path)
        root = os.path.dirname(file_path)
        
        # 移除hash模式
        new_filename = self.file_renamer.remove_hash_from_filename(filename)
        
        # 如果文件名没有变化，跳过
        if new_filename == filename:
            return "skipped"
        
        new_path = os.path.join(root, new_filename)
        
        logger.debug(f"重命名文件: {filename} -> {new_filename}")
        
        # 如果目标文件已存在，先备份并删除
        if os.path.exists(new_path):
            try:
                logger.warning(f"目标文件已存在，进行备份: {new_filename}")
                self._backup_file(new_path, new_path, input_base_path)
                os.remove(new_path)
            except Exception as e:
                logger.error(f"处理已存在的文件失败: {e}")
                return "failed"
        
        try:
            # 备份原文件
            self._backup_file(file_path, file_path, input_base_path)
            # 重命名
            os.rename(file_path, new_path)
            logger.info(f"重命名成功: {filename} -> {new_filename}")
            return "processed"
        except Exception as e:
            logger.error(f"重命名失败 {filename}: {e}")
            return "failed"
    
    def _backup_file(self, file_path: str, original_path: str, input_base_path: str):
        """备份文件到统一回收站目录"""
        try:
            logger.debug(f"开始备份文件: {original_path}")
            # 构建备份路径
            backup_base = r"E:\2EHV\.trash"
            # 计算相对路径（从输入路径开始）
            rel_path = os.path.relpath(os.path.dirname(original_path), input_base_path)
            backup_dir = os.path.join(backup_base, rel_path)
            
            # 确保备份目录存在
            os.makedirs(backup_dir, exist_ok=True)
            
            # 复制文件到备份目录
            backup_path = os.path.join(backup_dir, os.path.basename(original_path))
            shutil.copy2(file_path, backup_path)
            logger.info(f"文件已备份: {backup_path}")
            self.console.print(f"[dim]📦 已备份: {os.path.basename(backup_path)}[/dim]")
        except Exception as e:
            logger.error(f"备份失败 {original_path}: {e}")
            self.console.print(f"[red]❌ 备份失败: {os.path.basename(original_path)}[/red]")
    
    def _show_results(self, processed_count: int, removed_ads_count: int, skipped_count: int):
        """显示处理结果"""
        result_table = Table(title="处理结果", box=box.ROUNDED)
        result_table.add_column("项目", style="cyan")
        result_table.add_column("数量", style="green", justify="right")
        
        result_table.add_row("成功处理", str(processed_count))
        result_table.add_row("删除广告", str(removed_ads_count))
        result_table.add_row("跳过处理", str(skipped_count))
        
        self.console.print(result_table)
