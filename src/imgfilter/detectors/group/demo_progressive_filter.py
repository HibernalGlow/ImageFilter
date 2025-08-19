#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
逐档位过滤策略演示脚本

这个脚本演示了新的逐档位过滤功能，包括：
1. 尺寸档位过滤
2. 文件大小档位过滤  
3. 文件名档位过滤
4. 可配置的档位开关和顺序
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image
import random
import time

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from imgfilter.detectors.group.group_filter import GroupFilter, process_group_with_filters
from loguru import logger

def create_test_images(test_dir: Path, num_images: int = 8) -> List[str]:
    """
    创建测试图片，包含不同尺寸、大小和文件名的图片
    
    Args:
        test_dir: 测试目录
        num_images: 创建图片数量
        
    Returns:
        List[str]: 创建的图片路径列表
    """
    test_dir.mkdir(exist_ok=True)
    image_paths = []
    
    # 定义不同的图片配置
    image_configs = [
        # 格式: (width, height, quality, filename_prefix)
        (1920, 1080, 95, "01_high_res"),     # 高分辨率
        (1920, 1080, 85, "02_high_res"),     # 同分辨率，不同质量
        (1920, 1080, 75, "03_high_res"),     # 同分辨率，更低质量
        (1280, 720, 95, "04_medium_res"),    # 中分辨率
        (1280, 720, 85, "05_medium_res"),    # 同分辨率，不同质量
        (854, 480, 95, "06_low_res"),        # 低分辨率
        (854, 480, 85, "07_low_res"),        # 同分辨率，不同质量
        (640, 360, 95, "08_tiny_res"),       # 很低分辨率
    ]
    
    for i, (width, height, quality, prefix) in enumerate(image_configs[:num_images]):
        # 创建图片
        img = Image.new('RGB', (width, height), color=(
            random.randint(100, 255),
            random.randint(100, 255), 
            random.randint(100, 255)
        ))
        
        # 添加一些内容到图片上
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        
        # 绘制一些形状和文字
        draw.rectangle([50, 50, width-50, height-50], outline=(255, 255, 255), width=5)
        draw.text((100, 100), f"Test Image {i+1}", fill=(255, 255, 255))
        draw.text((100, 150), f"Size: {width}x{height}", fill=(255, 255, 255))
        draw.text((100, 200), f"Quality: {quality}", fill=(255, 255, 255))
        
        # 保存图片
        filename = f"{prefix}_{width}x{height}_q{quality}.jpg"
        image_path = test_dir / filename
        img.save(image_path, 'JPEG', quality=quality)
        image_paths.append(str(image_path))
        
        # 随机调整文件修改时间
        timestamp = time.time() - random.randint(0, 86400 * 7)  # 过去一周内的随机时间
        os.utime(image_path, (timestamp, timestamp))
        
        logger.info(f"创建测试图片: {filename} ({width}x{height}, {os.path.getsize(image_path)} bytes)")
    
    return image_paths

