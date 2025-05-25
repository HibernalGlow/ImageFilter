"""
JSON 到 PostgreSQL 数据迁移工具
"""
import asyncio
import orjson
import os
from pathlib import Path
from typing import List, Dict, Any
from loguru import logger
from datetime import datetime
import argparse

from hashu.core.postgresql_storage import PostgreSQLHashStorage, HashRecord
from hashu.utils.path_uri import PathURIGenerator, URIParser

class HashDataMigrator:
    """哈希数据迁移器"""
    
    def __init__(self, db_storage: PostgreSQLHashStorage):
        self.db_storage = db_storage
        self.migrated_count = 0
        self.error_count = 0
    
    def _create_enhanced_record(self, uri: str, hash_value: str, hash_size: int = 10, 
                               hash_version: int = 1, file_size: int = None, 
                               metadata: Dict = None) -> HashRecord:
        """创建增强的哈希记录，自动解析URI信息
        
        Args:
            uri: 原始URI
            hash_value: 哈希值
            hash_size: 哈希大小
            hash_version: 哈希版本
            file_size: 文件大小
            metadata: 元数据
            
        Returns:
            HashRecord: 增强的哈希记录
        """
        # 解析URI获取详细信息
        uri_info = URIParser.parse_uri(uri)
        
        return HashRecord(
            uri=uri,
            hash_value=hash_value,
            hash_size=hash_size,
            hash_version=hash_version,
            file_size=file_size,
            metadata=metadata or {},
            filename=uri_info.get('filename'),
            file_format=uri_info.get('file_format'),
            uri_without_format=uri_info.get('uri_without_format'),
            archive_name=uri_info.get('archive_name')
        )
    
    async def migrate_from_json_files(self, json_files: List[str]) -> Dict[str, Any]:
        """从JSON文件迁移数据到PostgreSQL
        
        Args:
            json_files: JSON文件路径列表
            
        Returns:
            Dict[str, Any]: 迁移结果统计
        """
        logger.info(f"🚀 开始迁移 {len(json_files)} 个JSON文件到PostgreSQL")
        
        total_records = 0
        successful_files = 0
        
        for json_file in json_files:
            try:
                records = await self._load_json_file(json_file)
                if records:
                    success_count = await self.db_storage.batch_insert_hashes(records)
                    total_records += len(records)
                    self.migrated_count += success_count
                    successful_files += 1
                    logger.info(f"✅ 文件 {json_file}: {success_count}/{len(records)} 条记录迁移成功")
                else:
                    logger.warning(f"⚠️ 文件 {json_file}: 没有有效记录")
                    
            except Exception as e:
                logger.error(f"❌ 迁移文件失败 {json_file}: {e}")
                self.error_count += 1
                continue
        
        # 获取数据库统计信息
        db_stats = await self.db_storage.get_statistics()
        
        migration_result = {
            'processed_files': len(json_files),
            'successful_files': successful_files,
            'total_source_records': total_records,
            'migrated_records': self.migrated_count,
            'error_count': self.error_count,
            'database_stats': db_stats,
            'migration_time': datetime.now().isoformat()
        }
        
        logger.info("✅ 数据迁移完成!")
        logger.info(f"📊 处理文件: {successful_files}/{len(json_files)}")
        logger.info(f"📊 迁移记录: {self.migrated_count}/{total_records}")
        logger.info(f"📊 数据库总记录: {db_stats.get('total_records', 0)}")
        
        return migration_result
    
    async def _load_json_file(self, json_file: str) -> List[HashRecord]:
        """加载JSON文件并转换为HashRecord列表
        
        Args:
            json_file: JSON文件路径
            
        Returns:
            List[HashRecord]: 哈希记录列表
        """
        if not os.path.exists(json_file):
            logger.warning(f"⚠️ JSON文件不存在: {json_file}")
            return []
        
        try:
            with open(json_file, 'rb') as f:
                data = orjson.loads(f.read())
            
            if not data:
                return []
            
            records = []
            
            # 处理新格式 (image_hashes_collection.json)
            if "hashes" in data:
                hashes = data["hashes"]
                hash_params = data.get("_hash_params", {})
                default_hash_size = hash_params.get("hash_size", 10)
                default_hash_version = hash_params.get("hash_version", 1)
                
                for uri, hash_data in hashes.items():
                    try:
                        if isinstance(hash_data, dict):
                            hash_value = hash_data.get('hash')
                            if not hash_value:
                                continue
                            record = self._create_enhanced_record(
                                uri=uri,
                                hash_value=hash_value,
                                hash_size=hash_data.get('size', default_hash_size),
                                hash_version=default_hash_version,
                                file_size=hash_data.get('file_size'),
                                metadata={
                                    'source_file': json_file,
                                    'original_format': 'new',
                                    **hash_data
                                }                            )
                            records.append(record)
                        else:
                            # 简单格式：直接是哈希值字符串
                            record = self._create_enhanced_record(
                                uri=uri,
                                hash_value=str(hash_data),
                                hash_size=default_hash_size,
                                hash_version=default_hash_version,
                                metadata={
                                    'source_file': json_file,
                                    'original_format': 'simple'
                                }
                            )
                            records.append(record)
                            
                    except Exception as e:
                        logger.warning(f"⚠️ 处理记录失败 {uri}: {e}")
                        continue
            
            else:
                # 处理旧格式 (image_hashes_global.json)
                special_keys = {'_hash_params', 'dry_run', 'input_paths'}
                hash_params = data.get("_hash_params", {})
                default_hash_size = hash_params.get("hash_size", 10)
                default_hash_version = hash_params.get("hash_version", 1)
                
                for k, v in data.items():
                    if k in special_keys:
                        continue
                    
                    try:
                        if isinstance(v, dict):
                            hash_value = v.get('hash')
                            if not hash_value:
                                continue
                            record = self._create_enhanced_record(
                                uri=k,
                                hash_value=hash_value,
                                hash_size=v.get('size', default_hash_size),
                                hash_version=default_hash_version,
                                file_size=v.get('file_size'),
                                metadata={
                                    'source_file': json_file,
                                    'original_format': 'legacy_dict',
                                    **v
                                }
                            )
                            records.append(record)                        
                        else:
                            # 简单格式：直接是哈希值字符串
                            record = self._create_enhanced_record(
                                uri=k,
                                hash_value=str(v),
                                hash_size=default_hash_size,
                                hash_version=default_hash_version,
                                metadata={
                                    'source_file': json_file,
                                    'original_format': 'legacy_simple'
                                }
                            )
                            records.append(record)
                            
                    except Exception as e:
                        logger.warning(f"⚠️ 处理记录失败 {k}: {e}")
                        continue
            
            logger.debug(f"📄 从 {json_file} 加载了 {len(records)} 条记录")
            return records
            
        except Exception as e:
            logger.error(f"❌ 加载JSON文件失败 {json_file}: {e}")
            return []
    
    async def verify_migration(self, json_files: List[str]) -> Dict[str, Any]:
        """验证迁移结果
        
        Args:
            json_files: 原始JSON文件列表
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        logger.info("🔍 开始验证迁移结果...")
        
        total_json_records = 0
        verified_records = 0
        missing_records = []
        
        for json_file in json_files:
            try:
                records = await self._load_json_file(json_file)
                total_json_records += len(records)
                
                # 批量查询数据库中的记录
                uris = [record.uri for record in records]
                db_records = await self.db_storage.get_hashes_batch(uris)
                
                for record in records:
                    if record.uri in db_records:
                        db_record = db_records[record.uri]
                        if db_record.hash_value == record.hash_value:
                            verified_records += 1
                        else:
                            logger.warning(f"⚠️ 哈希值不匹配 {record.uri}: "
                                         f"JSON={record.hash_value} DB={db_record.hash_value}")
                    else:
                        missing_records.append(record.uri)
                        
            except Exception as e:
                logger.error(f"❌ 验证文件失败 {json_file}: {e}")
                continue
        
        verification_result = {
            'total_json_records': total_json_records,
            'verified_records': verified_records,
            'missing_records_count': len(missing_records),
            'missing_records': missing_records[:10],  # 只显示前10个
            'verification_rate': verified_records / total_json_records if total_json_records > 0 else 0
        }
        
        logger.info("✅ 迁移验证完成!")
        logger.info(f"📊 验证记录: {verified_records}/{total_json_records} "
                   f"({verification_result['verification_rate']*100:.1f}%)")
        logger.info(f"📊 缺失记录: {len(missing_records)}")
        
        return verification_result

async def migrate_hash_data():
    """主迁移函数"""
    # 数据库连接配置（可以通过环境变量设置）
    db_storage = PostgreSQLHashStorage()
    
    try:
        # 初始化数据库
        await db_storage.initialize()
        
        # 要迁移的JSON文件列表
        json_files = [
            os.path.expanduser(r"E:\1EHV\image_hashes_collection.json"),
            os.path.expanduser(r"E:\1EHV\image_hashes_global.json")
        ]
        
        # 过滤存在的文件
        existing_files = [f for f in json_files if os.path.exists(f)]
        
        if not existing_files:
            logger.warning("❌ 没有找到可迁移的JSON文件")
            return
        
        logger.info(f"📁 找到 {len(existing_files)} 个JSON文件待迁移")
        
        # 执行迁移
        migrator = HashDataMigrator(db_storage)
        migration_result = await migrator.migrate_from_json_files(existing_files)
        
        # 验证迁移结果
        verification_result = await migrator.verify_migration(existing_files)
        
        # 保存迁移报告
        report = {
            'migration': migration_result,
            'verification': verification_result
        }
        
        report_file = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(orjson.dumps(report, option=orjson.OPT_INDENT_2).decode())
        
        logger.info(f"📋 迁移报告已保存: {report_file}")
        
    except Exception as e:
        logger.error(f"❌ 迁移过程失败: {e}")
        raise
    finally:
        await db_storage.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="哈希数据迁移工具")
    parser.add_argument("--files", nargs="+", help="要迁移的JSON文件路径")
    parser.add_argument("--verify-only", action="store_true", help="仅验证迁移结果")
    parser.add_argument("--db-url", help="PostgreSQL连接URL")
    
    args = parser.parse_args()
    
    if args.files:
        json_files = args.files
    else:
        json_files = [
            os.path.expanduser(r"E:\1EHV\image_hashes_collection.json"),
            os.path.expanduser(r"E:\1EHV\image_hashes_global.json")
        ]
    
    if args.db_url:
        os.environ['POSTGRESQL_URL'] = args.db_url
    
    # 运行迁移
    asyncio.run(migrate_hash_data())
