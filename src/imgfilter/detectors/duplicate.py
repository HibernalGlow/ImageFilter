import os
import logging
from typing import List, Dict, Tuple, Set, Union, Optional
import json
from PIL import Image
import pillow_avif
import pillow_jxl 
from io import BytesIO
import multiprocessing
import mmap  # 添加 mmap 导入
import tempfile
import shutil
import numpy as np
import ctypes
from regex import F
from hashu.core.calculate_hash_custom import ImageHashCalculator, PathURIGenerator
from hashu.utils.hash_accelerator import HashAccelerator
from concurrent.futures import ProcessPoolExecutor, as_completed  # 改为 ProcessPoolExecutor
from loguru import logger
from datetime import datetime

# 导入从 lpips.py 和 cluster.py 移动的函数
from imgfilter.detectors.dup.lpips import calculate_lpips_worker, find_similar_images_by_lpips_legacy, cudain
from imgfilter.detectors.dup.cluster import lpips_clustering_cpu, lpips_clustering_gpu

# 导入从duplicate.py提取到utils.py的函数
from imgfilter.detectors.utils import (
    calculate_hash_worker, 
    get_image_hash_static, 
    get_image_data,
    group_images_by_hash,
    compare_hash_with_reference,
    find_similar_images_by_phash_lpips_cluster
)

# 导入group filter功能
from imgfilter.detectors.group.group_filter import process_group_with_filters

# 设置基础环境变量
os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"
# LPIPS_USE_GPU 环境变量将在实例化时根据 use_gpu 参数设置

def _calculate_hash_worker(img_path: str, archive_path: str = None, temp_dir: str = None, 
                          image_archive_map: Dict[str, Union[str, Dict]] = None) -> Tuple[str, Optional[Tuple[str, str]]]:
    """
    多进程工作函数：为单张图片计算哈希值
    
    Args:
        img_path: 图片文件路径
        archive_path: 原始压缩包路径
        temp_dir: 临时解压目录
        image_archive_map: 图片到压缩包内信息的映射
        
    Returns:
        Tuple[str, Optional[Tuple[str, str]]]: (图片路径, (URI, 哈希值)) 或 (图片路径, None)
    """
    try:
        # 从映射中获取压缩包信息，如果不存在则尝试从路径推导
        zip_path = None
        internal_path = None
        
        if image_archive_map and img_path in image_archive_map:
            # 检查映射中的数据类型
            map_data = image_archive_map[img_path]
            if isinstance(map_data, dict):
                # 新格式：直接从字典中获取路径信息
                zip_path = map_data.get('zip_path')
                internal_path = map_data.get('internal_path')
                # 如果字典中有哈希值，可以直接使用
                if 'hash' in map_data and map_data['hash']:
                    uri = map_data.get('archive_uri') or PathURIGenerator.generate(f"{zip_path}!{internal_path}")
                    return img_path, (uri, map_data['hash'])
        elif temp_dir and archive_path and os.path.exists(img_path):
            # 计算相对于临时目录的路径
            if img_path.startswith(temp_dir):
                internal_path = os.path.relpath(img_path, temp_dir)
                internal_path = internal_path.replace('\\', '/')
                zip_path = archive_path
        elif '!' in img_path:
            # 处理压缩包内的图片路径
            # 检查是否是压缩包路径
            archive_extensions = ['.zip!','.cbz!','.cbr!', '.rar!', '.7z!', '.tar!']
            is_archive = any(ext in img_path for ext in archive_extensions)
            
            if is_archive:
                # 找到最后一个压缩文件扩展名的位置
                positions = [img_path.find(ext) for ext in archive_extensions if ext in img_path]
                split_pos = max([pos + len(ext) - 1 for pos, ext in zip(positions, [ext for ext in archive_extensions if ext in img_path])])
                
                # 分割压缩包路径和内部路径
                zip_path = img_path[:split_pos]
                internal_path = img_path[split_pos+1:]
        
        # 调用静态版本的哈希计算函数
        result = _get_image_hash_static(img_path, internal_path, zip_path)
        if result:
            return img_path, result
        return img_path, None
    except Exception as e:
        logger.error(f"[#hash_calc]计算哈希值失败 {img_path}: {e}")
        return img_path, None


