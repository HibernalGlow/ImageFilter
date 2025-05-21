"""图像清晰度评估模块"""
import cv2
import numpy as np
from PIL import Image
import pillow_avif
import pillow_jxl
from pathlib import Path
from typing import Dict, List, Union, Tuple
from io import BytesIO
from loguru import logger
class ImageClarityEvaluator:
    """图像清晰度评估类"""
    
    @staticmethod
    def batch_evaluate(image_paths: List[Union[str, Path]]) -> Dict[str, float]:
        """
        批量评估图像清晰度
        Args:
            image_paths: 图片路径列表
        Returns:
            字典{文件路径: 清晰度评分}
        """
        scores = {}
        for path in image_paths:
            try:
                score = ImageClarityEvaluator.calculate_definition(path)
                scores[str(path)] = score
            except Exception as e:
                logger.warning(f"清晰度评估失败 {path}: {str(e)}")
                scores[str(path)] = 0.0
        return scores

    @staticmethod
    def get_image_size(image_path: Union[str, Path]) -> Tuple[int, int]:
        """获取图片尺寸"""
        try:
            with Image.open(image_path) as img:
                return img.size  # (width, height)
        except Exception as e:
            logger.error(f"获取图片尺寸失败 {image_path}: {str(e)}")
            return (0, 0)

    @staticmethod
    def calculate_definition(image_path_or_data):
        """计算图像清晰度评分（基于Sobel梯度能量）"""
        try:
            # 统一转换为OpenCV格式
            if isinstance(image_path_or_data, (str, Path)):
                img = cv2.imread(str(image_path_or_data))
            elif isinstance(image_path_or_data, BytesIO):
                img = cv2.imdecode(np.frombuffer(image_path_or_data.getvalue(), np.uint8), cv2.IMREAD_COLOR)
            elif isinstance(image_path_or_data, bytes):
                img = cv2.imdecode(np.frombuffer(image_path_or_data, np.uint8), cv2.IMREAD_COLOR)
            elif isinstance(image_path_or_data, Image.Image):
                img = cv2.cvtColor(np.array(image_path_or_data), cv2.COLOR_RGB2BGR)
            else:
                raise ValueError("不支持的输入类型")

            if img is None:
                raise ValueError("无法解码图像数据")

            # 转换为灰度图
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 计算Sobel梯度能量
            sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            energy = sobelx**2 + sobely**2
            
            # 返回取整后的清晰度评分
            return round(np.mean(energy))  # 新增round取整

        except Exception as e:
            logger.error(f"清晰度计算失败: {str(e)}")
            return 0

