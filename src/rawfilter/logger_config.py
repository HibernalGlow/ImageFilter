import sys
import os
from pathlib import Path
from datetime import datetime
from loguru import logger

def setup_logger(app_name="app", project_root=None, console_output=True, log_file_path=None):
    """配置 Loguru 日志系统
    Args:
        app_name: 应用名称，用于日志目录
        project_root: 项目根目录，默认为当前文件所在目录
        console_output: 是否输出到控制台，默认为True
        log_file_path: 指定日志文件路径（用于多进程合并日志）
    Returns:
        tuple: (logger, config_info)
            - logger: 配置好的 logger 实例
            - config_info: 包含日志配置信息的字典
    """
    if project_root is None:
        project_root = Path(__file__).parent.resolve()
    logger.remove()
    if console_output:
        logger.add(
            sys.stdout,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>{elapsed}</blue> | <level>{level.icon} {level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        )
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")
    hour_str = current_time.strftime("%H")
    minute_str = current_time.strftime("%M%S")
    log_dir = os.path.join(project_root, "logs", app_name, date_str, hour_str)
    os.makedirs(log_dir, exist_ok=True)
    process_id = os.getpid()
    if log_file_path is not None:
        log_file = log_file_path
    else:
        log_file = os.path.join(log_dir, f"{minute_str}_{process_id}.log")
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {elapsed} | {level.icon} {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,  # 多进程安全
    )
    config_info = {
        'log_file': log_file,
    }
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

def init_worker_process():
    """为每个工作进程初始化日志配置"""
    global logger
    module_path = Path(__file__).parent.resolve()
    logger, _ = setup_logger(app_name="no_translate_find", project_root=module_path, console_output=False)
