"""
imgu 工具模块
"""
import logging
import os
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime
from loguru import logger

def setup_logger(app_name: str = "imgu", project_root: Optional[str] = None, console_output: bool = True):
    """设置日志记录器
    
    Args:
        app_name: 应用名称
        project_root: 项目根目录，如果为None则使用当前目录
        console_output: 是否输出到控制台
        
    Returns:
        logger 实例
    """
    # 移除所有处理程序
    logger.remove()
    
    # 设置日志格式
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    
    # 添加控制台处理程序
    if console_output:
        logger.add(sys.stderr, format=log_format, level="INFO")
    
    # 创建日志目录
    if project_root is None:
        project_root = os.getcwd()
        
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_dir = os.path.join(project_root, "logs", app_name, date_str)
    os.makedirs(log_dir, exist_ok=True)
    
    # 添加文件处理程序
    log_file = os.path.join(log_dir, f"{app_name}_{datetime.now().strftime('%H_%M_%S')}.log")
    logger.add(log_file, format=log_format, level="DEBUG", rotation="10 MB")
    
    # 记录初始信息
    logger.info(f"Logging to {log_file}")
    
    return logger
