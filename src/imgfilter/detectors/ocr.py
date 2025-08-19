import os
import json
import re
from typing import List, Dict, Tuple, Optional, Union, Any
from pathlib import Path
from PIL import Image
import pillow_avif  # 支持AVIF格式
import pillow_jxl   # 支持JXL格式
from loguru import logger

# 懒加载OCR相关功能
_ocr_module = None
_ocr_available = None
os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"
def _load_ocr_module():
    """
    懒加载OCR模块
    
    Returns:
        Tuple[bool, Any]: (是否成功加载, OCR模块或None)
    """
    global _ocr_module, _ocr_available
    
    # 如果已经尝试加载过，直接返回缓存结果
    if _ocr_available is not None:
        return _ocr_available, _ocr_module
    
    try:
        # 尝试导入OCR模块
        from imgutils import ocr as ocr_module
        _ocr_module = ocr_module
        _ocr_available = True
        logger.info("成功加载OCR模块")
        return True, _ocr_module
    except ImportError as e:
        logger.warning(f"无法导入OCR模块: {e}")
        _ocr_available = False
        _ocr_module = None
        return False, None


def list_rec_models() -> List[str]:
    """
    获取可用的OCR识别模型列表
    
    Returns:
        List[str]: 可用模型列表
    """
    success, module = _load_ocr_module()
    if success:
        try:
            return module.list_rec_models()
        except Exception as e:
            logger.error(f"获取OCR模型列表失败: {e}")
    
    # 如果无法获取真实的模型列表，返回默认模型列表
    return ["ch_PP-OCRv4_rec", "en_PP-OCRv4_rec", "japan_PP-OCRv3_rec"]


def ocr(image, detect_model: str = "ch_PP-OCRv4_det", recognize_model: str = "ch_PP-OCRv4_rec", **kwargs) -> List[Tuple]:
    """
    执行OCR识别
    
    Args:
        image: PIL图像对象
        detect_model: 检测模型名称
        recognize_model: 识别模型名称
        **kwargs: 其他参数
        
    Returns:
        List[Tuple]: OCR识别结果
    """
    success, module = _load_ocr_module()
    if success:
        try:
            return module.ocr(image, detect_model=detect_model, recognize_model=recognize_model, **kwargs)
        except Exception as e:
            logger.error(f"OCR识别失败: {e}")
    
    # 如果无法使用真实的OCR功能，返回空结果
    logger.warning("使用模拟OCR功能，请安装imgutils库获取完整功能")
    return []


