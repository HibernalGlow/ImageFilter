"""
数据库快速设置和测试脚本
"""
import asyncio
import os
import sys
from pathlib import Path
from loguru import logger

# 添加模块路径
sys.path.append(str(Path(__file__).parent.parent))

from hashu.core.postgresql_storage import PostgreSQLHashStorage, HashRecord
from hashu.utils.path_uri import PathURIGenerator, URIParser
from .init_database import DatabaseInitializer


async def quick_setup_and_test():
    """快速设置和测试数据库"""
    
    logger.info("🚀 开始快速设置和测试...")
    
    # 1. 检查环境变量
    logger.info("📋 检查环境配置...")
    
    required_env = ['POSTGRES_PASSWORD']
    missing_env = [var for var in required_env if not os.getenv(var)]
    
    if missing_env:
        logger.warning(f"⚠️ 缺少环境变量: {', '.join(missing_env)}")
        logger.info("💡 请设置以下环境变量:")
        for var in missing_env:
            if var == 'POSTGRES_PASSWORD':
                logger.info(f"   set {var}=your_database_password")
        
        # 使用默认密码进行测试
        os.environ['POSTGRES_PASSWORD'] = 'postgres'
        logger.info("🔧 使用默认密码 'postgres' 进行测试")
    
    # 2. 初始化数据库
    logger.info("🏗️ 初始化数据库...")
    
    connection_params = DatabaseInitializer.get_connection_params_from_env()
    initializer = DatabaseInitializer(connection_params)
    
    try:
        # 创建数据库（如果不存在）
        database_name = connection_params['database']
        await initializer.create_database_if_not_exists(database_name)
        
        # 初始化结构
        success = await initializer.initialize_schema()
        if not success:
            logger.error("❌ 数据库初始化失败")
            return False
        
        logger.info("✅ 数据库初始化成功")
        
    except Exception as e:
        logger.error(f"❌ 数据库设置失败: {e}")
        return False
    
    # 3. 测试数据库功能
    logger.info("🧪 测试数据库功能...")
    
    try:
        # 创建数据库存储实例
        db_storage = PostgreSQLHashStorage()
        await db_storage.initialize()
        
        # 测试数据
        test_uris = [
            "file:///E:/test/image1.jpg",
            "file:///E:/test/image2.png",
            "archive:///E:/test/archive.zip!folder/image3.webp",
            "archive:///E:/test/data.zip!images/photo.avif"
        ]
        
        test_records = []
        for i, uri in enumerate(test_uris):
            # 解析URI信息
            uri_info = URIParser.parse_uri(uri)
            
            record = HashRecord(
                uri=uri,
                hash_value=f"abc123def456{i:03d}",  # 测试哈希值
                hash_size=10,
                hash_version=1,
                file_size=1024 * (i + 1),
                metadata={'test': True, 'index': i},
                filename=uri_info.get('filename'),
                file_format=uri_info.get('file_format'),
                uri_without_format=uri_info.get('uri_without_format'),
                archive_name=uri_info.get('archive_name')
            )
            test_records.append(record)
        
        # 4. 测试插入
        logger.info("📝 测试数据插入...")
        
        for record in test_records:
            success = await db_storage.insert_hash(record)
            if success:
                logger.info(f"✅ 插入成功: {record.filename}")
            else:
                logger.error(f"❌ 插入失败: {record.filename}")
        
        # 5. 测试查询
        logger.info("🔍 测试数据查询...")
        
        for uri in test_uris:
            record = await db_storage.get_hash(uri)
            if record:
                logger.info(f"✅ 查询成功: {record.filename} ({record.file_format})")
            else:
                logger.error(f"❌ 查询失败: {uri}")
        
        # 6. 测试优先格式查询
        logger.info("🎯 测试优先格式查询...")
        
        test_uri = "file:///E:/test/image1.gif"  # 查询一个不存在的格式
        preferred_formats = ['jpg', 'png', 'webp']
        
        record = await db_storage.get_hash_with_format_priority(test_uri, preferred_formats)
        if record:
            logger.info(f"✅ 优先格式查询成功: 找到 {record.filename} ({record.file_format})")
        else:
            logger.info("ℹ️ 优先格式查询未找到匹配项（正常，因为是测试数据）")
        
        # 7. 测试统计信息
        logger.info("📊 测试统计信息...")
        
        stats = await db_storage.get_statistics()
        if stats:
            logger.info(f"📈 统计信息:")
            logger.info(f"   总记录数: {stats.get('total_records', 0)}")
            logger.info(f"   唯一哈希数: {stats.get('unique_hashes', 0)}")
            logger.info(f"   存储后端: {stats.get('storage_backend', 'Unknown')}")
        
        # 8. 清理测试数据
        logger.info("🧹 清理测试数据...")
        
        async with db_storage._pool.acquire() as conn:
            deleted = await conn.execute("""
                DELETE FROM image_hashes 
                WHERE metadata->>'test' = 'true'
            """)
            logger.info(f"✅ 清理完成，删除了测试记录")
        
        await db_storage.close()
        
        logger.info("🎉 所有测试通过！数据库设置成功！")
        
        # 9. 显示使用说明
        logger.info("\n" + "="*50)
        logger.info("📚 使用说明:")
        logger.info("1. 数据库已成功创建并测试")
        logger.info("2. 您可以使用以下命令管理数据库:")
        logger.info("   python database_manager.py status")
        logger.info("   python database_manager.py migrate <json_files>")
        logger.info("3. 或者运行批处理脚本:")
        logger.info("   manage_database.bat")
        logger.info("4. 配置文件: database_config.ini")
        logger.info("="*50)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        return False


async def show_current_config():
    """显示当前配置"""
    logger.info("📋 当前数据库配置:")
    
    params = DatabaseInitializer.get_connection_params_from_env()
    for key, value in params.items():
        if key == 'password':
            value = '*' * len(value) if value else '(未设置)'
        logger.info(f"   {key}: {value}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库快速设置和测试")
    parser.add_argument("--config-only", action="store_true", help="仅显示配置信息")
    parser.add_argument("--test-only", action="store_true", help="仅运行测试（假设数据库已设置）")
    
    args = parser.parse_args()
    
    if args.config_only:
        asyncio.run(show_current_config())
    else:
        success = asyncio.run(quick_setup_and_test())
        if not success:
            sys.exit(1)
