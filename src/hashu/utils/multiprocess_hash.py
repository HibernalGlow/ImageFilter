"""
多进程优化的哈希计算模块
专门用于多进程环境下的图片哈希计算，避免全局状态和文件竞争问题
"""

from PIL import Image
import imagehash
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple, Union, List, Optional, Any
import os
import orjson
from loguru import logger
from hashu.utils.path_uri import PathURIGenerator


class MultiProcessHashCalculator:
    """多进程优化的哈希计算器
    
    特点：
    1. 无全局状态依赖
    2. 不自动保存，避免文件竞争
    3. 支持预加载哈希缓存
    4. 优化的批量计算
    """
    
    def __init__(self, hash_cache: Dict[str, str] = None, hash_size: int = 10):
        """初始化多进程哈希计算器
        
        Args:
            hash_cache: 预加载的哈希缓存字典 {uri: hash_value}
            hash_size: 哈希大小，默认10
        """
        self.hash_cache = hash_cache or {}
        self.hash_size = hash_size
    
    @staticmethod
    def create_with_cache(cache_files: List[str] = None, hash_size: int = 10) -> 'MultiProcessHashCalculator':
        """创建带预加载缓存的计算器
        
        Args:
            cache_files: 哈希缓存文件路径列表
            hash_size: 哈希大小
            
        Returns:
            MultiProcessHashCalculator: 预加载缓存的计算器实例
        """
        cache = {}
        if cache_files:
            for file_path in cache_files:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'rb') as f:
                            data = orjson.loads(f.read())
                            hashes = data.get('hashes', data)
                            for uri, hash_data in hashes.items():
                                if isinstance(hash_data, dict):
                                    cache[uri] = hash_data.get('hash', '')
                                else:
                                    cache[uri] = str(hash_data)
                        logger.info(f"已加载缓存文件: {file_path}, 条目数: {len(hashes)}")
                    except Exception as e:
                        logger.warning(f"加载缓存文件失败 {file_path}: {e}")
        
        return MultiProcessHashCalculator(cache, hash_size)
    
    def calculate_hash(self, image_path_or_data: Union[str, Path, bytes, BytesIO, Image.Image], 
                      uri: str = None) -> Optional[str]:
        """计算图片哈希值（多进程安全版本）
        
        Args:
            image_path_or_data: 图片数据（路径、字节、BytesIO或PIL.Image对象）
            uri: 图片的标准化URI，如果为None则根据路径生成
            
        Returns:
            str: 哈希值字符串，失败返回None
        """
        try:
            # 生成或使用提供的URI
            if uri is None and isinstance(image_path_or_data, (str, Path)):
                uri = PathURIGenerator.generate(str(image_path_or_data))
            
            # 检查缓存
            if uri and uri in self.hash_cache:
                logger.debug(f"[MultiProcess]使用缓存哈希: {uri}")
                return self.hash_cache[uri]
            
            # 计算新哈希值
            pil_img = self._load_image(image_path_or_data)
            if pil_img is None:
                return None
            
            try:
                hash_obj = imagehash.phash(pil_img, hash_size=self.hash_size)
                hash_str = str(hash_obj)
                
                # 将结果添加到缓存（仅当前实例，不持久化）
                if uri:
                    self.hash_cache[uri] = hash_str
                
                logger.debug(f"[MultiProcess]计算新哈希: {uri} -> {hash_str}")
                return hash_str
                
            finally:
                # 只在打开新图片时关闭
                if not isinstance(image_path_or_data, Image.Image):
                    pil_img.close()
                    
        except Exception as e:
            logger.error(f"[MultiProcess]计算哈希失败: {e}")
            return None
    
    def _load_image(self, image_data: Union[str, Path, bytes, BytesIO, Image.Image]) -> Optional[Image.Image]:
        """加载图片数据为PIL.Image对象
        
        Args:
            image_data: 各种格式的图片数据
            
        Returns:
            PIL.Image.Image: 加载的图片对象，失败返回None
        """
        try:
            if isinstance(image_data, (str, Path)):
                return Image.open(image_data)
            elif isinstance(image_data, BytesIO):
                return Image.open(image_data)
            elif isinstance(image_data, bytes):
                return Image.open(BytesIO(image_data))
            elif isinstance(image_data, Image.Image):
                return image_data
            elif hasattr(image_data, 'read') and hasattr(image_data, 'seek'):
                # 支持mmap和类文件对象
                try:
                    buffer = BytesIO(image_data)
                    return Image.open(buffer)
                except Exception:
                    # 如果失败，尝试读取内容后再转换
                    position = image_data.tell()
                    image_data.seek(0)
                    content = image_data.read()
                    image_data.seek(position)
                    return Image.open(BytesIO(content))
            else:
                logger.error(f"不支持的图片数据类型: {type(image_data)}")
                return None
        except Exception as e:
            logger.error(f"加载图片数据失败: {e}")
            return None
    
    @staticmethod
    def calculate_hamming_distance(hash1: str, hash2: str) -> int:
        """计算两个哈希值的汉明距离（静态方法，多进程安全）
        
        Args:
            hash1: 第一个哈希值
            hash2: 第二个哈希值
            
        Returns:
            int: 汉明距离，失败返回较大值
        """
        try:
            # 统一转换为小写
            hash1_str = hash1.lower() if isinstance(hash1, str) else str(hash1).lower()
            hash2_str = hash2.lower() if isinstance(hash2, str) else str(hash2).lower()
            
            # 检查长度
            if len(hash1_str) != len(hash2_str):
                logger.warning(f"哈希长度不一致: {len(hash1_str)} vs {len(hash2_str)}")
                return 999
            
            # 转换为整数并计算异或
            hash1_int = int(hash1_str, 16)
            hash2_int = int(hash2_str, 16)
            xor = hash1_int ^ hash2_int
            
            # 计算位数
            if hasattr(int, 'bit_count'):
                return xor.bit_count()
            else:
                # 兼容性实现
                count = 0
                while xor:
                    count += xor & 1
                    xor >>= 1
                return count
                
        except Exception as e:
            logger.error(f"计算汉明距离失败: {e}")
            return 999


