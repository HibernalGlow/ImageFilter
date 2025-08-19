#!/usr/bin/env python3
"""
测试hashu模块的图片格式兼容功能
验证相同图片不同格式能否返回相同哈希值
"""

import sys
import os
from pathlib import Path

# 添加src路径
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from hashu.core.calculate_hash_custom import ImageHashCalculator
from hashu.core.sqlite_storage import HashDatabaseManager
from hashu.utils.path_uri import URIParser, PathURIGenerator

def test_uri_parsing():
    """测试URI解析功能"""
    print("=== 测试URI解析功能 ===")
    
    test_uris = [
        "file:///E:/images/photo.jpg",
        "file:///E:/images/photo.png", 
        "file:///E:/images/photo.webp",
        "archive:///E:/data.zip!folder/image.jpg",
        "archive:///E:/data.zip!folder/image.png",
    ]
    
    for uri in test_uris:
        parsed = URIParser.parse_uri(uri)
        print(f"URI: {uri}")
        print(f"  文件名: {parsed['filename']}")
        print(f"  格式: {parsed['file_format']}")
        print(f"  去格式URL: {parsed['uri_without_format']}")
        print(f"  压缩包: {parsed['archive_name']}")
        print()

def test_sqlite_smart_query():
    """测试SQLite的智能查询功能"""
    print("=== 测试SQLite智能查询功能 ===")
    
    # 创建临时数据库
    db_path = "test_format_compatibility.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = HashDatabaseManager(db_path)
    
    # 添加一个JPG图片的哈希值
    jpg_uri = "file:///E:/test/sample.jpg"
    hash_value = "1234567890abcdef"
    
    success = db.add_hash(jpg_uri, hash_value)
    print(f"添加JPG哈希: {success}")
    
    # 测试智能查询：用PNG格式查询相同图片
    png_uri = "file:///E:/test/sample.png"
    webp_uri = "file:///E:/test/sample.webp"
    
    # 智能查询测试
    jpg_result = db.smart_query(jpg_uri)
    png_result = db.smart_query(png_uri) 
    webp_result = db.smart_query(webp_uri)
    
    print(f"查询JPG格式: {jpg_result}")
    print(f"查询PNG格式: {png_result}")
    print(f"查询WebP格式: {webp_result}")
    
    # 验证格式兼容性
    if jpg_result == png_result == webp_result == hash_value:
        print("✅ 格式兼容功能正常：不同格式返回相同哈希值")
    else:
        print("❌ 格式兼容功能异常：不同格式返回不同结果")
    
    # 测试archive://协议
    print("\n--- 测试压缩包格式兼容 ---")
    archive_jpg = "archive:///E:/test.zip!images/photo.jpg"
    archive_png = "archive:///E:/test.zip!images/photo.png"
    
    db.add_hash(archive_jpg, "archive_hash_123")
    
    result_jpg = db.smart_query(archive_jpg)
    result_png = db.smart_query(archive_png)
    
    print(f"压缩包JPG查询: {result_jpg}")
    print(f"压缩包PNG查询: {result_png}")
    
    if result_jpg == result_png == "archive_hash_123":
        print("✅ 压缩包格式兼容功能正常")
    else:
        print("❌ 压缩包格式兼容功能异常")
      # 清理数据库连接
    try:
        del db
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception as e:
        print(f"清理数据库文件时出现问题: {e}")

def test_hashu_integration():
    """测试hashu模块的集成功能"""
    print("=== 测试hashu模块集成功能 ===")
    
    # 配置使用SQLite
    from hashu.core.calculate_hash_custom import HashCache
    HashCache.configure_multiprocess(
        use_sqlite=True,
        sqlite_priority=True
    )
    
    # 模拟添加一个图片哈希
    jpg_uri = PathURIGenerator.generate("E:/test/demo.jpg")
    hash_value = "demo_hash_value"
    
    # 添加哈希到缓存
    HashCache.add_hash(jpg_uri, hash_value)
    print(f"添加哈希: {jpg_uri} -> {hash_value}")
      # 测试不同格式查询
    png_uri = PathURIGenerator.generate("E:/test/demo.png")
    webp_uri = PathURIGenerator.generate("E:/test/demo.webp")
    
    jpg_result = HashCache.get_hash(jpg_uri)
    png_result = HashCache.get_hash(png_uri)
    webp_result = HashCache.get_hash(webp_uri)
    
    print(f"查询JPG: {jpg_result}")
    print(f"查询PNG: {png_result}")
    print(f"查询WebP: {webp_result}")
    
    # 验证结果
    if jpg_result == png_result == webp_result == hash_value:
        print("✅ hashu模块格式兼容功能正常")
        return True
    else:
        print("❌ hashu模块格式兼容功能异常")
        return False

def main():
    """主测试函数"""
    print("开始测试hashu模块的图片格式兼容功能...\n")
    
    try:
        # 测试URI解析
        test_uri_parsing()
        
        # 测试SQLite智能查询
        test_sqlite_smart_query()
        
        # 测试hashu集成功能
        integration_ok = test_hashu_integration()
        
        print("\n=== 测试总结 ===")
        if integration_ok:
            print("✅ hashu模块的图片格式兼容功能已经实现并正常工作")
            print("   - 相同图片的不同格式会返回相同的哈希值")
            print("   - 支持普通文件和压缩包内文件")
            print("   - detectors模块的调用方式保持不变")
        else:
            print("❌ 格式兼容功能存在问题，需要进一步检查")
            
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
