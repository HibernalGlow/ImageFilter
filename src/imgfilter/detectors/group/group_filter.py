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
import time

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
        logger.info(f"初始化GroupFilter，OCR模型: {ocr_model}")
        logger.debug(f"OCR缓存文件: {ocr_cache_file or '未指定'}")
        
        # 初始化OCR检测器
        try:
            self.text_detector = OcrDetector(cache_file=ocr_cache_file, default_model=ocr_model)
            self.ocr_model = ocr_model
            self.available_models = self.text_detector.available_models
            logger.info(f"OCR检测器初始化成功，可用模型: {len(self.available_models)}个")
            logger.debug(f"可用OCR模型列表: {self.available_models}")
        except Exception as e:
            logger.error(f"OCR检测器初始化失败: {e}")
            raise
    
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
        start_time = time.time()
        logger.info(f"开始时间过滤，输入图片数量: {len(group)}")
        to_delete = []
        
        if len(group) <= 1:
            logger.debug("图片数量不足，跳过时间过滤")
            return to_delete
        
        # 获取文件信息
        logger.debug("获取文件时间信息...")
        file_infos = {img: self._get_file_info(img) for img in group}
        
        # 根据修改时间排序，保留最新的
        sorted_by_mtime = sorted(group, key=lambda x: file_infos[x]['mtime'], reverse=True)
        newest_image = sorted_by_mtime[0]
        
        logger.debug(f"最新图片: {os.path.basename(newest_image)}，修改时间: {datetime.fromtimestamp(file_infos[newest_image]['mtime'])}")
        
        for img in group:
            if img != newest_image:
                # 计算时间差（秒）
                time_diff = file_infos[newest_image]['mtime'] - file_infos[img]['mtime']
                # 格式化为人类可读的时间差
                reason = f"修改时间早 {int(time_diff)} 秒"
                to_delete.append((img, reason))
                logger.debug(f"标记删除: {os.path.basename(img)} - {reason}")
        
        elapsed = time.time() - start_time
        logger.info(f"时间过滤完成，耗时: {elapsed:.3f}秒，删除 {len(to_delete)}/{len(group)} 张图片")
        return to_delete
    def apply_size_filter(self, group: List[str]) -> List[Tuple[str, str]]:
        """
        应用大小过滤（基于文件大小），返回要删除的图片和原因
        
        Args:
            group: 相似图片组
            
        Returns:
            List[Tuple[str, str]]: (要删除的图片路径, 删除原因)
        """
        start_time = time.time()
        logger.info(f"开始大小过滤，输入图片数量: {len(group)}")
        to_delete = []
        
        if len(group) <= 1:
            logger.debug("图片数量不足，跳过大小过滤")
            return to_delete
        
        # 获取文件大小
        logger.debug("获取文件大小信息...")
        file_sizes = {img: self._get_file_info(img)['size'] for img in group}
        
        # 保留最大的文件
        largest_image = max(group, key=lambda x: file_sizes[x])
        largest_size = file_sizes[largest_image]
        
        logger.debug(f"最大文件: {os.path.basename(largest_image)}，大小: {largest_size / (1024*1024):.2f} MB")
        
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
                logger.debug(f"标记删除: {os.path.basename(img)} - {reason}")
        
        elapsed = time.time() - start_time
        logger.info(f"大小过滤完成，耗时: {elapsed:.3f}秒，删除 {len(to_delete)}/{len(group)} 张图片")
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
        start_time = time.time()
        logger.info(f"开始OCR过滤，输入图片数量: {len(group)}")
        to_delete = []
        
        if len(group) <= 1:
            logger.debug("图片数量不足，跳过OCR过滤")
            return to_delete
        
        # 分析每张图片的文字
        logger.info("开始OCR文字分析...")
        text_analyses = {}
        density_analyses = {}
        for img in group:
            logger.debug(f"分析图片: {os.path.basename(img)}")
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
        
        logger.debug(f"语言分组结果: 中文{len(lang_groups['chinese'])}张, "
                    f"英文{len(lang_groups['english'])}张, "
                    f"日文{len(lang_groups['japanese'])}张, "
                    f"无文字{len(lang_groups['unknown'])}张")
        
        # 确定要保留的图片，优先级：中文 > 无文字 > 英文 > 日文
        if lang_groups['chinese']:
            # 如果有中文图片，优先考虑文字密度最高的，其次是文字数量最多的
            chinese_imgs = sorted(lang_groups['chinese'], 
                                 key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                 reverse=True)
            to_keep = chinese_imgs[0]
            keep_lang = 'chinese'
            logger.info(f"选择保留中文图片: {os.path.basename(to_keep)}")
        elif lang_groups['unknown']:
            # 如果没有中文但有无文字图片，保留最大的无文字图片
            to_keep = max(lang_groups['unknown'], 
                          key=lambda x: self._get_file_info(x)['size'])
            keep_lang = 'unknown'
            logger.info(f"选择保留无文字图片: {os.path.basename(to_keep)}")
        elif lang_groups['english']:
            # 如果没有中文和无文字但有英文，优先考虑文字密度最高的，其次是文字数量最多的
            english_imgs = sorted(lang_groups['english'], 
                                 key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                 reverse=True)
            to_keep = english_imgs[0]
            keep_lang = 'english'
            logger.info(f"选择保留英文图片: {os.path.basename(to_keep)}")
        elif lang_groups['japanese']:
            # 如果只有日文，优先考虑文字密度最高的，其次是文字数量最多的
            japanese_imgs = sorted(lang_groups['japanese'], 
                                  key=lambda x: (density_analyses[x]['text_density'], text_analyses[x]['text_count']),
                                  reverse=True)
            to_keep = japanese_imgs[0]
            keep_lang = 'japanese'
            logger.info(f"选择保留日文图片: {os.path.basename(to_keep)}")
        else:
            # 如果没有任何识别结果，保留文件大小最大的
            to_keep = max(group, key=lambda x: self._get_file_info(x)['size'])
            keep_lang = 'unknown'
            logger.warning(f"无法识别任何文字，保留最大文件: {os.path.basename(to_keep)}")
        
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
                logger.debug(f"标记删除: {os.path.basename(img)} - {reason}")
        
        elapsed = time.time() - start_time
        logger.info(f"OCR过滤完成，耗时: {elapsed:.3f}秒，删除 {len(to_delete)}/{len(group)} 张图片")
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
        start_time = time.time()
        logger.info(f"开始混合过滤策略，模式: {mode}，输入图片数量: {len(group)}")
        
        # 解析模式
        filters = mode.lower().split('_')
        if not all(f in ['ocr', 'time', 'size'] for f in filters) or len(filters) != 3:
            logger.warning(f"无效的过滤模式: {mode}，使用默认模式 ocr_time_size")
            filters = ['ocr', 'time', 'size']
        
        logger.debug(f"过滤顺序: {' -> '.join(filters)}")
        
        to_delete = set()
        removal_reasons = {}
        remaining = group.copy()
        
        # 按顺序应用过滤器
        for i, filter_type in enumerate(filters, 1):
            if len(remaining) <= 1:
                logger.debug(f"剩余图片数量不足(≤1)，提前结束过滤")
                break
                
            logger.info(f"第{i}步：应用 {filter_type} 过滤器，当前剩余 {len(remaining)} 张图片")
            
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
            
            logger.info(f"第{i}步完成：{filter_type} 过滤器删除了 {len(step_to_delete)} 张图片，剩余 {len(remaining)} 张")
        
        elapsed = time.time() - start_time
        logger.info(f"混合过滤完成，总耗时: {elapsed:.3f}秒，最终删除 {len(to_delete)}/{len(group)} 张图片")
        
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

    def _get_image_dimensions(self, image_path: str) -> Tuple[int, int]:
        """
        获取图片尺寸（宽度×高度）
        
        Args:
            image_path: 图片路径
            
        Returns:
            Tuple[int, int]: (宽度, 高度)，获取失败时返回(0, 0)
        """
        try:
            with Image.open(image_path) as img:
                return img.size  # PIL返回的是(width, height)
        except Exception as e:
            logger.error(f"获取图片尺寸失败 {image_path}: {e}")
            return (0, 0)
    
    def _get_image_pixel_count(self, image_path: str) -> int:
        """
        获取图片像素数量（总像素）
        
        Args:
            image_path: 图片路径
            
        Returns:
            int: 像素数量，获取失败时返回0
        """        
        try:
            width, height = self._get_image_dimensions(image_path)
            return width * height
        except Exception as e:
            logger.error(f"获取图片像素数量失败 {image_path}: {e}")
            return 0
    
    def _filter_by_dimensions(self, remaining_images: List[str], image_info: Dict[str, Dict]) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        按图片尺寸进行过滤（第一档位）
        
        Args:
            remaining_images: 剩余待过滤的图片列表
            image_info: 图片信息字典
            
        Returns:
            Tuple[List[str], List[Tuple[str, str]]]: (过滤后剩余图片, 要删除的图片和原因)
        """
        to_delete = []
        
        if len(remaining_images) <= 1:
            return remaining_images, to_delete
        
        # 按像素数量分组
        pixel_groups = {}
        for img in remaining_images:
            pixel_count = image_info[img]['pixel_count']
            if pixel_count not in pixel_groups:
                pixel_groups[pixel_count] = []
            pixel_groups[pixel_count].append(img)
        
        # 找到最大像素数量
        max_pixels = max(pixel_groups.keys()) if pixel_groups else 0
        
        # 如果最大像素数量组只有一张图片，保留它，删除其他的
        if max_pixels > 0 and len(pixel_groups[max_pixels]) == 1:
            keep_image = pixel_groups[max_pixels][0]
            for img in remaining_images:
                if img != keep_image:
                    keep_dims = image_info[keep_image]['dimensions']
                    current_dims = image_info[img]['dimensions']
                    reason = f"尺寸小 {current_dims[0]}×{current_dims[1]} < {keep_dims[0]}×{keep_dims[1]}"
                    to_delete.append((img, reason))
            return [keep_image], to_delete
        
        # 如果最大像素数量组有多张图片，保留这组图片，删除其他的
        elif max_pixels > 0 and len(pixel_groups[max_pixels]) > 1:
            new_remaining = pixel_groups[max_pixels]
            for pixel_count, imgs in pixel_groups.items():
                if pixel_count < max_pixels:
                    for img in imgs:
                        # 选择最大组中的任意一张作为参考
                        ref_img = new_remaining[0]
                        keep_dims = image_info[ref_img]['dimensions']
                        current_dims = image_info[img]['dimensions']
                        reason = f"尺寸小 {current_dims[0]}×{current_dims[1]} < {keep_dims[0]}×{keep_dims[1]}"
                        to_delete.append((img, reason))
            return new_remaining, to_delete
        
        return remaining_images, to_delete
    
    def _filter_by_file_size(self, remaining_images: List[str], image_info: Dict[str, Dict]) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        按文件大小进行过滤（第二档位）
        
        Args:
            remaining_images: 剩余待过滤的图片列表
            image_info: 图片信息字典
            
        Returns:
            Tuple[List[str], List[Tuple[str, str]]]: (过滤后剩余图片, 要删除的图片和原因)
        """
        to_delete = []
        
        if len(remaining_images) <= 1:
            return remaining_images, to_delete
        
        # 按文件大小分组
        size_groups = {}
        for img in remaining_images:
            file_size = image_info[img]['file_size']
            if file_size not in size_groups:
                size_groups[file_size] = []
            size_groups[file_size].append(img)
        
        # 找到最大文件大小
        max_size = max(size_groups.keys()) if size_groups else 0
        
        # 如果最大文件大小组只有一张图片，保留它，删除其他的
        if max_size > 0 and len(size_groups[max_size]) == 1:
            keep_image = size_groups[max_size][0]
            for img in remaining_images:
                if img != keep_image:
                    size_diff = max_size - image_info[img]['file_size']
                    if size_diff > 1024 * 1024:
                        reason = f"同尺寸但文件小 {size_diff / (1024 * 1024):.2f} MB"
                    elif size_diff > 1024:
                        reason = f"同尺寸但文件小 {size_diff / 1024:.2f} KB"
                    else:
                        reason = f"同尺寸但文件小 {size_diff} 字节"
                    to_delete.append((img, reason))
            return [keep_image], to_delete
        
        # 如果最大文件大小组有多张图片，保留这组图片，删除其他的
        elif max_size > 0 and len(size_groups[max_size]) > 1:
            new_remaining = size_groups[max_size]
            for file_size, imgs in size_groups.items():
                if file_size < max_size:
                    for img in imgs:
                        size_diff = max_size - file_size
                        if size_diff > 1024 * 1024:
                            reason = f"同尺寸但文件小 {size_diff / (1024 * 1024):.2f} MB"
                        elif size_diff > 1024:
                            reason = f"同尺寸但文件小 {size_diff / 1024:.2f} KB"
                        else:
                            reason = f"同尺寸但文件小 {size_diff} 字节"
                        to_delete.append((img, reason))
            return new_remaining, to_delete
        
        return remaining_images, to_delete
    
    def _filter_by_filename(self, remaining_images: List[str], image_info: Dict[str, Dict], reverse_filename: bool = False) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        按文件名进行过滤（第三档位）
        
        Args:
            remaining_images: 剩余待过滤的图片列表
            image_info: 图片信息字典
            reverse_filename: 是否反向排序（True=保留名称大的，False=保留名称小的）
            
        Returns:
            Tuple[List[str], List[Tuple[str, str]]]: (过滤后剩余图片, 要删除的图片和原因)
        """
        to_delete = []
        
        if len(remaining_images) <= 1:
            return remaining_images, to_delete
        
        # 按文件名排序
        if reverse_filename:
            # 保留名称大的（字典序靠后的）
            sorted_by_name = sorted(remaining_images, 
                                  key=lambda x: image_info[x]['filename'], reverse=True)
        else:
            # 保留名称小的（字典序靠前的）
            sorted_by_name = sorted(remaining_images, 
                                  key=lambda x: image_info[x]['filename'])
        
        keep_image = sorted_by_name[0]
        for img in remaining_images:
            if img != keep_image:
                keep_name = image_info[keep_image]['filename']
                current_name = image_info[img]['filename']
                if reverse_filename:
                    reason = f"同尺寸同大小但文件名小: {current_name} < {keep_name}"
                else:
                    reason = f"同尺寸同大小但文件名大: {current_name} > {keep_name}"
                to_delete.append((img, reason))
        
        return [keep_image], to_delete

    def apply_comprehensive_filter(self, group: List[str], filter_config: Dict[str, Union[bool, List[str]]] = None) -> List[Tuple[str, str]]:
        """
        应用综合过滤策略，逐档位进行过滤
        
        逐档位过滤逻辑：默认只用dimensions档位，尺寸相同或无法比较时切到下一档位，以此类推
        
        Args:
            group: 相似图片组
            filter_config: 过滤配置字典，支持以下选项：
                          {
                              'enable_progressive': True,       # 是否启用逐档位过滤模式
                              'use_dimensions': True,           # 是否使用图片尺寸（像素数量）
                              'use_file_size': True,            # 是否使用文件大小
                              'use_filename': True,             # 是否使用文件名
                              'reverse_filename': False,        # 文件名排序是否反向（True=保留名称大的，False=保留名称小的）
                              'filter_order': ['dimensions', 'file_size', 'filename']  # 过滤器顺序
                          }
            
        Returns:
            List[Tuple[str, str]]: (要删除的图片路径, 删除原因)
        """
        start_time = time.time()
        logger.info(f"开始综合过滤，输入图片数量: {len(group)}")
        
        # 默认配置
        default_config = {
            'enable_progressive': True,          # 启用逐档位过滤
            'use_dimensions': True,              # 启用尺寸过滤
            'use_file_size': True,               # 启用文件大小过滤
            'use_filename': True,                # 启用文件名过滤
            'reverse_filename': False,           # False表示保留名称小的
            'filter_order': ['dimensions', 'file_size', 'filename']  # 默认过滤顺序
        }
        
        # 合并用户配置
        config = default_config.copy()
        if filter_config:
            config.update(filter_config)
            logger.debug(f"使用自定义配置: {filter_config}")
        
        logger.debug(f"最终配置: {config}")
        
        # 收集所有图片的信息
        logger.debug("收集图片信息...")
        image_info = {}
        for img in group:
            info = {}
            
            # 获取图片尺寸信息
            info['pixel_count'] = self._get_image_pixel_count(img)
            info['dimensions'] = self._get_image_dimensions(img)
            
            # 获取文件大小信息
            file_info = self._get_file_info(img)
            info['file_size'] = file_info['size']
            
            # 获取文件名信息
            info['filename'] = os.path.basename(img).lower()  # 转小写进行比较
            
            image_info[img] = info
            logger.debug(f"图片信息 [{os.path.basename(img)}]: "
                        f"尺寸={info['dimensions'][0]}×{info['dimensions'][1]}, "
                        f"大小={info['file_size'] / (1024*1024):.2f}MB, "
                        f"文件名={info['filename']}")
        
        # 如果未启用逐档位过滤，使用传统的综合排序
        if not config.get('enable_progressive', True):
            logger.info("使用传统综合过滤模式")
            result = self._apply_traditional_comprehensive_filter(group, image_info, config)
        else:
            logger.info(f"使用逐档位过滤模式，顺序: {' -> '.join(config.get('filter_order', []))}")
            
            # 逐档位过滤逻辑
            remaining_images = group.copy()
            all_to_delete = []
            
            # 根据配置的顺序应用过滤器
            filter_order = config.get('filter_order', ['dimensions', 'file_size', 'filename'])
            
            for i, filter_type in enumerate(filter_order, 1):
                if len(remaining_images) <= 1:
                    logger.debug(f"剩余图片数量不足(≤1)，提前结束档位过滤")
                    break
                    
                logger.info(f"第{i}档位：{filter_type} 过滤，当前剩余 {len(remaining_images)} 张图片")
                
                if filter_type == 'dimensions' and config.get('use_dimensions', True):
                    remaining_images, to_delete = self._filter_by_dimensions(remaining_images, image_info)
                    all_to_delete.extend(to_delete)
                    
                elif filter_type == 'file_size' and config.get('use_file_size', True):
                    remaining_images, to_delete = self._filter_by_file_size(remaining_images, image_info)
                    all_to_delete.extend(to_delete)
                    
                elif filter_type == 'filename' and config.get('use_filename', True):
                    remaining_images, to_delete = self._filter_by_filename(
                        remaining_images, image_info, config.get('reverse_filename', False)
                    )
                    all_to_delete.extend(to_delete)
                
                logger.info(f"第{i}档位完成：删除了 {len(to_delete)} 张图片，剩余 {len(remaining_images)} 张")
            
            result = all_to_delete
        
        elapsed = time.time() - start_time
        logger.info(f"综合过滤完成，耗时: {elapsed:.3f}秒，删除 {len(result)}/{len(group)} 张图片")
        
        return result

    def _apply_traditional_comprehensive_filter(self, group: List[str], image_info: Dict[str, Dict], config: Dict) -> List[Tuple[str, str]]:
        """
        应用传统的综合过滤策略（非逐档位）
        
        Args:
            group: 相似图片组
            image_info: 图片信息字典
            config: 配置字典
            
        Returns:
            List[Tuple[str, str]]: (要删除的图片路径, 删除原因)
        """
        # 构建排序键函数
        def get_sort_key(img_path):
            info = image_info[img_path]
            key_parts = []
            
            # 尺寸优先级（像素数量，越大越好，所以用负值排序）
            if config.get('use_dimensions', True):
                key_parts.append(-info.get('pixel_count', 0))
            
            # 文件大小优先级（越大越好，所以用负值排序）
            if config.get('use_file_size', True):
                key_parts.append(-info.get('file_size', 0))
            
            # 文件名优先级
            if config.get('use_filename', True):
                filename = info.get('filename', '')
                if config.get('reverse_filename', False):
                    # 如果反向，则用反向字符串比较
                    key_parts.append(tuple(-ord(c) for c in filename))
                else:
                    # 默认情况，文件名小的优先
                    key_parts.append(filename)
            
            return tuple(key_parts)
        
        # 对图片进行排序，第一个是要保留的
        sorted_images = sorted(group, key=get_sort_key)
        keep_image = sorted_images[0]
        
        # 构建删除列表和原因
        to_delete = []
        for img in group:
            if img != keep_image:
                reasons = []
                keep_info = image_info[keep_image]
                current_info = image_info[img]
                
                # 构建删除原因
                if config.get('use_dimensions', True):
                    keep_pixels = keep_info.get('pixel_count', 0)
                    current_pixels = current_info.get('pixel_count', 0)
                    if keep_pixels > current_pixels:
                        keep_dims = keep_info.get('dimensions', (0, 0))
                        current_dims = current_info.get('dimensions', (0, 0))
                        reasons.append(f"尺寸小 {current_dims[0]}×{current_dims[1]} < {keep_dims[0]}×{keep_dims[1]}")
                    elif keep_pixels == current_pixels and config.get('use_file_size', True):
                        # 尺寸相同，比较文件大小
                        keep_size = keep_info.get('file_size', 0)
                        current_size = current_info.get('file_size', 0)
                        if keep_size > current_size:
                            size_diff = keep_size - current_size
                            if size_diff > 1024 * 1024:
                                reasons.append(f"同尺寸但文件小 {size_diff / (1024 * 1024):.2f} MB")
                            elif size_diff > 1024:
                                reasons.append(f"同尺寸但文件小 {size_diff / 1024:.2f} KB")
                            else:
                                reasons.append(f"同尺寸但文件小 {size_diff} 字节")
                        elif keep_size == current_size and config.get('use_filename', True):
                            # 文件大小也相同，比较文件名
                            keep_name = keep_info.get('filename', '')
                            current_name = current_info.get('filename', '')
                            if config.get('reverse_filename', False):
                                reasons.append(f"同尺寸同大小但文件名小: {current_name} < {keep_name}")
                            else:
                                reasons.append(f"同尺寸同大小但文件名大: {current_name} > {keep_name}")
                
                # 如果没有具体原因，使用通用原因
                if not reasons:
                    reasons.append("根据综合规则被过滤")
                
                reason = " | ".join(reasons)
                to_delete.append((img, reason))
        
        return to_delete

    def process_by_comprehensive(self, group: List[str], filter_config: Dict[str, bool] = None) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        使用综合策略处理相似图片组
        
        Args:
            group: 相似图片组
            filter_config: 过滤配置字典，参见 apply_comprehensive_filter 方法说明
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        to_delete = set()
        removal_reasons = {}
        
        deleted_files = self.apply_comprehensive_filter(group, filter_config)
        for img, reason in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'comprehensive',
                'details': reason
            }
            logger.info(f"标记删除图片: {os.path.basename(img)} - {reason}")
            
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


def process_group_with_filters(group: List[str], config: Union[str, Dict[str, Any], List[Dict[str, Any]]] = None, 
                              ocr_model: str = "ch_PP-OCRv4_rec") -> Tuple[Set[str], Dict[str, Dict]]:
    """
    使用过滤器处理相似图片组，提供给duplicate.py调用的便捷函数
    
    Args:
        group: 相似图片组
        config: 过滤配置，可以是:
                - 字符串: 预定义的过滤模式，如 "ocr", "time", "size", "comprehensive" 等
                - 字典: 综合过滤的配置参数，如 {"use_dimensions": True, "use_file_size": True}
                - 列表: 详细的过滤器配置列表
                - None: 默认使用综合过滤
        ocr_model: OCR识别模型名称
        
    Returns:
        Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
    """
    # 创建过滤器实例
    filter_instance = GroupFilter(ocr_model=ocr_model)
    
    # 处理配置
    if config is None:
        # 默认使用综合过滤
        return filter_instance.process_by_comprehensive(group)
    elif isinstance(config, str):
        # 预定义的过滤模式
        mode = config.lower()
        if mode == "comprehensive":
            return filter_instance.process_by_comprehensive(group)
        elif mode == "ocr":
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
    elif isinstance(config, dict):
        # 综合过滤配置字典
        return filter_instance.process_by_comprehensive(group, config)
    else:
        # 详细的过滤器配置列表
        return filter_instance.process_by_config(group, config)


if __name__ == "__main__":
    test_group_filter_ocr()
