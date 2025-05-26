"""新入口文件 - 兼容旧逻辑"""
import os
import sys
import zipfile
import re
import shutil
import uuid
import time
import subprocess
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich import box

from renamei.core.input_handler import InputHandler
from renamei.core.zip_processor import ZipProcessor
from renamei.core.directory_processor import DirectoryProcessor
from renamei.core.task_manager import ProcessStats
from loguru import logger
import os
import sys
from pathlib import Path
from datetime import datetime

def setup_logger(app_name="app", project_root=None, console_output=True):
    """配置 Loguru 日志系统
    
    Args:
        app_name: 应用名称，用于日志目录
        project_root: 项目根目录，默认为当前文件所在目录
        console_output: 是否输出到控制台，默认为True
        
    Returns:
        tuple: (logger, config_info)
            - logger: 配置好的 logger 实例
            - config_info: 包含日志配置信息的字典
    """
    # 获取项目根目录
    if project_root is None:
        project_root = Path(__file__).parent.resolve()
    
    # 清除默认处理器
    logger.remove()
    
    # 有条件地添加控制台处理器（简洁版格式）
    if console_output:
        logger.add(
            sys.stdout,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>{elapsed}</blue> | <level>{level.icon} {level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        )
    
    # 使用 datetime 构建日志路径
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")
    hour_str = current_time.strftime("%H")
    minute_str = current_time.strftime("%M%S")
    
    # 构建日志目录和文件路径
    log_dir = os.path.join(project_root, "logs", app_name, date_str, hour_str)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{minute_str}.log")
    
    # 添加文件处理器
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {elapsed} | {level.icon} {level: <8} | {name}:{function}:{line} - {message}",
    )
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

logger, config_info = setup_logger(app_name="renamei", console_output=True)

# 初始化日志和控制台
console = Console()