class OcrDetector:
    """文本检测器，提供OCR识别和文本分析功能"""
    
    def __init__(self, cache_file: str = None, default_model: str = "ch_PP-OCRv4_rec"):
        """
        初始化文本检测器
        
        Args:
            cache_file: OCR结果缓存文件路径
            default_model: 默认OCR识别模型
        """
        self.cache_file = cache_file or os.path.join(os.path.dirname(__file__), 'ocr_detector_cache.json')
        self.cache = self._load_cache()
        self.default_model = default_model
        
        # 获取可用模型列表
        try:
            self.available_models = list_rec_models()
            logger.info(f"可用OCR模型: {self.available_models}")
        except Exception as e:
            logger.error(f"获取OCR模型列表失败: {e}")
            self.available_models = []
    
    def _load_cache(self) -> Dict:
        """加载OCR结果缓存"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载OCR缓存文件失败: {e}")
        return {}
    
    def _save_cache(self):
        """保存OCR结果缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存OCR缓存文件失败: {e}")
    
    def detect_text_language(self, text: str) -> str:
        """
        检测文本语言类型
        
        Args:
            text: 需要检测的文本
            
        Returns:
            str: 语言类型 ('chinese', 'japanese', 'english', 'unknown')
        """
        # 正则表达式识别中文、日文、英文
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        japanese_pattern = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf]')
        english_pattern = re.compile(r'[a-zA-Z]')
        
        # 计算各种语言字符的数量
        chinese_count = len(chinese_pattern.findall(text))
        japanese_count = len(japanese_pattern.findall(text))
        english_count = len(english_pattern.findall(text))
        
        # 根据字符数量判断语言类型
        if chinese_count > japanese_count and chinese_count > english_count:
            return 'chinese'
        elif japanese_count > chinese_count and japanese_count > english_count:
            return 'japanese'
        elif english_count > chinese_count and english_count > japanese_count:
            return 'english'
        elif chinese_count == 0 and japanese_count == 0 and english_count == 0:
            return 'unknown'
        else:
            # 混合语言，返回最多的
            counts = [
                ('chinese', chinese_count),
                ('japanese', japanese_count),
                ('english', english_count)
            ]
            return max(counts, key=lambda x: x[1])[0]
    
    def perform_ocr(self, image_path: str, model: str = None) -> List[Tuple]:
        """
        对图片进行OCR识别
        
        Args:
            image_path: 图片路径
            model: OCR模型名称，为None时使用默认模型
            
        Returns:
            List[Tuple]: OCR识别结果
        """
        try:
            # 检查缓存
            ocr_model = model or self.default_model
            cache_key = f"{image_path}_{ocr_model}"
            if cache_key in self.cache:
                logger.info(f"使用OCR缓存结果: {os.path.basename(image_path)}")
                return self.cache[cache_key]
            
            # 打开图片
            image = Image.open(image_path)
            
            # 使用指定的OCR模型
            results = ocr(image, recognize_model=ocr_model)
            
            # 缓存结果
            self.cache[cache_key] = results
            self._save_cache()
            
            return results
        except Exception as e:
            logger.error(f"OCR识别失败 {image_path}: {e}")
            return []
    
    def get_ocr_text(self, image_path: str, model: str = None) -> str:
        """
        获取图片OCR识别的文本内容
        
        Args:
            image_path: 图片路径
            model: OCR模型名称，为None时使用默认模型
            
        Returns:
            str: 合并后的OCR文本
        """
        results = self.perform_ocr(image_path, model)
        
        # 提取所有文本并合并
        texts = [text for _, text, _ in results]
        return " ".join(texts)
    
    def analyze_image_text(self, image_path: str) -> Dict:
        """
        分析图片中的文字并返回语言信息
        
        Args:
            image_path: 图片路径
            
        Returns:
            Dict: 文字分析结果
        """
        # 使用中文模型进行初步识别
        text = self.get_ocr_text(image_path)
        
        # 检测语言
        lang = self.detect_text_language(text)
        
        # 如果初步识别为非中文，尝试使用对应语言的模型再次识别
        if lang == 'english' and 'en_PP-OCRv4_rec' in self.available_models:
            text = self.get_ocr_text(image_path, 'en_PP-OCRv4_rec')
        elif lang == 'japanese' and 'japan_PP-OCRv3_rec' in self.available_models:
            text = self.get_ocr_text(image_path, 'japan_PP-OCRv3_rec')
        
        # 返回分析结果
        return {
            'text': text,
            'language': lang,
            'text_count': len(text.strip())
        }
    
    def calculate_text_density(self, image_path: str, model: str = None) -> Dict:
        """
        计算图片的文字密度
        
        Args:
            image_path: 图片路径
            model: OCR模型名称，为None时使用默认模型
            
        Returns:
            Dict: 文字密度分析结果
        """
        try:
            # 获取OCR结果
            ocr_results = self.perform_ocr(image_path, model)
            
            # 如果没有OCR结果，返回零密度
            if not ocr_results:
                return {
                    'text_count': 0,
                    'text_area': 0,
                    'image_area': 0,
                    'text_density': 0.0,
                    'char_density': 0.0
                }
            
            # 打开图片获取尺寸
            with Image.open(image_path) as img:
                image_width, image_height = img.size
            image_area = image_width * image_height
            
            # 计算文本区域总面积
            text_area = 0
            total_chars = 0
            
            for result in ocr_results:
                # 确保结果格式正确
                if not isinstance(result, (list, tuple)) or len(result) < 2:
                    logger.warning(f"跳过无效的OCR结果项: {result}")
                    continue
                
                # 提取文本和边界框
                box, text = None, ""
                if len(result) >= 3:  # 标准格式：[box, text, confidence]
                    box, text, _ = result
                elif len(result) == 2:  # 简化格式：[box, text]
                    box, text = result
                
                # 确保text是字符串
                if not isinstance(text, str):
                    text = str(text) if text is not None else ""
                
                # 统计字符数
                total_chars += len(text)
                
                # 处理边界框计算面积
                if box is None or not box:
                    continue
                
                # 支持不同格式的边界框
                try:
                    if isinstance(box, (list, tuple)) and len(box) == 4:
                        # 处理标准四点边界框 [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
                        if all(isinstance(p, (list, tuple)) and len(p) == 2 for p in box):
                            x1, y1 = box[0]
                            x2, y2 = box[1]
                            x3, y3 = box[2]
                            x4, y4 = box[3]
                            
                            # 使用多边形面积公式
                            area = 0.5 * abs((x1*(y2-y4) + x2*(y3-y1) + x3*(y4-y2) + x4*(y1-y3)))
                            text_area += area
                        else:
                            # 可能是 [x1, y1, x2, y2] 格式的矩形边界框
                            x1, y1, x2, y2 = box
                            width = abs(x2 - x1)
                            height = abs(y2 - y1)
                            text_area += width * height
                    elif isinstance(box, dict) and all(k in box for k in ['left', 'top', 'width', 'height']):
                        # 字典格式的边界框 {'left': x, 'top': y, 'width': w, 'height': h}
                        text_area += box['width'] * box['height']
                    else:
                        logger.warning(f"无法识别的边界框格式: {box}")
                except Exception as e:
                    logger.warning(f"处理边界框时出错: {e}, 边界框: {box}")
                    continue
            
            # 计算密度指标
            text_density = text_area / image_area if image_area > 0 else 0
            char_density = total_chars / (image_width * image_height / 1000) if image_area > 0 else 0
            
            return {
                'text_count': total_chars,
                'text_area': text_area,
                'image_area': image_area,
                'text_density': text_density,  # 文本区域占图片面积的比例
                'char_density': char_density   # 每1000像素的字符数
            }
            
        except Exception as e:
            logger.error(f"计算文字密度失败 {image_path}: {e}")
            return {
                'text_count': 0,
                'text_area': 0,
                'image_area': 0,
                'text_density': 0.0,
                'char_density': 0.0,
                'error': str(e)
            }


