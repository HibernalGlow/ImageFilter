import os
from pathlib import Path
from typing import Optional
from hashu.core.calculate_hash_custom import HashCache, ImageHashCalculator, get_db_cached
from hashu.utils.path_uri import PathURIGenerator
from hashu.log import logger

def get_or_create_archive_hash(archive_path: str) -> Optional[str]:
    """
    获取或创建压缩包哈希：
    - 如果数据库中有同名（文件名相同，不同路径）压缩包，直接返回其哈希，并插入新路径记录。
    - 否则正常计算哈希并插入。
    - 每次都插入新记录（新路径+同哈希）。
    """
    db = get_db_cached()
    archive_path = os.path.abspath(archive_path)
    filename = os.path.basename(archive_path)
    
    # 查询所有同名压缩包记录
    try:
        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT * FROM image_hashes WHERE filename = ? AND source_type = 'file' ORDER BY calculated_time DESC",
            (filename,)
        )
        rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"数据库查询失败: {e}")
        rows = []

    # 标准化当前路径为uri
    uri = PathURIGenerator.generate(archive_path)

    if rows:
        # 已有同名压缩包，直接用其哈希
        hash_value = rows[0]['hash_value']
        logger.info(f"[hash_manager] 检测到同名压缩包，直接复用哈希: {filename} -> {hash_value}")
        # 仍然插入新路径记录
        db.add_hash(uri, hash_value, file_size=os.path.getsize(archive_path))
        db._get_connection().commit()
        return hash_value
    else:
        # 没有同名，正常计算哈希
        hash_result = ImageHashCalculator.calculate_phash(archive_path)
        if hash_result and 'hash' in hash_result:
            hash_value = hash_result['hash']
            db.add_hash(uri, hash_value, file_size=os.path.getsize(archive_path))
            db._get_connection().commit()
            logger.info(f"[hash_manager] 新压缩包哈希已计算并存储: {filename} -> {hash_value}")
            return hash_value
        else:
            logger.error(f"[hash_manager] 压缩包哈希计算失败: {archive_path}")
            return None 