"""
数据库管理便利脚本
提供常用的数据库操作命令
"""
import asyncio
import asyncpg
import os
from typing import Dict, List, Any
from loguru import logger
import argparse
from pathlib import Path

from .init_database import DatabaseInitializer
from .upgrade_database_schema import DatabaseSchemaUpgrader
from .migrate_to_postgresql import HashDataMigrator
from hashu.core.postgresql_storage import PostgreSQLHashStorage


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, connection_params: Dict[str, str]):
        self.connection_params = connection_params
        self.db_storage = PostgreSQLHashStorage(self._build_connection_url())
    
    def _build_connection_url(self) -> str:
        """构建连接URL"""
        params = self.connection_params
        return f"postgresql://{params['user']}:{params['password']}@{params['host']}:{params['port']}/{params['database']}"
    
    async def status(self) -> Dict[str, Any]:
        """获取数据库状态"""
        try:
            await self.db_storage.initialize()
            
            # 获取基本统计信息
            stats = await self.db_storage.get_statistics()
            
            # 获取表结构信息
            async with self.db_storage._pool.acquire() as conn:
                # 检查表是否存在
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                """)
                
                # 检查索引
                indexes = await conn.fetch("""
                    SELECT COUNT(*) as index_count
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                """)
                
                # 检查视图
                views = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.views 
                    WHERE table_schema = 'public'
                """)
                
                # 获取数据库大小
                db_size = await conn.fetchval("""
                    SELECT pg_size_pretty(pg_database_size(current_database()))
                """)
                
                return {
                    'connection_status': 'connected',
                    'database_size': db_size,
                    'tables': [row['table_name'] for row in tables],
                    'table_count': len(tables),
                    'index_count': indexes[0]['index_count'] if indexes else 0,
                    'views': [row['table_name'] for row in views],
                    'statistics': stats
                }
                
        except Exception as e:
            return {
                'connection_status': 'failed',
                'error': str(e)
            }
        finally:
            await self.db_storage.close()
    
    async def backup_schema(self, output_file: str) -> bool:
        """备份数据库结构"""
        try:
            # 这里可以使用 pg_dump 来备份结构
            # 由于需要调用外部命令，这里提供一个简化版本
            logger.info(f"📦 开始备份数据库结构到: {output_file}")
            
            # 实际实现需要调用 pg_dump 命令
            backup_command = (
                f"pg_dump --host={self.connection_params['host']} "
                f"--port={self.connection_params['port']} "
                f"--username={self.connection_params['user']} "
                f"--dbname={self.connection_params['database']} "
                f"--schema-only --file={output_file}"
            )
            
            logger.info(f"💡 请手动执行以下命令进行备份:")
            logger.info(f"   {backup_command}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 备份失败: {e}")
            return False
    
    async def cleanup_duplicates(self) -> int:
        """清理重复记录"""
        try:
            await self.db_storage.initialize()
            
            async with self.db_storage._pool.acquire() as conn:
                # 查找重复的URI
                duplicates = await conn.fetch("""
                    SELECT uri, COUNT(*) as count
                    FROM image_hashes
                    GROUP BY uri
                    HAVING COUNT(*) > 1
                """)
                
                if not duplicates:
                    logger.info("✅ 没有发现重复记录")
                    return 0
                
                cleaned_count = 0
                for dup in duplicates:
                    uri = dup['uri']
                    count = dup['count']
                    
                    # 保留最新的记录，删除其他的
                    deleted = await conn.execute("""
                        DELETE FROM image_hashes
                        WHERE uri = $1 AND id NOT IN (
                            SELECT id FROM image_hashes
                            WHERE uri = $1
                            ORDER BY updated_at DESC
                            LIMIT 1
                        )
                    """, uri)
                    
                    cleaned_count += count - 1
                    logger.info(f"🧹 清理URI重复记录: {uri} (删除 {count-1} 条)")
                
                logger.info(f"✅ 清理完成，共删除 {cleaned_count} 条重复记录")
                return cleaned_count
                
        except Exception as e:
            logger.error(f"❌ 清理重复记录失败: {e}")
            return 0
        finally:
            await self.db_storage.close()
    
    async def optimize_database(self) -> bool:
        """优化数据库"""
        try:
            await self.db_storage.initialize()
            
            async with self.db_storage._pool.acquire() as conn:
                logger.info("🔧 开始数据库优化...")
                
                # 更新表统计信息
                await conn.execute("ANALYZE image_hashes")
                logger.info("✅ 更新表统计信息完成")
                
                # 重建索引
                await conn.execute("REINDEX TABLE image_hashes")
                logger.info("✅ 重建索引完成")
                
                # 清理死元组
                await conn.execute("VACUUM image_hashes")
                logger.info("✅ 清理死元组完成")
                
                logger.info("✅ 数据库优化完成")
                return True
                
        except Exception as e:
            logger.error(f"❌ 数据库优化失败: {e}")
            return False
        finally:
            await self.db_storage.close()
    
    async def export_statistics(self, output_file: str) -> bool:
        """导出统计信息"""
        try:
            await self.db_storage.initialize()
            
            async with self.db_storage._pool.acquire() as conn:
                # 获取基本统计
                basic_stats = await conn.fetchrow("SELECT * FROM image_hashes_stats")
                
                # 获取格式分布
                format_stats = await conn.fetch("SELECT * FROM format_distribution")
                
                # 获取压缩包分布
                archive_stats = await conn.fetch("SELECT * FROM archive_distribution")
                
                # 组织数据
                stats_data = {
                    'basic_statistics': dict(basic_stats) if basic_stats else {},
                    'format_distribution': [dict(row) for row in format_stats],
                    'archive_distribution': [dict(row) for row in archive_stats],
                    'export_time': str(asyncio.get_event_loop().time())
                }
                
                # 写入文件
                import json
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(stats_data, f, indent=2, ensure_ascii=False, default=str)
                
                logger.info(f"📊 统计信息已导出到: {output_file}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 导出统计信息失败: {e}")
            return False
        finally:
            await self.db_storage.close()


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="数据库管理工具")
    parser.add_argument("--url", help="PostgreSQL连接URL")
    parser.add_argument("--host", default="localhost", help="数据库主机")
    parser.add_argument("--port", type=int, default=5432, help="数据库端口")
    parser.add_argument("--user", default="postgres", help="数据库用户名")
    parser.add_argument("--password", help="数据库密码")
    parser.add_argument("--database", default="image_hashes", help="数据库名称")
    
    # 操作命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 状态命令
    subparsers.add_parser('status', help='显示数据库状态')
    
    # 初始化命令
    init_parser = subparsers.add_parser('init', help='初始化数据库')
    init_parser.add_argument('--create-db', action='store_true', help='创建数据库')
    
    # 升级命令
    subparsers.add_parser('upgrade', help='升级数据库结构')
    
    # 迁移命令
    migrate_parser = subparsers.add_parser('migrate', help='从JSON文件迁移数据')
    migrate_parser.add_argument('files', nargs='+', help='JSON文件路径')
    
    # 清理命令
    subparsers.add_parser('cleanup', help='清理重复记录')
    
    # 优化命令
    subparsers.add_parser('optimize', help='优化数据库')
    
    # 备份命令
    backup_parser = subparsers.add_parser('backup', help='备份数据库结构')
    backup_parser.add_argument('--output', required=True, help='输出文件路径')
    
    # 导出统计命令
    export_parser = subparsers.add_parser('export-stats', help='导出统计信息')
    export_parser.add_argument('--output', required=True, help='输出文件路径')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
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
    
    manager = DatabaseManager(connection_params)
    
    try:
        if args.command == 'status':
            status = await manager.status()
            logger.info("📊 数据库状态:")
            logger.info(f"  连接状态: {status.get('connection_status')}")
            if status.get('connection_status') == 'connected':
                logger.info(f"  数据库大小: {status.get('database_size')}")
                logger.info(f"  表数量: {status.get('table_count')}")
                logger.info(f"  索引数量: {status.get('index_count')}")
                stats = status.get('statistics', {})
                if stats:
                    logger.info(f"  总记录数: {stats.get('total_records', 0)}")
                    logger.info(f"  唯一哈希数: {stats.get('unique_hashes', 0)}")
        
        elif args.command == 'init':
            initializer = DatabaseInitializer(connection_params)
            if hasattr(args, 'create_db') and args.create_db:
                await initializer.create_database_if_not_exists(connection_params['database'])
            await initializer.initialize_schema()
        
        elif args.command == 'upgrade':
            db_storage = PostgreSQLHashStorage(manager._build_connection_url())
            upgrader = DatabaseSchemaUpgrader(db_storage)
            await upgrader.upgrade_schema()
            await db_storage.close()
        
        elif args.command == 'migrate':
            db_storage = PostgreSQLHashStorage(manager._build_connection_url())
            migrator = HashDataMigrator(db_storage)
            await migrator.migrate_from_json_files(args.files)
            await db_storage.close()
        
        elif args.command == 'cleanup':
            cleaned = await manager.cleanup_duplicates()
            logger.info(f"✅ 清理完成，删除了 {cleaned} 条重复记录")
        
        elif args.command == 'optimize':
            success = await manager.optimize_database()
            if success:
                logger.info("✅ 数据库优化完成")
        
        elif args.command == 'backup':
            success = await manager.backup_schema(args.output)
            if success:
                logger.info("✅ 备份命令已提供")
        
        elif args.command == 'export-stats':
            success = await manager.export_statistics(args.output)
            if success:
                logger.info("✅ 统计信息导出完成")
    
    except Exception as e:
        logger.error(f"❌ 命令执行失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