def test_ocr_module():
    """测试OCR模块功能"""
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    test_dir = script_dir / "test_images"
    
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
    
    # 创建文本检测器
    detector = OcrDetector()
    
    # 对图片进行OCR分析
    successes = 0
    failures = 0
    
    for img_path in image_files:
        logger.info(f"分析图片: {os.path.basename(img_path)}")
        
        try:
            # 文本分析
            text_analysis = detector.analyze_image_text(img_path)
            logger.info(f"  语言: {text_analysis['language']}")
            logger.info(f"  文字数量: {text_analysis['text_count']}")
            text = text_analysis['text']
            logger.info(f"  文字内容: {text[:100]}..." if len(text) > 100 else text)
            
            # 密度分析
            density = detector.calculate_text_density(img_path)
            
            # 检查是否有错误字段
            if 'error' in density:
                logger.warning(f"  文字密度计算出现问题: {density['error']}")
                failures += 1
            else:
                logger.info(f"  文本区域面积: {density['text_area']:.2f} 像素²")
                logger.info(f"  图片总面积: {density['image_area']:.2f} 像素²")
                logger.info(f"  文本密度: {density['text_density']*100:.2f}%")
                logger.info(f"  字符密度: {density['char_density']:.2f} 字符/千像素")
                successes += 1
        except Exception as e:
            logger.error(f"处理图片时出错: {e}")
            failures += 1
        
        logger.info("----------")
    
    # 总结测试结果
    logger.info(f"测试完成: 成功 {successes} 个, 失败 {failures} 个")
    
    # 如果有失败，建议用户检查OCR模型和图片格式
    if failures > 0:
        logger.warning("有部分图片分析失败，可能的原因:")
        logger.warning("1. OCR模型未正确安装或加载")
        logger.warning("2. 图片格式不被支持或损坏")
        logger.warning("3. 边界框格式与预期不符")


