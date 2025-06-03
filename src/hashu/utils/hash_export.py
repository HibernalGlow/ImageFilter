"""
哈希计算导出模块 - 为外部应用提供便捷接口
"""
import os
import subprocess
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Union, Tuple
from loguru import logger

from hashu.utils.hash_process_config import (
    process_duplicates as _process_duplicates,
    get_latest_hash_file_path
)
from hashu.core.calculate_hash_custom import ImageHashCalculator, HashCache, ImgUtils

def calculate_hash_for_artist_folder(
    folder_path: Union[str, Path], 
    workers: int = 4, 
    force_update: bool = False
) -> Optional[str]:
    """计算画师文件夹的哈希值并返回哈希文件路径
    
    这个函数是为外部模块（如artfilter）提供的便捷接口，
    用于计算画师文件夹的哈希值并直接返回生成的哈希文件路径。
    
    Args:
        folder_path: 画师文件夹路径
        workers: 工作线程数
        force_update: 是否强制更新
        
    Returns:
        Optional[str]: 哈希文件路径，如果处理失败则返回None
    """
    try:
        # 确保folder_path是Path对象
        if isinstance(folder_path, str):
            folder_path = Path(folder_path)
            
        logger.info(f"[#process_log]开始处理画师文件夹: {folder_path}")
        
        # 检查文件夹是否存在
        if not folder_path.exists():
            logger.info("[#process_log]❌ 输入路径不存在")
            return None
            
        # 获取所有图片文件
        image_files = ImgUtils.get_img_files(str(folder_path))
        if not image_files:
            logger.info("[#process_log]❌ 没有找到需要处理的文件")
            return None
            
        # 哈希文件保存在画师目录下，命名为image_hashes.json
        hash_file_path = folder_path / "image_hashes.json"
        
        # 如果文件已存在且不强制更新，则直接返回
        if hash_file_path.exists() and not force_update:
            logger.info(f"[#update_log]✅ 哈希文件已存在: {hash_file_path}")
            return str(hash_file_path)
            
        logger.info(f"[#process_log]计算哈希值，总文件数: {len(image_files)}")
        
        # 计算哈希值
        hash_results = {}
        success_count = 0
        error_count = 0
        
        # 设置多进程环境
        HashCache.configure_multiprocess(
            enable_auto_save=True,
            enable_global_cache=True
        )
        
        # 使用多进程计算哈希值
        from concurrent.futures import ProcessPoolExecutor, as_completed
        
        with ProcessPoolExecutor(max_workers=workers) as executor:
            # 提交所有任务
            future_to_path = {
                executor.submit(_calculate_hash_for_single_image, img_path): img_path 
                for img_path in image_files
            }
            
            # 收集结果
            completed = 0
            total = len(image_files)
            
            for future in as_completed(future_to_path):
                img_path = future_to_path[future]
                try:
                    result = future.result()
                    if result['success']:
                        hash_results[img_path] = {
                            'hash': result['hash'],
                            'width': result.get('width'),
                            'height': result.get('height')
                        }
                        success_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    logger.info(f"[#process_log]❌ 处理文件失败: {img_path}: {e}")
                    error_count += 1
                
                completed += 1
                if completed % 20 == 0 or completed == total:
                    progress = int(completed / total * 100)
                    logger.info(f"[#process_log]哈希计算进度: {completed}/{total} ({progress}%)")
        
        # 保存哈希结果到文件
        output_data = {
            "artist_folder": str(folder_path),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_files": len(image_files),
            "success_count": success_count,
            "error_count": error_count,
            "hashes": hash_results
        }
        
        with open(hash_file_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
            
        # 将哈希文件路径追加到列表文件
        # 将哈希文件路径追加到列表文件
        hash_files_list_path = Path("E:/1BACKUP/ehv/config/hash_files_list.txt")
        hash_files_list_path.parent.mkdir(parents=True, exist_ok=True)
        with open(hash_files_list_path, 'a', encoding='utf-8') as f:
            f.write(f"{str(hash_file_path)}\n")
        logger.info(f"[#update_log]✅ 哈希文件已生成: {hash_file_path}")
        logger.info(f"[#update_log]总文件数: {len(image_files)}, 成功: {success_count}, 失败: {error_count}")
        
        return str(hash_file_path)
        
    except Exception as e:
        logger.info(f"[#process_log]❌ 处理画师文件夹时出错: {e}")
        return None

def _calculate_hash_for_single_image(image_path: str) -> Dict:
    """计算单个图片的哈希值
    
    Args:
        image_path: 图片路径
        
    Returns:
        Dict: 包含哈希结果的字典
    """
    try:
        # 调用哈希计算器
        result = ImageHashCalculator.calculate_phash(image_path)
        
        # 获取图片尺寸
        img_info = ImgUtils.get_image_info(image_path)
        width = img_info.get('width') if img_info else None
        height = img_info.get('height') if img_info else None
        
        return {
            'success': True,
            'hash': result,
            'width': width,
            'height': height
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def process_duplicates_with_hash_file(
    hash_file: str, 
    target_paths: List[str], 
    params: Optional[Dict] = None, 
    worker_count: int = 2
) -> None:
    """使用哈希文件处理重复文件
    
    这个函数是为外部模块（如artfilter）提供的便捷接口，
    用于使用哈希文件处理重复文件。
    
    Args:
        hash_file: 哈希文件路径
        target_paths: 要处理的目标路径列表
        params: 参数字典，包含处理参数
        worker_count: 工作线程数
    """
    # 调用内部函数进行处理
    _process_duplicates(hash_file, target_paths, params, worker_count)

def get_hash_file_path() -> Optional[str]:
    """获取最新的哈希文件路径
    
    这个函数是为外部模块提供的便捷接口，
    用于获取最新的哈希文件路径。
    
    Returns:
        Optional[str]: 最新的哈希文件路径，如果没有则返回None
    """
    return get_latest_hash_file_path() 