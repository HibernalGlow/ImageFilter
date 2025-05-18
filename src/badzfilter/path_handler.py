"""
路径处理模块 - 用于处理文件路径相关的功能
"""
import os
import pyperclip
from pathlib import Path
from loguru import logger
from .config import DEFAULT_PATHS

def get_paths_from_clipboard():
    """从剪贴板读取多行路径
    
    Returns:
        list: 有效路径对象列表
    """
    try:
        clipboard_content = pyperclip.paste()
        if not clipboard_content:
            return []
            
        paths = [
            Path(path.strip().strip('"').strip("'"))
            for path in clipboard_content.splitlines() 
            if path.strip()
        ]
        
        valid_paths = [
            path for path in paths 
            if path.exists()
        ]
        
        if valid_paths:
            logger.info(f"[#status] 📋 从剪贴板读取到 {len(valid_paths)} 个有效路径")
        else:
            logger.warning("[#warning] ⚠️ 剪贴板中没有有效路径")
            
        return valid_paths
        
    except Exception as e:
        logger.error(f"[#error] ❌ 读取剪贴板时出错: {e}")
        return []

def get_valid_paths(cli_paths=None, use_clipboard=False):
    """根据不同的输入来源获取有效路径
    
    Args:
        cli_paths (list, optional): 命令行传入的路径列表
        use_clipboard (bool): 是否从剪贴板获取路径
        
    Returns:
        list: 有效路径对象列表
    """
    directories = []
    
    # 1. 如果指定了从剪贴板获取路径
    if use_clipboard:
        directories.extend(get_paths_from_clipboard())
        
    # 2. 如果提供了命令行参数路径
    elif cli_paths:
        for path_str in cli_paths:
            path = Path(path_str.strip('"').strip("'"))
            if path.exists():
                directories.append(path)
            else:
                logger.warning(f"[#warning] ⚠️ 警告：路径不存在 - {path_str}")
    
    # 3. 如果以上两种方式都没有获取到路径，使用默认路径
    else:
        valid_default_paths = []
        for default_path in DEFAULT_PATHS:
            if default_path.exists():
                valid_default_paths.append(default_path)
                logger.info(f"[#status] 📂 使用默认路径: {default_path}")
            else:
                logger.warning(f"[#warning] ⚠️ 默认路径不存在: {default_path}")
        
        if valid_default_paths:
            directories.extend(valid_default_paths)
        else:
            logger.error("[#error] ❌ 所有默认路径都不存在")
    
    return directories