"""
数据库初始化脚本
用于创建和初始化图片哈希存储数据库
"""
import asyncio
import asyncpg
import os
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger
import argparse


class DatabaseInitializer:
    """数据库初始化器"""
    
    def __init__(self, connection_params: Dict[str, str]):
        """
        初始化数据库连接参数
        
        Args:
            connection_params: 数据库连接参数字典
        """
        self.connection_params = connection_params
        self.sql_file_path = Path(__file__).parent / "create_database.sql"
    
    async def create_database_if_not_exists(self, database_name: str) -> bool:
        """
        创建数据库（如果不存在）
        
        Args:
            database_name: 数据库名称
            
        Returns:
            bool: 是否成功创建或数据库已存在
        """
        try:
            # 连接到 postgres 数据库来创建新数据库
            postgres_params = self.connection_params.copy()
            postgres_params['database'] = 'postgres'
            
            conn = await asyncpg.connect(**postgres_params)
            try:
                # 检查数据库是否存在
                result = await conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1",
                    database_name
                )
                
                if result:
                    logger.info(f"✅ 数据库 '{database_name}' 已存在")
                    return True
                
                # 创建数据库
                await conn.execute(f'CREATE DATABASE "{database_name}"')
                logger.info(f"✅ 数据库 '{database_name}' 创建成功")
                return True
                
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"❌ 创建数据库失败: {e}")
            return False
    
    async def initialize_schema(self) -> bool:
        """
        初始化数据库结构
        
        Returns:
            bool: 是否成功初始化
        """
        try:
            # 读取SQL文件
            if not self.sql_file_path.exists():
                logger.error(f"❌ SQL文件不存在: {self.sql_file_path}")
                return False
            
            with open(self.sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            # 连接到目标数据库
            conn = await asyncpg.connect(**self.connection_params)
            try:
                # 执行SQL脚本
                await conn.execute(sql_content)
                logger.info("✅ 数据库结构初始化成功")
                
                # 验证表是否创建成功
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                """)
                
                table_names = [row['table_name'] for row in tables]
                logger.info(f"📊 创建的表: {', '.join(table_names)}")
                
                # 验证视图是否创建成功
                views = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.views 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                
                view_names = [row['table_name'] for row in views]
                if view_names:
                    logger.info(f"📊 创建的视图: {', '.join(view_names)}")
                
                return True
                
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"❌ 初始化数据库结构失败: {e}")
            return False
    
    async def get_database_info(self) -> Dict[str, Any]:
        """
        获取数据库信息
        
        Returns:
            Dict: 数据库信息
        """
        try:
            conn = await asyncpg.connect(**self.connection_params)
            try:
                # 获取数据库版本
                db_version = await conn.fetchval("SELECT version()")
                
                # 获取表信息
                tables_info = await conn.fetch("""
                    SELECT 
                        t.table_name,
                        t.table_type,
                        COALESCE(c.column_count, 0) as column_count
                    FROM information_schema.tables t
                    LEFT JOIN (
                        SELECT 
                            table_name,
                            COUNT(*) as column_count
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                        GROUP BY table_name
                    ) c ON t.table_name = c.table_name
                    WHERE t.table_schema = 'public'
                    ORDER BY t.table_name
                """)
                
                # 获取索引信息
                indexes_info = await conn.fetch("""
                    SELECT 
                        indexname,
                        tablename,
                        indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    ORDER BY tablename, indexname
                """)
                
                # 获取记录统计（如果表存在）
                stats = {}
                try:
                    stats = await conn.fetchrow("SELECT * FROM image_hashes_stats")
                    stats = dict(stats) if stats else {}
                except:
                    stats = {}
                
                return {
                    'database_version': db_version,
                    'tables': [dict(row) for row in tables_info],
                    'indexes': [dict(row) for row in indexes_info],
                    'statistics': stats
                }
                
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"❌ 获取数据库信息失败: {e}")
            return {}
    
    @staticmethod
    def get_connection_params_from_env() -> Dict[str, str]:
        """
        从环境变量获取数据库连接参数
        
        Returns:
            Dict: 连接参数
        """
        return {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', 'postgres'),
            'database': os.getenv('POSTGRES_DB', 'image_hashes')
        }
    
    @staticmethod
    def get_connection_params_from_url(url: str) -> Dict[str, str]:
        """
        从连接URL解析连接参数
        
        Args:
            url: PostgreSQL连接URL
            
        Returns:
            Dict: 连接参数
        """
        # 简单的URL解析（生产环境建议使用更完整的解析库）
        import re
        pattern = r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)'
        match = re.match(pattern, url)
        
        if not match:
            raise ValueError(f"无效的PostgreSQL连接URL: {url}")
        
        user, password, host, port, database = match.groups()
        return {
            'host': host,
            'port': int(port),
            'user': user,
            'password': password,
            'database': database
        }


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="图片哈希数据库初始化工具")
    parser.add_argument("--url", help="PostgreSQL连接URL")
    parser.add_argument("--host", default="localhost", help="数据库主机")
    parser.add_argument("--port", type=int, default=5432, help="数据库端口")
    parser.add_argument("--user", default="postgres", help="数据库用户名")
    parser.add_argument("--password", help="数据库密码")
    parser.add_argument("--database", default="image_hashes", help="数据库名称")
    parser.add_argument("--create-db", action="store_true", help="如果数据库不存在则创建")
    parser.add_argument("--info-only", action="store_true", help="仅显示数据库信息")
    
    args = parser.parse_args()
    
    # 获取连接参数
    if args.url:
        connection_params = DatabaseInitializer.get_connection_params_from_url(args.url)
    else:
        connection_params = {
            'host': args.host,
            'port': args.port,
            'user': args.user,
            'password': args.password or os.getenv('POSTGRES_PASSWORD', 'postgres'),
            'database': args.database
        }
    
    database_name = connection_params['database']
    initializer = DatabaseInitializer(connection_params)
    
    logger.info("🚀 开始数据库初始化...")
    logger.info(f"📍 目标数据库: {connection_params['host']}:{connection_params['port']}/{database_name}")
    
    try:
        # 创建数据库（如果需要）
        if args.create_db:
            success = await initializer.create_database_if_not_exists(database_name)
            if not success:
                logger.error("❌ 数据库创建失败，程序退出")
                return
        
        # 仅显示信息
        if args.info_only:
            info = await initializer.get_database_info()
            if info:
                logger.info("📊 数据库信息:")
                logger.info(f"  版本: {info.get('database_version', 'Unknown')}")
                logger.info(f"  表数量: {len(info.get('tables', []))}")
                logger.info(f"  索引数量: {len(info.get('indexes', []))}")
                
                stats = info.get('statistics', {})
                if stats:
                    logger.info("📈 数据统计:")
                    logger.info(f"  总记录数: {stats.get('total_records', 0)}")
                    logger.info(f"  唯一哈希数: {stats.get('unique_hashes', 0)}")
                    logger.info(f"  文件格式数: {stats.get('unique_formats', 0)}")
            return
        
        # 初始化数据库结构
        success = await initializer.initialize_schema()
        if success:
            logger.info("✅ 数据库初始化完成！")
            
            # 显示数据库信息
            info = await initializer.get_database_info()
            if info:
                logger.info("📊 数据库结构:")
                for table in info.get('tables', []):
                    logger.info(f"  {table['table_name']} ({table['table_type']}) - {table['column_count']} 列")
        else:
            logger.error("❌ 数据库初始化失败")
    
    except Exception as e:
        logger.error(f"❌ 程序执行失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