def _get_image_hash_static(image_path: str, internal_path: str = None, zip_path: str = None) -> Optional[Tuple[str, str]]:
    """
    静态版本的哈希计算函数，用于多进程
    
    Args:
        image_path: 图片文件路径
        internal_path: 压缩包内的相对路径（可选）
        zip_path: 压缩包路径（可选）
        
    Returns:
        Optional[Tuple[str, str]]: (uri, hash_value) 或 None
    """
    try:
        # 检查路径
        if not image_path:
            logger.error("[#hash_calc]图片路径为空")
            return None

        # 生成标准URI
        uri = None
        if zip_path and internal_path:
            uri = PathURIGenerator.generate(f"{zip_path}!{internal_path}")
        else:
            # 检查是否是压缩包中的图片
            if '!' in image_path:
                # 检查是否是压缩包路径
                archive_extensions = ['.zip!','.cbz!','.cbr!', '.rar!', '.7z!', '.tar!']
                is_archive = any(ext in image_path for ext in archive_extensions)
                
                if is_archive:
                    # 找到最后一个压缩文件扩展名的位置
                    positions = [image_path.find(ext) for ext in archive_extensions if ext in image_path]
                    split_pos = max([pos + len(ext) - 1 for pos, ext in zip(positions, [ext for ext in archive_extensions if ext in image_path])])
                    
                    # 分割压缩包路径和内部路径
                    zip_path = image_path[:split_pos]
                    internal_path = image_path[split_pos+1:]
                if not os.path.exists(zip_path):
                    return None
                uri = PathURIGenerator.generate(f"{zip_path}!{internal_path}")
            elif not os.path.exists(image_path):
                logger.error(f"[#hash_calc]图片路径不存在: {image_path}")
                return None
            else:
                uri = PathURIGenerator.generate(image_path)

        if not uri:
            logger.error(f"[#hash_calc]生成图片URI失败: {image_path}")
            return None

        # 查询全局缓存
        from hashu.core.calculate_hash_custom import ImageHashCalculator
        cached_hash = ImageHashCalculator.get_hash_from_url(uri)
        if cached_hash:
            logger.info(f"[#hash_calc]使用缓存的哈希值: {uri}")
            return uri, cached_hash

        # 直接读取图片数据（多进程环境下不能使用mmap缓存）
        img_data = None
        try:
            if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                with open(image_path, 'rb') as f:
                    img_data = f.read()
            else:
                logger.error(f"[#hash_calc]图片不存在或为空: {image_path}")
                return None
        except Exception as e:
            logger.error(f"[#hash_calc]读取图片数据失败 {image_path}: {e}")
            return None

        if not img_data:
            logger.error(f"[#hash_calc]获取图片数据失败: {image_path}")
            return None

        # 计算哈希值
        hash_result = ImageHashCalculator.calculate_phash(img_data, url=uri)

        if not hash_result:
            logger.error(f"[#hash_calc]计算图片哈希失败: {image_path}")
            return None

        hash_value = hash_result.get('hash') if isinstance(hash_result, dict) else hash_result
        if not hash_value:
            logger.error(f"[#hash_calc]获取哈希值失败: {image_path}")
            return None

        return uri, hash_value

    except Exception as e:
        logger.error(f"[#hash_calc]获取图片哈希异常 {image_path}: {str(e)}")
        return None