def create_multiprocess_hash_worker(cache_files: List[str] = None, 
                                  hash_size: int = 10) -> MultiProcessHashCalculator:
    """创建多进程工作器的哈希计算器
    
    这个函数设计用于多进程环境，在每个工作进程中调用一次来初始化
    
    Args:
        cache_files: 哈希缓存文件路径列表
        hash_size: 哈希大小
        
    Returns:
        MultiProcessHashCalculator: 配置好的计算器实例
    """
    return MultiProcessHashCalculator.create_with_cache(cache_files, hash_size)


# 用于多进程的静态函数
def calculate_hash_static(image_path_or_data: Union[str, Path, bytes], 
                         uri: str = None,
                         hash_size: int = 10,
                         cache_dict: Dict[str, str] = None) -> Optional[Tuple[str, str]]:
    """静态哈希计算函数，专门用于多进程环境
    
    Args:
        image_path_or_data: 图片数据
        uri: 标准化URI
        hash_size: 哈希大小
        cache_dict: 缓存字典
        
    Returns:
        Tuple[str, str]: (uri, hash_value) 或 None
    """
    try:
        # 生成URI
        if uri is None and isinstance(image_path_or_data, (str, Path)):
            uri = PathURIGenerator.generate(str(image_path_or_data))
        
        # 检查缓存
        if cache_dict and uri and uri in cache_dict:
            return uri, cache_dict[uri]
        
        # 计算哈希
        calculator = MultiProcessHashCalculator({}, hash_size)
        hash_value = calculator.calculate_hash(image_path_or_data, uri)
        
        if hash_value:
            return uri, hash_value
        return None
        
    except Exception as e:
        logger.error(f"静态哈希计算失败: {e}")
        return None
