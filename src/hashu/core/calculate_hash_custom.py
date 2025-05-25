"""
图片哈希计算模块
提供多种图片哈希计算方法和相似度比较功能
"""

from PIL import Image
import pillow_avif
import pillow_jxl
import cv2
import numpy as np
from io import BytesIO
from pathlib import Path
import imagehash
from itertools import combinations
from rich.markdown import Markdown
from rich.console import Console
from datetime import datetime
import orjson
import os
from urllib.parse import quote, unquote, urlparse
from dataclasses import dataclass
from typing import Dict, Tuple, Union, List, Optional
import re
from functools import lru_cache
import time
from hashu.utils.path_uri import PathURIGenerator 
from hashu.utils.image_clarity import ImageClarityEvaluator
from loguru import logger
# 导出这些类，使其保持向后兼容
__all__ = [
    'PathURIGenerator',
    'ImageClarityEvaluator',
    'ImageHashCalculator',
    'HashCache',
]

# 多进程同步锁
import threading
_cache_lock = threading.RLock()  # 使用递归锁防止死锁
# 全局配置
GLOBAL_HASH_FILES = [
    os.path.expanduser(r"E:\1EHV\image_hashes_collection.json"),
    os.path.expanduser(r"E:\1EHV\image_hashes_global.json")
]
CACHE_TIMEOUT = 1800  # 缓存超时时间(秒)
HASH_FILES_LIST=os.path.expanduser(r"E:\1EHV\hash_files_list.txt")
# 哈希计算参数
HASH_PARAMS = {
    'hash_size': 10,  # 默认哈希大小
    'hash_version': 1  # 哈希版本号，用于后续兼容性处理
}

# 多进程优化配置
MULTIPROCESS_CONFIG = {
    'enable_auto_save': True,  # 是否启用自动保存（多进程环境下建议关闭）
    'enable_global_cache': True,  # 是否启用全局缓存查询
    'preload_cache': None,  # 预加载的缓存字典，用于多进程环境
}

