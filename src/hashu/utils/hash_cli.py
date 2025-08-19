"""
哈希计算命令行工具
"""
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import time

from hashu import calculate_hash_for_artist_folder, process_duplicates_with_hash_file
from loguru import logger

def setup_logger():
    """配置日志输出"""
    logger.remove()  # 移除默认处理器
    
    # 添加控制台处理器
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
    )

def main():
    """命令行工具主函数"""
    setup_logger()
    
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="哈希计算命令行工具")
    
    # 添加参数
    parser.add_argument("--path", "-p", type=str, required=True, help="要处理的画师文件夹路径")
    parser.add_argument("--workers", "-w", type=int, default=4, help="工作线程数，默认为4")
    parser.add_argument("--force", "-f", action="store_true", help="是否强制更新哈希值")
    parser.add_argument("--duplicate-check", "-d", action="store_true", help="是否进行重复检测")
    parser.add_argument("--target", "-t", type=str, help="进行重复检测的目标路径，可与--path相同")
    parser.add_argument("--hamming", type=int, default=16, help="汉明距离阈值，默认为16")
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 确保文件夹路径存在
    folder_path = Path(args.path)
    if not folder_path.exists():
        logger.error(f"❌ 输入路径不存在: {folder_path}")
        return 1
        
    # 显示处理信息
    logger.info(f"🚀 开始处理画师文件夹: {folder_path}")
    logger.info(f"⚙️ 工作线程数: {args.workers}")
    logger.info(f"⚙️ 强制更新: {args.force}")
    
    # 计时开始
    start_time = time.time()
    
    # 计算哈希值
    hash_file_path = calculate_hash_for_artist_folder(
        folder_path, 
        workers=args.workers, 
        force_update=args.force
    )
    
    # 检查哈希计算结果
    if not hash_file_path:
        logger.error("❌ 哈希计算失败")
        return 1
        
    # 计算耗时
    elapsed = time.time() - start_time
    logger.info(f"✅ 哈希计算完成，耗时: {elapsed:.2f}秒")
    logger.info(f"📄 哈希文件: {hash_file_path}")
    
    # 如果需要进行重复检测
    if args.duplicate_check:
        target_path = args.target or args.path
        logger.info(f"🔍 开始进行重复检测，目标路径: {target_path}")
        
        # 准备参数
        params = {
            'ref_hamming_distance': args.hamming,
            'hash_size': 10,
            'filter_white_enabled': False
        }
        
        # 进行重复检测
        duplicate_start_time = time.time()
        process_duplicates_with_hash_file(
            hash_file_path,
            [target_path],
            params,
            args.workers
        )
        
        # 计算重复检测耗时
        duplicate_elapsed = time.time() - duplicate_start_time
        logger.info(f"✅ 重复检测完成，耗时: {duplicate_elapsed:.2f}秒")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 