#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库验证脚本

用于验证SQLite数据库中的数据完整性和性能
"""

import os
import sys
import time
import random
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from hashu.core.sqlite_storage import HashDatabaseManager
from hashu.config import get_config


def print_database_info(db_manager: HashDatabaseManager):
    """打印数据库基本信息"""
    print("数据库信息")
    print("=" * 50)
    print(f"数据库路径: {db_manager.db_path}")
    print(f"数据库存在: {db_manager.db_path.exists()}")
    if db_manager.db_path.exists():
        file_size = db_manager.db_path.stat().st_size
        print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
    print()


def print_statistics(db_manager: HashDatabaseManager):
    """打印数据库统计信息"""
    print("数据库统计")
    print("=" * 50)
    
    stats = db_manager.get_statistics()
    
    print(f"总记录数: {stats.get('total_records', 0)}")
    print(f"数据库大小: {stats.get('db_size_mb', 0)} MB")
    print()
    
    # 按来源类型统计
    if stats.get('by_source_type'):
        print("按来源类型统计:")
        for source_type, count in stats['by_source_type'].items():
            print(f"  {source_type}: {count:,} 条")
        print()
    
    # 按文件扩展名统计
    if stats.get('by_extension'):
        print("按文件扩展名统计(前10):")
        for ext, count in list(stats['by_extension'].items())[:10]:
            print(f"  {ext}: {count:,} 条")
        print()
    
    # 按压缩包统计
    if stats.get('by_archive'):
        print("按压缩包统计(前10):")
        for archive, count in list(stats['by_archive'].items())[:10]:
            print(f"  {archive}: {count:,} 条")
        print()


def test_query_performance(db_manager: HashDatabaseManager, sample_size: int = 1000):
    """测试查询性能"""
    print("查询性能测试")
    print("=" * 50)
    
    try:
        # 获取一些随机URI用于测试
        with db_manager._lock:
            conn = db_manager._get_connection()
            cursor = conn.execute(f"SELECT uri FROM image_hashes ORDER BY RANDOM() LIMIT {sample_size}")
            test_uris = [row['uri'] for row in cursor.fetchall()]
        
        if not test_uris:
            print("没有找到测试数据")
            return
        
        print(f"测试样本: {len(test_uris)} 个URI")
        
        # 测试精确查询
        start_time = time.time()
        successful_queries = 0
        
        for uri in test_uris:
            result = db_manager.get_hash(uri)
            if result:
                successful_queries += 1
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"精确查询测试:")
        print(f"  查询次数: {len(test_uris)}")
        print(f"  成功查询: {successful_queries}")
        print(f"  总耗时: {duration:.3f} 秒")
        print(f"  平均耗时: {duration * 1000 / len(test_uris):.3f} 毫秒/查询")
        print(f"  查询速度: {len(test_uris) / duration:.1f} 查询/秒")
        print()
        
        # 测试智能查询
        start_time = time.time()
        smart_successful_queries = 0
        
        for uri in test_uris[:min(100, len(test_uris))]:  # 智能查询测试较少样本
            result = db_manager.smart_query(uri)
            if result:
                smart_successful_queries += 1
        
        end_time = time.time()
        smart_duration = end_time - start_time
        smart_sample_size = min(100, len(test_uris))
        
        print(f"智能查询测试:")
        print(f"  查询次数: {smart_sample_size}")
        print(f"  成功查询: {smart_successful_queries}")
        print(f"  总耗时: {smart_duration:.3f} 秒")
        print(f"  平均耗时: {smart_duration * 1000 / smart_sample_size:.3f} 毫秒/查询")
        print(f"  查询速度: {smart_sample_size / smart_duration:.1f} 查询/秒")
        print()
        
    except Exception as e:
        print(f"性能测试失败: {e}")


def test_data_integrity(db_manager: HashDatabaseManager, sample_size: int = 100):
    """测试数据完整性"""
    print("数据完整性测试")
    print("=" * 50)
    
    try:
        # 检查必需字段
        with db_manager._lock:
            conn = db_manager._get_connection()
            
            # 检查空值
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN uri IS NULL OR uri = '' THEN 1 END) as empty_uri,
                    COUNT(CASE WHEN hash_value IS NULL OR hash_value = '' THEN 1 END) as empty_hash,
                    COUNT(CASE WHEN filename IS NULL OR filename = '' THEN 1 END) as empty_filename
                FROM image_hashes
            """)
            
            row = cursor.fetchone()
            print(f"字段完整性检查:")
            print(f"  总记录数: {row['total']:,}")
            print(f"  空URI: {row['empty_uri']:,}")
            print(f"  空哈希值: {row['empty_hash']:,}")
            print(f"  空文件名: {row['empty_filename']:,}")
            print()
            
            # 检查重复记录
            cursor = conn.execute("""
                SELECT COUNT(*) as duplicates
                FROM (
                    SELECT uri, COUNT(*) as cnt
                    FROM image_hashes
                    GROUP BY uri
                    HAVING COUNT(*) > 1
                )
            """)
            duplicates = cursor.fetchone()['duplicates']
            print(f"重复URI检查: {duplicates:,} 个重复URI")
            
            # 检查base_uri一致性
            cursor = conn.execute(f"""
                SELECT uri, base_uri, filename, file_extension
                FROM image_hashes
                ORDER BY RANDOM()
                LIMIT {sample_size}
            """)
            
            inconsistent_count = 0
            for row in cursor.fetchall():
                uri_info = db_manager.parse_uri(row['uri'])
                if (uri_info['base_uri'] != row['base_uri'] or 
                    uri_info['filename'] != row['filename'] or
                    uri_info['file_extension'] != row['file_extension']):
                    inconsistent_count += 1
            
            print(f"URI解析一致性检查 (样本{sample_size}): {inconsistent_count} 个不一致")
            print()
            
    except Exception as e:
        print(f"完整性测试失败: {e}")