class DuplicateImageDetector:
    """重复图片检测器，支持多种检测策略"""
    
    def __init__(self, hash_file: str = None, hamming_threshold: int = 16, 
                 ref_hamming_threshold: int = None, max_workers: int = None,
                 lpips_threshold: float = 0.02, lpips_max_workers: int = 16, 
                 use_gpu: bool = False):  # 添加use_gpu参数
        """
        初始化重复图片检测器
        
        Args:
            hash_file: 哈希文件路径，用于哈希模式
            hamming_threshold: 汉明距离阈值，用于相似图片组检测
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值，默认使用hamming_threshold
            max_workers: 最大工作进程数，默认为CPU核心数*2
            lpips_threshold: LPIPS距离阈值，用于LPIPS模式下相似图片检测
            lpips_max_workers: LPIPS计算专用的最大工作进程数，默认为16
            use_gpu: 是否使用GPU进行LPIPS计算，默认为False
        """
        self.hash_file = hash_file
        self.hamming_threshold = hamming_threshold
        self.ref_hamming_threshold = ref_hamming_threshold if ref_hamming_threshold is not None else hamming_threshold
        self.max_workers = max_workers or multiprocessing.cpu_count()*2
        self.lpips_max_workers = min(16 if lpips_max_workers is None else lpips_max_workers, self.max_workers)  # 确保不超过总的max_workers
        self.hash_cache = {}
        self.mmap_cache = {}  # 添加mmap缓存
        self.lpips_threshold = lpips_threshold  # 添加LPIPS阈值
        self.use_gpu = use_gpu  # 是否使用GPU
        
        # 初始化GPU环境（如果启用）
        if self.use_gpu:
            logger.info("初始化GPU环境用于LPIPS计算")
            cudain()
            os.environ['LPIPS_USE_GPU'] = '1'
        else:
            os.environ['LPIPS_USE_GPU'] = '0'
            
        if hash_file:
            self.hash_cache = self._load_hash_file()    
    def _cleanup_mmap_cache(self):
        """清理mmap缓存"""
        for path, (mm, f) in self.mmap_cache.items():
            try:
                if mm:
                    mm.close()
                if f:
                    f.close()
            except Exception as e:
                logger.error(f"[#hash_calc]清理mmap缓存失败 {path}: {e}")
        self.mmap_cache = {}
            
    def detect_duplicates(self, 
                         image_files: List[str],
                         archive_path: str = None, 
                         temp_dir: str = None,
                         image_archive_map: Dict[str, Union[str, Dict]] = None,
                         mode: str = 'quality', 
                         watermark_keywords: List[str] = None,
                         ref_hamming_threshold: int = None,
                         lpips_max_workers: int = None,  # LPIPS计算专用的最大工作进程数
                         use_legacy_lpips: bool = False,  # 是否使用传统LPIPS计算方法
                         use_gpu: bool = None,  # 运行时GPU模式切换
                         lpips_threshold: float = None,  # 运行时LPIPS阈值设置
                         *args, **kwargs) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        检测重复图片
        
        Args:
            image_files: 图片文件列表
            archive_path: 原始压缩包路径
            temp_dir: 临时解压目录
            image_archive_map: 图片到压缩包内URI的映射
            mode: 重复过滤模式 ('quality', 'watermark', 'hash', 'lpips')
            watermark_keywords: 水印关键词列表，用于watermark模式
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值
            lpips_max_workers: LPIPS计算专用的最大工作进程数
            use_legacy_lpips: 是否使用传统的LPIPS计算方法而非聚类方法（默认False，使用聚类）
            use_gpu: 是否使用GPU（覆盖初始化设置）
            lpips_threshold: LPIPS距离阈值（覆盖初始化设置）
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        if not image_files:
            return set(), {}
        
        # 处理动态GPU设置
        current_use_gpu = self.use_gpu
        if use_gpu is not None:
            current_use_gpu = use_gpu
            logger.info(f"运行时GPU模式设置: {'启用' if current_use_gpu else '禁用'}")
            # 根据运行时设置更新环境变量
            if current_use_gpu:
                cudain()
                os.environ['LPIPS_USE_GPU'] = '1'
            else:
                os.environ['LPIPS_USE_GPU'] = '0'
        
        # 处理动态LPIPS阈值设置
        current_lpips_threshold = self.lpips_threshold
        if lpips_threshold is not None:
            current_lpips_threshold = lpips_threshold
            logger.info(f"运行时LPIPS阈值设置: {current_lpips_threshold}")
        
        # 如果提供了lpips_max_workers参数，更新实例变量
        if lpips_max_workers is not None:
            self.lpips_max_workers = min(lpips_max_workers, self.max_workers)
            logger.info(f"更新LPIPS计算进程数为: {self.lpips_max_workers}")
        
        # 先清理之前可能的缓存
        self._cleanup_mmap_cache()
        
        # 预加载所有图片到mmap缓存
        self._preload_images_to_mmap(image_files)
        
        try:
            duplicate_results = set()
            duplicate_reasons = {}
            
            # 使用哈希文件模式
            if mode == 'hash':
                # 尝试从kwargs获取hash_file
                hash_file_from_kwargs = kwargs.get('hash_file')
                if hash_file_from_kwargs:
                    self.hash_file = hash_file_from_kwargs
                    # 如果之前没有加载，加载哈希文件数据
                    self.hash_cache = self._load_hash_file()
                
                if self.hash_cache:
                    return self._process_hash_images(image_files, archive_path, temp_dir, image_archive_map, ref_hamming_threshold)
                else:
                    logger.warning("[#hash_calc]已选择Hash模式但未提供有效的哈希文件")
            
            # LPIPS模式
            if mode == 'lpips':
                # 根据参数选择LPIPS实现方法
                if use_legacy_lpips:
                    logger.info(f"使用传统LPIPS方法进行相似图片检测（基于距离计算），阈值: {current_lpips_threshold}")
                    # 使用从lpips.py导入的函数
                    similar_groups = find_similar_images_by_lpips_legacy(
                        image_files, 
                        lpips_threshold=current_lpips_threshold,  # 使用动态设置的阈值
                        use_gpu=current_use_gpu, 
                        lpips_max_workers=self.lpips_max_workers
                    )
                else:
                    logger.info(f"使用两阶段哈希+LPIPS聚类方法进行相似图片检测，阈值: {current_lpips_threshold}")
                    # 使用两阶段方法
                    similar_groups = self._find_similar_images_by_phash_lpips_cluster(
                        image_files, 
                        archive_path, 
                        temp_dir, 
                        image_archive_map, 
                        current_use_gpu, 
                        current_lpips_threshold
                    )
            else:
                # 其他模式使用哈希方法查找相似图片组
                similar_groups = self._find_similar_images(image_files, archive_path, temp_dir, image_archive_map)
            
            # 对每个相似组应用过滤策略
            for group in similar_groups:
                if len(group) > 1:
                    if mode == 'watermark':
                        group_results, group_reasons = self._process_watermark_images(group, watermark_keywords)
                    elif mode == 'lpips':
                        # 使用quality过滤策略（基于文件大小）处理LPIPS相似组
                        group_results, group_reasons = self._process_lpips_images(group)
                    else:  # 默认使用quality模式
                        group_results, group_reasons = self._process_quality_images(group)
                        
                    duplicate_results.update(group_results)
                    duplicate_reasons.update(group_reasons)
            
            return duplicate_results, duplicate_reasons
        finally:
            # 清理mmap缓存
            self._cleanup_mmap_cache()
    
    def _preload_images_to_mmap(self, image_files: List[str]):
        """
        预加载所有图片文件到mmap缓存
        
        Args:
            image_files: 图片文件列表
        """
        logger.info(f"预加载 {len(image_files)} 张图片到内存映射...")
        
        for img_path in image_files:
            try:
                # 检查是否为压缩包内文件
                if '!' in img_path:
                    # 压缩包内文件不用预加载，会通过其他方式读取
                    continue
                
                # 检查文件是否存在且可读
                if not os.path.exists(img_path) or not os.path.isfile(img_path):
                    logger.warning(f"[#hash_calc]跳过不存在或非文件: {img_path}")
                    continue
                
                file_size = os.path.getsize(img_path)
                if file_size == 0:
                    logger.warning(f"[#hash_calc]跳过空文件: {img_path}")
                    continue
                
                # 打开文件并创建内存映射
                f = open(img_path, 'rb')
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                self.mmap_cache[img_path] = (mm, f)
                
            except Exception as e:
                logger.error(f"[#hash_calc]预加载图片失败 {img_path}: {e}")
                # 如果失败，确保任何已打开的资源被关闭
                if img_path in self.mmap_cache:
                    mm, f = self.mmap_cache.pop(img_path)
                    if mm:
                        try: mm.close()
                        except: pass
                    if f:
                        try: f.close()
                        except: pass
    
    def _get_image_data(self, image_path: str) -> Optional[Union[mmap.mmap, bytes]]:
        """
        从mmap缓存或文件中获取图片数据
        
        Args:
            image_path: 图片路径
            
        Returns:
            图片数据(mmap或字节)或None
        """
        # 检查是否在mmap缓存中
        if image_path in self.mmap_cache:
            mm, _ = self.mmap_cache[image_path]
            # 将文件指针重置到开头
            mm.seek(0)
            return mm
        
        # 如果不在缓存中，尝试读取文件
        try:
            if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                with open(image_path, 'rb') as f:
                    return f.read()
            else:
                logger.error(f"[#hash_calc]图片不存在或为空: {image_path}")
                return None
        except Exception as e:
            logger.error(f"[#hash_calc]读取图片数据失败 {image_path}: {e}")
            return None
    def _calculate_hash_for_single_image(self, img: str, archive_path: str = None, temp_dir: str = None, 
                                     image_archive_map: Dict[str, Union[str, Dict]] = None) -> Tuple[str, Tuple[str, str]]:
        """
        为单张图片计算哈希值(类方法版本)
        
        Args:
            img: 图片文件路径
            archive_path: 原始压缩包路径
            temp_dir: 临时解压目录
            image_archive_map: 图片到压缩包内信息的映射
            
        Returns:
            Tuple[str, Tuple[str, str]]: (图片路径, (URI, 哈希值)) 或 (图片路径, None)
        """
        try:
            # 从映射中获取压缩包信息，如果不存在则尝试从路径推导
            zip_path = None
            internal_path = None
            
            if image_archive_map and img in image_archive_map:
                # 检查映射中的数据类型
                map_data = image_archive_map[img]
                if isinstance(map_data, dict):
                    # 新格式：直接从字典中获取路径信息
                    zip_path = map_data.get('zip_path')
                    internal_path = map_data.get('internal_path')
                    # 如果字典中有哈希值，可以直接使用
                    if 'hash' in map_data and map_data['hash']:
                        uri = map_data.get('archive_uri') or PathURIGenerator.generate(f"{zip_path}!{internal_path}")
                        return img, (uri, map_data['hash'])
            elif temp_dir and archive_path and os.path.exists(img):
                # 计算相对于临时目录的路径
                if img.startswith(temp_dir):
                    internal_path = os.path.relpath(img, temp_dir)
                    internal_path = internal_path.replace('\\', '/')
                    zip_path = archive_path
            elif '!' in img:
                # 处理压缩包内的图片路径
                # 检查是否是压缩包路径
                archive_extensions = ['.zip!','.cbz!','.cbr!', '.rar!', '.7z!', '.tar!']
                is_archive = any(ext in img for ext in archive_extensions)
                
                if is_archive:
                    # 找到最后一个压缩文件扩展名的位置
                    positions = [img.find(ext) for ext in archive_extensions if ext in img]
                    split_pos = max([pos + len(ext) - 1 for pos, ext in zip(positions, [ext for ext in archive_extensions if ext in img])])
                    
                    # 分割压缩包路径和内部路径
                    zip_path = img[:split_pos]
                    internal_path = img[split_pos+1:]
            
            result = self._get_image_hash_with_preload(img, internal_path, zip_path)
            if result:
                return img, result
            return img, None
        except Exception as e:
            logger.error(f"[#hash_calc]计算哈希值失败 {img}: {e}")
            return img, None
    
    def _calculate_hashes_for_images(self, images: List[str], archive_path: str = None, temp_dir: str = None, 
                                    image_archive_map: Dict[str, Union[str, Dict]] = None) -> Dict[str, Tuple[str, str]]:
        """
        为图片列表计算哈希值 (多进程并发实现)
        
        Args:
            images: 图片文件列表
            archive_path: 原始压缩包路径
            temp_dir: 临时解压目录
            image_archive_map: 图片到压缩包内信息的映射，可以是字符串URI或包含详细信息的字典
            
        Returns:
            Dict[str, Tuple[str, str]]: {图片路径: (URI, 哈希值)}
        """
        hash_values = {}
        total_images = len(images)
        
        if total_images == 0:
            return hash_values
            
        # 使用进程池进行并发处理
        logger.info(f"[#hash_calc]开始并发计算 {total_images} 张图片的哈希值，使用 {self.max_workers} 个进程")
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_img = {
                executor.submit(
                    calculate_hash_worker,  # 使用从utils导入的函数
                    img, 
                    archive_path, 
                    temp_dir, 
                    image_archive_map
                ): img for img in images
            }
            
            # 收集完成的任务结果
            completed = 0
            for future in as_completed(future_to_img):
                img_path, result = future.result()
                completed += 1
                
                # 每处理10%的图片输出一次进度
                if completed % max(1, total_images // 10) == 0 or completed == total_images:
                    progress = (completed / total_images) * 100
                    logger.info(f"[#hash_calc]哈希计算进度: {completed}/{total_images} ({progress:.1f}%)")
                
                if result:
                    hash_values[img_path] = result
        
        logger.info(f"[#hash_calc]完成 {len(hash_values)}/{total_images} 张图片的哈希计算")
        return hash_values    
    
    def _get_image_hash_with_preload(self, image_path: str, internal_path: str = None, zip_path: str = None) -> Tuple[str, str]:
        """获取图片哈希值和URI，优先使用预加载的mmap数据
        
        Args:
            image_path: 图片文件路径
            internal_path: 压缩包内的相对路径（可选）
            zip_path: 压缩包路径（可选）
            
        Returns:
            Tuple[str, str]: (uri, hash_value) 或 None
        """
        try:
            # 检查路径
            if not image_path:
                logger.error("[#hash_calc]图片路径为空")
                return None

            # 生成标准URI
            uri = None
            if zip_path and internal_path:
                uri = PathURIGenerator.generate(f"{zip_path}!{internal_path}")
            else:
                # 检查是否是压缩包中的图片
                if '!' in image_path:
                    # 检查是否是压缩包路径
                    archive_extensions = ['.zip!','.cbz!','.cbr!', '.rar!', '.7z!', '.tar!']
                    is_archive = any(ext in image_path for ext in archive_extensions)
                    
                    if is_archive:
                        # 找到最后一个压缩文件扩展名的位置
                        positions = [image_path.find(ext) for ext in archive_extensions if ext in image_path]
                        split_pos = max([pos + len(ext) - 1 for pos, ext in zip(positions, [ext for ext in archive_extensions if ext in image_path])])
                        
                        # 分割压缩包路径和内部路径
                        zip_path = image_path[:split_pos]
                        internal_path = image_path[split_pos+1:]
                    if not os.path.exists(zip_path):
                        return None
                    uri = PathURIGenerator.generate(f"{zip_path}!{internal_path}")
                elif not os.path.exists(image_path):
                    logger.error(f"[#hash_calc]图片路径不存在: {image_path}")
                    return None
                else:
                    uri = PathURIGenerator.generate(image_path)

            if not uri:
                logger.error(f"[#hash_calc]生成图片URI失败: {image_path}")
                return None

            # 查询全局缓存
            from hashu.core.calculate_hash_custom import ImageHashCalculator
            cached_hash = ImageHashCalculator.get_hash_from_url(uri)
            if cached_hash:
                logger.info(f"[#hash_calc]使用缓存的哈希值: {uri}")
                return uri, cached_hash

            # 获取预加载的图片数据或直接读取
            img_data = get_image_data(image_path, self.mmap_cache)
            if not img_data:
                logger.error(f"[#hash_calc]获取图片数据失败: {image_path}")
                return None

            # 计算哈希值
            hash_result = ImageHashCalculator.calculate_phash(img_data, url=uri)

            if not hash_result:
                logger.error(f"[#hash_calc]计算图片哈希失败: {image_path}")
                return None

            hash_value = hash_result.get('hash') if isinstance(hash_result, dict) else hash_result
            if not hash_value:
                logger.error(f"[#hash_calc]获取哈希值失败: {image_path}")
                return None

            return uri, hash_value

        except Exception as e:
            logger.error(f"[#hash_calc]获取图片哈希异常 {image_path}: {str(e)}")
            return None
    def _load_hash_file(self) -> Dict:
        """加载哈希文件"""
        if not self.hash_file:
            return {}
            
        # 移除可能存在的额外引号
        clean_path = self.hash_file.strip('"\'')
        
        # 确保使用绝对路径
        if not os.path.isabs(clean_path):
            clean_path = os.path.abspath(clean_path)
        
        try:
            if not os.path.exists(clean_path):
                logger.error(f"[#hash_calc]哈希文件不存在: \"{clean_path}\"")
                return {}
                
            with open(clean_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"成功加载哈希文件: {clean_path}")
                hash_cache_data = data.get('hashes', {})
                return hash_cache_data
        except Exception as e:
            logger.error(f"[#hash_calc]加载哈希文件失败: {e}")
            return {}
            
    def _find_similar_images(self, images: List[str], archive_path: str = None, temp_dir: str = None, 
                            image_archive_map: Dict[str, Union[str, Dict]] = None) -> List[List[str]]:
        """查找相似的图片组"""
        # 使用utils.py中的group_images_by_hash函数替代
        groups = group_images_by_hash(
            images, 
            self.hamming_threshold,
            archive_path,
            temp_dir,
            image_archive_map,
            self._calculate_hashes_for_images  # 传递类方法作为计算哈希的函数
        )
        
        # 只返回多图片组
        return [group for group in groups if len(group) > 1]
    
    def _process_watermark_images(self, group: List[str], watermark_keywords: List[str] = None) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理水印过滤"""
        to_delete = set()
        removal_reasons = {}
        
        deleted_files = self._apply_watermark_filter(group, watermark_keywords)
        for img, texts in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'watermark',
                'watermark_texts': texts,
                'matched_keywords': [kw for kw in (watermark_keywords or []) if any(kw in text for text in texts)]
            }
            logger.info(f"标记删除有水印图片: {os.path.basename(img)}")
            
        return to_delete, removal_reasons
    
    def _apply_watermark_filter(self, group: List[str], watermark_keywords: List[str] = None) -> List[Tuple[str, List[str]]]:
        """
        应用水印过滤，返回要删除的图片和水印文字
        
        Args:
            group: 相似图片组
            watermark_keywords: 水印关键词列表，None时使用默认列表
        """
        from imgfilter.detectors.watermark import WatermarkDetector

        watermark_detector = WatermarkDetector()
        to_delete = []
        watermark_results = {}
        
        # 检测每张图片的水印
        for img_path in group:
            has_watermark, texts = watermark_detector.detect_watermark(img_path, watermark_keywords)
            watermark_results[img_path] = (has_watermark, texts)
            if has_watermark:
                logger.info(f"发现水印: {os.path.basename(img_path)} -> {texts}")
            
        # 找出无水印的图片
        clean_images = [img for img, (has_mark, _) in watermark_results.items() if not has_mark]
        if clean_images:
            # 如果有无水印图片，保留其中最大的一张
            keep_image = max(clean_images, key=lambda x: os.path.getsize(x))
            # 删除其他有水印的图片
            for img in group:
                if img != keep_image and watermark_results[img][0]:
                    to_delete.append((img, watermark_results[img][1]))
                    
        return to_delete
        
    def _process_quality_images(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理质量过滤，使用统一的综合过滤策略（逐档位过滤）"""
        # 使用新的逐档位过滤策略：默认只用尺寸档位，相同时自动切换到下一档位
        return process_group_with_filters(group, {
            'enable_progressive': True,       # 是否启用逐档位过滤模式
            'use_dimensions': True,           # 是否使用图片尺寸（像素数量）
            'use_file_size': True,            # 是否使用文件大小
            'use_filename': True,             # 是否使用文件名
            'reverse_filename': False,        # 文件名排序是否反向（True=保留名称大的，False=保留名称小的）
            'filter_order': ['dimensions', 'file_size', 'filename']  # 过滤器顺序
        })

    def _apply_quality_filter(self, group: List[str]) -> List[Tuple[str, str]]:
        """应用质量过滤（已弃用，保留以兼容旧代码）"""
        logger.warning("_apply_quality_filter已弃用，建议使用process_group_with_filters")
        # 调用新的统一过滤方法
        to_delete, reasons = self._process_quality_images(group)
        result = []
        for img in to_delete:
            reason_detail = reasons[img].get('details', 'quality filter')
            result.append((img, reason_detail))
        return result
    
    def _process_hash_images(self, group: List[str], archive_path: str = None, temp_dir: str = None, 
                           image_archive_map: Dict[str, Union[str, Dict]] = None, ref_hamming_threshold: int = None) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理哈希文件过滤"""
        to_delete = set()
        removal_reasons = {}
        
        # 使用传入的阈值或默认值
        threshold = ref_hamming_threshold if ref_hamming_threshold is not None else self.ref_hamming_threshold
        
        # 计算哈希值
        image_hashes = self._calculate_hashes_for_images(group, archive_path, temp_dir, image_archive_map)
        
        # 读取哈希文件
        # try:
        #     with open(self.hash_file, 'r', encoding='utf-8') as f:
        #         hash_data = json.load(f).get('hashes', {})
        # except Exception as e:
        #     logger.error(f"[#hash_calc]读取哈希文件失败: {e}")
        #     return to_delete, removal_reasons
        hash_data = self.hash_cache
        # 比较哈希值
        for img_path, (current_uri, current_hash) in image_hashes.items():
            try:
                result = self._compare_hash_with_reference(
                    img_path, current_uri, current_hash,
                    hash_data, threshold
                )
                if result:
                    match_uri, distance = result
                    to_delete.add(img_path)
                    removal_reasons[img_path] = {
                        'reason': 'hash_duplicate',
                        'ref_uri': match_uri,
                        'distance': distance
                    }
                    logger.info(f"标记删除重复图片: {os.path.basename(img_path)} (参考URI: {match_uri}, 距离: {distance})")
            except Exception as e:
                logger.error(f"[#hash_calc]比较哈希值失败 {img_path}: {e}")
                    
        return to_delete, removal_reasons

    def _compare_hash_with_reference(self, img_path: str, current_uri: str, current_hash: str, 
                                   hash_data: Dict, threshold: int) -> Tuple[str, int]:
        """比较哈希值与参考哈希值"""
        # 过滤掉当前URI
        filtered_hash_data = {uri: data for uri, data in hash_data.items() if uri != current_uri}
        
        # 使用utils.py中的compare_hash_with_reference函数
        result = compare_hash_with_reference(current_hash, filtered_hash_data, threshold)
        
        if result:
            return result
        return None

    def _find_similar_images_by_lpips_cluster(self, images: List[str], use_gpu: bool = None, threshold: float = None) -> List[List[str]]:
        """
        使用LPIPS聚类算法查找相似的图片组（使用cluster.py中的实现）
        
        Args:
            images: 图片文件列表
            use_gpu: 是否使用GPU（覆盖实例设置）
            threshold: LPIPS距离阈值（覆盖实例设置）
            
        Returns:
            List[List[str]]: 相似图片组列表
        """
        similar_groups = []
        
        # 检查图片数量
        if len(images) < 2:
            logger.warning("[#hash_calc]图片数量不足，至少需要2张图片进行聚类")
            return similar_groups
            
        # 使用传入的阈值或默认值
        current_threshold = self.lpips_threshold if threshold is None else threshold
            
        logger.info(f"[#hash_calc]开始进行LPIPS聚类，共 {len(images)} 张图片，阈值: {current_threshold}")
        
        # 记录开始时间
        start_time = datetime.now()
        
        # 确定当前GPU模式
        current_use_gpu = self.use_gpu if use_gpu is None else use_gpu
        
        # 根据GPU模式选择不同的聚类实现
        if current_use_gpu:
            logger.info("[#hash_calc]使用GPU模式进行LPIPS聚类")
            try:
                # 尝试GPU聚类
                clusters = lpips_clustering_gpu(images, threshold=current_threshold)
                logger.info("[#hash_calc]GPU聚类成功完成")
            except Exception as e:
                logger.error(f"[#hash_calc]GPU聚类失败，回退到CPU模式: {e}")
                # 如果GPU失败，回退到CPU模式
                clusters = lpips_clustering_cpu(images, threshold=current_threshold)
        else:
            logger.info("[#hash_calc]使用CPU模式进行LPIPS聚类")
            clusters = lpips_clustering_cpu(images, threshold=current_threshold)
        
        # 计算耗时
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"[#hash_calc]LPIPS聚类完成，耗时: {elapsed_time:.2f}秒 (模式: {'GPU' if current_use_gpu else 'CPU'})")
        
        # 按聚类分组
        cluster_dict = {}
        for img_path, cluster in zip(images, clusters):
            if cluster not in cluster_dict:
                cluster_dict[cluster] = []
            cluster_dict[cluster].append(img_path)
        
        # 计算聚类统计信息
        num_clusters = len(set(clusters) - {-1})
        noise_count = clusters.count(-1) if -1 in clusters else 0
        logger.info(f"[#hash_calc]聚类结果: {num_clusters} 个聚类, {noise_count} 个未归类项")
        
        # 只返回有多个图片的组，并且排除噪音组（cluster_id = -1）
        for cluster_id, group in cluster_dict.items():
            if len(group) > 1 and cluster_id != -1:  # 排除噪音/未聚类项（cluster_id = -1）
                similar_groups.append(group)
                logger.info(f"[#hash_calc]找到相似图像组 {cluster_id}: {len(group)}张")
        
        return similar_groups

    def _find_similar_images_by_phash_lpips_cluster(self, images: List[str], archive_path: str = None, 
                                                  temp_dir: str = None, image_archive_map: Dict[str, Union[str, Dict]] = None,
                                                  use_gpu: bool = None, threshold: float = None) -> List[List[str]]:
        """
        使用两阶段策略查找相似图片组：
        1. 首先用哈希(汉明距离)对图片进行预分组，减少LPIPS计算量
        2. 然后对每个预分组内的图片进行LPIPS聚类
        
        Args:
            images: 图片文件列表
            archive_path: 原始压缩包路径
            temp_dir: 临时解压目录
            image_archive_map: 图片到压缩包内的映射
            use_gpu: 是否使用GPU（覆盖实例设置）
            threshold: LPIPS距离阈值（覆盖实例设置）
            
        Returns:
            List[List[str]]: 相似图片组列表
        """
        # 使用传入的阈值或默认值
        current_threshold = self.lpips_threshold if threshold is None else threshold
        current_use_gpu = self.use_gpu if use_gpu is None else use_gpu
        
        # 使用工具函数中的实现
        return find_similar_images_by_phash_lpips_cluster(
            images=images,
            lpips_threshold=current_threshold,
            hash_threshold=self.hamming_threshold,
            calculate_hashes_func=self._calculate_hashes_for_images,
            lpips_cluster_func=self._find_similar_images_by_lpips_cluster,
            archive_path=archive_path,
            temp_dir=temp_dir,
            image_archive_map=image_archive_map,
            use_gpu=current_use_gpu
        )

    def _process_lpips_images(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理LPIPS相似图片组，使用统一的综合过滤策略"""
        # 使用综合过滤策略：尺寸大 > 文件大小大 > 文件名小
        to_delete, removal_reasons = process_group_with_filters(group, {
            'enable_progressive': True,       # 是否启用逐档位过滤模式
            'use_dimensions': True,           # 是否使用图片尺寸（像素数量）
            'use_file_size': True,            # 是否使用文件大小
            'use_filename': True,             # 是否使用文件名
            'reverse_filename': False,        # 文件名排序是否反向（True=保留名称大的，False=保留名称小的）
            'filter_order': ['dimensions', 'file_size', 'filename']  # 过滤器顺序
        })
        
        # 更新原因标记为 cluster
        for img in to_delete:
            if img in removal_reasons:
                removal_reasons[img]['reason'] = 'cluster'
                logger.info(f"标记删除LPIPS相似图片: {os.path.basename(img)} - {removal_reasons[img].get('details', '')}")
        
        return to_delete, removal_reasons
