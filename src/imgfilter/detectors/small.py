import os
import logging
from typing import List, Dict, Tuple, Set, Union
from PIL import Image
import pillow_avif  # AVIF支持
import pillow_jxl 
from io import BytesIO
from loguru import logger

class SmallImageDetector:
    """小尺寸图片检测器"""
    
    def __init__(self, min_size: int = 631):
        """
        初始化小图检测器
        
        Args:
            min_size: 最小图片尺寸（宽或高），小于此尺寸的图片将被判定为小图
        """
        self.min_size = min_size
        
    def detect_small_images(self, image_files: List[str], min_size: int = None) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        检测小尺寸图片
        
        Args:
            image_files: 图片文件列表
            min_size: 最小图片尺寸，如果提供则覆盖实例的默认值
            
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
                is_small, width, height = self.is_small_image(img_path, min_size_value)
                
                if is_small:
                    to_delete.add(img_path)
                    removal_reasons[img_path] = {
                        'reason': 'small_image',
                        'details': f'小于{min_size_value}像素',
                        'dimensions': f'{width}x{height}'
                    }
                    logger.info(f"标记删除小图: {os.path.basename(img_path)} ({width}x{height})")
            except Exception as e:
                logger.error(f"处理小图检测失败 {img_path}: {e}")
                
        return to_delete, removal_reasons
    
    def is_small_image(self, img_path: str, min_size: int = None) -> Tuple[bool, int, int]:
        """
        判断图片是否为小图
        
        Args:
            img_path: 图片文件路径
            min_size: 最小图片尺寸，如果提供则覆盖实例的默认值
            
        Returns:
            Tuple[bool, int, int]: (是否为小图, 宽度, 高度)
        """
        try:
            # 使用传入的值或默认值
            threshold = min_size if min_size is not None else self.min_size
            
            with Image.open(img_path) as img:
                width, height = img.size
                
                # 检查尺寸
                if width < threshold or height < threshold:
                    logger.info(f"图片尺寸: {width}x{height} 小于最小尺寸 {threshold}")
                    return True, width, height
                    
                logger.info(f"图片尺寸: {width}x{height} 大于最小尺寸 {threshold}")
                return False, width, height
                
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
