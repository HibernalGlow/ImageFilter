import os
import logging
from typing import List, Dict, Tuple, Set, Union
from PIL import Image
import pillow_avif  # AVIF支持
import pillow_jxl 
from io import BytesIO
from loguru import logger
from imgutils.validate import get_monochrome_score, is_monochrome  

class GrayscaleImageDetector:
    """灰度图、黑白图和纯色图检测器"""
    
    def __init__(self):
        """初始化灰度图检测器"""
        # 直接使用is_monochrome函数替代GrayscaleDetector
        pass
        
    def detect_grayscale_images(self, image_files: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        检测灰度图、纯白图和纯黑图
        
        Args:
            image_files: 图片文件列表
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        to_delete = set()
        removal_reasons = {}
        
        for img_path in image_files:
            try:
                with open(img_path, 'rb') as f:
                    img_data = f.read()
                    
                result, reason = self.detect_grayscale_image_bytes(img_data)
                
                if reason in ['monochrome', 'pure_white', 'pure_black', 'white_image']:
                    to_delete.add(img_path)
                    
                    # 映射原因到详细信息
                    details_map = {
                        'monochrome': '灰度图片',
                        'pure_white': '纯白图片',
                        'pure_black': '纯黑图片',
                        'white_image': '白图片'
                    }
                    
                    removal_reasons[img_path] = {
                        'reason': reason,
                        'details': details_map.get(reason, '黑白图片')
                    }
                    
                    logger.info(f"[#file_ops]🖼️ 标记删除{removal_reasons[img_path]['details']}: {os.path.basename(img_path)}")
                    
            except Exception as e:
                logger.error(f"[#file_ops]❌ 处理灰度图检测失败 {img_path}: {e}")

                
        return to_delete, removal_reasons
    def detect_grayscale_image_bytes(self, image_data):
        """
        检测图片字节数据是否为灰度图/纯白图/纯黑图
        
        Args:
            image_data: PIL.Image对象或图片字节数据
            
        Returns:
            Tuple[Union[bytes, None], Union[str, None]]: (处理后的图片数据, 错误原因)
        """
        try:
            # 先确保是PIL Image对象
            if isinstance(image_data, Image.Image):
                img = image_data
            else:
                img = Image.open(BytesIO(image_data))
                
            # 使用is_monochrome函数进行判断
            if is_monochrome(img):
                logger.info(f"[#file_ops]🖼️ is_monochrome检测到灰度图")
                return (None, 'monochrome')
                
            # 进一步尝试使用传统方法检测
            if isinstance(image_data, Image.Image):
                img = image_data
            else:
                img = Image.open(BytesIO(image_data))
            
            # 传统方法检测
            result, reason = self._legacy_detect_grayscale(img)
            if reason:
                return result, reason
                
            # 未检测到灰度图，返回原始数据
            if isinstance(image_data, Image.Image):
                return image_data, None
            else:
                img_byte_arr = BytesIO()
                img.save(img_byte_arr, format=img.format or 'PNG')
                return img_byte_arr.getvalue(), None
                
        except ValueError as ve:
            logger.info(f"[#file_ops]❌ 灰度检测发生ValueError: {str(ve)}")
            return (None, 'grayscale_detection_error')
        except Exception as e:
            logger.info(f"[#file_ops]❌ 灰度检测发生错误: {str(e)}")
            return None, 'grayscale_detection_error'
            
    def _legacy_detect_grayscale(self, img):
        """传统方法检测灰度图（作为备用）"""
        try:
            # 转换为RGB模式
            if img.mode not in ["RGB", "RGBA", "L"]:
                img = img.convert("RGB")
            
            # 1. 检查是否为原始灰度图
            if img.mode == "L":
                logger.info("[#file_ops]🖼️ 检测到原始灰度图")
                return None, 'monochrome'
            
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
                logger.info("[#file_ops]🖼️ 检测到纯白图")
                return None, 'pure_white'
            
            # 4. 检查是否为纯黑图
            if all(all(v < 15 for v in (pixel if isinstance(pixel, tuple) else (pixel,))) 
                   for pixel in pixels):
                logger.info("[#file_ops]🖼️ 检测到纯黑图")
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
                    logger.info("[#file_ops]🖼️ 检测到灰度图(RGB接近)")
                    return None, 'monochrome'
                    
            return img, None
            
        except Exception as e:
            logger.error(f"[#file_ops]❌ 传统灰度检测发生错误: {str(e)}")
            return img, None