def main():
    """主函数"""
    # 显示欢迎信息
    console.print(Panel(
        "[bold blue]图片文件名清理工具[/bold blue]\n",
        title="欢迎使用",
        border_style="blue"
    ))
    
    # 解析命令行参数
    args = InputHandler.parse_arguments()
    
    # 配置详细日志
    
    # 如果没有指定模式，让用户选择
    if not args.mode:
        args.mode = InputHandler.select_processing_mode()
    else:
        mode_name = "图片文件" if args.mode == 'image' else "压缩包"
        logger.info(f"使用命令行指定的处理模式: {args.mode}")
        console.print(f"[green]📝 处理模式: {mode_name}[/green]")
    
    # 获取输入路径
    target_paths = InputHandler.get_input_paths(args)
    
    # 如果没有有效路径，提示用户重新输入
    while not target_paths:
        console.print("\n")
        console.print(Panel(
            "[yellow]没有有效的输入路径[/yellow]",
            title="提示",
            border_style="yellow"
        ))
        
        if not Confirm.ask("[bold cyan]是否要重新输入路径?[/bold cyan]"):
            console.print("[yellow]退出程序[/yellow]")
            logger.info("用户选择退出程序")
            sys.exit(0)
        
        method = Prompt.ask(
            "[bold cyan]请选择输入方式[/bold cyan]",
            choices=["manual", "clipboard"],
            default="manual"
        )
        
        if method == "manual":
            target_paths = InputHandler._interactive_path_input()
        else:
            target_paths = InputHandler.get_paths_from_clipboard()
    
    # 收集需要处理的项目
    items_to_process = []
    logger.info("开始收集处理项目")
    
    for target_path in target_paths:
        logger.debug(f"分析路径: {target_path}")
        console.print(f"[cyan]📂 分析路径: {target_path}[/cyan]")
        
        input_base_path = os.path.dirname(target_path)
        
        if os.path.isdir(target_path):
            if args.mode == 'image':
                # 图片模式：收集目录
                items_to_process.append(target_path)
                logger.debug(f"添加图片目录: {target_path}")
            else:
                # 压缩包模式：收集目录下所有zip文件
                zip_count = 0
                for root, _, files in os.walk(target_path):
                    for file in files:
                        if file.lower().endswith('.zip'):
                            zip_path = os.path.join(root, file)
                            items_to_process.append((zip_path, input_base_path))
                            zip_count += 1
                logger.info(f"在目录 {target_path} 中发现 {zip_count} 个压缩包")
                console.print(f"[green]✅ 发现 {zip_count} 个压缩包[/green]")
                
        elif zipfile.is_zipfile(target_path):
            if args.mode == 'zip':
                # 压缩包模式：收集压缩包
                items_to_process.append((target_path, input_base_path))
                logger.debug(f"添加压缩包: {target_path}")
            else:
                logger.warning(f"当前为图片处理模式，跳过压缩包: {target_path}")
                console.print(f"[yellow]⚠️ 当前为图片处理模式，跳过压缩包: {os.path.basename(target_path)}[/yellow]")
        else:
            logger.warning(f"无效的路径: {target_path}")
            console.print(f"[red]❌ 无效路径: {target_path}[/red]")
    
    # 显示处理概览
    if items_to_process:
        overview_table = Table(title="处理概览", box=box.ROUNDED)
        overview_table.add_column("模式", style="cyan")
        overview_table.add_column("项目数量", style="green", justify="right")
        
        mode_name = "图片目录" if args.mode == 'image' else "压缩包"
        overview_table.add_row(mode_name, str(len(items_to_process)))
        
        console.print(overview_table)
        
        # 确认是否开始处理
        if Confirm.ask("[bold green]是否开始处理?[/bold green]", default=True):
            # 创建统计对象
            stats = ProcessStats()
            
            # 根据模式选择处理函数
            if args.mode == 'image':
                # 处理图片目录
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("处理图片目录...", total=len(items_to_process))
                    
                    for directory in items_to_process:
                        try:
                            progress.update(task, description=f"处理: {os.path.basename(directory)}")
                            # 使用默认配置文件路径初始化广告检测器
                            config_path = os.path.join(os.path.dirname(__file__), 'ad_detector_config.json')
                            dir_processor = DirectoryProcessor(console, config_path)
                            dir_processor.process_directory(directory)
                            stats.increment_processed()
                            progress.advance(task)
                        except Exception as e:
                            logger.error(f"处理目录失败 {directory}: {e}")
                            stats.increment_failed()
                            progress.advance(task)
            else:
                # 处理压缩包
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("处理压缩包...", total=len(items_to_process))
                    
                    for zip_path, input_base_path in items_to_process:
                        try:                              
                            progress.update(task, description=f"处理: {os.path.basename(zip_path)}")
                            # 使用默认配置文件路径初始化
                            config_path = os.path.join(os.path.dirname(__file__), 'ad_detector_config.json')
                            zip_processor = ZipProcessor(config_path)
                            zip_processor.process_zip(zip_path, input_base_path)
                            stats.increment_processed()
                            progress.advance(task)
                        except Exception as e:
                            logger.error(f"处理压缩包失败 {zip_path}: {e}")
                            stats.increment_failed()
                            progress.advance(task)
            
            # 显示最终统计
            final_table = Table(title="最终统计", box=box.ROUNDED)
            final_table.add_column("状态", style="cyan")
            final_table.add_column("数量", style="green", justify="right")
            
            final_table.add_row("✅ 成功处理", str(stats.processed_count))
            final_table.add_row("❌ 处理失败", str(stats.failed_count))
            final_table.add_row("⏭️ 跳过处理", str(stats.skipped_count))
            
            console.print(final_table)
            logger.info(f"处理完成 - 成功:{stats.processed_count}, 失败:{stats.failed_count}, 跳过:{stats.skipped_count}")
            console.print("[bold green]🎉 所有任务处理完成![/bold green]")
        else:
            console.print("[yellow]用户取消处理[/yellow]")
            logger.info("用户取消处理")
    else:
        console.print("[red]❌ 没有找到需要处理的文件[/red]")
        logger.warning("没有找到需要处理的文件")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断程序[/yellow]")
        logger.info("用户中断程序")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]❌ 程序执行出错: {e}[/red]")
        logger.error(f"程序执行出错: {e}")
        sys.exit(1)