def select_best_image(image_paths: List[str]) -> Tuple[str, Dict]:
    """
    从多张图片中选择文字内容最丰富的一张
    
    Args:
        image_paths: 图片路径列表
        
    Returns:
        Tuple[str, Dict]: (最佳图片路径, 分析结果)
    """
    if not image_paths:
        return None, {}
    
    # 创建文本检测器
    detector = OcrDetector()
    
    # 分析每张图片
    results = {}
    for img_path in image_paths:
        # 文本分析
        text_analysis = detector.analyze_image_text(img_path)
        density_analysis = detector.calculate_text_density(img_path)
        
        # 记录分析结果
        results[img_path] = {
            'language': text_analysis['language'],
            'text_count': text_analysis['text_count'],
            'text_density': density_analysis['text_density'],
            'char_density': density_analysis['char_density']
        }
        
        logger.debug(f"图片 [{os.path.basename(img_path)}] 分析结果: "
                   f"语言={text_analysis['language']}, "
                   f"文字数={text_analysis['text_count']}, "
                   f"文字密度={density_analysis['text_density']*100:.2f}%")
    
    # 基于语言优先级和文字密度选择最佳图片
    # 优先级: 中文 > 英文 > 日文 > 无文字
    language_priority = {
        'chinese': 3,
        'english': 2,
        'japanese': 1,
        'unknown': 0
    }
    
    # 按优先级分组
    grouped_by_lang = {}
    for img_path, data in results.items():
        lang = data['language']
        if lang not in grouped_by_lang:
            grouped_by_lang[lang] = []
        grouped_by_lang[lang].append(img_path)
    
    # 找出最高优先级的语言组
    best_lang = None
    for lang in sorted(grouped_by_lang.keys(), key=lambda l: language_priority.get(l, 0), reverse=True):
        if grouped_by_lang[lang]:
            best_lang = lang
            break
    
    if not best_lang or not grouped_by_lang[best_lang]:
        # 如果没有找到合适的语言组，返回第一张图片
        return image_paths[0], results.get(image_paths[0], {})
    
    # 在最佳语言组中，按文字密度和文字数量选择最佳图片
    best_images = grouped_by_lang[best_lang]
    best_image = max(best_images, 
                     key=lambda img: (results[img]['text_density'], results[img]['text_count']))
    
    return best_image, results[best_image]


if __name__ == "__main__":
    # 运行测试
    test_ocr_module()
    
    # 示例：如何使用select_best_image函数
    script_dir = Path(__file__).parent
    test_dir = script_dir / "test_images"
    
    if test_dir.exists():
        image_files = []
        for ext in ('.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif'):
            image_files.extend([str(p) for p in test_dir.glob(f"*{ext}")])
        
        if image_files:
            logger.info("\n示例：选择最佳图片")
            best_img, analysis = select_best_image(image_files)
            logger.info(f"最佳图片: {os.path.basename(best_img)}")
            logger.info(f"分析结果: 语言={analysis['language']}, "
                       f"文字数={analysis['text_count']}, "
                       f"文字密度={analysis['text_density']*100:.2f}%") 