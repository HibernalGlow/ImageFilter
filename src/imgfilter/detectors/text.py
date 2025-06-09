from pathlib import Path
import sys
import os
import json
from PIL import Image
import pillow_avif
import pillow_jxl
import numpy as np
from typing import Tuple, List, Dict, Union, Optional
import logging
import cv2
import time
from typing import List, Set, Dict, Tuple, Union
from imgfilter.detectors.gray.grayscale_detector import GrayscaleDetector, GrayscaleConfig

# 添加PathURIGenerator导入
from hashu.core.calculate_hash_custom import PathURIGenerator

# 设置日志
from loguru import logger
# 是否启用调试模式
DEBUG_MODE = False


class CVTextImageDetector:
    """基于计算机视觉的纯文本图片检测器类"""
    
    def __init__(self, cache_file: str = None, debug: bool = False):
        """
        初始化基于计算机视觉的纯文本图片检测器
        
        Args:
            cache_file: 检测结果缓存文件路径，默认为脚本所在目录下的cv_text_image_cache.json
            debug: 是否启用调试模式
        """
        global DEBUG_MODE
        DEBUG_MODE = debug
        self.cache_file = cache_file or os.path.join(os.path.dirname(__file__), 'cv_text_image_cache.json')
        self.detection_cache = self._load_cache()
        self.grayscale_detector = GrayscaleDetector(GrayscaleConfig())
        # 智能调整参数
        self.max_keep_count = 20  # 最大保留图片数量
        self.max_keep_ratio = 0.2  # 最大保留比例 (20%)

    def _load_cache(self) -> Dict:
        """加载缓存"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载缓存文件失败: {e}")
        return {}

    def _save_cache(self):
        """保存缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.detection_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存文件失败: {e}")

    def _get_image_uri(self, image_path: str) -> str:
        """生成图片的URI"""
        return PathURIGenerator.generate(image_path)

    def detect_text_image(self, image_path: str, threshold: float = 0.5) -> Tuple[bool, Dict]:
        """
        使用计算机视觉方法检测图片是否为纯文本图片
        
        Args:
            image_path: 图片文件路径
            threshold: 判定阈值，用于最终决策
            
        Returns:
            Tuple[bool, Dict]: (是否为纯文本图片, 检测结果详情)
        """
        try:
            # 生成图片URI
            image_uri = self._get_image_uri(image_path)
            
            # 检查缓存
            # if image_uri in self.detection_cache:
            #     logger.debug(f"使用缓存的检测结果: {image_uri}")
            #     cached_result = self.detection_cache[image_uri]
            #     return cached_result.get('is_text_image', False), cached_result
            
            # 获取图片尺寸
            with Image.open(image_path) as img:
                img_width, img_height = img.size
                total_area = img_width * img_height
            
            # 使用计算机视觉方法检测
            cv_result = self._analyze_image(image_path)
            
            # 判断是否为纯文本图片
            is_text_image = cv_result['line_score'] > 0 and cv_result['total_score'] >= threshold * 4  # 总分为4分，按比例判断
            
            # 保存结果到缓存
            result = {
                'is_text_image': is_text_image,
                'total_area': total_area,
                'threshold': threshold,
                **cv_result
            }
            
            self.detection_cache[image_uri] = result
            self._save_cache()
            
            logger.info(f"图片文本检测结果 [{os.path.basename(image_path)}]: " +
                       f"总分={cv_result['total_score']}/4, 是否文本图片={is_text_image}")
            
            return is_text_image, result
            
        except Exception as e:
            logger.error(f"检测纯文本图片时出错: {e}")
            return False, {'error': str(e)}
    
    def _analyze_image(self, image_path: str) -> Dict:
        """
        综合分析图像特征，判断是否为文本图片
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            Dict: 分析结果，包含各项特征得分和总分
        """
        try:
            # 使用Pillow读取图片
            with Image.open(image_path) as pil_img:
                # 先进行灰度检测
                grayscale_result = self.grayscale_detector.analyze_image(pil_img)
                if not (grayscale_result.is_grayscale or grayscale_result.is_white_image or grayscale_result.is_pure_white or grayscale_result.is_pure_black):
                    return {
                        'total_score': 0,
                        'line_score': 0,  # 确保包含所有必要键以防后续处理错误
                        'is_grayscale': False
                    }
                
                # 转换为RGB模式
                if pil_img.mode == 'RGBA':
                    pil_img = pil_img.convert('RGB')
                # 转换为numpy数组
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            
            # 获取图像尺寸
            height, width = img.shape[:2]
            
            # 转为灰度图
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 1. 行分析 - 检测文本行（这是判定的必要条件）
            line_score, line_info = self._analyze_text_lines(gray, height, width)
            
            # 如果没有检测到文本行，可以提前返回，避免后续不必要的计算
            if line_score == 0:
                return {
                    'line_score': 0,
                    'line_info': line_info,
                    'pattern_score': 0,
                    'edge_score': 0,
                    'color_score': 0,
                    'total_score': 0
                }
            
            # 执行其他分析
            pattern_score, pattern_info = self._analyze_frequency_pattern(gray, height, width)
            edge_score, edge_info = self._analyze_edges(gray)
            color_score, color_info = self._analyze_color_distribution(img)
            
            # 计算总分
            total_score = (line_score * 0.8 + pattern_score + edge_score * 0.8 + color_score * 1.4)
            
            # 添加文本密度分析补偿
            line_count = line_info.get('line_count', 0)
            line_uniformity = line_info.get('line_uniformity', 0)
            line_coverage = line_info.get('line_coverage', 0)
            if line_count >= 2 and line_uniformity > 0.6:
                density_bonus = min(0.4, line_coverage * 0.5)
                total_score += density_bonus
            
            result = {
                'line_score': line_score,
                'line_info': line_info,
                'pattern_score': pattern_score,
                'pattern_info': pattern_info,
                'edge_score': edge_score,
                'edge_info': edge_info,
                'color_score': color_score,
                'color_info': color_info,
                'total_score': total_score
            }
            
            if DEBUG_MODE:
                logger.info(f"CV分析结果: 行分析={line_score}, 频率模式={pattern_score}, " +
                           f"边缘分析={edge_score}, 颜色分析={color_score}, 总分={total_score}")
            
            return result
            
        except Exception as e:
            logger.error(f"图像分析失败: {e}")
            return {'total_score': 0, 'line_score': 0, 'error': str(e)}
            
    def _analyze_text_lines(self, gray_img: np.ndarray, height: int, width: int) -> Tuple[float, Dict]:
        """
        分析图像中的文本行特征
        
        Args:
            gray_img: 灰度图像
            height: 图像高度
            width: 图像宽度
            
        Returns:
            Tuple[float, Dict]: (得分, 详细信息)
        """
        try:
            # 自适应阈值分割，寻找可能的文本区域
            binary = cv2.adaptiveThreshold(
                gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # 膨胀操作连接临近文字
            kernel = np.ones((3, 15), np.uint8)  # 横向连接
            dilated = cv2.dilate(binary, kernel, iterations=1)
            
            # 查找轮廓
            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            # 分析轮廓
            min_area = height * width * 0.0005  # 最小面积阈值
            text_lines = []
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0
                area = w * h
                
                # 文本行通常较宽且细
                if area > min_area and aspect_ratio > 2.5 and h < height * 0.1:
                    text_lines.append((y, h, w, aspect_ratio))
            
            # 按y坐标排序
            text_lines.sort(key=lambda x: x[0])
            
            # 分析行特征
            line_count = len(text_lines)
            line_coverage = 0
            line_uniformity = 0
            avg_aspect_ratio = 0
            
            if line_count >= 3:  # 至少有3行才可能是文本图片
                # 计算行间距
                line_gaps = []
                for i in range(1, len(text_lines)):
                    prev_y, prev_h, _, _ = text_lines[i-1]
                    curr_y, _, _, _ = text_lines[i]
                    gap = curr_y - (prev_y + prev_h)
                    if gap > 0:
                        line_gaps.append(gap)
                
                # 计算行覆盖率
                if height > 0:
                    text_height_sum = sum(h for _, h, _, _ in text_lines)
                    line_coverage = text_height_sum / height
                
                # 计算行均匀性
                if line_gaps:
                    avg_gap = sum(line_gaps) / len(line_gaps)
                    gap_variance = np.var(line_gaps)
                    line_uniformity = 1 - min(1, gap_variance / (avg_gap ** 2) if avg_gap > 0 else 1)
                
                # 计算平均宽高比
                aspect_ratios = [ar for _, _, _, ar in text_lines]
                avg_aspect_ratio = sum(aspect_ratios) / len(aspect_ratios) if aspect_ratios else 0
            
            # 计算得分 (0-1)
            line_score = 0
            if line_count >= 5 and line_uniformity > 0.7:
                line_score = 1.0  # 行数多且均匀
            elif line_count >= 3 and line_uniformity > 0.5:
                line_score = 0.7  # 行数适中且较均匀
            elif line_count >= 2:
                line_score = 0.3  # 至少有几行
            
            info = {
                'line_count': line_count,
                'line_coverage': line_coverage,
                'line_uniformity': line_uniformity,
                'avg_aspect_ratio': avg_aspect_ratio
            }
            
            return line_score, info
            
        except Exception as e:
            logger.error(f"行分析失败: {e}")
            return 0, {'error': str(e)}
    
    def _analyze_frequency_pattern(self, gray_img: np.ndarray, height: int, width: int) -> Tuple[float, Dict]:
        """
        使用频率域分析检测文本的规律性排列
        
        Args:
            gray_img: 灰度图像
            height: 图像高度
            width: 图像宽度
            
        Returns:
            Tuple[float, Dict]: (得分, 详细信息)
        """
        try:
            # 应用FFT
            f_transform = np.fft.fft2(gray_img)
            f_shift = np.fft.fftshift(f_transform)
            magnitude_spectrum = 20 * np.log(np.abs(f_shift) + 1)
            
            # 将频谱标准化到0-255范围内
            magnitude_spectrum = cv2.normalize(magnitude_spectrum, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
            
            # 分析频谱中的水平线模式（通常表示文本行）
            horizontal_profile = np.sum(magnitude_spectrum[height//2-height//6:height//2+height//6, :], axis=0)
            vertical_profile = np.sum(magnitude_spectrum[:, width//2-width//6:width//2+width//6], axis=1)
            
            # 计算水平和垂直配置文件的峰值
            horizontal_peaks = np.sum(horizontal_profile > np.mean(horizontal_profile) * 1.5)
            vertical_peaks = np.sum(vertical_profile > np.mean(vertical_profile) * 1.5)
            
            # 文本图像通常在水平方向上有更多的规律性
            h_v_ratio = horizontal_peaks / max(1, vertical_peaks)
            
            # 计算得分 (0-1)
            pattern_score = 0
            if h_v_ratio > 1.8:
                pattern_score = 1.0  # 水平方向规律性非常明显
            elif h_v_ratio > 1.4:
                pattern_score = 0.7  # 水平方向规律性明显
            elif h_v_ratio > 1.1:
                pattern_score = 0.3  # 水平方向规律性略高
            
            info = {
                'h_v_ratio': h_v_ratio,
                'horizontal_peaks': int(horizontal_peaks),
                'vertical_peaks': int(vertical_peaks)
            }
            
            return pattern_score, info
            
        except Exception as e:
            logger.error(f"频率分析失败: {e}")
            return 0, {'error': str(e)}
    
    def _analyze_edges(self, gray_img: np.ndarray) -> Tuple[float, Dict]:
        """
        分析图像边缘特征，检测文本图像的边缘分布
        
        Args:
            gray_img: 灰度图像
            
        Returns:
            Tuple[float, Dict]: (得分, 详细信息)
        """
        try:
            # 计算Sobel边缘
            sobelx = cv2.Sobel(gray_img, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray_img, cv2.CV_64F, 0, 1, ksize=3)
            
            # 计算梯度幅度
            gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
            
            # 计算梯度方向
            gradient_direction = np.arctan2(sobely, sobelx) * 180 / np.pi
            
            # 统计垂直和水平方向的梯度
            horizontal_edges = np.sum((gradient_direction > -20) & (gradient_direction < 20) & 
                                      (gradient_magnitude > np.mean(gradient_magnitude) * 1.2))
            vertical_edges = np.sum(((gradient_direction > 70) & (gradient_direction < 110) | 
                                     (gradient_direction > -110) & (gradient_direction < -70)) & 
                                    (gradient_magnitude > np.mean(gradient_magnitude) * 1.2))
            
            # 文本图像通常垂直边缘更多
            edge_ratio = vertical_edges / max(1, horizontal_edges)
            
            # 计算边缘密度
            total_pixels = gray_img.shape[0] * gray_img.shape[1]
            edge_density = (vertical_edges + horizontal_edges) / max(1, total_pixels)
            
            # 计算得分 (0-1)
            edge_score = 0
            # 文本图片通常垂直边缘应明显多于水平边缘
            if edge_ratio > 1.8 and edge_density > 0.05:
                edge_score = 1.0  # 垂直边缘明显且边缘密度适中
            elif edge_ratio > 1.5 and edge_density > 0.03:
                edge_score = 0.7  # 垂直边缘较多且边缘密度较高
            # 如果水平边缘数量接近或超过垂直边缘，很可能不是文本图片
            elif edge_ratio < 1.2:
                edge_score = 0  # 水平边缘过多，不像是文本图片
            elif edge_ratio > 1.2:
                edge_score = 0.3  # 垂直边缘略多
            
            info = {
                'edge_ratio': edge_ratio,
                'edge_density': edge_density,
                'vertical_edges': int(vertical_edges),
                'horizontal_edges': int(horizontal_edges)
            }
            
            return edge_score, info
            
        except Exception as e:
            logger.error(f"边缘分析失败: {e}")
            return 0, {'error': str(e)}
    
    def _analyze_color_distribution(self, img: np.ndarray) -> Tuple[float, Dict]:
        """
        分析图像颜色分布特征，检测文本图像的颜色特征
        
        Args:
            img: 彩色图像
            
        Returns:
            Tuple[float, Dict]: (得分, 详细信息)
        """
        try:
            # 计算图像颜色直方图
            hist_b = cv2.calcHist([img], [0], None, [32], [0, 256])
            hist_g = cv2.calcHist([img], [1], None, [32], [0, 256])
            hist_r = cv2.calcHist([img], [2], None, [32], [0, 256])
            
            # 归一化直方图
            cv2.normalize(hist_b, hist_b, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(hist_g, hist_g, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(hist_r, hist_r, 0, 1, cv2.NORM_MINMAX)
            
            # 计算直方图的峰值数量（颜色种类）
            def count_peaks(hist, threshold=0.3):
                peaks = 0
                for i in range(1, len(hist)-1):
                    if hist[i] > threshold and hist[i] > hist[i-1] and hist[i] > hist[i+1]:
                        peaks += 1
                return peaks
                
            color_peaks = count_peaks(hist_b) + count_peaks(hist_g) + count_peaks(hist_r)
            
            # 计算颜色对比度
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            min_val, max_val, _, _ = cv2.minMaxLoc(gray)
            contrast = (max_val - min_val) / 255 if max_val > min_val else 0
            
            # 计算得分 (0-1)
            color_score = 0
            if color_peaks < 8 and contrast > 0.5:
                color_score = 1.0  # 颜色少且对比度高
            elif color_peaks < 12 or contrast > 0.4:
                color_score = 0.7  # 颜色较少或对比度较高
            elif color_peaks < 16:
                color_score = 0.3  # 颜色种类适中
            
            info = {
                'color_peaks': color_peaks,
                'contrast': contrast
            }
            
            return color_score, info
            
        except Exception as e:
            logger.error(f"颜色分析失败: {e}")
            return 0, {'error': str(e)}

    def _smart_adjust_threshold(self, image_files: List[str], initial_threshold: float = 0.5) -> Tuple[float, List[Tuple[str, float]]]:
        """
        智能调整阈值，确保保留的图片数量在合理范围内
        
        Args:
            image_files: 图片文件路径列表
            initial_threshold: 初始阈值
            
        Returns:
            Tuple[float, List[Tuple[str, float]]]: (最终使用的阈值, 要删除的图片列表)
        """
        total_images = len(image_files)
        max_delete_count = max(total_images - self.max_keep_count, 
                              total_images - int(total_images * (1 - self.max_keep_ratio)))
        
        logger.info(f"智能阈值调整: 总图片数={total_images}, 最大删除数={max_delete_count}")
        
        # 阈值调整范围和步长
        threshold_candidates = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        best_threshold = initial_threshold
        best_result = []
        
        # 尝试不同阈值，找到最适合的
        for threshold in threshold_candidates:
            logger.info(f"尝试阈值: {threshold}")
            
            # 使用当前阈值检测
            current_result = []
            for img_path in image_files:
                try:
                    is_text_image, result = self.detect_text_image(img_path, threshold)
                    score = result.get('total_score', 0) if isinstance(result, dict) else result
                    
                    if is_text_image:
                        current_result.append((img_path, score))
                except Exception as e:
                    logger.error(f"检测失败 {img_path}: {e}")
                    continue
            
            delete_count = len(current_result)
            logger.info(f"阈值 {threshold}: 检测到 {delete_count} 张文本图片")
            
            # 如果删除数量在合理范围内，使用此阈值
            if delete_count <= max_delete_count:
                best_threshold = threshold
                best_result = current_result
                logger.info(f"选择阈值 {threshold}: 删除 {delete_count} 张图片")
                break
            else:
                # 记录当前最优结果
                if not best_result or delete_count < len(best_result):
                    best_threshold = threshold
                    best_result = current_result
        
        # 如果所有阈值都超出限制，选择删除数量最少的
        if len(best_result) > max_delete_count:
            logger.warning(f"所有阈值都超出限制，使用阈值 {best_threshold} (删除 {len(best_result)} 张)")
            
            # 按分数排序，优先删除分数最高的（最明显的文本图片）
            best_result.sort(key=lambda x: x[1], reverse=True)
            best_result = best_result[:max_delete_count]
            logger.info(f"限制删除数量为 {len(best_result)} 张")
        
        return best_threshold, best_result

    def apply_text_filter(self, image_files: List[str], threshold: float = 0.5, use_smart_adjustment: bool = True) -> List[Tuple[str, float]]:
        """
        应用纯文本图片过滤，返回要删除的图片和检测分数
        
        Args:
            image_files: 图片文件路径列表
            threshold: 文本图片检测阈值
            use_smart_adjustment: 是否使用智能阈值调整
        
        Returns:
            List[Tuple[str, float]]: (待删除图片路径, 文本检测分数)列表
        """
        if use_smart_adjustment:
            # 使用智能调整
            final_threshold, to_delete = self._smart_adjust_threshold(image_files, threshold)
            logger.info(f"智能调整完成: 使用阈值 {final_threshold}, 删除 {len(to_delete)} 张图片")
            return to_delete
        else:
            # 使用原有逻辑
            to_delete = []
            
            # 检测每张图片是否为文本图片
            for img_path in image_files:
                try:
                    is_text_image, result = self.detect_text_image(img_path, threshold)
                    score = result.get('total_score', 0) if isinstance(result, dict) else result
                    
                    if is_text_image:
                        to_delete.append((img_path, score))
                        # 只记录基础名称，不记录完整路径
                        logger.info(f"图片文本检测结果 [{os.path.basename(img_path)}]: 总分={score}/4, 是否文本图片={is_text_image}")
                except Exception as e:
                    logger.error(f"处理纯文本图片检测失败 {img_path}: {e}")
            
            return to_delete

    def process_text_images(self, image_files: List[str], threshold: float = 0.5, use_smart_adjustment: bool = True) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        处理纯文本图片过滤，提供完整的过滤结果
        
        Args:
            image_files: 图片文件路径列表
            threshold: 文本图片检测阈值
            use_smart_adjustment: 是否使用智能阈值调整
        
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        to_delete = set()
        removal_reasons = {}
        
        # 使用智能调整或传统方法进行过滤
        deleted_files = self.apply_text_filter(image_files, threshold, use_smart_adjustment)
        for img, score in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'text_image',
                'details': '纯文本图片',
                'score': score
            }
            logger.info(f"标记删除纯文本图片: {os.path.basename(img)}")
        
        return to_delete, removal_reasons


def test_cv_text_image_detector(test_dir: str = None, debug: bool = False, test_smart_adjustment: bool = True):
    """测试基于计算机视觉的纯文本图片检测功能
    
    Args:
        test_dir: 测试图片目录，默认为脚本所在目录下的test_images
        debug: 是否启用调试模式
        test_smart_adjustment: 是否测试智能阈值调整功能
    """
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    test_dir = Path(input("请输入测试图片目录（默认使用脚本所在目录下的test_images）: ") or (script_dir / 'test_images'))
    
    # 确保测试目录存在
    test_dir.mkdir(exist_ok=True)
    
    # 设置调试模式

    
    # 检查测试目录中的图片
    image_files = []
    for ext in ('.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif'):
        image_files.extend(test_dir.glob(f"*{ext}"))
    
    if not image_files:
        logger.error(f"测试目录 {test_dir} 中没有找到图片文件")
        logger.info("请将测试图片放在以下目录中：")
        logger.info(str(test_dir))
        return
    
    # 创建检测器实例
    detector = CVTextImageDetector(debug=debug)
    
    # 对所有图片进行检测
    logger.info(f"开始检测文本图片，共 {len(image_files)} 个文件...")
    
    if test_smart_adjustment:
        logger.info("\n=== 测试智能阈值调整功能 ===")
        # 测试智能调整功能
        smart_to_delete = detector.apply_text_filter([str(f) for f in image_files], use_smart_adjustment=True)
        logger.info(f"智能调整后要删除的图片数量: {len(smart_to_delete)}")
        
        if smart_to_delete:
            logger.info("智能调整删除的图片:")
            for img_path, score in smart_to_delete:
                logger.info(f"  - {os.path.basename(img_path)}: {score:.2f}/4")
        
        logger.info("\n=== 对比传统方法 ===")
        # 对比传统方法
        traditional_to_delete = detector.apply_text_filter([str(f) for f in image_files], use_smart_adjustment=False)
        logger.info(f"传统方法要删除的图片数量: {len(traditional_to_delete)}")
        
        if traditional_to_delete:
            logger.info("传统方法删除的图片:")
            for img_path, score in traditional_to_delete:
                logger.info(f"  - {os.path.basename(img_path)}: {score:.2f}/4")
        
        # 输出对比结果
        logger.info(f"\n智能调整效果:")
        logger.info(f"传统方法删除数量: {len(traditional_to_delete)}")
        logger.info(f"智能调整删除数量: {len(smart_to_delete)}")
        saved_count = len(traditional_to_delete) - len(smart_to_delete)
        logger.info(f"智能调整节省了: {saved_count} 张图片")
        
        return
    
    text_images = []
    non_text_images = []
    
    for img_path in image_files:
        logger.info(f"\n处理图片: {img_path.name}")
        is_text_image, result = detector.detect_text_image(str(img_path))
        
        if is_text_image:
            text_images.append((img_path, result))
            logger.info(f"✅ [{img_path.name}] 被检测为纯文本图片")
            logger.info(f"   总分: {result.get('total_score', 0)}/4")
            logger.info(f"   行分析: {result.get('line_score', 0)}, 行数: {result.get('line_info', {}).get('line_count', 0)}")
        else:
            non_text_images.append((img_path, result))
            logger.info(f"❌ [{img_path.name}] 不是纯文本图片")
            logger.info(f"   总分: {result.get('total_score', 0)}/4")
    
    # 输出总结报告
    logger.info("\n=== 检测报告 ===")
    logger.info(f"总共检测了 {len(image_files)} 张图片")
    logger.info(f"检测到 {len(text_images)} 张纯文本图片, {len(non_text_images)} 张非纯文本图片")
    
    if text_images:
        logger.info("\n纯文本图片详情:")
        for i, (img_path, result) in enumerate(text_images, 1):
            logger.info(f"\n第 {i} 张: {img_path.name}")
            logger.info(f"总分: {result['total_score']}/4")
            logger.info(f"行分析得分: {result['line_score']}")
            logger.info(f"频率分析得分: {result['pattern_score']}")
            logger.info(f"边缘分析得分: {result['edge_score']}")
            logger.info(f"颜色分析得分: {result['color_score']}")


if __name__ == "__main__":
    test_cv_text_image_detector(debug=True)