class HashCache:
    """哈希值缓存管理类（优化多进程支持）"""
    _instance = None
    _cache = {}
    _initialized = False
    _last_refresh = 0
    _last_save = 0  # 新增：记录上次保存时间
    _hash_counter = 0  # 新增：哈希计算计数器

    def __new__(cls):
        """线程安全的单例模式"""
        with _cache_lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance

    @classmethod
    def get_cache(cls, use_preload: bool = False):
        """获取内存中的缓存数据
        
        Args:
            use_preload: 是否使用预加载缓存（多进程环境下推荐）
        """
        with _cache_lock:
            # 多进程环境下优先使用预加载缓存
            if use_preload and MULTIPROCESS_CONFIG.get('preload_cache'):
                return MULTIPROCESS_CONFIG['preload_cache']
                
            current_time = time.time()
              # 如果未初始化或者距离上次刷新超过超时时间，则刷新缓存
            if not cls._initialized or (current_time - cls._last_refresh > CACHE_TIMEOUT):
                cls.refresh_cache()
            return cls._cache.copy()  # 返回副本避免并发修改

    @classmethod
    def refresh_cache(cls):
        """刷新缓存并保持内存驻留（多进程优化版本）"""
        with _cache_lock:
            try:
                new_cache = {}
                loaded_files = []
                
                for hash_file in GLOBAL_HASH_FILES:
                    try:
                        if not os.path.exists(hash_file):
                            logger.debug(f"哈希文件不存在: {hash_file}")
                            continue
                            
                        with open(hash_file, 'rb') as f:
                            data = orjson.loads(f.read())
                            if not data:
                                logger.debug(f"哈希文件为空: {hash_file}")
                                continue
                        
                        # 处理新格式 (image_hashes_collection.json)
                        if "hashes" in data:
                            hashes = data["hashes"]
                            if not hashes:
                                logger.debug(f"哈希数据为空: {hash_file}")
                                continue
                                
                            for uri, hash_data in hashes.items():
                                if isinstance(hash_data, dict):
                                    if hash_str := hash_data.get('hash'):
                                        new_cache[uri] = hash_str
                                else:
                                    new_cache[uri] = str(hash_data)
                        else:
                            # 处理旧格式 (image_hashes_global.json)
                            # 排除特殊键
                            special_keys = {'_hash_params', 'dry_run', 'input_paths'}
                            for k, v in data.items():
                                if k not in special_keys:
                                    if isinstance(v, dict):
                                        if hash_str := v.get('hash'):
                                            new_cache[k] = hash_str
                                    else:
                                        new_cache[k] = str(v)
                                        
                        loaded_files.append(hash_file)
                        logger.debug(f"从 {hash_file} 加载了哈希值")
                                
                    except Exception as e:
                        logger.error(f"加载哈希文件失败 {hash_file}: {e}")
                        continue
                        
                if loaded_files:
                    cls._cache = new_cache  # 直接替换引用保证原子性
                    cls._initialized = True
                    cls._last_refresh = time.time()
                    logger.debug(f"哈希缓存已更新，共 {len(cls._cache)} 个条目，来源: {loaded_files}")
                else:
                    logger.warning("没有成功加载任何哈希文件")
                    if not cls._initialized:
                        cls._cache = {}  # 如果是首次初始化失败，确保有一个空缓存
                        cls._initialized = True
                    
            except Exception as e:
                logger.error(f"刷新哈希缓存失败: {e}")
                if not cls._initialized:
                    cls._cache = {}  # 如果是首次初始化失败，确保有一个空缓存                    cls._initialized = True

    @classmethod
    def sync_to_file(cls, force=False):
        """将内存缓存同步到文件
        
        Args:
            force: 是否强制同步，忽略计时器和计数器
        
        Returns:
            bool: 是否执行了保存操作
        """
        # 多进程环境下如果禁用自动保存，则直接返回
        if not MULTIPROCESS_CONFIG.get('enable_auto_save', True) and not force:
            return False
            
        with _cache_lock:
            current_time = time.time()
            should_save_by_time = (current_time - cls._last_save > 300)  # 5分钟保存一次
            should_save_by_count = (cls._hash_counter >= 10)  # 累积10个新哈希值保存一次
            
            if force or should_save_by_time or should_save_by_count:
                try:
                    logger.info(f"同步哈希缓存到文件, 共{len(cls._cache)}个条目 [计数:{cls._hash_counter}, 间隔:{int(current_time-cls._last_save)}秒]")
                    ImageHashCalculator.save_global_hashes(cls._cache)
                    cls._last_save = current_time
                    cls._hash_counter = 0  # 重置计数器
                    return True
                except Exception as e:
                    logger.error(f"同步缓存到文件失败: {e}")
                    return False
            
            return False

    @classmethod
    def add_hash(cls, uri: str, hash_value: str, auto_sync: bool = True):
        """添加哈希值到缓存
        
        Args:
            uri: 标准化的URI
            hash_value: 哈希值
            auto_sync: 是否自动同步到文件
        """
        with _cache_lock:
            cls._cache[uri] = hash_value
            if auto_sync:
                cls._hash_counter += 1
                cls.sync_to_file()

    @classmethod
    def get_hash(cls, uri: str, use_preload: bool = False) -> Optional[str]:
        """获取指定URI的哈希值
        
        Args:
            uri: 标准化的URI
            use_preload: 是否使用预加载缓存
            
        Returns:
            Optional[str]: 哈希值，未找到返回None
        """
        cache = cls.get_cache(use_preload=use_preload)
        return cache.get(uri)

    @classmethod
    def preload_cache_for_multiprocess(cls, cache_dict: Dict[str, str]) -> None:
        """为多进程环境预加载缓存
        
        Args:
            cache_dict: 预加载的缓存字典
        """
        MULTIPROCESS_CONFIG['preload_cache'] = cache_dict
        logger.info(f"已预加载缓存，共 {len(cache_dict)} 个条目")

    @classmethod
    def configure_multiprocess(cls, enable_auto_save: bool = False, 
                             enable_global_cache: bool = True,
                             preload_cache: Optional[Dict[str, str]] = None) -> None:
        """配置多进程环境
        
        Args:
            enable_auto_save: 是否启用自动保存（多进程下建议关闭）
            enable_global_cache: 是否启用全局缓存查询
            preload_cache: 预加载的缓存字典
        """
        MULTIPROCESS_CONFIG.update({
            'enable_auto_save': enable_auto_save,
            'enable_global_cache': enable_global_cache,
            'preload_cache': preload_cache
        })
        logger.info(f"多进程配置已更新: auto_save={enable_auto_save}, global_cache={enable_global_cache}")

    @classmethod
    def get_cache_stats(cls) -> Dict[str, any]:
        """获取缓存统计信息"""
        with _cache_lock:
            return {
                'cache_size': len(cls._cache),
                'initialized': cls._initialized,
                'last_refresh': cls._last_refresh,
                'last_save': cls._last_save,
                'hash_counter': cls._hash_counter,
                'multiprocess_config': MULTIPROCESS_CONFIG.copy()
            }

