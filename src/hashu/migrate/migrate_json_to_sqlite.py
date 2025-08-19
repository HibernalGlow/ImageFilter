#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON到SQLite数据库迁移脚本

此脚本用于将现有的JSON哈希文件迁移到SQLite数据库中。
支持批量迁移多个JSON文件，并提供详细的迁移统计信息。
"""

import os
import sys
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from hashu.core.sqlite_storage import HashDatabaseManager
from hashu.config import get_config


def setup_logging(verbose: bool = False):
    """设置日志配置"""
    logger.remove()  # 移除默认处理器
    
    log_level = "DEBUG" if verbose else "INFO"
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    
    # 控制台输出
    logger.add(sys.stdout, format=log_format, level=log_level, colorize=True)
    
    # 文件输出
    log_dir = project_root / "src" / "hashu" / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"migrate_json_to_sqlite_{int(time.time())}.log"
    logger.add(log_file, format=log_format, level="DEBUG", rotation="10 MB")
    
    logger.info(f"日志文件: {log_file}")


def find_json_files(paths: List[str]) -> List[str]:
    """查找JSON哈希文件
    
    Args:
        paths: 要搜索的路径列表
        
    Returns:
        找到的JSON文件路径列表
    """
    json_files = []
    
    for path_str in paths:
        path = Path(path_str).expanduser()
        
        if path.is_file() and path.suffix.lower() == '.json':
            json_files.append(str(path))
            logger.info(f"找到JSON文件: {path}")
        elif path.is_dir():
            # 搜索目录中的JSON文件
            for json_file in path.rglob("*.json"):
                # 过滤可能的哈希文件
                if any(keyword in json_file.name.lower() for keyword in 
                       ['hash', 'image_hash', 'collection', 'global']):
                    json_files.append(str(json_file))
                    logger.info(f"找到JSON文件: {json_file}")
        else:
            logger.warning(f"路径不存在或不是有效文件: {path}")
    
    return json_files


def validate_json_file(file_path: str) -> bool:
    """验证JSON文件是否为有效的哈希文件
    
    Args:
        file_path: JSON文件路径
        
    Returns:
        是否为有效的哈希文件
    """
    try:
        import orjson
        with open(file_path, 'rb') as f:
            data = orjson.loads(f.read())
        
        if not isinstance(data, dict):
            return False
        
        # 检查是否包含哈希数据
        if "hashes" in data:
            # 新格式
            hashes = data["hashes"]
            if isinstance(hashes, dict) and len(hashes) > 0:
                return True
        else:
            # 旧格式 - 检查是否有非特殊键的条目
            special_keys = {'_hash_params', 'dry_run', 'input_paths'}
            hash_entries = {k: v for k, v in data.items() if k not in special_keys}
            if len(hash_entries) > 0:
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"验证JSON文件失败 {file_path}: {e}")
        return False


def migrate_single_file(db_manager: HashDatabaseManager, json_file: str, 
                       force: bool = False) -> Dict[str, Any]:
    """迁移单个JSON文件
    
    Args:
        db_manager: 数据库管理器
        json_file: JSON文件路径
        force: 是否强制迁移（忽略已迁移检查）
        
    Returns:
        迁移结果统计
    """
    result = {
        'file': json_file,
        'success': False,
        'migrated_count': 0,
        'error': None,
        'start_time': time.time(),
        'end_time': None,
        'duration': 0
    }
    
    try:
        logger.info(f"开始迁移: {json_file}")
        
        # 验证文件
        if not validate_json_file(json_file):
            result['error'] = "不是有效的哈希JSON文件"
            logger.warning(f"跳过无效文件: {json_file}")
            return result
        
        # 检查是否已经迁移过（如果不强制迁移）
        if not force:
            # 这里可以添加检查逻辑，比如查询迁移日志表
            pass
        
        # 执行迁移
        migrated_count = db_manager.migrate_from_json(json_file)
        
        result['migrated_count'] = migrated_count
        result['success'] = True
        result['end_time'] = time.time()
        result['duration'] = result['end_time'] - result['start_time']
        
        logger.info(f"迁移完成: {json_file} -> {migrated_count} 条记录，耗时: {result['duration']:.2f}秒")
        
    except Exception as e:
        result['error'] = str(e)
        result['end_time'] = time.time()
        result['duration'] = result['end_time'] - result['start_time']
        logger.error(f"迁移失败 {json_file}: {e}")
    
    return result


def print_migration_summary(results: List[Dict[str, Any]]):
    """打印迁移摘要"""
    total_files = len(results)
    successful_files = sum(1 for r in results if r['success'])
    failed_files = total_files - successful_files
    total_records = sum(r['migrated_count'] for r in results)
    total_duration = sum(r['duration'] for r in results)
    
    logger.info("=" * 60)
    logger.info("迁移摘要")
    logger.info("=" * 60)
    logger.info(f"总文件数: {total_files}")
    logger.info(f"成功迁移: {successful_files}")
    logger.info(f"迁移失败: {failed_files}")
    logger.info(f"总记录数: {total_records}")
    logger.info(f"总耗时: {total_duration:.2f}秒")
    logger.info(f"平均速度: {total_records/total_duration:.1f} 记录/秒" if total_duration > 0 else "N/A")
    logger.info("=" * 60)
    
    if failed_files > 0:
        logger.info("失败的文件:")
        for result in results:
            if not result['success']:
                logger.error(f"  {result['file']}: {result['error']}")
    
    if successful_files > 0:
        logger.info("成功迁移的文件:")
        for result in results:
            if result['success']:
                logger.info(f"  {result['file']}: {result['migrated_count']} 条记录")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="将JSON哈希文件迁移到SQLite数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 迁移单个文件
  python migrate_json_to_sqlite.py /path/to/hash_file.json
  
  # 迁移多个文件
  python migrate_json_to_sqlite.py file1.json file2.json
  
  # 迁移目录中的所有JSON文件
  python migrate_json_to_sqlite.py /path/to/hash_directory/
  
  # 使用配置文件中的默认JSON文件
  python migrate_json_to_sqlite.py --use-config
  
  # 强制迁移（覆盖已存在的记录）
  python migrate_json_to_sqlite.py --force file.json
  
  # 指定数据库路径
  python migrate_json_to_sqlite.py --db-path /custom/path/hash.db file.json
        """
    )
    
    parser.add_argument(
        'paths', 
        nargs='*', 
        help='要迁移的JSON文件或目录路径'
    )
    
    parser.add_argument(
        '--use-config',
        action='store_true',
        help='使用配置文件中的JSON文件路径'
    )
    
    parser.add_argument(
        '--db-path',
        help='SQLite数据库文件路径（默认使用配置文件中的路径）'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='强制迁移，覆盖已存在的记录'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='试运行，不实际执行迁移'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细输出'
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.verbose)
    
    try:
        # 获取要迁移的JSON文件列表
        json_files = []
        
        if args.use_config:
            # 从配置文件获取JSON文件路径
            try:
                config = get_config()
                config_json_files = config.get_json_hash_files()
                json_files.extend(config_json_files)
                logger.info(f"从配置文件获取到 {len(config_json_files)} 个JSON文件")
            except Exception as e:
                logger.error(f"从配置文件获取JSON文件失败: {e}")
                sys.exit(1)
        
        if args.paths:
            # 从命令行参数获取文件路径
            found_files = find_json_files(args.paths)
            json_files.extend(found_files)
        
        if not json_files:
            logger.error("没有找到要迁移的JSON文件")
            logger.info("请使用 --help 查看使用方法")
            sys.exit(1)
        
        # 去重
        json_files = list(set(json_files))
        logger.info(f"总共找到 {len(json_files)} 个JSON文件")
        
        if args.dry_run:
            logger.info("试运行模式，以下文件将被迁移:")
            for json_file in json_files:
                if validate_json_file(json_file):
                    logger.info(f"  ✓ {json_file}")
                else:
                    logger.info(f"  ✗ {json_file} (无效)")
            return
        
        # 初始化数据库
        logger.info("初始化数据库...")
        db_manager = HashDatabaseManager(args.db_path)
        
        # 打印数据库信息
        stats = db_manager.get_statistics()
        logger.info(f"数据库路径: {db_manager.db_path}")
        logger.info(f"迁移前记录数: {stats.get('total_records', 0)}")
        
        # 执行迁移
        results = []
        start_time = time.time()
        
        for i, json_file in enumerate(json_files, 1):
            logger.info(f"进度: {i}/{len(json_files)}")
            result = migrate_single_file(db_manager, json_file, args.force)
            results.append(result)
        
        end_time = time.time()
        
        # 打印摘要
        print_migration_summary(results)
        
        # 打印最终数据库统计
        final_stats = db_manager.get_statistics()
        logger.info(f"迁移后记录数: {final_stats.get('total_records', 0)}")
        logger.info(f"数据库大小: {final_stats.get('db_size_mb', 0)} MB")
        
        logger.info(f"总耗时: {end_time - start_time:.2f}秒")
        logger.info("迁移完成!")
        
    except KeyboardInterrupt:
        logger.warning("用户中断迁移")
        sys.exit(130)
    except Exception as e:
        logger.error(f"迁移过程中发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
