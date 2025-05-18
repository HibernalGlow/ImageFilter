"""
主程序入口模块 - 整合所有功能并提供命令行接口
"""
import os
import sys
import argparse
from pathlib import Path
from loguru import logger

# 导入自定义模块
from .logger_module import setup_logger
from .path_handler import get_valid_paths
from .archive_checker import process_directory

# 尝试导入TUI界面模块（可能在某些环境下不可用）
try:
    from textual_logger import TextualLoggerManager
except ImportError:
    TEXTUAL_AVAILABLE = False
TEXTUAL_AVAILABLE = False
from .config import TEXTUAL_LAYOUT

def run_check(paths=None, use_clipboard=False, no_tui=False, force_check=False):
    """压缩包检查功能的核心函数，可供其他脚本导入使用
    
    参数:
        paths (list, 可选): 要处理的路径列表。默认为None。
        use_clipboard (bool, 可选): 是否从剪贴板读取路径。默认为False。
        no_tui (bool, 可选): 是否禁用TUI界面。默认为False。
        force_check (bool, 可选): 是否强制检查所有文件，忽略已处理记录。默认为False。
        
    返回:
        int: 状态码，0 表示成功，1 表示未提供有效路径，2 表示处理过程中出现错误
    """
    # 根据是否使用TUI配置日志
    if no_tui or not TEXTUAL_AVAILABLE:
        # 重新初始化日志，启用控制台输出
        logger, config_info = setup_logger(app_name="badzipfliter", console_output=True)
        logger.info("使用控制台输出模式")
    else:
        # 初始化日志，不使用控制台输出（将由TUI接管）
        logger, config_info = setup_logger(app_name="badzipfliter", console_output=False)
        # 初始化TextualLogger
        TextualLoggerManager.set_layout(TEXTUAL_LAYOUT, config_info['log_file'], newtab=True)
        logger.info("使用TUI界面模式")
    
    directories = get_valid_paths(paths or [], use_clipboard)
    
    if not directories:
        logger.error("[#error] ❌ 未提供任何有效的路径")
        return 1  # 返回错误状态码 1：未提供有效路径

    # 根据参数决定是否跳过已检查的文件
    skip_checked = not force_check
    if force_check:
        logger.info("[#status] 🔄 强制检查模式：将检查所有文件，包括之前已检查过的")
    else:
        logger.info("[#status] ℹ️ 标准检查模式：将跳过之前已检查且完好的文件")
        
    # 可以根据CPU核心数调整线程数
    max_workers = os.cpu_count() or 4
    
    # 处理每个目录
    total_dirs = len(directories)
    errors_occurred = False
    
    for idx, directory in enumerate(directories):
        try:
            dir_progress = int((idx / total_dirs) * 100) if total_dirs > 0 else 100
            logger.info(f"[@progress] 处理目录 ({idx+1}/{total_dirs}) {dir_progress}%")
            logger.info(f"[#status] 📂 开始处理目录: {directory}")
            process_result = process_directory(directory, skip_checked, max_workers=max_workers)
            # 如果 process_directory 函数返回了结果，可以在这里判断
            logger.info(f"[#success] ✅ 目录处理完成: {directory}")
        except Exception as e:
            errors_occurred = True
            logger.error(f"[#error] ❌ 处理目录 {directory} 时出错: {str(e)}")
    
    # 最终完成
    logger.info(f"[@progress] 处理目录 ({total_dirs}/{total_dirs}) 100%")
    
    # 返回最终状态码
    if errors_occurred:
        return 2  # 处理过程中出现错误
    return 0  # 成功完成全部处理

def main():
    """命令行入口函数
    
    返回:
        int: 状态码，0 表示成功，1 表示未提供有效路径，2 表示处理过程中出现错误
    """
    parser = argparse.ArgumentParser(description='压缩包完整性检查工具')
    parser.add_argument('paths', nargs='*', help='要处理的路径列表')
    parser.add_argument('-c', '--clipboard', action='store_true', help='从剪贴板读取路径')
    parser.add_argument('--no_tui', action='store_true', help='不使用TUI界面，只使用控制台输出')
    parser.add_argument('--force_check', action='store_true', help='强制检查所有文件，忽略已处理记录')
    args = parser.parse_args()

    # 调用核心功能函数
    return run_check(
        paths=args.paths,
        use_clipboard=args.clipboard,
        no_tui=args.no_tui,
        force_check=args.force_check
    )
    
if __name__ == "__main__":
    main()