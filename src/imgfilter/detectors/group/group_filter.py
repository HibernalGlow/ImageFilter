import os
import logging
from typing import List, Dict, Tuple, Set, Union, Optional, Any
import json
import re
from datetime import datetime
from PIL import Image
import pillow_avif
import pillow_jxl
from loguru import logger
from pathlib import Path

# 懒加载OCR模块
from .. import ocr
from ..ocr import OcrDetector


class GroupFilter:
    """相似图片组过滤器，提供多种过滤策略"""
    
    def __init__(self, ocr_cache_file: str = None, ocr_model: str = "ch_PP-OCRv4_rec"):
        """
        初始化相似图片组过滤器
        
        Args:
            ocr_cache_file: OCR结果缓存文件路径
            ocr_model: OCR识别模型名称，默认中文模型
        """
        # 初始化OCR检测器
        self.text_detector = OcrDetector(cache_file=ocr_cache_file, default_model=ocr_model)
        self.ocr_model = ocr_model
        self.available_models = self.text_detector.available_models
    
    def _get_file_info(self, file_path: str) -> dict:
        """获取文件信息（大小、创建时间、修改时间）"""
        try:
            stats = os.stat(file_path)
            return {
                'size': stats.st_size,
                'ctime': stats.st_ctime,  # 创建时间
                'mtime': stats.st_mtime   # 修改时间
            }
        except Exception as e:
            logger.error(f"获取文件信息失败 {file_path}: {e}")
            return {
                'size': 0,
                'ctime': 0,
                'mtime': 0
            }
    
    def _perform_ocr(self, image_path: str, model: str = None) -> List[Tuple]:
        """
        对图片进行OCR识别（使用OcrDetector实例）
        
        Args:
            image_path: 图片路径
            model: OCR模型名称，为None时使用默认模型
            
        Returns:
            List[Tuple]: OCR识别结果
        """
        return self.text_detector.perform_ocr(image_path, model)
    
    def _get_ocr_text(self, image_path: str, model: str = None) -> str:
        """
        获取图片OCR识别的文本内容（使用OcrDetector实例）
        
        Args:
            image_path: 图片路径
            model: OCR模型名称，为None时使用默认模型
            
        Returns:
            str: 合并后的OCR文本
        """
        return self.text_detector.get_ocr_text(image_path, model)
    
    def _analyze_image_text(self, image_path: str) -> Dict:
        """
        分析图片中的文字并返回语言信息（使用OcrDetector实例）
        
        Args:
            image_path: 图片路径
            
        Returns:
            Dict: 文字分析结果
        """
        return self.text_detector.analyze_image_text(image_path)
    
    def _analyze_image_text_density(self, image_path: str) -> Dict:
        """
        分析图片的文字密度（使用OcrDetector实例）
        
        Args:
            image_path: 图片路径
            
        Returns:
            Dict: 文字密度分析结果
        """
        return self.text_detector.calculate_text_density(image_path)
    
    def apply_time_filter(self, group: List[str]) -> List[Tuple[str, str]]:
        """
        应用时间过滤（基于创建/修改时间），返回要删除的图片和原因
        
        Args:
            group: 相似图片组
            
        Returns:
            List[Tuple[str, str]]: (要删除的图片路径, 删除原因)
        """
        to_delete = []
        
        # 获取文件信息
        file_infos = {img: self._get_file_info(img) for img in group}
        
        # 根据修改时间排序，保留最新的
        sorted_by_mtime = sorted(group, key=lambda x: file_infos[x]['mtime'], reverse=True)
        newest_image = sorted_by_mtime[0]
        
        # 删除其他较旧的文件
        for img in group:
            if img != newest_image:
                # 计算时间差（秒）
                time_diff = file_infos[newest_image]['mtime'] - file_infos[img]['mtime']
                # 格式化为人类可读的时间差
                reason = f"修改时间早 {int(time_diff)} 秒"
                to_delete.append((img, reason))
        
        return to_delete
    
    def apply_size_filter(self, group: List[str]) -> List[Tuple[str, str]]:
        """
        应用大小过滤（基于文件大小），返回要删除的图片和原因
        
        Args:
            group: 相似图片组
            
        Returns:
            List[Tuple[str, str]]: (要删除的图片路径, 删除原因)
        """
        to_delete = []
        
        # 获取文件大小
        file_sizes = {img: self._get_file_info(img)['size'] for img in group}
        
        # 保留最大的文件
        largest_image = max(group, key=lambda x: file_sizes[x])
        
        # 删除其他较小的文件
        for img in group:
            if img != largest_image:
                # 计算大小差异
                size_diff = file_sizes[largest_image] - file_sizes[img]
                # 格式化为人类可读的大小差异
                if size_diff > 1024 * 1024:
                    reason = f"文件小 {size_diff / (1024 * 1024):.2f} MB"
                elif size_diff > 1024:
                    reason = f"文件小 {size_diff / 1024:.2f} KB"
                else:
                    reason = f"文件小 {size_diff} 字节"
                to_delete.append((img, reason))
        
        return to_delete
    
    def apply_ocr_filter(self, group: List[str]) -> List[Tuple[str, str]]:
        """
        应用OCR过滤（基于文字识别），返回要删除的图片和原因
        优先级：中文 > 无文字 > 英文 > 日文
        
        Args:
            group: 相似图片组
            
        Returns:
            List[Tuple[str, str]]: (要删除的图片路径, 删除原因)
        """
        to_delete = []
        
        # 分析每张图片的文字
        text_analyses = {}
        density_analyses = {}
        for img in group:
            text_analyses[img] = self._analyze_image_text(img)
            density_analyses[img] = self._analyze_image_text_density(img)
            
            # 记录文本分析结果
            logger.info(f"图片OCR分析 [{os.path.basename(img)}]: "
                       f"语言={text_analyses[img]['language']}, "
                       f"文字数={text_analyses[img]['text_count']}, "
                       f"文字密度={density_analyses[img]['text_density']*100:.2f}%")
        
        # 按语言分类
        lang_groups = {
            'chinese': [],
            'english': [],
            'japanese': [],
            'unknown': []
        }
        
        for img in group:
            lang = text_analyses[img]['language']
            lang_groups[lang].append(img)
        
        # 确定要保留的图片，优先级：中文 > 无文字 > 英文 > 日文
        if lang_groups['chinese']:
            # 如果有中文图片，优先考虑文字密度最高的，其次是文字数量最多的
            chinese_imgs = sorted(lang_groups['chinese'], 
                                 key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                 reverse=True)
            to_keep = chinese_imgs[0]
            keep_lang = 'chinese'
        elif lang_groups['unknown']:
            # 如果没有中文但有无文字图片，保留最大的无文字图片
            to_keep = max(lang_groups['unknown'], 
                          key=lambda x: self._get_file_info(x)['size'])
            keep_lang = 'unknown'
        elif lang_groups['english']:
            # 如果没有中文和无文字但有英文，优先考虑文字密度最高的，其次是文字数量最多的
            english_imgs = sorted(lang_groups['english'], 
                                 key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                 reverse=True)
            to_keep = english_imgs[0]
            keep_lang = 'english'
        elif lang_groups['japanese']:
            # 如果只有日文，优先考虑文字密度最高的，其次是文字数量最多的
            japanese_imgs = sorted(lang_groups['japanese'], 
                                  key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                  reverse=True)
            to_keep = japanese_imgs[0]
            keep_lang = 'japanese'
        else:
            # 如果没有任何识别结果，保留文件大小最大的
            to_keep = max(group, key=lambda x: self._get_file_info(x)['size'])
            keep_lang = 'unknown'
        
        # 删除其他图片
        for img in group:
            if img != to_keep:
                img_lang = text_analyses[img]['language']
                if img_lang == keep_lang:
                    # 同语言，比较文字密度和数量
                    density_diff = density_analyses[to_keep]['text_density'] - density_analyses[img]['text_density']
                    text_diff = text_analyses[to_keep]['text_count'] - text_analyses[img]['text_count']
                    
                    if density_diff > 0.05:  # 密度差异大于5%
                        reason = f"同为{img_lang}，但文字密度低 {density_diff*100:.1f}%"
                    else:
                        reason = f"同为{img_lang}，但文字少 {text_diff} 个"
                else:
                    # 不同语言，基于优先级决定
                    reason = f"语言为{img_lang}，优先保留{keep_lang}"
                
                to_delete.append((img, reason))
        
        return to_delete

    def process_by_time(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        按照时间策略处理相似图片组
        
        Args:
            group: 相似图片组
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        to_delete = set()
        removal_reasons = {}
        
        deleted_files = self.apply_time_filter(group)
        for img, reason in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'time',
                'details': reason
            }
            logger.info(f"标记删除较旧图片: {os.path.basename(img)}")
            
        return to_delete, removal_reasons
    
    def process_by_size(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        按照大小策略处理相似图片组
        
        Args:
            group: 相似图片组
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        to_delete = set()
        removal_reasons = {}
        
        deleted_files = self.apply_size_filter(group)
        for img, reason in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'size',
                'details': reason
            }
            logger.info(f"标记删除较小图片: {os.path.basename(img)}")
            
        return to_delete, removal_reasons
    
    def process_by_ocr(self, group: List[str]) -> List[Tuple[str, str]]:
        """
        应用OCR过滤（基于文字识别），返回要删除的图片和原因
        优先级：中文 > 无文字 > 英文 > 日文
        
        Args:
            group: 相似图片组
            
        Returns:
            List[Tuple[str, str]]: (要删除的图片路径, 删除原因)
        """
        to_delete = []
        
        # 分析每张图片的文字
        text_analyses = {}
        density_analyses = {}
        for img in group:
            text_analyses[img] = self._analyze_image_text(img)
            density_analyses[img] = self._analyze_image_text_density(img)
            
            # 记录文本分析结果
            logger.info(f"图片OCR分析 [{os.path.basename(img)}]: "
                       f"语言={text_analyses[img]['language']}, "
                       f"文字数={text_analyses[img]['text_count']}, "
                       f"文字密度={density_analyses[img]['text_density']*100:.2f}%")
        
        # 按语言分类
        lang_groups = {
            'chinese': [],
            'english': [],
            'japanese': [],
            'unknown': []
        }
        
        for img in group:
            lang = text_analyses[img]['language']
            lang_groups[lang].append(img)
        
        # 确定要保留的图片，优先级：中文 > 无文字 > 英文 > 日文
        if lang_groups['chinese']:
            # 如果有中文图片，优先考虑文字密度最高的，其次是文字数量最多的
            chinese_imgs = sorted(lang_groups['chinese'], 
                                 key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                 reverse=True)
            to_keep = chinese_imgs[0]
            keep_lang = 'chinese'
        elif lang_groups['unknown']:
            # 如果没有中文但有无文字图片，保留最大的无文字图片
            to_keep = max(lang_groups['unknown'], 
                          key=lambda x: self._get_file_info(x)['size'])
            keep_lang = 'unknown'
        elif lang_groups['english']:
            # 如果没有中文和无文字但有英文，优先考虑文字密度最高的，其次是文字数量最多的
            english_imgs = sorted(lang_groups['english'], 
                                 key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                 reverse=True)
            to_keep = english_imgs[0]
            keep_lang = 'english'
        elif lang_groups['japanese']:
            # 如果只有日文，优先考虑文字密度最高的，其次是文字数量最多的
            japanese_imgs = sorted(lang_groups['japanese'], 
                                  key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                  reverse=True)
            to_keep = japanese_imgs[0]
            keep_lang = 'japanese'
        else:
            # 如果没有任何识别结果，保留文件大小最大的
            to_keep = max(group, key=lambda x: self._get_file_info(x)['size'])
            keep_lang = 'unknown'
        
        # 删除其他图片
        for img in group:
            if img != to_keep:
                img_lang = text_analyses[img]['language']
                if img_lang == keep_lang:
                    # 同语言，比较文字密度和数量
                    density_diff = density_analyses[to_keep]['text_density'] - density_analyses[img]['text_density']
                    text_diff = text_analyses[to_keep]['text_count'] - text_analyses[img]['text_count']
                    
                    if density_diff > 0.05:  # 密度差异大于5%
                        reason = f"同为{img_lang}，但文字密度低 {density_diff*100:.1f}%"
                    else:
                        reason = f"同为{img_lang}，但文字少 {text_diff} 个"
                else:
                    # 不同语言，基于优先级决定
                    reason = f"语言为{img_lang}，优先保留{keep_lang}"
                
                to_delete.append((img, reason))
        
        return to_delete

    def process_by_ocr_time(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        混合策略处理相似图片组（结合OCR和时间）
        
        Args:
            group: 相似图片组
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        # 先按OCR过滤
        ocr_to_delete, ocr_reasons = self.process_by_ocr(group)
        
        # 如果OCR过滤后只剩一张或没有，直接返回结果
        remaining = [img for img in group if img not in ocr_to_delete]
        if len(remaining) <= 1:
            return ocr_to_delete, ocr_reasons
        
        # 对剩余图片进行时间过滤
        time_to_delete, time_reasons = self.process_by_time(remaining)
        
        # 合并结果
        to_delete = ocr_to_delete | time_to_delete
        removal_reasons = {**ocr_reasons, **time_reasons}
        
        return to_delete, removal_reasons
    
    def process_by_ocr_size(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        混合策略处理相似图片组（结合OCR和大小）
        
        Args:
            group: 相似图片组
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        # 先按OCR过滤
        ocr_to_delete, ocr_reasons = self.process_by_ocr(group)
        
        # 如果OCR过滤后只剩一张或没有，直接返回结果
        remaining = [img for img in group if img not in ocr_to_delete]
        if len(remaining) <= 1:
            return ocr_to_delete, ocr_reasons
        
        # 对剩余图片进行大小过滤
        size_to_delete, size_reasons = self.process_by_size(remaining)
        
        # 合并结果
        to_delete = ocr_to_delete | size_to_delete
        removal_reasons = {**ocr_reasons, **size_reasons}
        
        return to_delete, removal_reasons
    
    def process_by_time_size(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        混合策略处理相似图片组（结合时间和大小）
        
        Args:
            group: 相似图片组
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        # 先按时间过滤
        time_to_delete, time_reasons = self.process_by_time(group)
        
        # 如果时间过滤后只剩一张或没有，直接返回结果
        remaining = [img for img in group if img not in time_to_delete]
        if len(remaining) <= 1:
            return time_to_delete, time_reasons
        
        # 对剩余图片进行大小过滤
        size_to_delete, size_reasons = self.process_by_size(remaining)
        
        # 合并结果
        to_delete = time_to_delete | size_to_delete
        removal_reasons = {**time_reasons, **size_reasons}
        
        return to_delete, removal_reasons
    
    def process_by_hybrid(self, group: List[str], mode: str = "ocr_time_size") -> Tuple[Set[str], Dict[str, Dict]]:
        """
        混合策略处理相似图片组（可配置过滤顺序）
        
        Args:
            group: 相似图片组
            mode: 过滤模式，可选值:
                 - "ocr_time_size": 先OCR，再时间，最后大小
                 - "ocr_size_time": 先OCR，再大小，最后时间
                 - "time_ocr_size": 先时间，再OCR，最后大小
                 - "time_size_ocr": 先时间，再大小，最后OCR
                 - "size_ocr_time": 先大小，再OCR，最后时间
                 - "size_time_ocr": 先大小，再时间，最后OCR
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        # 解析模式
        filters = mode.lower().split('_')
        if not all(f in ['ocr', 'time', 'size'] for f in filters) or len(filters) != 3:
            logger.warning(f"无效的过滤模式: {mode}，使用默认模式 ocr_time_size")
            filters = ['ocr', 'time', 'size']
        
        to_delete = set()
        removal_reasons = {}
        remaining = group.copy()
        
        # 按顺序应用过滤器
        for filter_type in filters:
            if len(remaining) <= 1:
                break
                
            if filter_type == 'ocr':
                filter_func = self.process_by_ocr
            elif filter_type == 'time':
                filter_func = self.process_by_time
            else:  # size
                filter_func = self.process_by_size
            
            # 应用过滤器
            step_to_delete, step_reasons = filter_func(remaining)
            
            # 更新结果
            to_delete.update(step_to_delete)
            removal_reasons.update(step_reasons)
            
            # 更新剩余图片
            remaining = [img for img in remaining if img not in step_to_delete]
        
        return to_delete, removal_reasons
    
    def process_by_config(self, group: List[str], config: List[Dict[str, Any]]) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        根据配置字典处理相似图片组，支持灵活配置过滤器顺序和参数
        
        配置字典格式示例:
        [
            {"type": "ocr", "params": {"model": "ch_PP-OCRv4_rec"}},
            {"type": "time", "params": {}},
            {"type": "size", "params": {}}
        ]
        
        Args:
            group: 相似图片组
            config: 过滤器配置列表，每个元素包含过滤器类型和参数
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        if not config:
            logger.warning("过滤配置为空，使用默认OCR过滤")
            return self.process_by_ocr(group)
            
        to_delete = set()
        removal_reasons = {}
        remaining = group.copy()
        
        # 按配置顺序应用过滤器
        for filter_config in config:
            if len(remaining) <= 1:
                break
                
            filter_type = filter_config.get("type", "").lower()
            params = filter_config.get("params", {})
            
            if filter_type == "ocr":
                # 处理OCR过滤器参数
                ocr_model = params.get("model", self.ocr_model)
                # 如果需要临时切换OCR模型
                old_model = self.ocr_model
                if ocr_model != self.ocr_model:
                    self.ocr_model = ocr_model
                
                # 应用OCR过滤
                step_to_delete, step_reasons = self.process_by_ocr(remaining)
                
                # 恢复原始OCR模型
                if ocr_model != old_model:
                    self.ocr_model = old_model
                    
            elif filter_type == "time":
                # 应用时间过滤
                step_to_delete, step_reasons = self.process_by_time(remaining)
                
            elif filter_type == "size":
                # 应用大小过滤
                step_to_delete, step_reasons = self.process_by_size(remaining)
                
            else:
                logger.warning(f"未知的过滤器类型: {filter_type}，跳过")
                continue
            
            # 更新结果
            to_delete.update(step_to_delete)
            removal_reasons.update(step_reasons)
            
            # 更新剩余图片
            remaining = [img for img in remaining if img not in step_to_delete]
            
            # 记录日志
            logger.info(f"应用 {filter_type} 过滤器后剩余 {len(remaining)} 张图片")
        
        return to_delete, removal_reasons


def test_group_filter_ocr(test_dir: str = None):
    """
    测试相似图片组过滤器的OCR功能
    
    Args:
        test_dir: 测试图片目录，默认为脚本所在目录下的test_images
    """
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    test_dir = Path(test_dir) if test_dir else script_dir / "test_images"
    
    # 确保测试目录存在
    test_dir.mkdir(exist_ok=True)
    
    # 检查测试目录中的图片
    image_files = []
    for ext in ('.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif'):
        image_files.extend([str(p) for p in test_dir.glob(f"*{ext}")])
    
    if not image_files:
        logger.error(f"测试目录 {test_dir} 中没有找到图片文件")
        logger.info("请将测试图片放在以下目录中：")
        logger.info(str(test_dir))
        return
    
    # 创建过滤器实例
    filter = GroupFilter()
    
    # 对所有图片进行OCR分析
    logger.info(f"开始OCR分析，共 {len(image_files)} 张图片...")
    
    # 模拟相似图片组
    similar_groups = [image_files]
    
    # 测试不同的过滤策略
    filter_modes = [
        ("OCR过滤", filter.process_by_ocr),
        ("时间过滤", filter.process_by_time),
        ("大小过滤", filter.process_by_size),
        ("OCR+时间混合过滤", filter.process_by_ocr_time),
        ("OCR+大小混合过滤", filter.process_by_ocr_size),
        ("时间+大小混合过滤", filter.process_by_time_size)
    ]
    
    # 对每个相似组应用不同的过滤策略
    for group in similar_groups:
        logger.info(f"\n处理相似图片组，共 {len(group)} 张图片")
        
        # 分析每张图片的OCR结果和文字密度
        for img in group:
            analysis = filter._analyze_image_text(img)
            density = filter._analyze_image_text_density(img)
            
            logger.info(f"图片 [{os.path.basename(img)}] OCR分析结果:")
            logger.info(f"  语言: {analysis['language']}")
            logger.info(f"  文字数量: {analysis['text_count']}")
            logger.info(f"  文字内容: {analysis['text'][:100]}..." if len(analysis['text']) > 100 else analysis['text'])
            logger.info(f"  文字密度: {density['text_density']*100:.2f}%")
            logger.info(f"  字符密度: {density['char_density']:.2f} 字符/千像素")
        
        # 测试不同过滤策略
        for mode_name, filter_func in filter_modes:
            logger.info(f"\n应用 {mode_name}:")
            to_delete, reasons = filter_func(group)
            
            if to_delete:
                logger.info(f"  标记删除 {len(to_delete)} 张图片:")
                for img in to_delete:
                    reason = reasons[img]
                    logger.info(f"  - {os.path.basename(img)}: {reason['reason']} ({reason['details']})")
            else:
                logger.info(f"  没有图片被标记删除")
        
        # 测试混合过滤策略
        logger.info("\n应用自定义混合过滤策略 (OCR->时间->大小):")
        to_delete, reasons = filter.process_by_hybrid(group, "ocr_time_size")
        if to_delete:
            logger.info(f"  标记删除 {len(to_delete)} 张图片:")
            for img in to_delete:
                reason = reasons[img]
                logger.info(f"  - {os.path.basename(img)}: {reason['reason']} ({reason['details']})")
        else:
            logger.info(f"  没有图片被标记删除")


def process_group_with_filters(group: List[str], config: Union[str, List[Dict[str, Any]]] = None, 
                              ocr_model: str = "ch_PP-OCRv4_rec") -> Tuple[Set[str], Dict[str, Dict]]:
    """
    使用过滤器处理相似图片组，提供给duplicate.py调用的便捷函数
    
    Args:
        group: 相似图片组
        config: 过滤配置，可以是:
                - 字符串: 预定义的过滤模式，如 "ocr", "time", "size", "ocr_time", 等
                - 列表: 详细的过滤器配置列表
                - None: 默认使用OCR过滤
        ocr_model: OCR识别模型名称
        
    Returns:
        Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
    """
    # 创建过滤器实例
    filter_instance = GroupFilter(ocr_model=ocr_model)
    
    # 处理配置
    if config is None:
        # 默认使用OCR过滤
        return filter_instance.process_by_ocr(group)
    elif isinstance(config, str):
        # 预定义的过滤模式
        mode = config.lower()
        if mode == "ocr":
            return filter_instance.process_by_ocr(group)
        elif mode == "time":
            return filter_instance.process_by_time(group)
        elif mode == "size":
            return filter_instance.process_by_size(group)
        elif mode == "ocr_time":
            return filter_instance.process_by_ocr_time(group)
        elif mode == "ocr_size":
            return filter_instance.process_by_ocr_size(group)
        elif mode == "time_size":
            return filter_instance.process_by_time_size(group)
        else:
            # 尝试作为混合模式处理
            return filter_instance.process_by_hybrid(group, mode)
    else:
        # 详细的过滤器配置列表
        return filter_instance.process_by_config(group, config)


if __name__ == "__main__":
    test_group_filter_ocr()
