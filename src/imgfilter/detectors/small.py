import os
import json
import logging
from typing import List, Dict, Tuple, Set, Union
from PIL import Image
import pillow_avif  # AVIF支持
import pillow_jxl 
from io import BytesIO
from loguru import logger

class SmallImageDetector:
    """小尺寸图片检测器"""
    def __init__(self, min_size: int = None, config_path: str = None):
        """
        初始化小图检测器
        
        Args:
            min_size: 最小图片尺寸，如果提供则覆盖配置文件的默认值
            config_path: 配置文件路径，默认使用内置配置
        """
        # 加载配置
        self._load_config(config_path)
        
        # 如果传入了min_size参数，则覆盖配置文件中的值
        if min_size is not None:
            self.min_size = min_size
    
    def _load_config(self, config_path: str = None):
        """加载配置文件"""
        if config_path is None:
            # 使用默认配置文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, 'small_detector_config.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                default_settings = config.get('default_settings', {})
                
                self.min_size = default_settings.get('min_size', 630)
                self.default_width_range = default_settings.get('width_range', [])
                self.default_height_range = default_settings.get('height_range', [])
                
                logger.info(f"已加载小图检测器配置: min_size={self.min_size}, "
                          f"width_range={self.default_width_range}, height_range={self.default_height_range}")
        except Exception as e:
            logger.warning(f"加载配置文件失败，使用默认配置: {e}")
            self.min_size = 630
            self.default_width_range = []
            self.default_height_range = []
    def detect_small_images(self, image_files: List[str], min_size: int = None, **kwargs) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        检测小尺寸图片
        
        Args:
            image_files: 图片文件列表
            min_size: 最小图片尺寸，如果提供则覆盖实例的默认值
            **kwargs: 额外参数字典，支持精细控制：
                - width_range: [min, max] 宽度范围，空列表[]表示不检查宽度
                - height_range: [min, max] 高度范围，空列表[]表示不检查高度
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        to_delete = set()
        removal_reasons = {}
        
        # 使用传入的值或默认值
        min_size_value = min_size if min_size is not None else self.min_size
        
        for img_path in image_files:
            try:
                # 处理单个图片
                is_small, width, height, reason = self.is_small_image(img_path, min_size_value, **kwargs)
                
                if is_small:
                    to_delete.add(img_path)
                    removal_reasons[img_path] = {
                        'reason': 'small_image',
                        'details': reason,
                        'dimensions': f'{width}x{height}'
                    }
                    logger.info(f"标记删除小图: {os.path.basename(img_path)} ({width}x{height}) - {reason}")
            except Exception as e:                logger.error(f"处理小图检测失败 {img_path}: {e}")
                
        return to_delete, removal_reasons
    
    def is_small_image(self, img_path: str, min_size: int = None, **kwargs) -> Tuple[bool, int, int, str]:
        """
        判断图片是否为小图
        
        Args:
            img_path: 图片文件路径
            min_size: 最小图片尺寸，如果提供则覆盖实例的默认值
            **kwargs: 额外参数字典，支持精细控制：
                - width_range: [min, max] 宽度范围，空列表[]表示不检查宽度
                - height_range: [min, max] 高度范围，空列表[]表示不检查高度
            
        Returns:
            Tuple[bool, int, int, str]: (是否为小图, 宽度, 高度, 原因)
        """        
        try:
            # 获取精细控制参数，如果没有提供则使用配置文件中的默认值
            width_range = kwargs.get('width_range', self.default_width_range)
            height_range = kwargs.get('height_range', self.default_height_range)
            
            with Image.open(img_path) as img:
                width, height = img.size
                
                # 如果没有提供精细控制参数，使用默认逻辑（只检查高度=630）
                if not width_range and not height_range:
                    # 使用传入的值或默认值
                    threshold = min_size if min_size is not None else self.min_size
                    
                    # 默认只检查高度 = 630
                    if height == threshold:
                        logger.info(f"图片高度: {height} 等于排除高度 {threshold}")
                        return True, width, height, f'高度等于{threshold}'
                        
                    logger.info(f"图片尺寸: {width}x{height} 不符合默认排除条件")
                    return False, width, height, ''
                
                # 使用精细控制参数
                reasons = []
                
                # 检查宽度范围
                if width_range and len(width_range) == 2:
                    min_width, max_width = width_range
                    if min_width <= width <= max_width:
                        reasons.append(f'宽度在范围[{min_width}, {max_width}]内')
                
                # 检查高度范围  
                if height_range and len(height_range) == 2:
                    min_height, max_height = height_range
                    if min_height <= height <= max_height:
                        reasons.append(f'高度在范围[{min_height}, {max_height}]内')
                
                # 如果有任何条件匹配，则标记为小图
                if reasons:
                    reason = ', '.join(reasons)
                    logger.info(f"图片尺寸: {width}x{height} 符合排除条件: {reason}")
                    return True, width, height, reason
                    
                logger.info(f"图片尺寸: {width}x{height} 不符合任何排除条件")
                return False, width, height, ''
                
        except Exception as e:
            logger.error(f"检测图片尺寸时发生错误: {str(e)}")
            raise
    
    def detect_small_image_bytes(self, image_data, min_size: int = None):
        """
        检测图片字节数据是否为小图
        
        Args:
            image_data: PIL.Image对象或图片字节数据
            min_size: 最小图片尺寸，如果提供则覆盖实例的默认值
            
        Returns:
            Tuple[Union[bytes, None], Union[str, None]]: (处理后的图片数据, 错误原因)
        """
        try:
            # 使用传入的值或默认值
            threshold = min_size if min_size is not None else self.min_size
            
            # 统一转换为PIL Image对象
            if isinstance(image_data, Image.Image):
                img = image_data
            else:
                img = Image.open(BytesIO(image_data))
                
            # 获取图片尺寸
            width, height = img.size
            
            # 检查尺寸
            if width < threshold or height < threshold:
                logger.info(f"[#image_processing]🖼️ 图片尺寸: {width}x{height} 小于最小尺寸 {threshold}")
                return None, 'small_image'
                
            logger.info(f"[#image_processing]🖼️ 图片尺寸: {width}x{height} 大于最小尺寸 {threshold}")
            
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
