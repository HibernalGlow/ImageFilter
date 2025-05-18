"""
imgutils 库适配器

提供对 imgutils 库的简化接口封装，用于 imgu 命令行工具
"""
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union
from loguru import logger
from io import BytesIO
from PIL import Image
import threading
import imagehash

# 导入 imgutils 官方API
try:
    from imgutils.validate.monochrome import get_monochrome_score
    from imgutils.ocr import detect_text_with_ocr
    from imgutils.tagging.wd14 import get_tags
    from imgutils.segment.isnetis import segment_with_isnetis
    from imgutils.edge.lineart_anime import edge_image_with_lineart_anime
    from imgutils.edge.canny import edge_image_with_canny
except ImportError as e:
    logger.error(f"导入 imgutils 模块失败: {e}")
    raise RuntimeError("无法导入 imgutils 组件，请确保已安装 dghs-imgutils 包")

_lock = threading.Lock()

class ImgutilsAdapter:
    """imgutils 库适配器，提供对 imgutils 功能的简化访问"""

    @staticmethod
    def detect_grayscale(image_path_or_data, threshold: float = 0.7) -> Tuple[bool, Dict]:
        """
        检测图像是否为灰度图
        
        Args:
            image_path_or_data: 图像路径或图像数据
            threshold: 灰度判断阈值，默认0.7
            
        Returns:
            (is_gray, details): 是否是灰度图和详细信息
        """
        try:
            score = get_monochrome_score(image_path_or_data)
            is_mono = score >= threshold
            return is_mono, {"score": score}
        except Exception as e:
            logger.error(f"灰度图检测失败: {e}")
            return False, {"error": str(e)}

    @staticmethod
    def detect_text_image(image_path_or_data, threshold: float = 0.5) -> Tuple[bool, Dict]:
        """
        检测图像是否为文本图像（基于OCR文本框数量/面积）
        
        Args:
            image_path_or_data: 图像路径或图像数据
            threshold: 文本图像判断阈值，默认0.5
            
        Returns:
            (is_text, details): 是否是文本图像和详细信息
        """
        try:
            ocr_result = detect_text_with_ocr(image_path_or_data)
            # 统计检测到的文本框数量
            text_count = len(ocr_result)
            is_text = text_count >= int(threshold * 10)  # 经验阈值：大于一定数量文本框
            return is_text, {"text_count": text_count, "ocr_result": ocr_result}
        except Exception as e:
            logger.error(f"文本图像检测失败: {e}")
            return False, {"error": str(e)}

    @staticmethod
    def generate_tags(image_path_or_data, model: str = "ConvNext") -> Tuple[List[str], Dict]:
        """
        生成图像标签（使用WD14）
        
        Args:
            image_path_or_data: 图像路径或图像数据
            model: 使用的模型名称，默认为"ConvNext"
            
        Returns:
            (tags, details): 标签列表和详细信息
        """
        try:
            with _lock:
                tags, scores = get_tags(
                    image_path_or_data,
                    model_name=model,
                    general_threshold=0.35,
                    character_threshold=0.35,
                    format_tags=True
                )
            tag_details = dict(zip(tags, scores))
            return tags, {"scores": tag_details}
        except Exception as e:
            logger.error(f"生成标签失败: {e}")
            return [], {"error": str(e)}

    @staticmethod
    def calculate_image_hash(image_path_or_data) -> Optional[str]:
        """
        计算图像哈希值 (使用 imagehash 库)
        
        Args:
            image_path_or_data: 图像路径或图像数据
            
        Returns:
            图像哈希值的字符串表示
        """
        try:
            if isinstance(image_path_or_data, (str, Path)):
                img = Image.open(image_path_or_data)
            elif isinstance(image_path_or_data, (bytes, BytesIO)):
                img = Image.open(BytesIO(image_path_or_data) if isinstance(image_path_or_data, bytes) else image_path_or_data)
            elif isinstance(image_path_or_data, Image.Image):
                img = image_path_or_data
            else:
                raise ValueError(f"不支持的输入类型: {type(image_path_or_data)}")
                
            # 使用感知哈希算法
            phash = str(imagehash.phash(img))
            return phash
        except Exception as e:
            logger.error(f"计算图像哈希失败: {e}")
            return None

    @staticmethod
    def compare_image_hashes(hash1: str, hash2: str, threshold: int = 4) -> Tuple[bool, int]:
        """
        比较两个图像哈希值的相似度（汉明距离）
        
        Args:
            hash1: 第一个哈希值
            hash2: 第二个哈希值
            threshold: 相似度阈值，低于此值认为相似
            
        Returns:
            (is_similar, distance): 是否相似和汉明距离
        """
        try:
            # imagehash 的 hash 字符串可以直接转为 imagehash.ImageHash 对象
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            distance = h1 - h2
            return distance <= threshold, distance
        except Exception as e:
            logger.error(f"比较图像哈希失败: {e}")
            return False, -1

    @staticmethod
    def extract_character(image_path_or_data, output_path: str, format: str = 'png') -> Optional[str]:
        """
        使用 isnetis 分割角色并保存
        
        Args:
            image_path_or_data: 图像路径或图像数据
            output_path: 输出路径
            format: 输出格式，默认为PNG
            
        Returns:
            输出文件路径，失败则返回None
        """
        try:
            result_img = segment_with_isnetis(image_path_or_data, background='white')
            out_path = str(output_path)
            if format.lower() == 'webp':
                out_path = out_path.rsplit('.', 1)[0] + '.webp'
            Image.fromarray(result_img).save(out_path, format=format.upper())
            return out_path
        except Exception as e:
            logger.error(f"角色提取失败: {e}")
            return None

    @staticmethod
    def generate_lineart(image_path_or_data, output_path: str, method: str = 'lineart_anime') -> Optional[str]:
        """
        生成线稿图像
        
        Args:
            image_path_or_data: 图像路径或图像数据
            output_path: 输出路径
            method: 线稿生成方法
            
        Returns:
            输出文件路径，失败则返回None
        """
        try:
            if method == 'lineart_anime':
                result_img = edge_image_with_lineart_anime(image_path_or_data)
            elif method == 'canny':
                result_img = edge_image_with_canny(image_path_or_data)
            else:
                raise ValueError(f"不支持的线稿方法: {method}")
            Image.fromarray(result_img).save(output_path)
            return output_path
        except Exception as e:
            logger.error(f"线稿生成失败: {e}")
            return None

    @staticmethod
    def get_image_size(image_path_or_data) -> Tuple[int, int]:
        """
        获取图像尺寸
        
        Args:
            image_path_or_data: 图像路径或图像数据
            
        Returns:
            (width, height): 图像宽度和高度
        """
        try:
            if isinstance(image_path_or_data, (str, Path)):
                with Image.open(image_path_or_data) as img:
                    return img.width, img.height
            elif isinstance(image_path_or_data, (bytes, BytesIO)):
                with Image.open(BytesIO(image_path_or_data) if isinstance(image_path_or_data, bytes) else image_path_or_data) as img:
                    return img.width, img.height
            elif isinstance(image_path_or_data, Image.Image):
                return image_path_or_data.width, image_path_or_data.height
            else:
                raise ValueError(f"不支持的输入类型: {type(image_path_or_data)}")
        except Exception as e:
            logger.error(f"获取图像尺寸失败: {e}")
            return 0, 0
