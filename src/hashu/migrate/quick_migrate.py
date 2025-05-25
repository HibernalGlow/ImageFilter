#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的JSON到SQLite迁移脚本

快速迁移现有JSON哈希文件到SQLite数据库的简化脚本
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from hashu.core.sqlite_storage import HashDatabaseManager
from hashu.config import get_config

def quick_migrate():
    """快速迁移配置文件中的JSON文件到SQLite"""
    print("正在初始化配置管理器...")
    
    try:
        # 获取配置
        config = get_config()
        json_files = config.get_json_hash_files()
        
        print(f"找到 {len(json_files)} 个JSON文件:")
        for json_file in json_files:
            if os.path.exists(json_file):
                print(f"  ✓ {json_file}")
            else:
                print(f"  ✗ {json_file} (不存在)")
        
        # 初始化数据库
        print("\n正在初始化SQLite数据库...")
        db_manager = HashDatabaseManager()
        
        # 获取迁移前统计
        stats_before = db_manager.get_statistics()
        print(f"数据库路径: {db_manager.db_path}")
        print(f"迁移前记录数: {stats_before.get('total_records', 0)}")
        
        # 执行迁移
        total_migrated = 0
        start_time = time.time()
        
        for json_file in json_files:
            if os.path.exists(json_file):
                print(f"\n正在迁移: {json_file}")
                try:
                    migrated_count = db_manager.migrate_from_json(json_file)
                    total_migrated += migrated_count
                    print(f"  成功迁移 {migrated_count} 条记录")
                except Exception as e:
                    print(f"  迁移失败: {e}")
            else:
                print(f"\n跳过不存在的文件: {json_file}")
        
        # 获取迁移后统计
        stats_after = db_manager.get_statistics()
        end_time = time.time()
        
        print("\n" + "="*50)
        print("迁移完成!")
        print("="*50)
        print(f"总共迁移: {total_migrated} 条记录")
        print(f"迁移后记录数: {stats_after.get('total_records', 0)}")
        print(f"数据库大小: {stats_after.get('db_size_mb', 0)} MB")
        print(f"耗时: {end_time - start_time:.2f} 秒")
        
        if total_migrated > 0:
            print(f"平均速度: {total_migrated/(end_time - start_time):.1f} 记录/秒")
        
        # 显示数据库统计
        if stats_after.get('by_source_type'):
            print(f"\n按来源类型统计:")
            for source_type, count in stats_after['by_source_type'].items():
                print(f"  {source_type}: {count} 条")
        
        if stats_after.get('by_extension'):
            print(f"\n按文件扩展名统计(前10):")
            for ext, count in list(stats_after['by_extension'].items())[:10]:
                print(f"  {ext}: {count} 条")
        
    except Exception as e:
        print(f"迁移过程中发生错误: {e}")
        return False
    
    return True

def main():
    """主函数"""
    print("JSON到SQLite数据库迁移脚本")
    print("=" * 50)
    
    # 检查参数
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print("""
使用方法:
  python quick_migrate.py                 # 迁移配置文件中的JSON文件
  python quick_migrate.py --help          # 显示帮助信息
  
此脚本会自动从配置文件中读取JSON哈希文件路径，并迁移到SQLite数据库。
如果需要更多选项，请使用 migrate_json_to_sqlite.py 脚本。
            """)
            return
    
    try:
        success = quick_migrate()
        if success:
            print("\n迁移成功完成!")
        else:
            print("\n迁移失败!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n用户中断迁移")
        sys.exit(130)

if __name__ == "__main__":
    main()
