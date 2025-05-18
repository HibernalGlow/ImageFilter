"""
历史记录管理模块
"""
import os
import json
from datetime import datetime
from .config import HISTORY_FILE
from loguru import logger

def load_check_history():
    """加载检测历史记录（从JSON文件）
    
    Returns:
        dict: 历史记录字典
    """
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f) or {}
        except json.JSONDecodeError:
            logger.error(f"[#error] 历史记录文件格式错误，将创建新的历史记录")
            return {}
    return {}

def save_check_history(history):
    """保存检测历史记录（到JSON文件）
    
    Args:
        history (dict): 要保存的历史记录字典
    """
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def update_file_history(file_path, is_valid):
    """更新单个文件的历史记录
    
    Args:
        file_path (str): 文件路径
        is_valid (bool): 文件是否有效
        
    Returns:
        dict: 更新后的文件记录
    """
    history = load_check_history()
    
    # 创建或更新记录
    file_record = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'valid': is_valid
    }
    
    history[file_path] = file_record
    save_check_history(history)
    
    return file_record