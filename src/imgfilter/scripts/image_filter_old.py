import os
import logging
from typing import List, Set, Dict, Tuple, Union
from hashu.core.calculate_hash_custom import ImageHashCalculator, PathURIGenerator
from imgfilter.detectors.watermark import WatermarkDetector

from imgfilter.detectors.text import CVTextImageDetector
from PIL import Image
import pillow_avif  # AVIF支持
import pillow_jxl 
from io import BytesIO
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from hashu.utils.hash_accelerator import HashAccelerator
import mmap
import numpy as np
from loguru import logger

class ImageFilter:
    """图片过滤器，支持多种独立的过滤功能"""
    
    def __init__(self, hash_file: str = None, hamming_threshold: int = 12, ref_hamming_threshold: int = None, max_workers: int = None):
        """
        初始化过滤器
        
        Args:
            hash_file: 哈希文件路径
            hamming_threshold: 汉明距离阈值
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值，默认使用hamming_threshold
            max_workers: 最大工作线程数，默认为CPU核心数
        """
        self.hash_file = hash_file
        self.hamming_threshold = hamming_threshold
        self.ref_hamming_threshold = ref_hamming_threshold if ref_hamming_threshold is not None else hamming_threshold
        self.hash_cache = {}  # 初始化空缓存
        if hash_file:
            self.hash_cache = self._load_hash_file()
        self.watermark_detector = WatermarkDetector()
        self.text_detector = CVTextImageDetector()
        self.max_workers = max_workers or multiprocessing.cpu_count()
        self.file_cache = {}  # 添加文件缓存
        self.cache_size_limit = 100 * 1024 * 1024  # 100MB缓存限制
        self.current_cache_size = 0
        
    def _load_hash_file(self) -> Dict:
        """加载哈希文件"""
        try:
            if not os.path.exists(self.hash_file):
                logger.error(f"哈希文件不存在: {self.hash_file}")
                return {}
                
            with open(self.hash_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"成功加载哈希文件: {self.hash_file}")
            return data.get('hashes', {})
        except Exception as e:
            logger.error(f"加载哈希文件失败: {e}")
            return {}

    def _read_file_optimized(self, file_path: str) -> bytes:
        """优化的文件读取方法
        
        使用多种策略读取文件:
        1. 首先检查内存缓存
        2. 对于小文件(<10MB)使用普通读取
        3. 对于大文件使用mmap
        4. 维护缓存大小限制
        """
        try:
            # 检查缓存
            if file_path in self.file_cache:
                return self.file_cache[file_path]

            file_size = os.path.getsize(file_path)
            
            # 小文件直接读取
            if file_size < 10 * 1024 * 1024:  # 10MB
                with open(file_path, 'rb') as f:
                    data = f.read()
            else:
                # 大文件使用mmap
                with open(file_path, 'rb') as f:
                    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        data = mm.read()

            # 缓存管理
            if self.current_cache_size + file_size <= self.cache_size_limit:
                self.file_cache[file_path] = data
                self.current_cache_size += file_size
            elif len(self.file_cache) > 0:
                # 如果缓存满了，移除最早的项目
                oldest_file = next(iter(self.file_cache))
                oldest_size = len(self.file_cache[oldest_file])
                del self.file_cache[oldest_file]
                self.current_cache_size -= oldest_size
                
                # 尝试缓存新文件
                if self.current_cache_size + file_size <= self.cache_size_limit:
                    self.file_cache[file_path] = data
                    self.current_cache_size += file_size

            return data
            
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return None

    def _process_small_images(self, cover_files: List[str], min_size: int) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理小图过滤"""
        to_delete = set()
        removal_reasons = {}
        
        # 使用线程池并行处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self._process_single_image, img_path, min_size): img_path
                for img_path in cover_files
            }
            
            for future in as_completed(future_to_file):
                img_path = future_to_file[future]
                try:
                    result = future.result()
                    if result:
                        should_delete, reason = result
                        if should_delete:
                            to_delete.add(img_path)
                            removal_reasons[img_path] = {
                                'reason': 'small_image',
                                'details': f'小于{min_size}像素'
                            }
                            logger.info(f"标记删除小图: {os.path.basename(img_path)}")
                except Exception as e:
                    logger.error(f"处理小图检测失败 {img_path}: {e}")
                
        return to_delete, removal_reasons

    def _process_single_image(self, img_path: str, min_size: int) -> Tuple[bool, str]:
        """处理单个图片"""
        try:
            # 使用优化的文件读取
            img_data = self._read_file_optimized(img_path)
            if img_data is None:
                return False, None
                
            result, reason = self.detect_small_image(img_data, {'min_size': min_size})
            return reason == 'small_image', reason
            
        except Exception as e:
            logger.error(f"处理图片失败 {img_path}: {e}")
            return False, None

    def _process_grayscale_images(self, cover_files: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理黑白图过滤"""
        to_delete = set()
        removal_reasons = {}
        
        for img_path in cover_files:
            try:
                with open(img_path, 'rb') as f:
                    img_data = f.read()
                result, reason = self.detect_grayscale_image(img_data)
                if reason in ['grayscale', 'pure_white', 'pure_black']:
                    to_delete.add(img_path)
                    removal_reasons[img_path] = {
                        'reason': reason,
                        'details': {
                            'grayscale': '灰度图片',
                            'pure_white': '纯白图片',
                            'pure_black': '纯黑图片'
                        }.get(reason, '黑白图片')
                    }
                    logger.info(f"标记删除{removal_reasons[img_path]['details']}: {os.path.basename(img_path)}")
            except Exception as e:
                logger.error(f"处理灰度图检测失败 {img_path}: {e}")
                
        return to_delete, removal_reasons

    def _process_text_images(self, image_files: List[str], threshold: float = 0.5) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理纯文本图片过滤"""
        to_delete = set()
        removal_reasons = {}
        
        # 使用封装好的方法进行过滤，与水印过滤相似的设计
        deleted_files = self._apply_text_filter(image_files, threshold)
        for img, score in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'text_image',
                'details': '纯文本图片',
                'score': score
            }
            logger.info(f"标记删除纯文本图片: {os.path.basename(img)}")
        
        return to_delete, removal_reasons

    def _apply_text_filter(self, image_files: List[str], threshold: float = 0.5) -> List[Tuple[str, float]]:
        """
        应用纯文本图片过滤，返回要删除的图片和检测分数
        
        Args:
            image_files: 图片文件路径列表
            threshold: 文本图片检测阈值
        
        Returns:
            List[Tuple[str, float]]: (待删除图片路径, 文本检测分数)列表
        """
        to_delete = []
        
        # 检测每张图片是否为文本图片
        for img_path in image_files:
            try:
                is_text_image, result = self.text_detector.detect_text_image(img_path, threshold)
                score = result.get('total_score', 0) if isinstance(result, dict) else result
                
                if is_text_image:
                    to_delete.append((img_path, score))
                    # 只记录基础名称，不记录完整路径
                    logger.info(f"图片文本检测结果 [{os.path.basename(img_path)}]: 总分={score}/4, 是否文本图片={is_text_image}")
            except Exception as e:
                logger.error(f"处理纯文本图片检测失败 {img_path}: {e}")
        
        return to_delete

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
        
    def _process_quality_images(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理质量过滤"""
        to_delete = set()
        removal_reasons = {}
        
        deleted_files = self._apply_quality_filter(group)
        for img, size_diff in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'quality',
                'size_diff': size_diff
            }
            logger.info(f"标记删除较小图片: {os.path.basename(img)}")
            
        return to_delete, removal_reasons

    def _process_hash_images(self, group: List[str], ref_hamming_threshold: int = None) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理哈希文件过滤"""
        to_delete = set()
        removal_reasons = {}
        
        # 使用传入的阈值或默认值
        threshold = ref_hamming_threshold if ref_hamming_threshold is not None else self.ref_hamming_threshold
        
        # 使用线程池并行计算哈希值
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 并行计算哈希值
            future_to_img = {
                executor.submit(self._get_image_hash_and_uri, img_path): img_path 
                for img_path in group
            }
            
            # 收集结果
            hash_values = {}
            for future in as_completed(future_to_img):
                img_path = future_to_img[future]
                try:
                    result = future.result()
                    if result:
                        uri, hash_value = result
                        hash_values[img_path] = (uri, hash_value)
                except Exception as e:
                    logger.error(f"计算哈希值失败 {img_path}: {e}")
        
        # 读取哈希文件
        try:
            with open(self.hash_file, 'r', encoding='utf-8') as f:
                hash_data = json.load(f).get('hashes', {})
        except Exception as e:
            logger.error(f"读取哈希文件失败: {e}")
            return to_delete, removal_reasons
        
        # 并行比较哈希值
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 创建比较任务
            future_to_comparison = {
                executor.submit(
                    self._compare_hash_with_reference,
                    img_path, current_uri, current_hash,
                    hash_data, threshold
                ): img_path
                for img_path, (current_uri, current_hash) in hash_values.items()
            }
            
            # 收集结果
            for future in as_completed(future_to_comparison):
                img_path = future_to_comparison[future]
                try:
                    result = future.result()
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
                    logger.error(f"比较哈希值失败 {img_path}: {e}")
                    
        return to_delete, removal_reasons

    def _get_image_hash_and_uri(self, img_path: str) -> Tuple[str, str]:
        """获取图片的哈希值和URI"""
        try:
            if not os.path.exists(img_path):
                return None
            
            uri = PathURIGenerator.generate(img_path)
            if not uri:
                return None
                
            hash_value = self._get_image_hash(img_path)
            if not hash_value:
                return None
                
            return uri, hash_value
            
        except Exception as e:
            logger.error(f"获取图片哈希和URI失败 {img_path}: {e}")
            return None

    def _compare_hash_with_reference(self, img_path: str, current_uri: str, current_hash: str, 
                                   hash_data: Dict, threshold: int) -> Tuple[str, int]:
        """比较哈希值与参考哈希值"""
        try:
            # 使用加速器进行批量比较
            ref_hashes = []
            uri_map = {}
            
            # 收集参考哈希值
            for uri, ref_data in hash_data.items():
                if uri == current_uri:
                    continue
                    
                ref_hash = ref_data.get('hash') if isinstance(ref_data, dict) else str(ref_data)
                if not ref_hash:
                    continue
                    
                ref_hashes.append(ref_hash)
                uri_map[ref_hash] = uri
            
            # 使用加速器查找相似哈希
            similar_hashes = HashAccelerator.find_similar_hashes(
                current_hash,
                ref_hashes,
                uri_map,
                threshold
            )
            
            # 如果找到相似哈希,返回第一个(最相似的)
            if similar_hashes:
                ref_hash, uri, distance = similar_hashes[0]
                return uri, distance
                
            return None
            
        except Exception as e:
            logger.error(f"比较哈希值失败 {img_path}: {e}")
            return None

    def process_images(
        self, 
        image_files: List[str],
        enable_small_filter: bool = None,
        enable_grayscale_filter: bool = None,
        enable_duplicate_filter: bool = None,
        enable_text_filter: bool = None,
        min_size: int = 631,
        duplicate_filter_mode: str = 'quality',  # 'quality', 'watermark' or 'hash'
        watermark_keywords: List[str] = None,  # 水印关键词列表
        ref_hamming_threshold: int = None,  # 哈希文件过滤的汉明距离阈值
        text_threshold: float = 0.5,  # 纯文本图片检测阈值
        **kwargs
    ) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        处理图片列表，支持多种独立的过滤功能
        
        Args:
            image_files: 图片文件路径列表
            enable_small_filter: 是否启用小图过滤
            enable_grayscale_filter: 是否启用黑白图过滤
            enable_duplicate_filter: 是否启用重复图片过滤
            enable_text_filter: 是否启用纯文本图片过滤
            min_size: 最小图片尺寸
            duplicate_filter_mode: 重复图片过滤模式 ('quality', 'watermark' 或 'hash')
            watermark_keywords: 水印关键词列表，None时使用默认列表
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值，None时使用初始化时的值
            text_threshold: 纯文本图片检测阈值
            **kwargs: 其他可扩展的参数
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        sorted_files = sorted(image_files)
        
        if not sorted_files:
            return set(), {}
            
        logger.info(f"开始处理{len(sorted_files)}张图片")
        
        to_delete = set()
        removal_reasons = {}
        
        # 1. 小图过滤
        if enable_small_filter:
            small_to_delete, small_reasons = self._process_small_images(sorted_files, min_size)
            to_delete.update(small_to_delete)
            removal_reasons.update(small_reasons)
        
        # 2. 黑白图过滤
        if enable_grayscale_filter:
            gray_to_delete, gray_reasons = self._process_grayscale_images(sorted_files)
            # 避免重复添加
            gray_to_delete = {img for img in gray_to_delete if img not in to_delete}
            to_delete.update(gray_to_delete)
            removal_reasons.update({k: v for k, v in gray_reasons.items() if k in gray_to_delete})
        
        # 3. 重复图片过滤
        if enable_duplicate_filter:
            # 获取未被其他过滤器删除的文件
            remaining_files = [f for f in sorted_files if f not in to_delete]
            if remaining_files:
                if duplicate_filter_mode == 'hash' and self.hash_file:
                    # 直接使用哈希文件进行过滤
                    hash_to_delete, hash_reasons = self._process_hash_images(remaining_files, ref_hamming_threshold)
                    to_delete.update(hash_to_delete)
                    removal_reasons.update(hash_reasons)
                else:
                    # 使用传统的相似图片组过滤
                    similar_groups = self._find_similar_images(remaining_files)
                    for group in similar_groups:
                        if len(group) <= 1:
                            continue
                            
                        if duplicate_filter_mode == 'watermark':
                            # 水印过滤模式
                            watermark_to_delete, watermark_reasons = self._process_watermark_images(group, watermark_keywords)
                            to_delete.update(watermark_to_delete)
                            removal_reasons.update(watermark_reasons)
                        else:
                            # 质量过滤模式（默认）
                            quality_to_delete, quality_reasons = self._process_quality_images(group)
                            to_delete.update(quality_to_delete)
                            removal_reasons.update(quality_reasons)
        
        # 4. 纯文本图片过滤
        if enable_text_filter:
            # 获取未被其他过滤器删除的文件
            remaining_files = [f for f in sorted_files if f not in to_delete]
            if remaining_files:
                text_to_delete, text_reasons = self._process_text_images(remaining_files, text_threshold)
                to_delete.update(text_to_delete)
                removal_reasons.update(text_reasons)
        
        return to_delete, removal_reasons

    def _find_similar_images(self, images: List[str]) -> List[List[str]]:
        """查找相似的图片组"""
        similar_groups = []
        processed = set()
        
        # 并行计算所有图片的哈希值
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_img = {
                executor.submit(self._get_image_hash, img): img 
                for img in images
            }
            
            # 收集哈希值
            hash_values = {}
            for future in as_completed(future_to_img):
                img = future_to_img[future]
                try:
                    hash_value = future.result()
                    if hash_value:
                        hash_values[img] = hash_value
                except Exception as e:
                    logger.error(f"计算哈希值失败 {img}: {e}")
        
        # 使用加速器进行批量比较
        target_hashes = list(hash_values.values())
        img_by_hash = {hash_val: img for img, hash_val in hash_values.items()}
        
        # 批量查找相似哈希
        similar_results = HashAccelerator.batch_find_similar_hashes(
            target_hashes,
            target_hashes,
            img_by_hash,
            self.hamming_threshold
        )
        
        # 处理结果,构建相似图片组
        for target_hash, similar_hashes in similar_results.items():
            if target_hash not in processed:
                current_group = [img_by_hash[target_hash]]
                processed.add(target_hash)
                
                for similar_hash, uri, distance in similar_hashes:
                    if similar_hash not in processed:
                        current_group.append(img_by_hash[similar_hash])
                        processed.add(similar_hash)
                        logger.info(f"找到相似图片: {os.path.basename(uri)} (距离: {distance})")
                
                if len(current_group) > 1:
                    similar_groups.append(current_group)
                    logger.info(f"找到相似图片组: {len(current_group)}张")
                
        return similar_groups

    def _compare_hashes(self, hash1: str, hash2: str, img2: str, threshold: int) -> bool:
        """比较两个哈希值"""
        try:
            if not hash2:
                return False
                
            # 使用加速器计算汉明距离
            distances = HashAccelerator.calculate_hamming_distances(hash1, [hash2])
            if distances.size > 0 and distances[0] <= threshold:
                logger.info(f"找到相似图片: {os.path.basename(img2)} (距离: {distances[0]})")
                return True
            return False
            
        except Exception as e:
            logger.error(f"比较哈希值失败: {e}")
            return False

    def _get_image_hash(self, image_path: str) -> str:
        """获取图片哈希值，优先从缓存读取"""
        try:
            # 增加路径有效性检查
            if not image_path:
                logger.error("图片路径为空")
                return None
                
            if not os.path.exists(image_path):
                logger.error(f"图片路径不存在: {image_path}")
                return None
            
            image_uri = PathURIGenerator.generate(image_path)
            if not image_uri:  # 处理生成URI失败的情况
                logger.error(f"生成图片URI失败: {image_path}")
                return None

            # 增加缓存键存在性检查
            if self.hash_cache:
                if image_uri in self.hash_cache:
                    hash_data = self.hash_cache[image_uri]
                    # 处理不同的缓存数据结构
                    if isinstance(hash_data, dict):
                        hash_value = hash_data.get('hash')
                        if hash_value:
                            return hash_value
                    elif hash_data:  # 兼容旧版本字符串格式
                        return str(hash_data)

            # 使用优化的文件读取
            img_data = self._read_file_optimized(image_path)
            if not img_data:
                logger.error(f"读取图片文件失败: {image_path}")
                return None

            # 计算新哈希
            hash_result = ImageHashCalculator.calculate_phash(BytesIO(img_data))
            if not hash_result:
                logger.error(f"计算图片哈希失败: {image_path}")
                return None
                
            hash_value = hash_result.get('hash') if isinstance(hash_result, dict) else hash_result
            if not hash_value:
                logger.error(f"获取哈希值失败: {image_path}")
                return None

            # 更新缓存
            self.hash_cache[image_uri] = {'hash': hash_value}
            return hash_value
        
        except Exception as e:
            logger.error(f"获取图片哈希异常 {image_path}: {str(e)}")
            return None

    def _apply_watermark_filter(self, group: List[str], watermark_keywords: List[str] = None) -> List[Tuple[str, List[str]]]:
        """
        应用水印过滤，返回要删除的图片和水印文字
        
        Args:
            group: 相似图片组
            watermark_keywords: 水印关键词列表，None时使用默认列表
        """
        to_delete = []
        watermark_results = {}
        
        # 检测每张图片的水印
        for img_path in group:
            has_watermark, texts = self.watermark_detector.detect_watermark(img_path, watermark_keywords)
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

    def _apply_quality_filter(self, group: List[str]) -> List[Tuple[str, str]]:
        """应用质量过滤（基于文件大小），返回要删除的图片和大小差异"""
        to_delete = []
        # 获取文件大小
        file_sizes = {img: os.path.getsize(img) for img in group}
        # 保留最大的文件
        keep_image = max(group, key=lambda x: file_sizes[x])
        
        # 删除其他较小的文件
        for img in group:
            if img != keep_image:
                size_diff = f"{file_sizes[keep_image] - file_sizes[img]} bytes"
                to_delete.append((img, size_diff))
                
        return to_delete

    def detect_small_image(self, image_data, params):
        """独立的小图检测
        
        Args:
            image_data: PIL.Image对象或图片字节数据
            params: 参数字典，包含min_size等配置
            
        Returns:
            Tuple[Union[bytes, None], Union[str, None]]: (处理后的图片数据, 错误原因)
        """
        try:
            # 统一转换为PIL Image对象
            if isinstance(image_data, Image.Image):
                img = image_data
            else:
                img = Image.open(BytesIO(image_data))
                
            # 获取图片尺寸
            width, height = img.size
            min_size = params.get('min_size', 631)
            
            # 检查尺寸
            if width < min_size or height < min_size:
                logger.info(f"[#image_processing]🖼️ 图片尺寸: {width}x{height} 小于最小尺寸 {min_size}")
                return None, 'small_image'
                
            logger.info(f"[#image_processing]🖼️ 图片尺寸: {width}x{height} 大于最小尺寸 {min_size}")
            
            # 如果输入是字节数据，返回字节数据；如果是PIL Image，返回原对象
            if isinstance(image_data, Image.Image):
                return image_data, None
            else:
                img_byte_arr = BytesIO()
                img.save(img_byte_arr, format=img.format or 'PNG')
                return img_byte_arr.getvalue(), None
                
        except Exception as e:
            logger.error(f"检测图片尺寸时发生错误: {str(e)}")
            return None, 'size_detection_error'

    def detect_grayscale_image(self, image_data):
        """独立的灰度图和纯色图检测
        
        Args:
            image_data: PIL.Image对象或图片字节数据
            
        Returns:
            Tuple[Union[bytes, None], Union[str, None]]: (处理后的图片数据, 错误原因)
        """
        try:
            # 统一转换为PIL Image对象
            if isinstance(image_data, Image.Image):
                img = image_data
            else:
                img = Image.open(BytesIO(image_data))
            
            # 转换为RGB模式
            if img.mode not in ["RGB", "RGBA", "L"]:
                img = img.convert("RGB")
            
            # 1. 检查是否为原始灰度图
            if img.mode == "L":
                logger.info("[#image_processing]🖼️ 检测到原始灰度图")
                return None, 'grayscale'
            
            # 2. 获取图片的采样点进行分析
            width, height = img.size
            sample_points = [
                (x, y) 
                for x in range(0, width, max(1, width//10))
                for y in range(0, height, max(1, height//10))
            ][:100]  # 最多取100个采样点
            
            # 获取采样点的像素值
            pixels = [img.getpixel(point) for point in sample_points]
            
            # 3. 检查是否为纯白图
            if all(all(v > 240 for v in (pixel if isinstance(pixel, tuple) else (pixel,))) 
                   for pixel in pixels):
                logger.info("[#image_processing]🖼️ 检测到纯白图")
                return None, 'pure_white'
            
            # 4. 检查是否为纯黑图
            if all(all(v < 15 for v in (pixel if isinstance(pixel, tuple) else (pixel,))) 
                   for pixel in pixels):
                logger.info("[#image_processing]🖼️ 检测到纯黑图")
                return None, 'pure_black'
            
            # 5. 检查是否为灰度图
            if img.mode in ["RGB", "RGBA"]:
                is_grayscale = all(
                    abs(pixel[0] - pixel[1]) < 5 and 
                    abs(pixel[1] - pixel[2]) < 5 and
                    abs(pixel[0] - pixel[2]) < 5 
                    for pixel in pixels
                )
                if is_grayscale:
                    logger.info("[#image_processing]🖼️ 检测到灰度图(RGB接近)")
                    return None, 'grayscale'
            
            # 返回原始数据
            if isinstance(image_data, Image.Image):
                return image_data, None
            else:
                img_byte_arr = BytesIO()
                img.save(img_byte_arr, format=img.format or 'PNG')
                return img_byte_arr.getvalue(), None
                
        except Exception as e:
            logger.error(f"检测灰度图时发生错误: {str(e)}")
            return None, 'grayscale_detection_error'