def test_archive_protocol_support(db_manager: HashDatabaseManager):
    """测试archive://协议支持"""
    print("Archive协议支持测试")
    print("=" * 50)
    
    try:
        with db_manager._lock:
            conn = db_manager._get_connection()
            
            # 统计archive://协议的记录
            cursor = conn.execute("""
                SELECT COUNT(*) as archive_count
                FROM image_hashes
                WHERE uri LIKE 'archive://%'
            """)
            archive_count = cursor.fetchone()['archive_count']
            
            print(f"Archive协议记录数: {archive_count:,}")
            
            if archive_count > 0:
                # 获取一些archive记录样本
                cursor = conn.execute("""
                    SELECT uri, archive_name, base_uri
                    FROM image_hashes
                    WHERE uri LIKE 'archive://%'
                    LIMIT 5
                """)
                
                print("Archive记录样本:")
                for row in cursor.fetchall():
                    print(f"  URI: {row['uri']}")
                    print(f"  Archive: {row['archive_name']}")
                    print(f"  Base URI: {row['base_uri']}")
                    print()
            
    except Exception as e:
        print(f"Archive协议测试失败: {e}")


def interactive_query(db_manager: HashDatabaseManager):
    """交互式查询"""
    print("交互式查询")
    print("=" * 50)
    print("输入URI查询哈希值，输入'quit'退出")
    
    while True:
        try:
            uri = input("\n请输入URI: ").strip()
            if uri.lower() in ['quit', 'exit', 'q']:
                break
            
            if not uri:
                continue
            
            # 精确查询
            start_time = time.time()
            exact_result = db_manager.get_hash(uri)
            exact_time = time.time() - start_time
            
            # 智能查询
            start_time = time.time()
            smart_result = db_manager.smart_query(uri)
            smart_time = time.time() - start_time
            
            print(f"精确查询结果: {exact_result or '未找到'} (耗时: {exact_time*1000:.2f}ms)")
            print(f"智能查询结果: {smart_result or '未找到'} (耗时: {smart_time*1000:.2f}ms)")
            
            if smart_result and not exact_result:
                # 显示匹配的记录
                uri_info = db_manager.parse_uri(uri)
                matches = db_manager.find_by_base_uri(uri_info['base_uri'])
                print(f"通过base_uri匹配到 {len(matches)} 条记录:")
                for match in matches[:3]:  # 只显示前3条
                    print(f"  {match['uri']}")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"查询错误: {e}")


def main():
    """主函数"""
    print("SQLite数据库验证工具")
    print("=" * 70)
    print()
    
    try:
        # 初始化数据库
        db_manager = HashDatabaseManager()
        
        # 打印基本信息
        print_database_info(db_manager)
        
        # 打印统计信息
        print_statistics(db_manager)
        
        # 数据完整性测试
        test_data_integrity(db_manager)
        
        # Archive协议测试
        test_archive_protocol_support(db_manager)
        
        # 性能测试
        test_query_performance(db_manager)
        
        # 交互式查询（可选）
        if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
            interactive_query(db_manager)
        
        print("验证完成!")
        
    except Exception as e:
        print(f"验证过程中发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
