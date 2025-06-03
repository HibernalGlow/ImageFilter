"""
SQLite数据库存储模块
支持自定义archive://协议和向下兼容JSON格式
"""
from hashu.log import logger

import sqlite3
import os
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, unquote
from datetime import datetime
import orjson


class HashDatabaseManager:
    """哈希数据库管理器"""
    
    def __init__(self, db_path: str = None):
        """初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径，默认从配置管理器获取
        """
        if db_path is None:
            # 从配置管理器获取默认数据库路径
            try:
                from hashu.config import get_config
                config = get_config()
                primary_db = config.get_primary_sqlite_database()
                db_path = primary_db if primary_db else os.path.expanduser("~/hash_database.db")
            except ImportError:
                # 向后兼容：如果配置管理器不可用，使用默认路径
                db_path = os.path.expanduser("~/hash_database.db")
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._lock = threading.RLock()
        self._connection_pool = {}
        
        # 初始化数据库表结构
        self._init_database()
        
        logger.info(f"哈希数据库已初始化: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（线程安全）"""
        thread_id = threading.get_ident()
        
        if thread_id not in self._connection_pool:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row  # 使返回结果支持字典访问
            conn.execute("PRAGMA foreign_keys = ON")  # 启用外键约束
            conn.execute("PRAGMA journal_mode = WAL")  # 启用WAL模式提高并发性能
            self._connection_pool[thread_id] = conn
            
        return self._connection_pool[thread_id]
    
    def _init_database(self):
        """初始化数据库表结构"""
        with self._lock:
            conn = self._get_connection()
            
            # 创建主哈希表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS image_hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uri TEXT NOT NULL UNIQUE,                    -- 完整的URI (包含archive://)
                    filename TEXT NOT NULL,                      -- 文件名
                    file_extension TEXT,                         -- 文件扩展名 (.jpg, .png等)
                    base_uri TEXT NOT NULL,                      -- 去掉扩展名的URI (用于格式转换匹配)
                    archive_name TEXT,                           -- 压缩包名称 (如果是压缩包内文件)
                    hash_value TEXT NOT NULL,                    -- 哈希值
                    hash_size INTEGER DEFAULT 10,               -- 哈希大小
                    hash_algorithm TEXT DEFAULT 'phash',        -- 哈希算法
                    file_size INTEGER,                           -- 文件大小(字节)
                    image_width INTEGER,                         -- 图片宽度
                    image_height INTEGER,                        -- 图片高度
                    created_time REAL,                           -- 创建时间(时间戳)
                    modified_time REAL,                          -- 修改时间(时间戳)
                    accessed_time REAL,                          -- 访问时间(时间戳)
                    calculated_time REAL NOT NULL,              -- 哈希计算时间(时间戳)
                    source_type TEXT DEFAULT 'file',            -- 来源类型: file, archive, url
                    metadata TEXT,                               -- 额外元数据(JSON格式)
                    
                    -- 索引优化
                    UNIQUE(uri)
                )
            """)
            
            # 创建索引以优化查询性能
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_base_uri ON image_hashes(base_uri)",
                "CREATE INDEX IF NOT EXISTS idx_hash_value ON image_hashes(hash_value)",
                "CREATE INDEX IF NOT EXISTS idx_filename ON image_hashes(filename)",
                "CREATE INDEX IF NOT EXISTS idx_archive_name ON image_hashes(archive_name)",
                "CREATE INDEX IF NOT EXISTS idx_file_extension ON image_hashes(file_extension)",
                "CREATE INDEX IF NOT EXISTS idx_calculated_time ON image_hashes(calculated_time)",
                "CREATE INDEX IF NOT EXISTS idx_source_type ON image_hashes(source_type)",
                
                # 复合索引
                "CREATE INDEX IF NOT EXISTS idx_base_uri_ext ON image_hashes(base_uri, file_extension)",
                "CREATE INDEX IF NOT EXISTS idx_archive_filename ON image_hashes(archive_name, filename)",
            ]
            
            for index_sql in indexes:
                conn.execute(index_sql)
            
            # 创建迁移记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS migration_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file TEXT NOT NULL,                   -- 来源JSON文件路径
                    migrated_count INTEGER NOT NULL,            -- 迁移的记录数
                    migration_time REAL NOT NULL,               -- 迁移时间
                    status TEXT DEFAULT 'completed'             -- 迁移状态
                )
            """)
            
            conn.commit()
    
    def parse_uri(self, uri: str) -> Dict[str, str]:
        """解析URI并提取各个组件
        
        Args:
            uri: 要解析的URI
            
        Returns:
            包含URI组件的字典
        """
        result = {
            'uri': uri,
            'filename': '',
            'file_extension': '',
            'base_uri': '',
            'archive_name': '',
            'source_type': 'file'
        }
        
        try:
            if uri.startswith('archive://'):
                # 解析archive://协议
                # 格式: archive://path/to/archive.zip!/internal/path/image.jpg
                result['source_type'] = 'archive'
                # 去掉协议前缀
                path_part = uri[10:]  # 去掉 "archive://"
                if '!/' in path_part:
                    archive_path, internal_path = path_part.split('!/', 1)
                    result['archive_name'] = os.path.basename(archive_path)
                    result['filename'] = internal_path  # 这里直接用相对路径
                    # 构建base_uri (去掉扩展名)
                    name_without_ext = os.path.splitext(os.path.basename(internal_path))[0]
                    result['base_uri'] = f"archive://{archive_path}!/{os.path.dirname(internal_path)}/{name_without_ext}".rstrip('/')
                else:
                    # 没有内部路径的情况
                    result['filename'] = os.path.basename(path_part)
                    result['base_uri'] = f"archive://{os.path.splitext(path_part)[0]}"
            elif '://' in uri:
                # 其他协议（如http, https等）
                result['source_type'] = 'url'
                parsed = urlparse(uri)
                result['filename'] = os.path.basename(unquote(parsed.path))
                base_path = os.path.splitext(unquote(parsed.path))[0]
                result['base_uri'] = f"{parsed.scheme}://{parsed.netloc}{base_path}"
                
            else:
                # 普通文件路径
                result['source_type'] = 'file'
                result['filename'] = os.path.basename(uri)
                result['base_uri'] = os.path.splitext(uri)[0]
            
            # 提取文件扩展名
            if result['filename']:
                result['file_extension'] = os.path.splitext(result['filename'])[1].lower()
                
        except Exception as e:
            logger.warning(f"解析URI失败 {uri}: {e}")
            result['filename'] = os.path.basename(uri)
            result['base_uri'] = os.path.splitext(uri)[0]
        
        return result
    
    def add_hash(self, uri: str, hash_value: str, 
                 file_size: int = None, 
                 image_dimensions: Tuple[int, int] = None,
                 file_times: Dict[str, float] = None,
                 metadata: Dict[str, Any] = None,
                 hash_size: int = 10,
                 hash_algorithm: str = 'phash') -> bool:
        """添加哈希记录
        
        Args:
            uri: 图片URI
            hash_value: 哈希值
            file_size: 文件大小
            image_dimensions: 图片尺寸 (width, height)
            file_times: 文件时间信息 {'created': timestamp, 'modified': timestamp, 'accessed': timestamp}
            metadata: 额外元数据
            hash_size: 哈希大小
            hash_algorithm: 哈希算法
            
        Returns:
            是否添加成功
        """
        try:
            with self._lock:
                conn = self._get_connection()
                
                # 解析URI
                uri_info = self.parse_uri(uri)
                
                # 准备插入数据
                current_time = time.time()
                
                insert_data = {
                    'uri': uri,
                    'filename': uri_info['filename'],
                    'file_extension': uri_info['file_extension'],
                    'base_uri': uri_info['base_uri'],
                    'archive_name': uri_info['archive_name'] or None,
                    'hash_value': hash_value,
                    'hash_size': hash_size,
                    'hash_algorithm': hash_algorithm,
                    'file_size': file_size,
                    'image_width': image_dimensions[0] if image_dimensions else None,
                    'image_height': image_dimensions[1] if image_dimensions else None,
                    'created_time': file_times.get('created') if file_times else None,
                    'modified_time': file_times.get('modified') if file_times else None,
                    'accessed_time': file_times.get('accessed') if file_times else None,
                    'calculated_time': current_time,
                    'source_type': uri_info['source_type'],
                    'metadata': orjson.dumps(metadata).decode() if metadata else None
                }
                
                # 使用INSERT OR REPLACE来处理重复记录
                conn.execute("""
                    INSERT OR REPLACE INTO image_hashes (
                        uri, filename, file_extension, base_uri, archive_name,
                        hash_value, hash_size, hash_algorithm, file_size,
                        image_width, image_height, created_time, modified_time,
                        accessed_time, calculated_time, source_type, metadata
                    ) VALUES (
                        :uri, :filename, :file_extension, :base_uri, :archive_name,
                        :hash_value, :hash_size, :hash_algorithm, :file_size,
                        :image_width, :image_height, :created_time, :modified_time,
                        :accessed_time, :calculated_time, :source_type, :metadata
                    )
                """, insert_data)
                
                conn.commit()
                logger.debug(f"添加哈希记录: {uri} -> {hash_value}")
                return True
                
        except Exception as e:
            logger.error(f"添加哈希记录失败 {uri}: {e}")
            return False
    
    def get_hash(self, uri: str) -> Optional[str]:
        """获取指定URI的哈希值
        
        Args:
            uri: 图片URI
            
        Returns:
            哈希值，未找到返回None
        """
        try:
            with self._lock:
                conn = self._get_connection()
                
                # 优先精确匹配
                cursor = conn.execute(
                    "SELECT hash_value FROM image_hashes WHERE uri = ?",
                    (uri,)
                )
                row = cursor.fetchone()
                
                if row:
                    return row['hash_value']
                
                return None
                
        except Exception as e:
            logger.error(f"查询哈希值失败 {uri}: {e}")
            return None
    
    def find_by_base_uri(self, base_uri: str) -> List[Dict[str, Any]]:
        """根据base_uri查找所有匹配的记录（用于格式转换匹配）
        
        Args:
            base_uri: 去掉扩展名的URI
            
        Returns:
            匹配的记录列表
        """
        try:
            with self._lock:
                conn = self._get_connection()
                
                cursor = conn.execute("""
                    SELECT * FROM image_hashes 
                    WHERE base_uri = ? 
                    ORDER BY calculated_time DESC
                """, (base_uri,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"按base_uri查询失败 {base_uri}: {e}")
            return []
    
    def smart_query(self, uri: str) -> Optional[str]:
        """智能查询：优先匹配去掉格式的URL，方便图片格式转换
        
        Args:
            uri: 图片URI
            
        Returns:
            哈希值，未找到返回None
        """
        try:
            # 1. 首先尝试精确匹配
            exact_hash = self.get_hash(uri)
            if exact_hash:
                logger.debug(f"精确匹配找到哈希: {uri}")
                return exact_hash
            
            # 2. 解析URI并尝试base_uri匹配
            uri_info = self.parse_uri(uri)
            base_uri = uri_info['base_uri']
            
            if base_uri != uri:
                matches = self.find_by_base_uri(base_uri)
                if matches:
                    # 返回最新的记录
                    latest_match = matches[0]
                    hash_value = latest_match['hash_value']
                    logger.debug(f"base_uri匹配找到哈希: {base_uri} -> {hash_value}")
                    logger.debug(f"匹配的完整URI: {latest_match['uri']}")
                    return hash_value
            
            logger.debug(f"未找到哈希值: {uri}")
            return None
            
        except Exception as e:
            logger.error(f"智能查询失败 {uri}: {e}")
            return None
    
    def batch_add_hashes(self, hash_records: List[Dict[str, Any]]) -> int:
        """批量添加哈希记录
        
        Args:
            hash_records: 哈希记录列表
            
        Returns:
            成功添加的记录数
        """
        try:
            with self._lock:
                conn = self._get_connection()
                current_time = time.time()
                
                processed_records = []
                for record in hash_records:
                    uri_info = self.parse_uri(record['uri'])
                    
                    processed_record = {
                        'uri': record['uri'],
                        'filename': uri_info['filename'],
                        'file_extension': uri_info['file_extension'],
                        'base_uri': uri_info['base_uri'],
                        'archive_name': uri_info['archive_name'] or None,
                        'hash_value': record['hash_value'],
                        'hash_size': record.get('hash_size', 10),
                        'hash_algorithm': record.get('hash_algorithm', 'phash'),
                        'file_size': record.get('file_size'),
                        'image_width': record.get('image_width'),
                        'image_height': record.get('image_height'),
                        'created_time': record.get('created_time'),
                        'modified_time': record.get('modified_time'),
                        'accessed_time': record.get('accessed_time'),
                        'calculated_time': record.get('calculated_time', current_time),
                        'source_type': uri_info['source_type'],
                        'metadata': orjson.dumps(record['metadata']).decode() if record.get('metadata') else None
                    }
                    processed_records.append(processed_record)
                
                # 批量插入
                conn.executemany("""
                    INSERT OR REPLACE INTO image_hashes (
                        uri, filename, file_extension, base_uri, archive_name,
                        hash_value, hash_size, hash_algorithm, file_size,
                        image_width, image_height, created_time, modified_time,
                        accessed_time, calculated_time, source_type, metadata
                    ) VALUES (
                        :uri, :filename, :file_extension, :base_uri, :archive_name,
                        :hash_value, :hash_size, :hash_algorithm, :file_size,
                        :image_width, :image_height, :created_time, :modified_time,
                        :accessed_time, :calculated_time, :source_type, :metadata
                    )
                """, processed_records)
                
                conn.commit()
                logger.info(f"批量添加 {len(processed_records)} 条哈希记录")
                return len(processed_records)
                
        except Exception as e:
            logger.error(f"批量添加哈希记录失败: {e}")
            return 0
    
    def migrate_from_json(self, json_file_path: str) -> int:
        """从JSON文件迁移数据到SQLite
        
        Args:
            json_file_path: JSON文件路径
            
        Returns:
            迁移的记录数
        """
        try:
            with open(json_file_path, 'rb') as f:
                data = orjson.loads(f.read())
            
            migration_records = []
            
            # 处理新格式 (image_hashes_collection.json)
            if "hashes" in data:
                hashes = data["hashes"]
                for uri, hash_data in hashes.items():
                    if isinstance(hash_data, dict):
                        record = {
                            'uri': uri,
                            'hash_value': hash_data.get('hash', ''),
                            'hash_size': hash_data.get('size', 10),
                            'calculated_time': hash_data.get('timestamp', time.time()),
                            'metadata': {k: v for k, v in hash_data.items() 
                                       if k not in ['hash', 'size', 'timestamp']}
                        }
                        migration_records.append(record)
                    else:
                        # 简单的字符串格式
                        record = {
                            'uri': uri,
                            'hash_value': str(hash_data),
                            'calculated_time': time.time()
                        }
                        migration_records.append(record)
            else:
                # 处理旧格式 (image_hashes_global.json)
                special_keys = {'_hash_params', 'dry_run', 'input_paths'}
                for uri, hash_data in data.items():
                    if uri not in special_keys:
                        if isinstance(hash_data, dict):
                            record = {
                                'uri': uri,
                                'hash_value': hash_data.get('hash', ''),
                                'hash_size': hash_data.get('size', 10),
                                'calculated_time': hash_data.get('timestamp', time.time()),
                                'metadata': {k: v for k, v in hash_data.items() 
                                           if k not in ['hash', 'size', 'timestamp']}
                            }
                            migration_records.append(record)
                        else:
                            record = {
                                'uri': uri,
                                'hash_value': str(hash_data),
                                'calculated_time': time.time()
                            }
                            migration_records.append(record)
            
            # 批量插入
            migrated_count = self.batch_add_hashes(migration_records)
            
            # 记录迁移日志
            with self._lock:
                conn = self._get_connection()
                conn.execute("""
                    INSERT INTO migration_log (source_file, migrated_count, migration_time)
                    VALUES (?, ?, ?)
                """, (json_file_path, migrated_count, time.time()))
                conn.commit()
            
            logger.info(f"从 {json_file_path} 迁移了 {migrated_count} 条记录")
            return migrated_count
            
        except Exception as e:
            logger.error(f"从JSON文件迁移失败 {json_file_path}: {e}")
            return 0
    
    def export_to_json(self, output_file: str, format_type: str = 'new') -> bool:
        """导出数据到JSON格式（保持向下兼容）
        
        Args:
            output_file: 输出文件路径
            format_type: 格式类型 ('new' 或 'old')
            
        Returns:
            是否导出成功
        """
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.execute("SELECT * FROM image_hashes ORDER BY calculated_time")
                
                if format_type == 'new':
                    # 新格式
                    export_data = {
                        "_hash_params": "hash_size=10;hash_version=1",
                        "hashes": {}
                    }
                    
                    for row in cursor:
                        hash_info = {
                            'hash': row['hash_value'],
                            'size': row['hash_size'],
                            'timestamp': row['calculated_time']
                        }
                        
                        # 添加额外信息
                        if row['file_size']:
                            hash_info['file_size'] = row['file_size']
                        if row['image_width'] and row['image_height']:
                            hash_info['dimensions'] = [row['image_width'], row['image_height']]
                        if row['metadata']:
                            try:
                                metadata = orjson.loads(row['metadata'])
                                hash_info.update(metadata)
                            except:
                                pass
                        
                        export_data["hashes"][row['uri']] = hash_info
                        
                else:
                    # 旧格式
                    export_data = {}
                    for row in cursor:
                        export_data[row['uri']] = {
                            'hash': row['hash_value'],
                            'size': row['hash_size']
                        }
            
            # 写入文件
            with open(output_file, 'wb') as f:
                f.write(orjson.dumps(export_data, option=orjson.OPT_INDENT_2))
            
            logger.info(f"导出数据到 {output_file}，格式: {format_type}")
            return True
            
        except Exception as e:
            logger.error(f"导出到JSON失败: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            with self._lock:
                conn = self._get_connection()
                
                stats = {}
                
                # 总记录数
                cursor = conn.execute("SELECT COUNT(*) as total FROM image_hashes")
                stats['total_records'] = cursor.fetchone()['total']
                
                # 按来源类型统计
                cursor = conn.execute("""
                    SELECT source_type, COUNT(*) as count 
                    FROM image_hashes 
                    GROUP BY source_type
                """)
                stats['by_source_type'] = {row['source_type']: row['count'] for row in cursor}
                
                # 按文件扩展名统计
                cursor = conn.execute("""
                    SELECT file_extension, COUNT(*) as count 
                    FROM image_hashes 
                    WHERE file_extension IS NOT NULL
                    GROUP BY file_extension 
                    ORDER BY count DESC
                    LIMIT 10
                """)
                stats['by_extension'] = {row['file_extension']: row['count'] for row in cursor}
                
                # 按压缩包统计
                cursor = conn.execute("""
                    SELECT archive_name, COUNT(*) as count 
                    FROM image_hashes 
                    WHERE archive_name IS NOT NULL
                    GROUP BY archive_name 
                    ORDER BY count DESC
                    LIMIT 10
                """)
                stats['by_archive'] = {row['archive_name']: row['count'] for row in cursor}
                
                # 数据库文件大小
                stats['db_size_bytes'] = self.db_path.stat().st_size if self.db_path.exists() else 0
                stats['db_size_mb'] = round(stats['db_size_bytes'] / 1024 / 1024, 2)
                
                return stats
                
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def close(self):
        """关闭数据库连接"""
        try:
            for conn in self._connection_pool.values():
                conn.close()
            self._connection_pool.clear()
            logger.info("数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}")


# 全局数据库实例
_db_instance = None
_db_lock = threading.Lock()


def get_database_instance(db_path: str = None) -> HashDatabaseManager:
    """获取全局数据库实例（单例模式）"""
    global _db_instance
    
    with _db_lock:
        if _db_instance is None:
            _db_instance = HashDatabaseManager(db_path)
        return _db_instance


def initialize_database(db_path: str = None) -> HashDatabaseManager:
    """初始化数据库"""
    return get_database_instance(db_path)
