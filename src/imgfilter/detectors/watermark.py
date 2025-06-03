from pathlib import Path
import sys
import os
import json
from PIL import Image
import pillow_avif
import pillow_jxl 
import numpy as np
from typing import Tuple, List, Dict, Optional
import logging
import requests
import base64
from io import BytesIO

# 添加PathURIGenerator导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from hashu.core.calculate_hash_custom import PathURIGenerator

from loguru import logger
class WatermarkDetector:
    """水印检测器类"""
    
    def __init__(self, api_url: str = "http://127.0.0.1:6789/api/ocr", cache_file: str = None):
        """
        初始化水印检测器
        
        Args:
            api_url: UmiOCR HTTP API地址，默认为本地1224端口
            cache_file: OCR结果缓存文件路径，默认为脚本所在目录下的ocr_cache.json
        """
        self.api_url = api_url
        self.cache_file = cache_file or os.path.join(os.path.dirname(__file__), 'ocr_cache.json')
        self.ocr_cache = self._load_cache()
        self.watermark_keywords = [
            "汉化", "翻译", "扫描", "嵌字", "翻译", "组", "漢化",
            "扫图", "嵌字", "校对", "翻译", "润色", "招募", "公众号",
            "众筹", "关注", "有偿", "福利", "二维", "淘宝", "免费",
        ]
        
    def _load_cache(self) -> Dict:
        """加载OCR缓存"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"[#update_log]加载缓存文件失败: {e}")
        return {}

    def _save_cache(self):
        """保存OCR缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.ocr_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[#update_log]保存缓存文件失败: {e}")

    def _get_image_uri(self, image_path: str) -> str:
        """生成图片的URI"""
        return PathURIGenerator.generate(image_path)

    def detect_watermark(self, image_path: str, keywords: List[str] = None) -> Tuple[bool, List[str]]:
        """
        检测图片中是否存在水印
        
        Args:
            image_path: 图片文件路径
            keywords: 自定义水印关键词列表，None时使用默认列表
            
        Returns:
            Tuple[bool, List[str]]: (是否存在水印, 检测到的水印文字列表)
        """
        try:
            # 生成图片URI
            image_uri = self._get_image_uri(image_path)
            
            # 检查缓存
            if image_uri in self.ocr_cache:
                logger.info(f"使用缓存的OCR结果: {image_uri}")
                detected_texts = self.ocr_cache[image_uri]
            else:
                # 调用UmiOCR进行文字识别
                ocr_result = self._run_ocr(image_path)
                detected_texts = self._parse_ocr_result(ocr_result)
                
                # 保存到缓存
                self.ocr_cache[image_uri] = detected_texts
                self._save_cache()
                logger.info(f"已缓存OCR结果: {image_uri}")
            
            # 使用指定的关键词列表或默认列表
            check_keywords = keywords if keywords is not None else self.watermark_keywords
            
            # 检查是否包含水印关键词
            watermark_texts = []
            for text in detected_texts:
                if any(keyword in text for keyword in check_keywords):
                    watermark_texts.append(text)
                    
            return bool(watermark_texts), watermark_texts
            
        except Exception as e:
            logger.error(f"[#update_log]检测水印时出错: {e}")
            return False, []
            
    def _run_ocr(self, image_path: str) -> str:
        """
        运行OCR识别
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            str: OCR识别结果的JSON字符串
        """
        try:
            # 读取图片并转换为base64
            with Image.open(image_path) as img:
                # 转换为RGB模式（如果是RGBA，去掉alpha通道）
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                    
                # 将图片转换为base64
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            # 准备请求数据
            data = {
                "base64": img_base64,
                "options": {
                    "language": "zh",  # 设置为中文
                    "model": "fast"    # 使用快速模式
                }
            }
            
            # 发送POST请求到UmiOCR
            response = requests.post(self.api_url, json=data)
            
            if response.status_code != 200:
                raise RuntimeError(f"UmiOCR API请求失败: {response.text}")
                
            return response.text
            
        except Exception as e:
            logger.error(f"[#update_log]运行OCR时出错: {e}")
            raise
            
    def _parse_ocr_result(self, ocr_output: str) -> List[str]:
        """
        解析OCR输出结果，将相近位置的文字合并成句子
        
        Args:
            ocr_output: OCR输出的JSON字符串
            
        Returns:
            List[str]: 识别出的文本列表，相近位置的文字会被合并
        """
        try:
            result = json.loads(ocr_output)
            texts = []
            
            if isinstance(result, dict) and "code" in result and result["code"] == 100:
                # 获取所有文本块
                text_blocks = []
                for item in result.get("data", []):
                    if isinstance(item, dict):
                        # UmiOCR的返回格式中包含了文本位置信息
                        text = item.get("text", "").strip()
                        if text:
                            # 如果有位置信息，记录下来
                            pos = item.get("pos", [])  # pos格式: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                            if pos:
                                # 使用中心点y坐标作为合并依据
                                y_center = (pos[0][1] + pos[2][1]) / 2
                                text_blocks.append((text, y_center))
                            else:
                                text_blocks.append((text, -1))  # 没有位置信息的放在最后
                
                # 按y坐标排序
                text_blocks.sort(key=lambda x: x[1])
                
                # 合并相近位置的文本
                current_group = []
                current_y = None
                Y_THRESHOLD = 10  # 垂直距离阈值，可以根据实际情况调整
                
                for text, y in text_blocks:
                    if current_y is None:
                        current_group.append(text)
                        current_y = y
                    elif y == -1 or abs(y - current_y) <= Y_THRESHOLD:
                        # 同一行或没有位置信息的文本
                        current_group.append(text)
                    else:
                        # 新的一行
                        if current_group:
                            texts.append(" ".join(current_group))
                        current_group = [text]
                        current_y = y
                
                # 添加最后一组
                if current_group:
                    texts.append(" ".join(current_group))
            else:
                logger.error(f"[#update_log]OCR识别失败: {result.get('message', '未知错误')}")
            
            return texts
            
        except json.JSONDecodeError:
            logger.error("[#update_log]解析OCR结果失败")
            return []
            
        except Exception as e:
            logger.error(f"[#update_log]解析OCR结果时出错: {e}")
            return []
            
    def compare_images(self, image1_path: str, image2_path: str) -> Dict:
        """
        比较两张图片的水印情况
        
        Args:
            image1_path: 第一张图片的路径
            image2_path: 第二张图片的路径
            
        Returns:
            Dict: 比较结果，包含两张图片的水印检测结果
        """
        result = {
            "image1": {
                "path": image1_path,
                "has_watermark": False,
                "watermark_texts": []
            },
            "image2": {
                "path": image2_path,
                "has_watermark": False,
                "watermark_texts": []
            },
            "comparison": {
                "different_watermark": False,
                "watermarked_version": None
            }
        }
        
        # 检测两张图片
        result["image1"]["has_watermark"], result["image1"]["watermark_texts"] = self.detect_watermark(image1_path)
        result["image2"]["has_watermark"], result["image2"]["watermark_texts"] = self.detect_watermark(image2_path)
        
        # 判断是否一张有水印一张没有
        if result["image1"]["has_watermark"] != result["image2"]["has_watermark"]:
            result["comparison"]["different_watermark"] = True
            result["comparison"]["watermarked_version"] = "image1" if result["image1"]["has_watermark"] else "image2"
            
        return result

def test_watermark_detector():
    """测试水印检测功能"""
    # 创建检测器实例
    detector = WatermarkDetector()
    
    # 测试图片路径
    test_image1 = "path/to/test/image1.jpg"  # 有水印的图片
    test_image2 = "path/to/test/image2.jpg"  # 无水印的图片
    
    # 确保测试图片存在
    if not (os.path.exists(test_image1) and os.path.exists(test_image2)):
        logger.error("[#file_ops]测试图片不存在")
        return
        
    # 比较两张图片
    result = detector.compare_images(test_image1, test_image2)
    
    # 打印结果
    logger.info("水印检测结果:")
    logger.info(json.dumps(result, indent=2, ensure_ascii=False))

def run_demo():
    """运行演示程序，自动在测试文件夹下检测和比较图片"""
    logger.info("开始运行水印检测演示程序...")
    
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    test_dir = script_dir / "test_images"
    
    # 确保测试目录存在
    test_dir.mkdir(exist_ok=True)
    
    # 检查测试目录中的图片
    image_files = []
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        image_files.extend(test_dir.glob(f"*{ext}"))
    
    if not image_files:
        logger.error(f"[#file_ops]测试目录 {test_dir} 中没有找到图片文件")
        logger.info("请将测试图片放在以下目录中：")
        logger.info(str(test_dir))
        return
    
    # 创建检测器实例
    detector = WatermarkDetector()
    
    # 首先对所有图片进行OCR识别
    logger.info("开始对所有图片进行OCR识别...")
    for img_path in image_files:
        logger.info(f"处理图片: {img_path.name}")
        detector.detect_watermark(str(img_path))
    
    # 对所有图片进行两两比较
    total_comparisons = 0
    watermark_pairs = []
    
    logger.info(f"\n开始比较图片，共 {len(image_files)} 个文件...")
    
    for i, img1 in enumerate(image_files):
        for j, img2 in enumerate(image_files[i+1:], i+1):
            total_comparisons += 1
            logger.info(f"\n比较第 {total_comparisons} 组：")
            logger.info(f"图片1: {img1.name}")
            logger.info(f"图片2: {img2.name}")
            
            # 比较两张图片
            result = detector.compare_images(str(img1), str(img2))
            
            # 如果发现一张有水印一张没有的情况
            if result["comparison"]["different_watermark"]:
                watermark_pairs.append({
                    "watermarked": result["image1"] if result["comparison"]["watermarked_version"] == "image1" else result["image2"],
                    "clean": result["image2"] if result["comparison"]["watermarked_version"] == "image1" else result["image1"]
                })
                logger.info("✅ 发现水印差异！")
                logger.info(f"有水印版本: {watermark_pairs[-1]['watermarked']['path']}")
                logger.info(f"无水印版本: {watermark_pairs[-1]['clean']['path']}")
                logger.info(f"检测到的水印文字: {watermark_pairs[-1]['watermarked']['watermark_texts']}")
            else:
                logger.info("❌ 未发现水印差异")
    
    # 输出总结报告
    logger.info("\n=== 检测报告 ===")
    logger.info(f"总共比较了 {total_comparisons} 组图片")
    logger.info(f"发现 {len(watermark_pairs)} 组有水印差异的图片")
    
    if watermark_pairs:
        logger.info("\n详细结果:")
        for i, pair in enumerate(watermark_pairs, 1):
            logger.info(f"\n第 {i} 组:")
            logger.info(f"有水印文件: {Path(pair['watermarked']['path']).name}")
            logger.info(f"无水印文件: {Path(pair['clean']['path']).name}")
            logger.info(f"水印文字: {', '.join(pair['watermarked']['watermark_texts'])}")

if __name__ == "__main__":
    # test_watermark_detector()  # 注释掉原来的测试函数
    run_demo()  # 运行新的演示程序