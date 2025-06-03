"""
压缩包检查模块 - 负责检测压缩文件完整性和处理相关操作
"""
import os
import subprocess
import shutil
import concurrent.futures
from datetime import datetime
from pathlib import Path
from loguru import logger

from .config import ARCHIVE_EXTENSIONS
from .history_manager import update_file_history, load_check_history, save_check_history

def check_archive(file_path):
    """检测压缩包是否损坏
    
    Args:
        file_path (str): 压缩文件路径
        
    Returns:
        bool: 如果文件完好返回True，否则返回False
    """
    try:
        result = subprocess.run(['7z', 't', file_path], 
                              capture_output=True, 
                              text=True)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"[#error] ❌ 检测文件 {file_path} 时发生错误: {str(e)}")
        return False

def get_archive_files(directory, archive_extensions=None):
    """快速收集需要处理的文件
    
    Args:
        directory (str or Path): 要处理的目录
        archive_extensions (tuple, optional): 要处理的压缩文件扩展名
        
    Yields:
        str: 符合条件的文件路径
    """
    if archive_extensions is None:
        archive_extensions = ARCHIVE_EXTENSIONS
        
    for root, _, files in os.walk(directory):
        for filename in files:
            if any(filename.lower().endswith(ext) for ext in archive_extensions):
                yield os.path.join(root, filename)

def process_single_file(file_path, file_index, total_files):
    """处理单个压缩包文件
    
    Args:
        file_path (str): 压缩文件路径
        file_index (int): 文件索引
        total_files (int): 总文件数
        
    Returns:
        dict: 包含处理结果的字典
    """
    logger.info(f"[#status] 🔍 正在检测: {file_path}")
    is_valid = check_archive(file_path)
    result = {
        'path': file_path,
        'valid': is_valid,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    # 更新进度
    progress_percentage = int((file_index + 1) / total_files * 100)
    logger.info(f"[@progress] 检测压缩包完整性 ({file_index + 1}/{total_files}) {progress_percentage}%")
    return result


def process_directory(directory, skip_checked=False, max_workers=4):
    """处理目录下的所有压缩包文件
    
    Args:
        directory (str or Path): 要处理的目录
        skip_checked (bool): 是否跳过已检查过且完好的文件
        max_workers (int): 并行处理的线程数
    """
    check_history = load_check_history()
    
    # 删除temp_开头的文件夹
    for root, dirs, _ in os.walk(directory, topdown=True):
        for dir_name in dirs[:]:  # 使用切片创建副本以避免在迭代时修改列表
            if dir_name.startswith('temp_'):
                try:
                    dir_path = os.path.join(root, dir_name)
                    logger.info(f"[#status] 🗑️ 正在删除临时文件夹: {dir_path}")
                    shutil.rmtree(dir_path)
                except Exception as e:
                    logger.error(f"[#error] 删除文件夹 {dir_path} 时发生错误: {str(e)}")

    # 收集需要处理的文件
    files_to_process = []
    for root, _, files in os.walk(directory):
        for filename in files:
            if filename.lower().endswith(ARCHIVE_EXTENSIONS):
                file_path = os.path.join(root, filename)
                if file_path.endswith('.tdel'):
                    continue
                if skip_checked and file_path in check_history and check_history[file_path]['valid']:
                    logger.info(f"[#status] ⏭️ 跳过已检查且完好的文件: {file_path}")
                    continue
                files_to_process.append(file_path)

    if not files_to_process:
        logger.info("[#status] ✨ 没有需要处理的文件")
        return    # 更新进度信息
    total_files = len(files_to_process)

    # 使用线程池处理文件
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 使用enumerate获取索引，方便更新进度
        futures = [executor.submit(process_single_file, file_path, i, total_files) for i, file_path in enumerate(files_to_process)]
        
        # 处理结果
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            file_path = result['path']
            is_valid = result['valid']
            
            check_history[file_path] = {
                'time': result['time'],
                'valid': is_valid
            }
            
            if not is_valid:
                new_path = file_path + '.tdel'
                # 如果.tdel文件已存在，先删除它
                if os.path.exists(new_path):
                    try:
                        os.remove(new_path)
                        logger.info(f"[#status] 🗑️ 删除已存在的文件: {new_path}")
                    except Exception as e:
                        logger.error(f"[#error] 删除文件 {new_path} 时发生错误: {str(e)}")
                        continue
                
                try:
                    os.rename(file_path, new_path)
                    logger.warning(f"[#warning] ⚠️ 文件损坏,已重命名为: {new_path}")
                except Exception as e:
                    logger.error(f"[#error] 重命名文件时发生错误: {str(e)}")
            else:
                logger.info(f"[#success] ✅ 文件完好: {file_path}")
            
            # 定期保存检查历史
            save_check_history(check_history)

    # 处理结果的循环结束后，添加删除空文件夹的功能
    removed_count = 0
    logger.info(f"[@progress] 清理空文件夹 (0/100) 0%")
    
    # 获取目录总数以计算进度
    dir_count = sum(len(dirs) for _, dirs, _ in os.walk(directory))
    processed_dirs = 0
    
    for root, dirs, _ in os.walk(directory, topdown=False):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            try:
                if not os.listdir(dir_path):  # 检查文件夹是否为空
                    os.rmdir(dir_path)
                    removed_count += 1
                    logger.info(f"[#status] 🗑️ 已删除空文件夹: {dir_path}")
            except Exception as e:
                logger.error(f"[#error] 删除空文件夹失败 {dir_path}: {str(e)}")
            
            # 更新进度
            processed_dirs += 1
            progress = int(processed_dirs / dir_count * 100) if dir_count > 0 else 100
            logger.info(f"[@progress] 清理空文件夹 ({processed_dirs}/{dir_count}) {progress}%")
    
    logger.info(f"[@progress] 清理空文件夹 ({dir_count}/{dir_count}) 100%")
    if removed_count > 0:
        logger.info(f"[#success] ✨ 共删除了 {removed_count} 个空文件夹")