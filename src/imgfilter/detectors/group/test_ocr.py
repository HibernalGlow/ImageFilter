#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试OCR功能的脚本
"""

import os
import sys
from pathlib import Path
import argparse
from loguru import logger

# 添加项目根目录到系统路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"
from imgfilter.detectors.group.group_filter import GroupFilter


def setup_logger():
    """设置日志记录器"""
    logger.remove()  # 移除默认处理程序
    logger.add(sys.stderr, level="INFO", 
               format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{function}</cyan>: <level>{message}</level>")


def test_ocr_with_languages(test_dir: str = None, models: list = None):
    """
    使用不同语言模型测试OCR功能
    
    Args:
        test_dir: 测试图片目录
        models: 要测试的OCR模型列表，默认为中文、英文和日文模型
    """
    setup_logger()
    
    # 默认测试模型
    if not models:
        models = ["ch_PP-OCRv4_rec", "en_PP-OCRv4_rec", "japan_PP-OCRv3_rec"]
    
    # 获取测试目录
    if not test_dir:
        test_dir = Path(__file__).parent / "test_images"
    else:
        test_dir = Path(test_dir)
    
    # 确保测试目录存在
    test_dir.mkdir(exist_ok=True)
    
    logger.info(f"测试目录: {test_dir}")
    logger.info(f"测试模型: {models}")
    
    # 查找测试图片
    image_files = []
    for ext in ('.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif'):
        image_files.extend([str(p) for p in test_dir.glob(f"*{ext}")])
    
    if not image_files:
        logger.error(f"测试目录 {test_dir} 中没有找到图片文件")
        logger.info("请将测试图片放在以下目录中：")
        logger.info(str(test_dir))
        return
    
    logger.info(f"找到 {len(image_files)} 张测试图片")
    
    # 创建GroupFilter实例
    filter = GroupFilter()
    
    # 检查可用模型
    available_models = filter.available_models
    logger.info(f"可用OCR模型: {available_models}")
    
    # 对每个图片使用不同模型进行OCR测试
    for img_path in image_files:
        logger.info(f"\n测试图片: {os.path.basename(img_path)}")
        
        # 使用不同模型进行OCR
        for model in models:
            if model not in available_models:
                logger.warning(f"模型 {model} 不可用，跳过")
                continue
                
            logger.info(f"使用模型 {model} 进行OCR:")
            try:
                # 执行OCR
                ocr_results = filter._perform_ocr(img_path, model)
                
                if ocr_results:
                    # 输出OCR结果
                    logger.info(f"  识别到 {len(ocr_results)} 个文本区域:")
                    for i, (box, text, score) in enumerate(ocr_results, 1):
                        logger.info(f"  {i}. 文本: '{text}' (置信度: {score:.4f}, 位置: {box})")
                else:
                    logger.info("  未识别到文本")
                    
                # 分析语言
                text = filter._get_ocr_text(img_path, model)
                lang = filter._detect_text_language(text)
                logger.info(f"  检测到的语言: {lang}")
                logger.info(f"  文本内容: {text[:100]}..." if len(text) > 100 else f"  文本内容: {text}")
                
            except Exception as e:
                logger.error(f"OCR处理失败: {e}")
    
    logger.info("\nOCR测试完成")


def test_group_filter_with_ocr(test_dir: str = None):
    """
    测试使用OCR进行相似图片组过滤
    
    Args:
        test_dir: 测试图片目录
    """
    setup_logger()
    
    # 获取测试目录
    if not test_dir:
        test_dir = Path(__file__).parent / "test_images"
    else:
        test_dir = Path(test_dir)
    
    # 确保测试目录存在
    test_dir.mkdir(exist_ok=True)
    
    # 查找测试图片
    image_files = []
    for ext in ('.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif'):
        image_files.extend([str(p) for p in test_dir.glob(f"*{ext}")])
    
    if len(image_files) < 2:
        logger.error(f"测试目录 {test_dir} 中图片数量不足，至少需要2张图片")
        return
    
    # 创建GroupFilter实例
    filter = GroupFilter()
    
    # 模拟相似图片组
    similar_group = image_files
    
    # 测试OCR过滤
    logger.info("\n测试OCR过滤:")
    to_delete, reasons = filter.process_by_ocr(similar_group)
    
    if to_delete:
        logger.info(f"OCR过滤结果: 保留 {len(similar_group) - len(to_delete)} 张图片，删除 {len(to_delete)} 张图片")
        for img in to_delete:
            reason = reasons[img]
            logger.info(f"  删除: {os.path.basename(img)} - {reason['details']}")
    else:
        logger.info("OCR过滤结果: 没有图片被标记删除")
    
    # 测试混合过滤
    logger.info("\n测试混合过滤 (OCR+时间+大小):")
    to_delete, reasons = filter.process_by_hybrid(similar_group, "ocr_time_size")
    
    if to_delete:
        logger.info(f"混合过滤结果: 保留 {len(similar_group) - len(to_delete)} 张图片，删除 {len(to_delete)} 张图片")
        for img in to_delete:
            reason = reasons[img]
            logger.info(f"  删除: {os.path.basename(img)} - {reason['reason']} ({reason['details']})")
    else:
        logger.info("混合过滤结果: 没有图片被标记删除")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="测试OCR功能")
    parser.add_argument("--dir", type=str, help="测试图片目录")
    parser.add_argument("--mode", type=str, default="all", choices=["all", "ocr", "filter"],
                        help="测试模式: all=全部测试, ocr=仅OCR测试, filter=仅过滤测试")
    parser.add_argument("--models", type=str, help="要测试的OCR模型，用逗号分隔")
    
    args = parser.parse_args()
    
    # 处理模型参数
    models = None
    if args.models:
        models = [m.strip() for m in args.models.split(",")]
    
    # 根据模式执行测试
    if args.mode in ["all", "ocr"]:
        test_ocr_with_languages(args.dir, models)
    
    if args.mode in ["all", "filter"]:
        test_group_filter_with_ocr(args.dir)


if __name__ == "__main__":
    main() 