class ImgUtils:
    """图片工具类"""
    
    @staticmethod
    def get_img_files(directory):
        """获取目录中的所有图片文件
        
        Args:
            directory: 目录路径
            
        Returns:
            list: 图片文件路径列表
        """
        image_files = []
        image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif', '.bmp', '.gif', '.tiff')
        
        try:
            for root, _, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith(image_extensions):
                        image_files.append(os.path.join(root, file))
        except Exception as e:
            logger.error(f"扫描目录失败 {directory}: {e}")
            return []
                    
        return image_files
    
@dataclass
class ProcessResult:
    """处理结果的数据类"""
    uri: str  # 标准化的URI
    hash_value: dict  # 图片哈希值
    file_type: str  # 文件类型（'image' 或 'archive'）
    original_path: str  # 原始文件路径

class ImageHashCalculator:
    """图片哈希计算类"""
    
    @staticmethod
    def normalize_path(path: str, internal_path: str = None) -> str:
        """标准化路径为URI格式
        
        Args:
            path: 文件路径
            internal_path: 压缩包内部路径（可选）
            
        Returns:
            str: 标准化的URI
        """
        if internal_path:
            return PathURIGenerator.generate(f"{path}!{internal_path}")
        return PathURIGenerator.generate(path)

    @staticmethod
    def get_hash_from_url(url: str) -> Optional[str]:
        """
        根据URL查询全局哈希值
        Args:
            url: 标准化的URI
        Returns:
            str: 哈希值字符串，未找到返回None
        """
        try:
            if not url:
                logger.warning("URL为空")
                return None

            # 标准化URL格式
            normalized_url = PathURIGenerator.generate(url) if '://' not in url else url
            if not normalized_url:
                logger.warning(f"[#update_log]URL标准化失败: {url}")
                return None
            
            # 检查内存缓存
            cached_hashes = HashCache.get_cache()
            if not cached_hashes:
                logger.debug("[#hash_calc]哈希缓存为空")
                return None
                
            if hash_value := cached_hashes.get(normalized_url):
                logger.debug(f"[#hash_calc]从缓存找到哈希值: {normalized_url}")
                return hash_value
                
            # 未命中缓存时主动扫描全局文件
            for hash_file in GLOBAL_HASH_FILES:
                if not os.path.exists(hash_file):
                    logger.debug(f"[#hash_calc]哈希文件不存在: {hash_file}")
                    continue
                    
                try:
                    with open(hash_file, 'rb') as f:
                        data = orjson.loads(f.read())
                        if not data:
                            logger.debug(f"[#hash_calc]哈希文件为空: {hash_file}")
                            continue
                            
                        # 处理新旧格式
                        hashes = data.get('hashes', data) if 'hashes' in data else data
                        if not hashes:
                            logger.debug(f"[#hash_calc]哈希数据为空: {hash_file}")
                            continue
                            
                        if hash_value := hashes.get(normalized_url):
                            if isinstance(hash_value, dict):
                                hash_str = hash_value.get('hash')
                                if hash_str:
                                    logger.debug(f"[#hash_calc]从全局文件找到哈希值: {normalized_url}")
                                    return hash_str
                            else:
                                logger.debug(f"[#hash_calc]从全局文件找到哈希值: {normalized_url}")
                                return str(hash_value)
                except Exception as e:
                    logger.warning(f"[#update_log]读取哈希文件失败 {hash_file}: {e}")
                    continue
            
            logger.debug(f"[#hash_calc]未找到哈希值: {normalized_url}")
            return None
            
        except Exception as e:
            logger.warning(f"[#update_log]查询哈希失败 {url}: {e}")
            return None    @staticmethod
    def calculate_phash(image_path_or_data, hash_size=10, url=None, auto_save=True, use_preload=False):
        """使用感知哈希算法计算图片哈希值
        
        Args:
            image_path_or_data: 可以是图片路径(str/Path)、BytesIO对象、bytes对象或PIL.Image对象
            hash_size: 哈希大小，默认值为10
            url: 图片的URL，用于记录来源。如果为None且image_path_or_data是路径，则使用标准化的URI
            auto_save: 是否自动保存到全局文件（多进程环境下建议关闭）
            use_preload: 是否使用预加载缓存（多进程环境下推荐开启）
            
        Returns:
            dict: 包含哈希值和元数据的字典，失败时返回None
            {
                'hash': str,  # 16进制格式的感知哈希值
                'size': int,  # 哈希大小
                'url': str,   # 标准化的URI
            }
        """
        try:
            # 生成标准化的URI
            if url is None and isinstance(image_path_or_data, (str, Path)):
                path_str = str(image_path_or_data)
                url = PathURIGenerator.generate(path_str)
            
            # 优先从缓存查询（支持多进程预加载缓存）
            if url and MULTIPROCESS_CONFIG.get('enable_global_cache', True):
                if use_preload:
                    cached_hash = HashCache.get_hash(url, use_preload=True)
                else:
                    cached_hash = ImageHashCalculator.get_hash_from_url(url)
                    
                if cached_hash:
                    return {
                        'hash': cached_hash,
                        'size': HASH_PARAMS['hash_size'],
                        'url': url,
                        'from_cache': True
                    }
            
            # 如果缓存中没有，则计算新的哈希值
            # 如果没有提供URL且输入是路径，则生成标准化的URI
            if url is None and isinstance(image_path_or_data, (str, Path)):
                path_str = str(image_path_or_data)
                url = PathURIGenerator.generate(path_str)  # 使用新类生成URI
                logger.debug(f"[#hash_calc]正在计算URI: {url} 的哈希值")
            
            # 根据输入类型选择不同的打开方式
            if isinstance(image_path_or_data, (str, Path)):
                pil_img = Image.open(image_path_or_data)
            elif isinstance(image_path_or_data, BytesIO):
                pil_img = Image.open(image_path_or_data)
            elif isinstance(image_path_or_data, bytes):
                pil_img = Image.open(BytesIO(image_path_or_data))
            elif isinstance(image_path_or_data, Image.Image):
                pil_img = image_path_or_data
            elif hasattr(image_path_or_data, 'read') and hasattr(image_path_or_data, 'seek'):
                # 支持mmap和类文件对象
                try:
                    # 首先尝试直接转换为BytesIO（适用于mmap对象）
                    buffer = BytesIO(image_path_or_data)
                    pil_img = Image.open(buffer)
                except Exception as inner_e:
                    # 如果失败，尝试读取内容后再转换
                    logger.debug(f"[#hash_calc]直接转换失败，尝试读取内容: {inner_e}")
                    try:
                        position = image_path_or_data.tell()  # 保存当前位置
                        image_path_or_data.seek(0)  # 回到开头
                        content = image_path_or_data.read()  # 读取全部内容
                        image_path_or_data.seek(position)  # 恢复位置
                        pil_img = Image.open(BytesIO(content))
                    except Exception as e2:
                        raise ValueError(f"无法从类文件对象读取图片数据: {e2}")
            else:
                raise ValueError(f"不支持的输入类型: {type(image_path_or_data)}")
            
            # 使用imagehash库的phash实现
            hash_obj = imagehash.phash(pil_img, hash_size=hash_size)
            
            # 只在打开新图片时关闭
            if not isinstance(image_path_or_data, Image.Image):
                pil_img.close()
            
            # 转换为十六进制字符串
            hash_str = str(hash_obj)
            
            if not hash_str:
                raise ValueError("生成的哈希值为空")
                
            # 将新结果添加到缓存（支持多进程配置）
            if url and MULTIPROCESS_CONFIG.get('enable_global_cache', True):
                # 在多进程环境下，根据配置决定是否自动保存
                save_enabled = MULTIPROCESS_CONFIG.get('enable_auto_save', True) and auto_save
                HashCache.add_hash(url, hash_str, auto_sync=save_enabled)
                
            logger.debug(f"计算的哈希值: {hash_str}")
            return {
                'hash': hash_str,
                'size': hash_size,
                'url': url,
                'from_cache': False
            }
            
        except Exception as e:
            logger.warning(f"计算失败: {e}")
            return None

    @staticmethod
    def calculate_hamming_distance(hash1, hash2):
        """计算两个哈希值之间的汉明距离
        
        Args:
            hash1: 第一个哈希值（可以是字典格式或字符串格式）
            hash2: 第二个哈希值（可以是字典格式或字符串格式）
            
        Returns:
            int: 汉明距离，如果计算失败则返回float('inf')
        """
        try:
            # 新增代码：统一转换为小写
            hash1_str = hash1['hash'].lower() if isinstance(hash1, dict) else hash1.lower()
            hash2_str = hash2['hash'].lower() if isinstance(hash2, dict) else hash2.lower()
            
            # 确保两个哈希值长度相同
            if len(hash1_str) != len(hash2_str):
                logger.info(f"哈希长度不一致: {len(hash1_str)} vs {len(hash2_str)}")
                return float('inf')
            
            # 将十六进制字符串转换为整数
            hash1_int = int(hash1_str, 16)
            hash2_int = int(hash2_str, 16)
            
            # 计算异或值
            xor = hash1_int ^ hash2_int
            
            # 使用Python 3.10+的bit_count()方法（如果可用）
            if hasattr(int, 'bit_count'):
                distance = xor.bit_count()
            else:
                # 优化的分治法实现
                x = xor
                x = (x & 0x5555555555555555) + ((x >> 1) & 0x5555555555555555)  # 每2位分组
                x = (x & 0x3333333333333333) + ((x >> 2) & 0x3333333333333333)  # 每4位分组
                x = (x & 0x0F0F0F0F0F0F0F0F) + ((x >> 4) & 0x0F0F0F0F0F0F0F0F)  # 每8位分组
                # 由于哈希值不超过64位，可以直接累加高位
                x = (x + (x >> 8)) & 0x00FF00FF00FF00FF  # 累加每个字节
                x = (x + (x >> 16)) & 0x0000FFFF0000FFFF  # 累加每2个字节
                distance = (x + (x >> 32)) & 0x7F  # 最终结果不会超过64
            
            logger.info(f"比较哈希值: {hash1_str} vs {hash2_str}, 汉明距离: {distance}")
            return distance
            
        except Exception as e:
            logger.info(f"计算汉明距离时出错: {e}")
            return float('inf')

    @staticmethod
    def match_existing_hashes(path: Path, existing_hashes: Dict[str, dict], is_global: bool = False) -> Dict[str, ProcessResult]:
        """匹配路径与现有哈希值"""
        results = {}
        # if '去图' in path:
        #     return results
        if not existing_hashes:
            return results
            
        file_path = str(path).replace('\\', '/')
        
        # 统一使用包含匹配
        for uri, hash_value in existing_hashes.items():
            if file_path in uri:
                # 如果是全局哈希，hash_value是字符串；如果是本地哈希，hash_value是字典
                if isinstance(hash_value, str):
                    hash_str = hash_value
                else:
                    hash_str = hash_value.get('hash', '')
                    
                file_type = 'archive' if '!' in uri else 'image'
                results[uri] = ProcessResult(
                    uri=uri,
                    hash_value={'hash': hash_str, 'size': HASH_PARAMS['hash_size'], 'url': uri},
                    file_type=file_type,
                    original_path=file_path
                )
                # 根据来源显示不同的日志
                log_prefix = "[🌍全局缓存]" if is_global else "[📁本地缓存]"
                logger.info(f"[#hash_calc]{log_prefix} {file_type}: {file_path}  哈希值: {hash_str}")
        
        if results:
            logger.info(f"[#hash_calc]✅ 使用现有哈希文件的结果，跳过处理")
            logger.info(f"[#current_progress]处理进度: [已完成] 使用现有哈希")
            
        return results



    @staticmethod
    def are_images_similar(hash1_str, hash2_str, threshold=2):
        """判断两个图片是否相似
        
        Args:
            hash1_str: 第一个图片的哈希值
            hash2_str: 第二个图片的哈希值
            threshold: 汉明距离阈值，小于等于此值认为相似
            
        Returns:
            bool: 是否相似
        """
        distance = ImageHashCalculator.calculate_hamming_distance(hash1_str, hash2_str)
        return distance <= threshold 

    @staticmethod
    def compare_folder_images(folder_path, hash_type='phash', threshold=2, output_html=None):
        """改进版：增加尺寸和清晰度对比"""
        console = Console()
        folder = Path(folder_path)
        image_exts = ('*.jpg', '*.jpeg', '*.png', '*.avif', '*.jxl', '*.webp', '*.JPG', '*.JPEG')
        image_files = [f for ext in image_exts for f in folder.glob(f'**/{ext}')]
        
        results = []
        # 新增：预计算所有图片的元数据
        meta_data = {}
        for img in image_files:
            width, height = ImageClarityEvaluator.get_image_size(img)
            meta_data[str(img)] = {
                'width': width,
                'height': height,
                'clarity': 0.0  # 稍后填充
            }
        
        # 批量计算清晰度
        clarity_scores = ImageClarityEvaluator.batch_evaluate(image_files)
        for path, score in clarity_scores.items():
            meta_data[path]['clarity'] = score
        
        for img1, img2 in combinations(image_files, 2):
            try:
                hash1 = getattr(ImageHashCalculator, f'calculate_{hash_type}')(img1)
                hash2 = getattr(ImageHashCalculator, f'calculate_{hash_type}')(img2)
                distance = ImageHashCalculator.calculate_hamming_distance(hash1, hash2)
                is_similar = distance <= threshold
                
                results.append({
                    'pair': (img1, img2),
                    'distance': distance,
                    'similar': is_similar
                })
            except Exception as e:
                logger.warning(f"对比 {img1} 和 {img2} 失败: {e}")
        
        # 生成HTML报告
        html_content = [
            '<!DOCTYPE html>',
            '<html><head>',
            '<meta charset="UTF-8">',
            '<title>图片相似度对比报告</title>',
            '<style>',
            '  table {border-collapse: collapse; width: 100%; margin: 20px 0;}',
            '  th, td {border: 1px solid #ddd; padding: 12px; text-align: center;}',
            '  img {max-width: 200px; height: auto; transition: transform 0.3s;}',
            '  img:hover {transform: scale(1.5); cursor: zoom-in;}',
            '  .similar {color: #28a745;}',
            '  .different {color: #dc3545;}',
            '  body {font-family: Arial, sans-serif; margin: 30px;}',
            '</style></head><body>',
            '<h1>图片相似度对比报告</h1>',
            f'<p><strong>对比时间</strong>：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>',
            f'<p><strong>哈希算法</strong>：{hash_type.upper()}</p>',
            f'<p><strong>相似阈值</strong>：{threshold}</p>',
            '<table>',
            '  <tr><th>图片1</th><th>图片2</th><th>尺寸</th><th>清晰度</th><th>汉明距离</th><th>相似判定</th></tr>'
        ]

        for res in results:
            status_class = 'similar' if res['similar'] else 'different'
            status_icon = '✅' if res['similar'] else '❌'
            img1_path = str(res['pair'][0].resolve()).replace('\\', '/')
            img2_path = str(res['pair'][1].resolve()).replace('\\', '/')
            img1_meta = meta_data[str(res['pair'][0])]
            img2_meta = meta_data[str(res['pair'][1])]
            
            html_content.append(
                f'<tr>'
                f'<td><img src="file:///{img1_path}" alt="{img1_path}"><br>{img1_meta["width"]}x{img1_meta["height"]}</td>'
                f'<td><img src="file:///{img2_path}" alt="{img2_path}"><br>{img2_meta["width"]}x{img2_meta["height"]}</td>'
                f'<td>{img1_meta["width"]}x{img1_meta["height"]} vs<br>{img2_meta["width"]}x{img2_meta["height"]}</td>'
                f'<td>{img1_meta["clarity"]:.1f} vs {img2_meta["clarity"]:.1f}</td>'
                f'<td>{res["distance"]}</td>'
                f'<td class="{status_class}">{status_icon} {"相似" if res["similar"] else "不相似"}</td>'
                f'</tr>'
            )
            
        html_content.extend(['</table></body></html>'])
        
        # 控制台简化输出
        console.print(f"完成对比，共处理 {len(results)} 组图片对")
        
        if output_html:
            output_path = Path(output_html)
            output_path.write_text('\n'.join(html_content), encoding='utf-8')
            console.print(f"HTML报告已保存至：[bold green]{output_path.resolve()}[/]")
            console.print("提示：在浏览器中打开文件可查看交互式图片缩放效果")

    @staticmethod
    def save_global_hashes(hash_dict: Dict[str, str]) -> None:
        """保存哈希值到全局缓存文件（性能优化版）"""
        try:
            output_dict = {
                "_hash_params": f"hash_size={HASH_PARAMS['hash_size']};hash_version={HASH_PARAMS['hash_version']}",
                "hashes": hash_dict  # 直接存储字符串字典，跳过中间转换
            }
            
            os.makedirs(os.path.dirname(GLOBAL_HASH_FILES[-1]), exist_ok=True)
            with open(GLOBAL_HASH_FILES[-1], 'wb') as f:
                # 使用orjson的OPT_SERIALIZE_NUMPY选项提升数值处理性能
                f.write(orjson.dumps(output_dict, 
                    option=orjson.OPT_INDENT_2 | 
                    orjson.OPT_SERIALIZE_NUMPY |
                    orjson.OPT_APPEND_NEWLINE))
            logger.debug(f"已保存哈希缓存到: {GLOBAL_HASH_FILES[-1]}")  # 改为debug级别减少日志量
        except Exception as e:
            logger.warning(f"保存全局哈希缓存失败: {e}", exc_info=True)

    @staticmethod
    def load_global_hashes() -> Dict[str, str]:
        """从全局缓存文件加载所有哈希值（性能优化版）"""
        try:
            if os.path.exists(GLOBAL_HASH_FILES[-1]):
                with open(GLOBAL_HASH_FILES[-1], 'rb') as f:
                    data = orjson.loads(f.read())
                    return {
                        uri: entry["hash"] if isinstance(entry, dict) else entry
                        for uri, entry in data.get("hashes", {}).items()
                    }
            return {}
        except Exception as e:
            logger.warning(f"加载全局哈希缓存失败: {e}", exc_info=True)
            return {}

    @staticmethod
    def save_hash_file_path(file_path: str) -> None:
        """将哈希文件路径保存到路径集合文件中
        
        Args:
            file_path: 要保存的哈希文件路径
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(HASH_FILES_LIST), exist_ok=True)
            # 追加模式写入路径
            with open(HASH_FILES_LIST, 'a', encoding='utf-8') as f:
                f.write(f"{file_path}\n")
            logger.info(f"已将哈希文件路径保存到集合文件: {HASH_FILES_LIST}")
        except Exception as e:
            logger.error(f"保存哈希文件路径失败: {e}")

    @staticmethod
    def get_latest_hash_file_path() -> Optional[str]:
        """获取最新的哈希文件路径
        
        Returns:
            Optional[str]: 最新的哈希文件路径，如果没有则返回None
        """
        try:
            if not os.path.exists(HASH_FILES_LIST):
                return None
                
            with open(HASH_FILES_LIST, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            if not lines:
                return None
                
            # 获取最后一行并去除空白字符
            latest_path = lines[-1].strip()
            
            # 检查文件是否存在
            if os.path.exists(latest_path):
                return latest_path
            else:
                logger.error(f"最新的哈希文件不存在: {latest_path}")
                return None
                
        except Exception as e:
            logger.error(f"获取最新哈希文件路径失败: {e}")
            return None

    @staticmethod
    def load_existing_hashes(directory: Path) -> Dict[str, str]:
        """最终修复版哈希加载"""
        existing_hashes = {}
        try:
            hash_file = directory / 'image_hashes.json'
            if not hash_file.exists():
                return existing_hashes
            
            with open(hash_file, 'rb') as f:
                data = orjson.loads(f.read())
                
                if 'results' in data:
                    results = data['results']
                    for uri, result in results.items():
                        # 修复字段映射问题
                        if isinstance(result, dict):
                            # 统一使用hash字段
                            hash_str = str(result.get('hash', ''))
                            # 添加类型验证
                            if len(hash_str) >= 8:  # 调整为更宽松的长度验证
                                existing_hashes[uri] = {
                                    'hash': hash_str.lower(),
                                    'size': HASH_PARAMS['hash_size'],
                                    'url': uri
                                }
                                continue
                        logger.warning(f"无效的哈希条目: {uri} - {result}")
                
                logger.info(f"从 {hash_file} 加载到有效条目: {len(existing_hashes)}")
                return existing_hashes
            
        except Exception as e:
            logger.error(f"加载哈希文件失败: {str(e)}", exc_info=True)
            return {}

    @staticmethod
    def save_hash_results(results: Dict[str, ProcessResult], output_path: Path, dry_run: bool = False) -> None:
        """保存哈希结果到文件"""
        try:
            output = {
                "_hash_params": f"hash_size={HASH_PARAMS['hash_size']};hash_version={HASH_PARAMS['hash_version']}",
                "dry_run": dry_run,
                "hashes": {uri: {"hash": result.hash_value['hash']} for uri, result in results.items()}  # 与全局结构一致
            }
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(orjson.dumps(output, option=orjson.OPT_INDENT_2))
            logger.info(f"结果已保存到: {output_path} (共 {len(output['hashes'])} 个哈希值)")
            
            ImageHashCalculator.save_hash_file_path(str(output_path))
            
        except Exception as e:
            logger.error(f"保存哈希结果失败: {e}") 


    @staticmethod
    def load_hashes(file_path: Path) -> Tuple[Dict[str, str], dict]:
        """加载哈希文件（仅处理新结构）"""
        try:
            with open(file_path, 'rb') as f:
                data = orjson.loads(f.read())
                hash_params = ImageHashCalculator.parse_hash_params(data.get('_hash_params', ''))
                return {
                    k: v['hash']  # 新结构强制要求hash字段
                    for k, v in data.get('hashes', {}).items()
                }, hash_params
        except Exception as e:
            logger.debug(f"尝试新结构加载失败，回退旧结构: {e}")
            return LegacyHashLoader.load(file_path)  # 分离的旧结构加载

    @staticmethod
    def migrate_hashes(file_path: Path) -> None:
        """迁移旧哈希文件到新格式"""
        hashes, params = ImageHashCalculator.load_hashes(file_path)
        if hashes:
            ImageHashCalculator.save_hash_results(
                results={uri: ProcessResult(h, None, None) for uri, h in hashes.items()},
                output_path=file_path,
                dry_run=False
            )
            logger.info(f"已迁移哈希文件格式: {file_path}")

    @staticmethod
    def test_hash_cache():
        """缓存功能测试demo"""
        console = Console()
        test_file = r"E:\2EHV\test\0.jpg"  # 替换为实际测试文件路径
        url=ImageHashCalculator.normalize_path(test_file)
        # 第一次计算（应加载缓存）
        console.print("\n[bold cyan]=== 第一次计算（加载缓存）===[/]")
        start_time = time.time()
        hash1 = ImageHashCalculator.calculate_phash(test_file)
        load_hashes=ImageHashCalculator.load_hashes(test_file)
        console.print(f"耗时: {time.time()-start_time:.2f}s")
        
        # 第二次计算（应使用缓存）
        console.print("\n[bold cyan]=== 第二次计算（使用缓存）===[/]")
        start_time = time.time()
        hash2 = ImageHashCalculator.calculate_phash(test_file)
        console.print(f"耗时: {time.time()-start_time:.2f}s")
        
        # 验证结果
        console.print("\n[bold]测试结果:[/]")
        console.print(f"哈希值是否一致: {hash1['hash'] == hash2['hash']}")
        console.print(f"是否来自缓存: {hash1.get('from_cache', False)} | {hash2.get('from_cache', False)}")

class LegacyHashLoader:
    """旧结构哈希文件加载器（后期可整体移除）"""
    
    @staticmethod
    def load(file_path: Path) -> Tuple[Dict[str, str], dict]:
        """加载旧版哈希文件结构"""
        try:
            with open(file_path, 'rb') as f:
                data = orjson.loads(f.read())
                return LegacyHashLoader._parse_old_structure(data)
        except:
            return {}, {}
    @staticmethod
    def parse_hash_params(param_str: str) -> dict:
        """解析哈希参数字符串"""
        params = {
            'hash_size': HASH_PARAMS['hash_size'],
            'hash_version': HASH_PARAMS['hash_version']
        }
        for pair in param_str.split(';'):
            if '=' in pair:
                key, val = pair.split('=', 1)
                if key in params:
                    params[key] = int(val)
        return params
    @staticmethod
    def _parse_old_structure(data: dict) -> Tuple[Dict[str, str], dict]:
        """解析不同旧版结构"""
        hash_params = ImageHashCalculator.parse_hash_params(data.get('_hash_params', ''))
        
        # 版本1: 包含results的结构
        if 'results' in data:
            return {
                uri: item.get('hash') or uri.split('[hash-')[1].split(']')[0]
                for uri, item in data['results'].items()
            }, hash_params
            
        # 版本2: 包含files的结构
        if 'files' in data:
            return {
                k: v if isinstance(v, str) else v.get('hash', '')
                for k, v in data['files'].items()
            }, hash_params
            
        # 版本3: 最旧全局文件结构
        return {
            k: v['hash'] if isinstance(v, dict) else v
            for k, v in data.items()
            if k not in ['_hash_params', 'dry_run', 'input_paths']
        }, hash_params 
        

if __name__ == "__main__":
    # 执行缓存测试
    ImageHashCalculator.test_hash_cache()
    # 原有清晰度测试保持不变
    def test_image_clarity():
        """清晰度评估测试demo"""
        test_dir = Path(r"E:\2EHV\test")
        console = Console()
        
        # 获取所有图片文件
        image_files = list(test_dir.glob("*.jpg")) + list(test_dir.glob("*.png"))
        console.print(f"找到 {len(image_files)} 张测试图片")
        
        # 计算清晰度并排序
        results = []
        for img_path in image_files[:1300]:  # 限制前1300张
            score = ImageClarityEvaluator.calculate_definition(img_path)
            results.append((img_path.name, score))
        
        # 按清晰度降序排序
        sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
        
        # 输出结果
        console.print(Markdown("## 图像清晰度排名"))
        console.print("| 排名 | 文件名 | 清晰度得分 |")
        console.print("|------|--------|------------|")
        for idx, (name, score) in enumerate(sorted_results[:20], 1):
            console.print(f"| {idx:2d} | {name} | {score:.2f} |")
            
    # 执行测试
    # test_image_clarity()