def demonstrate_progressive_filter():
    """演示逐档位过滤功能"""
    logger.info("=" * 60)
    logger.info("逐档位过滤策略演示")
    logger.info("=" * 60)
    
    # 创建临时测试目录
    temp_dir = Path(tempfile.mkdtemp(prefix="progressive_filter_demo_"))
    logger.info(f"测试目录: {temp_dir}")
    
    try:
        # 创建测试图片
        logger.info("\n1. 创建测试图片...")
        image_paths = create_test_images(temp_dir)
        
        # 显示图片信息
        logger.info("\n2. 测试图片信息:")
        filter_instance = GroupFilter()
        for img_path in image_paths:
            file_info = filter_instance._get_file_info(img_path)
            dimensions = filter_instance._get_image_dimensions(img_path)
            pixel_count = filter_instance._get_image_pixel_count(img_path)
            
            logger.info(f"  {os.path.basename(img_path)}:")
            logger.info(f"    尺寸: {dimensions[0]}x{dimensions[1]} ({pixel_count:,} 像素)")
            logger.info(f"    大小: {file_info['size']:,} 字节")
            logger.info(f"    修改时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_info['mtime']))}")
        
        # 测试不同的过滤配置
        test_configs = [
            {
                'name': '默认逐档位过滤（尺寸→大小→文件名）',
                'config': {
                    'enable_progressive': True,
                    'use_dimensions': True,
                    'use_file_size': True,
                    'use_filename': True,
                    'reverse_filename': False,
                    'filter_order': ['dimensions', 'file_size', 'filename']
                }
            },
            {
                'name': '仅尺寸档位过滤',
                'config': {
                    'enable_progressive': True,
                    'use_dimensions': True,
                    'use_file_size': False,
                    'use_filename': False,
                    'filter_order': ['dimensions']
                }
            },
            {
                'name': '尺寸+大小档位过滤',
                'config': {
                    'enable_progressive': True,
                    'use_dimensions': True,
                    'use_file_size': True,
                    'use_filename': False,
                    'filter_order': ['dimensions', 'file_size']
                }
            },
            {
                'name': '反向文件名排序（保留名称大的）',
                'config': {
                    'enable_progressive': True,
                    'use_dimensions': True,
                    'use_file_size': True,
                    'use_filename': True,
                    'reverse_filename': True,
                    'filter_order': ['dimensions', 'file_size', 'filename']
                }
            },
            {
                'name': '自定义过滤顺序（大小→尺寸→文件名）',
                'config': {
                    'enable_progressive': True,
                    'use_dimensions': True,
                    'use_file_size': True,
                    'use_filename': True,
                    'reverse_filename': False,
                    'filter_order': ['file_size', 'dimensions', 'filename']
                }
            },
            {
                'name': '传统综合过滤（非逐档位）',
                'config': {
                    'enable_progressive': False,
                    'use_dimensions': True,
                    'use_file_size': True,
                    'use_filename': True,
                    'reverse_filename': False
                }
            }
        ]
        
        # 执行测试
        for i, test_case in enumerate(test_configs, 1):
            logger.info(f"\n{i + 2}. 测试配置: {test_case['name']}")
            logger.info("-" * 50)
            
            try:
                to_delete, removal_reasons = process_group_with_filters(
                    image_paths, 
                    test_case['config']
                )
                
                if to_delete:
                    logger.info(f"标记删除 {len(to_delete)} 张图片:")
                    for img_path in to_delete:
                        reason_info = removal_reasons[img_path]
                        logger.info(f"  - {os.path.basename(img_path)}: {reason_info['details']}")
                    
                    remaining = [img for img in image_paths if img not in to_delete]
                    if remaining:
                        logger.info(f"保留图片: {os.path.basename(remaining[0])}")
                else:
                    logger.info("没有图片被标记删除")
                    
            except Exception as e:
                logger.error(f"测试失败: {e}")
        
        # 演示单独的档位过滤函数
        logger.info(f"\n{len(test_configs) + 3}. 演示单独档位过滤函数")
        logger.info("-" * 50)
        
        # 收集图片信息
        image_info = {}
        for img_path in image_paths:
            info = {}
            info['pixel_count'] = filter_instance._get_image_pixel_count(img_path)
            info['dimensions'] = filter_instance._get_image_dimensions(img_path)
            file_info = filter_instance._get_file_info(img_path)
            info['file_size'] = file_info['size']
            info['filename'] = os.path.basename(img_path).lower()
            image_info[img_path] = info
        
        # 测试尺寸档位过滤
        logger.info("\n尺寸档位过滤结果:")
        remaining_images = image_paths.copy()
        remaining_images, deleted_by_dimensions = filter_instance._filter_by_dimensions(remaining_images, image_info)
        for img, reason in deleted_by_dimensions:
            logger.info(f"  删除: {os.path.basename(img)} - {reason}")
        logger.info(f"  剩余 {len(remaining_images)} 张图片")
        
        # 测试文件大小档位过滤（在尺寸过滤的基础上）
        if len(remaining_images) > 1:
            logger.info("\n文件大小档位过滤结果:")
            remaining_images, deleted_by_size = filter_instance._filter_by_file_size(remaining_images, image_info)
            for img, reason in deleted_by_size:
                logger.info(f"  删除: {os.path.basename(img)} - {reason}")
            logger.info(f"  剩余 {len(remaining_images)} 张图片")
        
        # 测试文件名档位过滤（在前面过滤的基础上）
        if len(remaining_images) > 1:
            logger.info("\n文件名档位过滤结果:")
            remaining_images, deleted_by_filename = filter_instance._filter_by_filename(remaining_images, image_info, reverse_filename=False)
            for img, reason in deleted_by_filename:
                logger.info(f"  删除: {os.path.basename(img)} - {reason}")
            logger.info(f"  最终保留: {os.path.basename(remaining_images[0]) if remaining_images else '无'}")
        
    finally:
        # 清理临时目录
        logger.info(f"\n清理测试目录: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)

def demonstrate_configuration_options():
    """演示配置选项的使用"""
    logger.info("\n" + "=" * 60)
    logger.info("配置选项使用演示")
    logger.info("=" * 60)
    
    # 模拟图片组（实际使用中这些会是真实的图片路径）
    mock_group = [
        "test_1920x1080_large.jpg",
        "test_1920x1080_medium.jpg", 
        "test_1280x720_small.jpg",
        "test_640x360_tiny.jpg"
    ]
    
    logger.info("模拟图片组:")
    for img in mock_group:
        logger.info(f"  - {img}")
    
    # 演示不同的字符串配置
    logger.info("\n1. 使用字符串配置:")
    string_configs = [
        "comprehensive",  # 使用综合过滤
        "size",          # 仅使用大小过滤
        "time",          # 仅使用时间过滤
    ]
    
    for config in string_configs:
        logger.info(f"  配置 '{config}': 将调用对应的过滤方法")
    
    # 演示字典配置
    logger.info("\n2. 使用字典配置示例:")
    dict_configs = [
        {
            'name': '仅启用尺寸过滤',
            'config': {
                'use_dimensions': True,
                'use_file_size': False,
                'use_filename': False
            }
        },
        {
            'name': '启用尺寸和大小过滤',
            'config': {
                'use_dimensions': True,
                'use_file_size': True,
                'use_filename': False
            }
        },
        {
            'name': '自定义过滤顺序',
            'config': {
                'use_dimensions': True,
                'use_file_size': True,
                'use_filename': True,
                'filter_order': ['file_size', 'dimensions', 'filename']
            }
        },
        {
            'name': '禁用逐档位过滤（使用传统模式）',
            'config': {
                'enable_progressive': False,
                'use_dimensions': True,
                'use_file_size': True,
                'use_filename': True
            }
        }
    ]
    
    for config_info in dict_configs:
        logger.info(f"  {config_info['name']}:")
        for key, value in config_info['config'].items():
            logger.info(f"    {key}: {value}")
        logger.info("")

if __name__ == "__main__":
    # 配置日志
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # 运行演示
    try:
        demonstrate_progressive_filter()
        demonstrate_configuration_options()
        
        logger.info("\n" + "=" * 60)
        logger.info("演示完成！")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\n演示被用户中断")
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
