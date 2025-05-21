"""
ImgFilter核心过滤器模块
"""
import os
import logging
from typing import List, Set, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from pathlib import Path
from loguru import logger

# 导入检测器工厂
from imgfilter.detectors.factory import DetectorFactory

class ImageFilter:
    """图片过滤器，支持多种独立的过滤功能"""
    
    def __init__(self, hash_file: str = None, hamming_threshold: int = 12, ref_hamming_threshold: int = None, max_workers: int = None, config_file: str = None):
        """
        初始化过滤器
        
        Args:
            hash_file: 哈希文件路径
            hamming_threshold: 汉明距离阈值
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值，默认使用hamming_threshold
            max_workers: 最大工作线程数，默认为CPU核心数
            config_file: 检测器配置文件路径，可以是JSON或TOML格式
        """
        self.hash_file = hash_file
        self.hamming_threshold = hamming_threshold
        self.ref_hamming_threshold = ref_hamming_threshold if ref_hamming_threshold is not None else hamming_threshold
        
        # 加载配置文件
        if config_file:
            self._load_config(config_file)
        else:
            # 默认配置文件路径
            default_config_files = [
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "detector_config.toml"),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "detector_config.json")
            ]
            
            # 尝试加载默认配置文件
            for cfg_file in default_config_files:
                if os.path.exists(cfg_file):
                    try:
                        self._load_config(cfg_file)
                        logger.info(f"[#cur_stats]已加载默认检测器配置: {cfg_file}")
                        break
                    except Exception as e:
                        logger.error(f"[#update_log]❌ 加载默认配置文件失败: {str(e)}")
                        
        # 使用工厂创建检测器实例
        self.watermark_detector = DetectorFactory.create_detector(DetectorFactory.WATERMARK)
        self.text_detector = DetectorFactory.create_detector(DetectorFactory.TEXT)
        self.duplicate_detector = DetectorFactory.create_detector(
            DetectorFactory.DUPLICATE,
            hash_file=hash_file, 
            hamming_threshold=hamming_threshold, 
            ref_hamming_threshold=ref_hamming_threshold,
            max_workers=max_workers
        )
        self.small_image_detector = DetectorFactory.create_detector(DetectorFactory.SMALL)
        self.grayscale_detector = DetectorFactory.create_detector(DetectorFactory.GRAYSCALE)
        
        self.max_workers = max_workers or multiprocessing.cpu_count()
    
    def _load_config(self, config_file: str):
        """
        加载检测器配置文件
        
        Args:
            config_file: 配置文件路径，支持JSON和TOML格式
        """
        try:
            DetectorFactory.configure_from_file(config_file)
            logger.info(f"[#cur_stats]已加载检测器配置: {config_file}")
        except Exception as e:
            logger.error(f"[#update_log]❌ 加载配置文件失败: {str(e)}")
            raise
        
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
            duplicate_filter_mode: 重复图片过滤模式 ('quality', 'watermark' 或 'hash')
            watermark_keywords: 水印关键词列表，None时使用默认列表
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值，None时使用初始化时的值
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
        
        # 定义过滤器配置
        filters = [
            # 阶段1: 小图过滤
            {
                'name': 'small_image_filter',
                'enabled': enable_small_filter,
                'parallel': True,
                'processor': lambda files: self.small_image_detector.detect_small_images(files, min_size)
            },
            # 阶段2: 灰度图过滤
            {
                'name': 'grayscale_filter',
                'enabled': enable_grayscale_filter,
                'parallel': True,
                'processor': lambda files: self.grayscale_detector.detect_grayscale_images(files)
            },
            # 阶段3: 重复图片过滤
            {
                'name': 'duplicate_filter',
                'enabled': enable_duplicate_filter,
                'parallel': True,
                'processor': lambda files: self.duplicate_detector.detect_duplicates(
                    files,
                    archive_path=archive_path,
                    temp_dir=temp_dir,
                    image_archive_map=image_archive_map,
                    mode=duplicate_filter_mode,
                    watermark_keywords=watermark_keywords,
                    ref_hamming_threshold=ref_hamming_threshold,
                    *args,
                    **kwargs
                )
            },
            # 阶段4: 纯文本图片过滤
            {
                'name': 'text_filter',
                'enabled': enable_text_filter,
                'parallel': True,
                'processor': lambda files: self.text_detector.process_text_images(
                    files, 
                    threshold=text_threshold,
                    *args,
                    **kwargs
                )
            }
        ]
        
        # 执行所有过滤器
        for filter_config in filters:
            if not filter_config['enabled']:
                continue
                
            # 获取未被其他过滤器删除的文件
            remaining = [f for f in sorted_files if f not in to_delete]
            if not remaining:
                break
                
            if filter_config.get('parallel', False):
                # 并行处理过滤器
                if filter_config['enabled']:
                    # 使用 ThreadPoolExecutor 代替 threaded 装饰器
                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        logger.info(f"[#cur_stats]开始并行处理{filter_config['name']} 线程数: {self.max_workers}")
                        futures = []
                        futures.append(executor.submit(filter_config['processor'], remaining))
                        
                        for future in as_completed(futures):
                            try:
                                task_to_delete, task_reasons = future.result()
                                to_delete.update(task_to_delete)
                                removal_reasons.update(task_reasons)
                            except Exception as e:
                                logger.error(f"[#update_log]❌ 过滤器执行错误: {str(e)}")
            else:
                # 顺序处理单个过滤器
                filter_results, filter_reasons = filter_config['processor'](remaining)
                to_delete.update(filter_results)
                removal_reasons.update(filter_reasons)
        
        return to_delete, removal_reasons

