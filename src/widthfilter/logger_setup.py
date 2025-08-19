"""日志设置模块"""

import os
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger

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
        enqueue=True,     )
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

# 设置Textual日志界面布局
TEXTUAL_LAYOUT = {
    "current_stats": {"ratio": 2, "title": "📊 总体进度", "style": "lightyellow"},
    "current_progress": {"ratio": 2, "title": "🔄 当前处理", "style": "lightcyan"},
    "process_log": {"ratio": 3, "title": "📝 处理日志", "style": "lightgreen"},
    "update_log": {"ratio": 2, "title": "ℹ️ 更新日志", "style": "lightblue"}
}

def init_textual_logger(config_info):
    """初始化TextualLogger"""
    try:
        from textual_logger import TextualLoggerManager
        TextualLoggerManager.set_layout(TEXTUAL_LAYOUT, config_info['log_file'])
        return True
    except ImportError:
        logger.warning("未找到textual_logger模块，将使用标准日志输出")
        return False
    except Exception as e:
        logger.error(f"初始化Textual日志失败: {e}")
        return False 