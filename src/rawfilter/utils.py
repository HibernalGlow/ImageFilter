import os
import pyperclip
from loguru import logger
import win32com.client
from typing import List, Optional
import shutil
import re
def clean_filename(self, filename: str) -> str:
    """清理文件名，只保留主文件名部分进行比较"""
    # 移除扩展名
    name = os.path.splitext(filename)[0]
    
    # 移除所有括号内容和指标信息
    name = re.sub(r'\[[^\]]*\]|\([^)]*\)|\{[^}]*\}', '', name)
    
    # 移除特殊字符和多余空格
    name = re.sub(r'[^\w\s\-]', '', name)
    name = re.sub(r'\s+', '', name)
    
    return name.strip().lower()


def get_paths_from_clipboard():
    """从剪贴板读取多行路径"""
    try:
        clipboard_content = pyperclip.paste()
        if not clipboard_content:
            return []
        paths = [
            path.strip().strip('"').strip("'")
            for path in clipboard_content.splitlines()
            if path.strip()
        ]
        valid_paths = [
            path for path in paths
            if os.path.exists(path)
        ]
        if valid_paths:
            logger.info("[#file_ops] 📋 从剪贴板读取到 %d 个有效路径", len(valid_paths))
        else:
            logger.info("[#error_log] ⚠️ 剪贴板中没有有效路径")
        return valid_paths
    except Exception as e:
        logger.info("[#error_log] ❌ 读取剪贴板时出错: %s", e)
        return []

def get_long_path_name(path_str: str) -> str:
    """转换为长路径格式"""
    # 修正字符串转义问题
    if not path_str.startswith('\\\\?\\'):
        if os.path.isabs(path_str):
            return '\\\\?\\' + path_str
    return path_str

def safe_path(path: str) -> str:
    try:
        abs_path = os.path.abspath(path)
        return get_long_path_name(abs_path)
    except Exception as e:
        return path

def process_paths(paths: List[str]) -> List[str]:
    valid_paths = []
    for path in paths:
        path = path.strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        elif path.startswith("'") and path.endswith("'"):
            path = path[1:-1]
        if path:
            try:
                safe_path_str = safe_path(path)
                if os.path.exists(safe_path_str):
                    valid_paths.append(safe_path_str)
                else:
                    logger.info("[#error_log] ❌ 路径不存在或无法访问: %s", path)
            except Exception as e:
                logger.info("[#error_log] ❌ 处理路径时出错: %s, 错误: %s", path, str(e))
    if not valid_paths:
        logger.info("[#error_log] ⚠️ 没有有效的路径")
    return valid_paths

def create_shortcut(src_path: str, dst_path: str) -> bool:
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(dst_path + ".lnk")
        shortcut.Targetpath = src_path
        shortcut.save()
        return True
    except Exception as e:
        logger.error("[#error_log] 创建快捷方式失败: %s", str(e))
        return False

def handle_multi_main_file(file_path: str, base_dir: str) -> Optional[str]:
    try:
        full_path = os.path.join(base_dir, file_path)
        dir_name = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        name, ext = os.path.splitext(file_name)
        new_name = f"{name}[multi-main]{ext}"
        new_rel_path = os.path.join(dir_name, new_name) if dir_name else new_name
        new_full_path = os.path.join(base_dir, new_rel_path)
        shutil.copy2(full_path, new_full_path)
        logger.info("[#file_ops] ✅ 已创建multi-main副本: %s", new_rel_path)
        return new_rel_path
    except Exception as e:
        logger.error("[#error_log] ❌ 创建multi-main副本失败 %s: %s", file_path, str(e))
        return None
