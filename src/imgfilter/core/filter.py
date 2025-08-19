"""
ImgFilter核心过滤器模块
"""
import os
import logging
from typing import List, Set, Dict, Tuple
import multiprocessing
from loguru import logger
import json
from imgfilter.detectors.watermark import WatermarkDetector
from imgfilter.detectors.text import CVTextImageDetector
from imgfilter.detectors.duplicate import DuplicateImageDetector
from imgfilter.detectors.small import SmallImageDetector
from imgfilter.detectors.gray.grayscale import GrayscaleImageDetector
# from imgfilter.deepghs.detectors.grayscale import GrayscaleImageDetector
class ImageFilter:
    """图片过滤器，支持多种独立的过滤功能"""
    
    def __init__(self, hash_file: str = None, hamming_threshold: int = 12, ref_hamming_threshold: int = None, 
                max_workers: int = None, lpips_threshold: float = 0.02):
        """
        初始化过滤器
        
        Args:
            hash_file: 哈希文件路径
            hamming_threshold: 汉明距离阈值
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值，默认使用hamming_threshold
            max_workers: 最大工作线程数，默认为CPU核心数
            lpips_threshold: LPIPS相似度阈值，用于LPIPS模式
        """
        self.hash_file = hash_file
        self.hamming_threshold = hamming_threshold
        self.ref_hamming_threshold = ref_hamming_threshold if ref_hamming_threshold is not None else hamming_threshold
        self.watermark_detector = WatermarkDetector()
        
        # 初始化各种检测器
        self.text_detector = CVTextImageDetector()
        self.duplicate_detector = DuplicateImageDetector(
            hash_file=hash_file, 
            hamming_threshold=hamming_threshold, 
            ref_hamming_threshold=ref_hamming_threshold,
            max_workers=max_workers,
            lpips_threshold=lpips_threshold
        )
        self.small_image_detector = SmallImageDetector()
        self.grayscale_detector = GrayscaleImageDetector()
        self.max_workers = max_workers or multiprocessing.cpu_count()
        
    def _process_small_images(self, files: List[str], min_size: int) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理小图过滤"""
        logger.info(f"[#cur_stats]开始小图过滤，处理{len(files)}张图片")
        try:
            return self.small_image_detector.detect_small_images(files, min_size)
        except Exception as e:
            logger.error(f"[#update_log]❌ 小图过滤执行错误: {str(e)}")
            return set(), {}
    
    def _process_grayscale_images(self, files: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理灰度图过滤"""
        logger.info(f"[#cur_stats]开始灰度图过滤，处理{len(files)}张图片")
        try:
            return self.grayscale_detector.detect_grayscale_images(files)
        except Exception as e:
            logger.error(f"[#update_log]❌ 灰度图过滤执行错误: {str(e)}")
            return set(), {}
    
    def _process_duplicate_images(self, files: List[str], archive_path: str = None, temp_dir: str = None,
                                image_archive_map: Dict[str, str] = None, duplicate_filter_mode: str = 'quality',
                                watermark_keywords: List[str] = None, ref_hamming_threshold: int = None,
                                lpips_threshold: float = None, *args, **kwargs) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理重复图片过滤"""
        logger.info(f"[#cur_stats]开始重复图片过滤，处理{len(files)}张图片")
        try:
            return self.duplicate_detector.detect_duplicates(
                files,
                archive_path=archive_path,
                temp_dir=temp_dir,
                image_archive_map=image_archive_map,
                mode=duplicate_filter_mode,
                watermark_keywords=watermark_keywords,
                ref_hamming_threshold=ref_hamming_threshold,
                lpips_threshold=lpips_threshold,
                *args,
                **kwargs
            )
        except Exception as e:
            logger.error(f"[#update_log]❌ 重复图片过滤执行错误: {str(e)}")
            return set(), {}
    
    def _process_text_images(self, files: List[str], text_threshold: float = 0.5, 
                           *args, **kwargs) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理纯文本图片过滤"""
        logger.info(f"[#cur_stats]开始纯文本图片过滤，处理{len(files)}张图片")
        try:
            return self.text_detector.process_text_images(
                files, 
                threshold=text_threshold,
                *args,
                **kwargs
            )
        except Exception as e:
            logger.error(f"[#update_log]❌ 纯文本图片过滤执行错误: {str(e)}")
            return set(), {}

    def process_images(
        self, 
        image_files: List[str],
        enable_small_filter: bool = None,
        enable_grayscale_filter: bool = None,
        enable_duplicate_filter: bool = None,
        enable_text_filter: bool = None,
        min_size: int = 630,
        duplicate_filter_mode: str = 'quality',  # 'quality', 'watermark', 'hash' or 'lpips'
        watermark_keywords: List[str] = None,  # 水印关键词列表
        ref_hamming_threshold: int = None,  # 哈希文件过滤的汉明距离阈值
        lpips_threshold: float = None,  # LPIPS相似度阈值
        text_threshold: float = 0.5,  # 纯文本图片检测阈值
        archive_path: str = None,     # 压缩包路径
        temp_dir: str = None,         # 临时解压目录
        image_archive_map: Dict[str, str] = None,  # 图片到压缩包内URI的映射
        *args,
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
            duplicate_filter_mode: 重复图片过滤模式 ('quality', 'watermark', 'hash' 或 'lpips')
            watermark_keywords: 水印关键词列表，None时使用默认列表
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值，None时使用初始化时的值
            lpips_threshold: LPIPS相似度阈值，None时使用初始化时的值
            text_threshold: 纯文本图片检测阈值
            archive_path: 压缩包路径
            temp_dir: 临时解压目录
            image_archive_map: 图片到压缩包内URI的映射
            **kwargs: 其他可扩展的参数
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        sorted_files = sorted(image_files)
        if not sorted_files:
            return set(), {}
            
        logger.info(f"[#cur_stats]开始处理{len(sorted_files)}张图片")
        to_delete = set()
        removal_reasons = {}
        
        # 定义过滤器执行顺序
        filters = [
            {'name': 'small_image_filter', 'enabled': enable_small_filter},
            {'name': 'grayscale_filter', 'enabled': enable_grayscale_filter},
            {'name': 'duplicate_filter', 'enabled': enable_duplicate_filter},
            {'name': 'text_filter', 'enabled': enable_text_filter}
        ]
        
        # 按顺序执行各个过滤器
        for filter_config in filters:
            if not filter_config['enabled']:
                continue
                
            # 获取未被其他过滤器删除的文件
            remaining = [f for f in sorted_files if f not in to_delete]
            if not remaining:
                break
                
            # 根据过滤器名称调用对应的处理函数
            if filter_config['name'] == 'small_image_filter':
                filter_results, filter_reasons = self._process_small_images(remaining, min_size)
            elif filter_config['name'] == 'grayscale_filter':
                filter_results, filter_reasons = self._process_grayscale_images(remaining)
            elif filter_config['name'] == 'duplicate_filter':
                filter_results, filter_reasons = self._process_duplicate_images(
                    remaining, archive_path, temp_dir, image_archive_map, 
                    duplicate_filter_mode, watermark_keywords, ref_hamming_threshold, 
                    lpips_threshold, *args, **kwargs
                )
            elif filter_config['name'] == 'text_filter':
                filter_results, filter_reasons = self._process_text_images(
                    remaining, text_threshold, *args, **kwargs
                )
            else:
                continue
                
            to_delete.update(filter_results)
            removal_reasons.update(filter_reasons)
        
        return to_delete, removal_reasons

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