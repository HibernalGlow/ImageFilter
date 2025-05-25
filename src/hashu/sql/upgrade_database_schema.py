"""
数据库结构升级脚本
用于将现有的数据库结构升级到支持新字段的版本
"""
import asyncio
import asyncpg
import os
from typing import Dict, List, Any
from loguru import logger
from datetime import datetime

from hashu.core.postgresql_storage import PostgreSQLHashStorage, get_database
from hashu.utils.path_uri import URIParser


class DatabaseSchemaUpgrader:
    """数据库结构升级器"""
    
    def __init__(self, db_storage: PostgreSQLHashStorage):
        self.db_storage = db_storage
        self.upgraded_count = 0
        self.error_count = 0
    
    async def check_schema_version(self) -> Dict[str, Any]:
        """检查当前数据库结构版本"""
        try:
            async with self.db_storage._pool.acquire() as conn:
                # 检查是否存在新字段
                columns_query = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'image_hashes' 
                AND table_schema = 'public'
                ORDER BY column_name
                """
                
                columns = await conn.fetch(columns_query)
                column_names = [row['column_name'] for row in columns]
                
                # 检查新字段是否存在
                new_fields = ['filename', 'file_format', 'uri_without_format', 'archive_name']
                missing_fields = [field for field in new_fields if field not in column_names]
                
                return {
                    'current_columns': column_names,
                    'missing_fields': missing_fields,
                    'needs_upgrade': len(missing_fields) > 0,
                    'total_records': await self._get_total_records_count()
                }
                
        except Exception as e:
            logger.error(f"❌ 检查数据库结构失败: {e}")
            return {'needs_upgrade': False, 'error': str(e)}
    
    async def _get_total_records_count(self) -> int:
        """获取总记录数"""
        try:
            async with self.db_storage._pool.acquire() as conn:
                result = await conn.fetchval("SELECT COUNT(*) FROM image_hashes")
                return result or 0
        except Exception as e:
            logger.warning(f"获取记录数失败: {e}")
            return 0
    
    async def upgrade_schema(self) -> Dict[str, Any]:
        """升级数据库结构"""
        logger.info("🚀 开始升级数据库结构...")
        
        try:
            # 首先检查是否需要升级
            schema_info = await self.check_schema_version()
            if not schema_info.get('needs_upgrade', False):
                logger.info("✅ 数据库结构已经是最新版本")
                return {'success': True, 'message': '无需升级'}
            
            missing_fields = schema_info.get('missing_fields', [])
            logger.info(f"📋 需要添加的字段: {missing_fields}")
            
            # 添加新字段
            await self._add_missing_columns(missing_fields)
            
            # 创建新索引
            await self._create_new_indexes()
            
            # 迁移现有数据
            await self._migrate_existing_data()
            
            logger.info("✅ 数据库结构升级完成")
            return {
                'success': True,
                'upgraded_records': self.upgraded_count,
                'error_count': self.error_count,
                'upgrade_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ 数据库结构升级失败: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _add_missing_columns(self, missing_fields: List[str]) -> None:
        """添加缺失的列"""
        field_definitions = {
            'filename': 'VARCHAR(512)',
            'file_format': 'VARCHAR(32)',
            'uri_without_format': 'VARCHAR(2048)',
            'archive_name': 'VARCHAR(512)'
        }
        
        async with self.db_storage._pool.acquire() as conn:
            for field in missing_fields:
                if field in field_definitions:
                    sql = f"ALTER TABLE image_hashes ADD COLUMN IF NOT EXISTS {field} {field_definitions[field]}"
                    await conn.execute(sql)
                    logger.info(f"✅ 添加字段: {field}")
    
    async def _create_new_indexes(self) -> None:
        """创建新索引"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_image_hashes_uri_without_format ON image_hashes (uri_without_format)",
            "CREATE INDEX IF NOT EXISTS idx_image_hashes_filename ON image_hashes (filename)",
            "CREATE INDEX IF NOT EXISTS idx_image_hashes_file_format ON image_hashes (file_format)",
            "CREATE INDEX IF NOT EXISTS idx_image_hashes_archive_name ON image_hashes (archive_name)",
            "CREATE INDEX IF NOT EXISTS idx_image_hashes_format_search ON image_hashes (uri_without_format, file_format)"
        ]
        
        async with self.db_storage._pool.acquire() as conn:
            for index_sql in indexes:
                try:
                    await conn.execute(index_sql)
                    logger.debug(f"✅ 创建索引成功")
                except Exception as e:
                    logger.warning(f"创建索引失败: {e}")
    
    async def _migrate_existing_data(self) -> None:
        """迁移现有数据，填充新字段"""
        logger.info("📊 开始迁移现有数据...")
        
        try:
            # 分批处理，避免内存占用过大
            batch_size = 1000
            offset = 0
            
            while True:
                # 查询一批需要更新的记录
                sql = """
                SELECT id, uri FROM image_hashes 
                WHERE filename IS NULL OR file_format IS NULL OR uri_without_format IS NULL
                ORDER BY id 
                LIMIT $1 OFFSET $2
                """
                
                async with self.db_storage._pool.acquire() as conn:
                    rows = await conn.fetch(sql, batch_size, offset)
                    
                    if not rows:
                        break
                    
                    # 处理这批记录
                    for row in rows:
                        try:
                            await self._update_record_fields(row['id'], row['uri'])
                            self.upgraded_count += 1
                        except Exception as e:
                            logger.warning(f"更新记录失败 ID={row['id']}: {e}")
                            self.error_count += 1
                    
                    offset += batch_size
                    
                    if len(rows) < batch_size:
                        break
                    
                    # 进度报告
                    if offset % 5000 == 0:
                        logger.info(f"📈 已处理 {offset} 条记录...")
            
            logger.info(f"✅ 数据迁移完成: 成功 {self.upgraded_count}, 失败 {self.error_count}")
            
        except Exception as e:
            logger.error(f"❌ 数据迁移失败: {e}")
            raise
    
    async def _update_record_fields(self, record_id: int, uri: str) -> None:
        """更新单条记录的新字段"""
        # 解析URI获取详细信息
        uri_info = URIParser.parse_uri(uri)
        
        update_sql = """
        UPDATE image_hashes 
        SET 
            filename = $2,
            file_format = $3,
            uri_without_format = $4,
            archive_name = $5,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
        """
        
        async with self.db_storage._pool.acquire() as conn:
            await conn.execute(
                update_sql,
                record_id,
                uri_info.get('filename'),
                uri_info.get('file_format'),
                uri_info.get('uri_without_format'),
                uri_info.get('archive_name')
            )


async def upgrade_database_schema():
    """主升级函数"""
    try:
        # 获取数据库实例
        db = await get_database()
        
        # 创建升级器
        upgrader = DatabaseSchemaUpgrader(db)
        
        # 检查当前状态
        schema_info = await upgrader.check_schema_version()
        logger.info(f"📊 数据库状态: {schema_info}")
        
        if schema_info.get('needs_upgrade', False):
            # 执行升级
            result = await upgrader.upgrade_schema()
            logger.info(f"🎉 升级结果: {result}")
        else:
            logger.info("✅ 数据库已经是最新版本，无需升级")
        
        # 关闭数据库连接
        await db.close()
        
    except Exception as e:
        logger.error(f"❌ 升级过程失败: {e}")
        raise


if __name__ == "__main__":
    # 运行升级
    asyncio.run(upgrade_database_schema())
