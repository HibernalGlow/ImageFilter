"""
SQLite存储集成演示
展示hashu模块的SQLite + JSON双存储功能和智能查询特性
"""

import os
import time
from pathlib import Path
from typing import List, Dict, Any

from hashu.core.calculate_hash_custom import ImageHashCalculator, HashCache, get_db_cached
from hashu.utils.hash_process_config import setup_multiprocess_hash_environment
from loguru import logger


def setup_demo_environment():
    """设置演示环境"""
    logger.info("🚀 设置SQLite存储演示环境")
    
    # 配置多进程环境并启用SQLite
    HashCache.configure_multiprocess(
        enable_auto_save=True,
        enable_global_cache=True,
        use_sqlite=True,
        sqlite_priority=True
    )
    
    logger.info("✅ SQLite存储已启用")


def demo_basic_hash_calculation():
    """演示基本哈希计算和存储"""
    logger.info("\n=== 基本哈希计算演示 ===")
    
    # 测试图片路径（请根据实际情况调整）
    test_images = [
        r"E:\2EHV\test\0.jpg",
        r"E:\2EHV\test\1.jpg",
        r"D:\1VSCODE\Projects\ImageAll\ImageFilter\test_images\sample1.jpg",
        ".",  # 当前目录查找
    ]
    
    # 查找实际存在的测试图片
    actual_images = []
    for img_path in test_images:
        if img_path == ".":
            # 在当前目录查找图片文件
            for ext in ['*.jpg', '*.png', '*.jpeg', '*.webp']:
                found = list(Path(".").glob(ext))
                actual_images.extend([str(f) for f in found[:2]])  # 最多取2个
        elif os.path.exists(img_path):
            actual_images.append(img_path)
    
    if not actual_images:
        logger.warning("❌ 没有找到测试图片，创建示例路径")
        # 创建一些archive://协议的示例URI用于测试
        test_uris = [
            "archive:///test/sample.zip!/images/photo1.jpg",
            "archive:///test/sample.zip!/images/photo1.png",
            "archive:///test/sample.zip!/images/photo1.webp",
            "/regular/path/to/image.jpg"
        ]
        
        # 直接添加到数据库进行测试
        db = get_db_cached()
        for i, uri in enumerate(test_uris):
            hash_value = f"test_hash_{i:04d}"
            metadata = {
                'file_size': 1024 * (i + 1),
                'width': 800 + i * 100,
                'height': 600 + i * 100
            }
            success = db.add_hash(uri, hash_value, metadata=metadata)
            logger.info(f"  添加测试记录 {uri}: {'成功' if success else '失败'}")
        
        return
    
    logger.info(f"找到 {len(actual_images)} 个测试图片")
    
    # 计算哈希值
    results = []
    for img_path in actual_images[:3]:  # 最多处理3个图片
        logger.info(f"\n📸 处理图片: {img_path}")
        
        start_time = time.time()
        result = ImageHashCalculator.calculate_phash(img_path)
        end_time = time.time()
        
        if result:
            results.append(result)
            logger.info(f"  ✅ 哈希值: {result['hash']}")
            logger.info(f"  📊 来源: {result.get('storage_backend', '未知')}")
            logger.info(f"  ⏱️ 耗时: {end_time - start_time:.3f}秒")
            logger.info(f"  🗂️ 缓存命中: {'是' if result.get('from_cache') else '否'}")
            
            # 显示元数据
            if metadata := result.get('metadata'):
                logger.info(f"  📐 尺寸: {metadata.get('width')}x{metadata.get('height')}")
                logger.info(f"  📄 格式: {metadata.get('format')}")
        else:
            logger.error(f"  ❌ 哈希计算失败")
    
    return results


def demo_smart_query():
    """演示智能查询功能（格式转换匹配）"""
    logger.info("\n=== 智能查询演示 ===")
    
    db = get_db_cached()
    
    # 添加一些测试数据用于智能查询
    test_data = [
        ("archive:///test/photos.zip!/vacation/beach.jpg", "abc123def456"),
        ("archive:///test/photos.zip!/vacation/beach.png", "abc123def456"),
        ("archive:///test/photos.zip!/vacation/beach.webp", "abc123def456"),
        ("archive:///test/photos.zip!/vacation/mountain.jpg", "xyz789uvw012"),
        ("/local/path/image.jpg", "local123hash"),
    ]
    
    logger.info("📝 添加测试数据...")
    for uri, hash_value in test_data:
        metadata = {'test_data': True, 'width': 1920, 'height': 1080}
        db.add_hash(uri, hash_value, metadata=metadata)
        logger.info(f"  添加: {uri}")
    
    # 测试智能查询
    test_queries = [
        "archive:///test/photos.zip!/vacation/beach.gif",  # 不存在的格式，应该找到其他格式
        "archive:///test/photos.zip!/vacation/beach.avif", # 另一个不存在的格式
        "/local/path/image.png",  # 本地路径的格式转换
    ]
    
    logger.info("\n🔍 测试智能查询...")
    for query_uri in test_queries:
        logger.info(f"\n🎯 查询: {query_uri}")
        
        # 使用HashCache的智能查询
        hash_value = HashCache.get_hash(query_uri)
        if hash_value:
            logger.info(f"  ✅ 找到哈希值: {hash_value}")
        else:
            logger.info("  ❌ 未找到匹配的哈希值")
        
        # 使用SQLite的详细智能查询
        results = HashCache.smart_query_with_formats(query_uri, ['jpg', 'png', 'webp'])
        if results:
            logger.info(f"  📋 智能查询找到 {len(results)} 个匹配结果:")
            for result in results:
                logger.info(f"    - {result['uri']} -> {result['hash_value']}")
        else:
            logger.info("  📋 智能查询未找到结果")


