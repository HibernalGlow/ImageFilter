#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试基于JSON配置的过滤功能
"""

import os
import sys
from pathlib import Path
import json
import argparse
from loguru import logger

# 添加项目根目录到系统路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from imgfilter.detectors.group.group_filter import process_group_with_filters


def setup_logger():
    """设置日志记录器"""
    logger.remove()  # 移除默认处理程序
    logger.add(sys.stderr, level="INFO", 
               format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{function}</cyan>: <level>{message}</level>")


def test_filter_with_config(test_dir: str = None, config_file: str = None):
    """
    使用JSON配置测试过滤功能
    
    Args:
        test_dir: 测试图片目录
        config_file: 过滤配置文件路径
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
    
    logger.info(f"找到 {len(image_files)} 张测试图片")
    
    # 加载配置文件
    filter_configs = []
    if config_file:
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                filter_configs = json.load(f)
                logger.info(f"已加载配置文件: {config_file}")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return
    else:
        # 使用默认配置
        filter_configs = [
            # 配置1: OCR -> 时间 -> 大小
            [
                {"type": "ocr", "params": {"model": "ch_PP-OCRv4_rec"}},
                {"type": "time", "params": {}},
                {"type": "size", "params": {}}
            ],
            # 配置2: 时间 -> OCR -> 大小
            [
                {"type": "time", "params": {}},
                {"type": "ocr", "params": {"model": "ch_PP-OCRv4_rec"}},
                {"type": "size", "params": {}}
            ],
            # 配置3: 大小 -> OCR
            [
                {"type": "size", "params": {}},
                {"type": "ocr", "params": {"model": "ch_PP-OCRv4_rec"}}
            ],
            # 配置4: 仅OCR，使用英文模型
            [
                {"type": "ocr", "params": {"model": "en_PP-OCRv4_rec"}}
            ]
        ]
    
    # 模拟相似图片组
    similar_group = image_files
    
    # 测试每个配置
    for i, config in enumerate(filter_configs, 1):
        logger.info(f"\n测试配置 {i}:")
        logger.info(f"配置内容: {json.dumps(config, ensure_ascii=False, indent=2)}")
        
        try:
            # 应用过滤
            to_delete, reasons = process_group_with_filters(similar_group, config)
            
            if to_delete:
                logger.info(f"过滤结果: 保留 {len(similar_group) - len(to_delete)} 张图片，删除 {len(to_delete)} 张图片")
                for img in to_delete:
                    reason = reasons[img]
                    logger.info(f"  删除: {os.path.basename(img)} - {reason['reason']} ({reason['details']})")
            else:
                logger.info("过滤结果: 没有图片被标记删除")
        except Exception as e:
            logger.error(f"应用配置 {i} 失败: {e}")
    
    # 测试字符串配置
    string_configs = ["ocr", "time", "size", "ocr_time", "ocr_size", "time_size", "ocr_time_size"]
    
    for config in string_configs:
        logger.info(f"\n测试字符串配置: {config}")
        
        try:
            # 应用过滤
            to_delete, reasons = process_group_with_filters(similar_group, config)
            
            if to_delete:
                logger.info(f"过滤结果: 保留 {len(similar_group) - len(to_delete)} 张图片，删除 {len(to_delete)} 张图片")
                for img in to_delete:
                    reason = reasons[img]
                    logger.info(f"  删除: {os.path.basename(img)} - {reason['reason']} ({reason['details']})")
            else:
                logger.info("过滤结果: 没有图片被标记删除")
        except Exception as e:
            logger.error(f"应用配置 {config} 失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="测试基于JSON配置的过滤功能")
    parser.add_argument("--dir", type=str, help="测试图片目录")
    parser.add_argument("--config", type=str, help="过滤配置文件路径")
    
    args = parser.parse_args()
    
    test_filter_with_config(args.dir, args.config)


if __name__ == "__main__":
    main() 