#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
逐档位过滤快速测试脚本

用于快速验证逐档位过滤功能是否正常工作
"""

import os
import sys
from pathlib import Path
from typing import List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from imgfilter.detectors.group.group_filter import GroupFilter, process_group_with_filters
from loguru import logger

def quick_test():
    """快速测试逐档位过滤功能"""
    logger.info("快速测试逐档位过滤功能")
    logger.info("=" * 40)
    
    # 创建过滤器实例
    filter_instance = GroupFilter()
    
    # 模拟图片信息（实际使用中会从真实图片获取）
    mock_image_info = {
        'img1.jpg': {
            'pixel_count': 2073600,  # 1920x1080
            'dimensions': (1920, 1080),
            'file_size': 1500000,    # 1.5MB
            'filename': 'img1.jpg'
        },
        'img2.jpg': {
            'pixel_count': 2073600,  # 1920x1080 (相同尺寸)
            'dimensions': (1920, 1080),
            'file_size': 1200000,    # 1.2MB (较小)
            'filename': 'img2.jpg'
        },
        'img3.jpg': {
            'pixel_count': 921600,   # 1280x720 (较小尺寸)
            'dimensions': (1280, 720),
            'file_size': 800000,     # 0.8MB
            'filename': 'img3.jpg'
        },
        'img4.jpg': {
            'pixel_count': 2073600,  # 1920x1080 (相同尺寸)
            'dimensions': (1920, 1080),
            'file_size': 1200000,    # 1.2MB (与img2相同大小)
            'filename': 'img4.jpg'   # 文件名较大
        }
    }
    
    mock_images = list(mock_image_info.keys())
    
    logger.info("模拟图片信息:")
    for img, info in mock_image_info.items():
        logger.info(f"  {img}: {info['dimensions'][0]}x{info['dimensions'][1]}, {info['file_size']:,} bytes")
    
    # 测试1: 尺寸档位过滤
    logger.info("\n测试1: 尺寸档位过滤")
    remaining_images = mock_images.copy()
    remaining_images, deleted_by_dimensions = filter_instance._filter_by_dimensions(remaining_images, mock_image_info)
    
    logger.info("尺寸过滤结果:")
    for img, reason in deleted_by_dimensions:
        logger.info(f"  删除: {img} - {reason}")
    logger.info(f"  剩余: {remaining_images}")
    
    # 测试2: 在剩余图片上应用文件大小档位过滤
    if len(remaining_images) > 1:
        logger.info("\n测试2: 文件大小档位过滤")
        remaining_images, deleted_by_size = filter_instance._filter_by_file_size(remaining_images, mock_image_info)
        
        logger.info("大小过滤结果:")
        for img, reason in deleted_by_size:
            logger.info(f"  删除: {img} - {reason}")
        logger.info(f"  剩余: {remaining_images}")
    
    # 测试3: 在剩余图片上应用文件名档位过滤
    if len(remaining_images) > 1:
        logger.info("\n测试3: 文件名档位过滤")
        remaining_images, deleted_by_filename = filter_instance._filter_by_filename(remaining_images, mock_image_info, reverse_filename=False)
        
        logger.info("文件名过滤结果:")
        for img, reason in deleted_by_filename:
            logger.info(f"  删除: {img} - {reason}")
        logger.info(f"  最终保留: {remaining_images[0] if remaining_images else '无'}")
    
    # 测试4: 完整的逐档位过滤
    logger.info("\n测试4: 完整的逐档位过滤")
    
    # 重新创建模拟图片组用于完整测试
    test_group = list(mock_image_info.keys())
    
    # 模拟apply_comprehensive_filter的逻辑
    config = {
        'enable_progressive': True,
        'use_dimensions': True,
        'use_file_size': True,
        'use_filename': True,
        'reverse_filename': False,
        'filter_order': ['dimensions', 'file_size', 'filename']
    }
    
    logger.info("应用完整逐档位过滤:")
    
    # 逐档位过滤逻辑
    remaining_images = test_group.copy()
    all_to_delete = []
    
    for filter_type in config['filter_order']:
        if len(remaining_images) <= 1:
            break
            
        logger.info(f"\n应用 {filter_type} 档位过滤:")
        logger.info(f"  输入: {remaining_images}")
        
        if filter_type == 'dimensions' and config.get('use_dimensions', True):
            remaining_images, to_delete = filter_instance._filter_by_dimensions(remaining_images, mock_image_info)
            all_to_delete.extend(to_delete)
            
        elif filter_type == 'file_size' and config.get('use_file_size', True):
            remaining_images, to_delete = filter_instance._filter_by_file_size(remaining_images, mock_image_info)
            all_to_delete.extend(to_delete)
            
        elif filter_type == 'filename' and config.get('use_filename', True):
            remaining_images, to_delete = filter_instance._filter_by_filename(
                remaining_images, mock_image_info, config.get('reverse_filename', False)
            )
            all_to_delete.extend(to_delete)
        
        if to_delete:
            for img, reason in to_delete:
                logger.info(f"  删除: {img} - {reason}")
        else:
            logger.info(f"  无删除")
        logger.info(f"  剩余: {remaining_images}")
    
    logger.info(f"\n最终结果:")
    logger.info(f"总删除: {len(all_to_delete)} 张")
    for img, reason in all_to_delete:
        logger.info(f"  - {img}: {reason}")
    logger.info(f"最终保留: {remaining_images[0] if remaining_images else '无'}")

if __name__ == "__main__":
    # 配置日志
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    try:
        quick_test()
        logger.info("\n快速测试完成！")
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
