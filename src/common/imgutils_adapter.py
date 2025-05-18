"""
imgutils 适配器模块 - 提供 imgutils 库的集成接口

此模块封装了 imgutils 库提供的图像处理功能，使其易于在现有项目中使用。
"""
import os
import logging
from typing import Dict, List, Tuple, Optional, Union, Any
from pathlib import Path
import numpy as np
from PIL import Image
from io import BytesIO

# imgutils 相关导入
from imgutils.tagging import get_wd14_tags
from imgutils.detect.monochrome import estimate_monochrome
from imgutils.metrics.ccip import ccip_compare, ccip_clustering
from imgutils.detect.text import detect_text_blocks
from imgutils.segment import segment_rgba_with_isnetis
from imgutils.edge import detect_edge

# 创建日志记录器
logger = logging.getLogger(__name__)

class ImgUtilsAdapter:
    """imgutils 库适配器，提供统一接口"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化 imgutils 适配器
        
        Args:
            config: 配置参数字典
        """
        self.config = config or {}
        # 可以在这里添加各种模型的初始化

    def detect_grayscale(self, image_data) -> Tuple[bool, float, Dict[str, Any]]:
        """
        检测图像是否为灰度图/黑白图
        
        Args:
            image_data: 图像数据，可以是 PIL.Image、字节数据或文件路径
            
        Returns:
            Tuple[bool, float, Dict]: (是否为灰度图, 灰度评分, 详细信息)
        """
        try:
            # 确保图像是 PIL.Image 对象
            if isinstance(image_data, bytes) or isinstance(image_data, BytesIO):
                img = Image.open(BytesIO(image_data) if isinstance(image_data, bytes) else image_data)
            elif isinstance(image_data, str) and os.path.exists(image_data):
                img = Image.open(image_data)
            elif isinstance(image_data, Image.Image):
                img = image_data
            else:
                logger.error(f"不支持的图像数据类型: {type(image_data)}")
                return False, 0.0, {"error": "不支持的图像数据类型"}
            
            # 使用 imgutils 的灰度检测
            result = estimate_monochrome(img)
            
            # 整理结果
            is_grayscale = result["monochrome_probability"] > 0.7
            score = result["monochrome_probability"]
            
            details = {
                "monochrome_probability": result["monochrome_probability"],
                "reason": "grayscale" if is_grayscale else "color",
                "details": result
            }
            
            # 检查是否纯白或纯黑
            if is_grayscale and "brightness" in result:
                if result["brightness"] > 0.95:
                    details["reason"] = "pure_white"
                elif result["brightness"] < 0.05:
                    details["reason"] = "pure_black"
            
            return is_grayscale, score, details
            
        except Exception as e:
            logger.error(f"灰度检测出错: {str(e)}")
            return False, 0.0, {"error": str(e)}
    
    def detect_image_similarity(self, 
                               image1_data, 
                               image2_data) -> Tuple[float, Dict[str, Any]]:
        """
        比较两个图像的相似度
        
        Args:
            image1_data: 第一个图像数据
            image2_data: 第二个图像数据
            
        Returns:
            Tuple[float, Dict]: (相似度评分, 详细信息)
        """
        try:
            # 准备图像数据
            def prepare_image(data):
                if isinstance(data, bytes) or isinstance(data, BytesIO):
                    return Image.open(BytesIO(data) if isinstance(data, bytes) else data)
                elif isinstance(data, str) and os.path.exists(data):
                    return Image.open(data)
                elif isinstance(data, Image.Image):
                    return data
                else:
                    raise ValueError(f"不支持的图像数据类型: {type(data)}")
            
            img1 = prepare_image(image1_data)
            img2 = prepare_image(image2_data)
            
            # 使用 CCIP 比较图像相似度
            similarity = ccip_compare([img1, img2])[0, 1]
            
            details = {
                "similarity": similarity,
                "is_similar": similarity > 0.85  # 可配置的阈值
            }
            
            return similarity, details
            
        except Exception as e:
            logger.error(f"图像相似度检测出错: {str(e)}")
            return 0.0, {"error": str(e)}
    
    def cluster_images(self, 
                      image_paths: List[str], 
                      min_samples: int = 2) -> Tuple[List[int], Dict[str, Any]]:
        """
        对图像进行聚类
        
        Args:
            image_paths: 图像路径列表
            min_samples: 最小样本数
            
        Returns:
            Tuple[List[int], Dict]: (聚类标签, 详细信息)
        """
        try:
            # 加载图像
            images = [Image.open(path) for path in image_paths]
            
            # 使用 CCIP 聚类
            labels = ccip_clustering(images, min_samples=min_samples)
            
            details = {
                "cluster_count": len(set(label for label in labels if label != -1)),
                "noise_count": labels.count(-1) if hasattr(labels, "count") else sum(1 for label in labels if label == -1)
            }
            
            return labels, details
            
        except Exception as e:
            logger.error(f"图像聚类出错: {str(e)}")
            return [], {"error": str(e)}
    
    def detect_text_image(self, 
                         image_data) -> Tuple[bool, float, Dict[str, Any]]:
        """
        检测是否为文本图像
        
        Args:
            image_data: 图像数据
            
        Returns:
            Tuple[bool, float, Dict]: (是否为文本图像, 文本比例评分, 详细信息)
        """
        try:
            # 准备图像
            if isinstance(image_data, bytes) or isinstance(image_data, BytesIO):
                img = Image.open(BytesIO(image_data) if isinstance(image_data, bytes) else image_data)
            elif isinstance(image_data, str) and os.path.exists(image_data):
                img = Image.open(image_data)
            elif isinstance(image_data, Image.Image):
                img = image_data
            else:
                logger.error(f"不支持的图像数据类型: {type(image_data)}")
                return False, 0.0, {"error": "不支持的图像数据类型"}
            
            # 使用 imgutils 的文本检测
            text_blocks = detect_text_blocks(img)
            
            if not text_blocks:
                return False, 0.0, {"text_blocks": 0, "text_area_ratio": 0.0}
            
            # 计算文本区域占比
            img_area = img.width * img.height
            text_area = sum((block[2] - block[0]) * (block[3] - block[1]) for block in text_blocks)
            text_ratio = text_area / img_area
            
            # 判断是否为文本图像
            is_text_image = text_ratio > 0.5  # 可配置的阈值
            
            details = {
                "text_blocks": len(text_blocks),
                "text_area_ratio": text_ratio
            }
            
            return is_text_image, text_ratio, details
            
        except Exception as e:
            logger.error(f"文本图像检测出错: {str(e)}")
            return False, 0.0, {"error": str(e)}
    
    def image_tagging(self, 
                     image_data) -> Dict[str, Any]:
        """
        生成图像标签
        
        Args:
            image_data: 图像数据
            
        Returns:
            Dict: 标签信息
        """
        try:
            # 准备图像
            if isinstance(image_data, bytes) or isinstance(image_data, BytesIO):
                img_path = "_temp_img.jpg"
                with open(img_path, "wb") as f:
                    f.write(image_data if isinstance(image_data, bytes) else image_data.getvalue())
            elif isinstance(image_data, str) and os.path.exists(image_data):
                img_path = image_data
            elif isinstance(image_data, Image.Image):
                img_path = "_temp_img.jpg"
                image_data.save(img_path)
            else:
                logger.error(f"不支持的图像数据类型: {type(image_data)}")
                return {"error": "不支持的图像数据类型"}
            
            # 使用 imgutils 的标签生成
            rating, features, chars = get_wd14_tags(img_path)
            
            # 清理临时文件
            if img_path == "_temp_img.jpg" and os.path.exists(img_path):
                os.remove(img_path)
            
            return {
                "rating": rating,
                "features": features,
                "characters": chars
            }
            
        except Exception as e:
            logger.error(f"图像标签生成出错: {str(e)}")
            return {"error": str(e)}
    
    def extract_character(self, 
                         image_data) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        从图像中提取角色
        
        Args:
            image_data: 图像数据
            
        Returns:
            Tuple[Image.Image, Dict]: (处理后的图像, 详细信息)
        """
        try:
            # 准备图像
            if isinstance(image_data, bytes) or isinstance(image_data, BytesIO):
                img = Image.open(BytesIO(image_data) if isinstance(image_data, bytes) else image_data)
            elif isinstance(image_data, str) and os.path.exists(image_data):
                img = Image.open(image_data)
            elif isinstance(image_data, Image.Image):
                img = image_data
            else:
                logger.error(f"不支持的图像数据类型: {type(image_data)}")
                return None, {"error": "不支持的图像数据类型"}
            
            # 使用 imgutils 提取角色
            mask, image_rgba = segment_rgba_with_isnetis(img)
            
            details = {
                "has_character": mask is not None and mask.max() > 0,
                "mask_coverage": float(np.mean(mask)) if mask is not None else 0.0
            }
            
            return image_rgba, details
            
        except Exception as e:
            logger.error(f"角色提取出错: {str(e)}")
            return None, {"error": str(e)}
    
    def generate_edge_image(self, 
                           image_data, 
                           method: str = "lineart_anime") -> Tuple[Image.Image, Dict[str, Any]]:
        """
        生成边缘图/线稿图
        
        Args:
            image_data: 图像数据
            method: 边缘检测方法，可选 'canny', 'lineart', 'lineart_anime'
            
        Returns:
            Tuple[Image.Image, Dict]: (处理后的图像, 详细信息)
        """
        try:
            # 准备图像
            if isinstance(image_data, bytes) or isinstance(image_data, BytesIO):
                img = Image.open(BytesIO(image_data) if isinstance(image_data, bytes) else image_data)
            elif isinstance(image_data, str) and os.path.exists(image_data):
                img = Image.open(image_data)
            elif isinstance(image_data, Image.Image):
                img = image_data
            else:
                logger.error(f"不支持的图像数据类型: {type(image_data)}")
                return None, {"error": "不支持的图像数据类型"}
            
            # 使用 imgutils 生成边缘图
            edge_img = detect_edge(img, method=method)
            
            return edge_img, {"method": method}
            
        except Exception as e:
            logger.error(f"边缘图生成出错: {str(e)}")
            return None, {"error": str(e)}