def demo_migration_and_export():
    """演示数据迁移和导出功能"""
    logger.info("\n=== 数据迁移和导出演示 ===")
    
    # 执行JSON到SQLite的迁移
    logger.info("📦 执行JSON到SQLite迁移...")
    migrated_count = HashCache.migrate_to_sqlite(force_refresh=True)
    logger.info(f"✅ 迁移了 {migrated_count} 条记录")
    
    # 获取数据库统计信息
    logger.info("\n📊 数据库统计信息:")
    stats = HashCache.get_database_statistics()
    
    if memory_stats := stats.get('memory_cache'):
        logger.info(f"  内存缓存: {memory_stats['cache_size']} 条记录")
    
    if sqlite_stats := stats.get('sqlite'):
        if 'error' in sqlite_stats:
            logger.error(f"  SQLite错误: {sqlite_stats['error']}")
        else:
            logger.info(f"  SQLite记录: {sqlite_stats.get('total_records', 0)} 条")
            logger.info(f"  数据库大小: {sqlite_stats.get('db_size_mb', 0)} MB")
            
            # 显示格式分布
            if by_ext := sqlite_stats.get('by_extension'):
                logger.info("  格式分布:")
                for ext, count in list(by_ext.items())[:5]:
                    logger.info(f"    {ext}: {count} 个")
    
    # 导出到JSON（兼容性测试）
    logger.info("\n💾 导出SQLite数据到JSON...")
    export_file = "hash_export_demo.json"
    success = HashCache.export_sqlite_to_json(export_file, format_type='new')
    if success:
        logger.info(f"✅ 数据已导出到: {export_file}")
        
        # 检查文件大小
        if os.path.exists(export_file):
            file_size = os.path.getsize(export_file)
            logger.info(f"  文件大小: {file_size} 字节")
            
            # 清理测试文件
            try:
                os.remove(export_file)
                logger.info("🗑️ 已清理导出的测试文件")
            except:
                pass
    else:
        logger.error("❌ 导出失败")


def demo_performance_comparison():
    """演示性能对比"""
    logger.info("\n=== 性能对比演示 ===")
    
    # 测试查询性能
    test_uris = [
        "archive:///test/large.zip!/folder/image001.jpg",
        "archive:///test/large.zip!/folder/image002.png", 
        "/path/to/local/image.jpg",
        "https://example.com/remote/image.webp"
    ]
    
    # 添加测试数据
    db = get_db_cached()
    for i, uri in enumerate(test_uris):
        hash_value = f"perf_test_{i:04d}"
        db.add_hash(uri, hash_value)
    
    # SQLite查询性能测试
    logger.info("🚀 SQLite查询性能测试...")
    start_time = time.time()
    
    for _ in range(100):  # 100次查询
        for uri in test_uris:
            HashCache.get_hash(uri)
    
    sqlite_time = time.time() - start_time
    logger.info(f"  SQLite: {sqlite_time:.3f}秒 (400次查询)")
    
    # 内存缓存性能测试（禁用SQLite）
    logger.info("🧠 内存缓存性能测试...")
    HashCache.configure_multiprocess(use_sqlite=False)
    
    start_time = time.time()
    
    for _ in range(100):
        for uri in test_uris:
            HashCache.get_hash(uri)
    
    memory_time = time.time() - start_time
    logger.info(f"  内存缓存: {memory_time:.3f}秒 (400次查询)")
    
    # 恢复SQLite配置
    HashCache.configure_multiprocess(use_sqlite=True)
    
    # 性能比较
    if sqlite_time > 0 and memory_time > 0:
        ratio = sqlite_time / memory_time
        logger.info(f"📈 性能比较: SQLite/内存 = {ratio:.2f}x")
        
        if ratio < 1.5:
            logger.info("✅ SQLite性能表现良好")
        elif ratio < 3.0:
            logger.info("⚠️ SQLite性能可接受")
        else:
            logger.info("❗ SQLite性能需要优化")


def main():
    """主演示函数"""
    logger.info("🎭 SQLite存储集成演示开始")
    
    try:
        # 设置环境
        setup_demo_environment()
        
        # 基本功能演示
        demo_basic_hash_calculation()
        
        # 智能查询演示
        demo_smart_query()
        
        # 迁移和导出演示
        demo_migration_and_export()
        
        # 性能对比演示
        demo_performance_comparison()
        
        logger.info("\n🎉 SQLite存储集成演示完成!")
        
        # 显示最终统计
        logger.info("\n📊 最终统计信息:")
        stats = HashCache.get_cache_stats()
        logger.info(f"  内存缓存大小: {stats['cache_size']}")
        logger.info(f"  SQLite已启用: {stats['sqlite_enabled']}")
        logger.info(f"  多进程配置: {stats['multiprocess_config']}")
        
    except Exception as e:
        logger.error(f"❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
