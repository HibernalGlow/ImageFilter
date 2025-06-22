"""
文件组分析器模块
用于分析和比较同一组内的多个文件，提取最优指标
"""

import os
import re
import logging
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from .number_shortener import shorten_number_cn

from loguru import logger
@dataclass
class FileMetrics:
    """文件指标数据类"""
    width: int = 0
    page_count: int = 0
    clarity_score: float = 0.0
    
    def __str__(self) -> str:
        parts = []
        if self.width > 0:
            parts.append(f"{self.width}@WD")
        if self.page_count > 0:
            parts.append(f"{self.page_count}@PX")
        if self.clarity_score > 0:
            parts.append(f"{int(self.clarity_score)}@DE")
        return "{" + ",".join(parts) + "}" if parts else ""

class GroupAnalyzer:
    """文件组分析器，用于分析同一组内的多个文件并提取最优指标"""
    
    def __init__(self):
        """初始化分析器"""
        self.emoji_map = {
            'width': '📏',  # 宽度使用尺子emoji
            'page_count': '📄',  # 页数使用纸张emoji
            'clarity_score': '🔍'  # 清晰度使用放大镜emoji
        }
    
    def clean_filename(self, filename: str) -> str:
        """清理文件名，只保留主文件名部分进行比较"""
        # 移除扩展名
        name = os.path.splitext(filename)[0]
        
        # 移除所有括号内容和指标信息
        name = re.sub(r'\[[^\]]*\]|\([^)]*\)|\{[^}]*\}', '', name)
        
        # 移除特殊字符和多余空格
        name = re.sub(r'[^\w\s\-]', '', name)
        name = re.sub(r'\s+', '', name)
        
        return name.strip().lower()
    
    def group_similar_files(self, files: List[str]) -> Dict[str, List[str]]:
        """将相似文件分组
        
        Args:
            files: 文件路径列表
            
        Returns:
            Dict[str, List[str]]: 以清理后的文件名为键，原始文件列表为值的字典
        """
        groups: Dict[str, List[str]] = {}
        logger.info("🔍 开始文件分组...")
        
        for file in files:
            clean_name = self.clean_filename(file)
            if not clean_name:
                logger.info(f"⚠️ 跳过无效文件名: {file}")
                continue
                
            if clean_name not in groups:
                groups[clean_name] = []
            groups[clean_name].append(file)
            logger.debug(f"📑 文件 '{file}' 被分组到 '{clean_name}'")
        
        # 记录分组结果
        for clean_name, group_files in groups.items():
            if len(group_files) > 1:
                logger.info(f"📦 找到组 '{clean_name}': {len(group_files)}个文件")
                for f in group_files:
                    logger.debug(f"  - {f}")
        
        return groups
    
    def extract_metrics(self, filename: str) -> Optional[FileMetrics]:
        """从文件名中提取指标信息"""
        try:
            metrics = FileMetrics()
            
            # 匹配花括号中的指标信息
            pattern = r'\{([^}]+)\}'
            match = re.search(pattern, filename)
            if not match:
                return None
                
            metrics_str = match.group(1)
            # 分析各个指标
            for metric in metrics_str.split(','):
                if '@WD' in metric:
                    width_str = metric.replace('@WD', '').strip()
                    try:
                        metrics.width = int(float(width_str))
                    except ValueError:
                        pass
                elif '@PX' in metric:
                    page_str = metric.replace('@PX', '').strip()
                    try:
                        metrics.page_count = int(float(page_str))
                    except ValueError:
                        pass
                elif '@DE' in metric:
                    clarity_str = metric.replace('@DE', '').strip()
                    try:
                        metrics.clarity_score = float(clarity_str)
                    except ValueError:
                        pass
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ 提取指标失败 {filename}: {str(e)}")
            return None
    
    def analyze_group(self, files: List[str]) -> Dict[str, Tuple[float, str]]:
        """分析文件组，返回每个指标的最优值和对应文件"""
        logger.info(f"🔍 开始分析文件组: {len(files)}个文件")
        
        best_metrics = {
            'width': (0, ''),
            'page_count': (0, ''),
            'clarity_score': (0, '')
        }
        
        all_metrics = []
        # 收集所有文件的指标
        for file in files:
            metrics = self.extract_metrics(file)
            if metrics:
                all_metrics.append((file, metrics))
                logger.info(f"📊 文件指标: {file} -> {metrics}")
                
                # 更新最优值
                if metrics.width > best_metrics['width'][0]:
                    best_metrics['width'] = (metrics.width, file)
                if metrics.page_count > best_metrics['page_count'][0]:
                    best_metrics['page_count'] = (metrics.page_count, file)
                if metrics.clarity_score > best_metrics['clarity_score'][0]:
                    best_metrics['clarity_score'] = (metrics.clarity_score, file)
        
        # 检查哪些指标是统一的
        unified_metrics = self._find_unified_metrics(all_metrics)
        logger.info(f"🎯 统一指标: {unified_metrics}")
        
        # 返回非统一的最优指标
        return {
            metric: (value, file)
            for metric, (value, file) in best_metrics.items()
            if metric not in unified_metrics
        }
    
    def _find_unified_metrics(self, metrics_list: List[Tuple[str, FileMetrics]]) -> List[str]:
        """找出所有文件都相同的指标"""
        if not metrics_list:
            return []
            
        unified = []
        first_metrics = metrics_list[0][1]
        
        # 检查每个指标是否统一
        if all(m[1].width == first_metrics.width for m in metrics_list):
            unified.append('width')
        if all(m[1].page_count == first_metrics.page_count for m in metrics_list):
            unified.append('page_count')
        if all(m[1].clarity_score == first_metrics.clarity_score for m in metrics_list):
            unified.append('clarity_score')
            
        return unified
    
    def format_best_metrics(self, best_metrics: Dict[str, Tuple[float, str]]) -> str:
        """格式化最优指标信息"""
        parts = []
        
        # 添加每个非统一的最优指标
        for metric, (value, _) in best_metrics.items():
            if value > 0:
                emoji = self.emoji_map.get(metric, '')
                if metric == 'width':
                    parts.append(f"{emoji}{value}@WD")
                elif metric == 'page_count':
                    parts.append(f"{emoji}{int(value)}@PX")
                elif metric == 'clarity_score':
                    parts.append(f"{emoji}{int(value)}@DE")
        
        return "{" + ",".join(parts) + "}" if parts else ""