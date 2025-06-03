"""
ImgFilter命令行功能实现
"""
import os
import argparse
from typing import List
from imgfilter.core.filter import ImageFilter

def filter_images(args):
    """执行图片过滤"""
    filter = ImageFilter(
        hash_file=args.hash_file,
        hamming_threshold=args.hamming_threshold
    )
    
    # 收集图片文件列表
    image_files = []
    if os.path.isdir(args.input):
        for root, _, files in os.walk(args.input):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
                    image_files.append(os.path.join(root, file))
    else:
        image_files = [args.input]
    
    # 处理图片
    to_delete, reasons = filter.process_images(
        image_files,
        enable_small_filter=args.small,
        enable_grayscale_filter=args.grayscale,
        enable_duplicate_filter=args.duplicate,
        enable_text_filter=args.text,
        min_size=args.min_size,
        duplicate_filter_mode=args.dup_mode,
        text_threshold=args.text_threshold
    )
    
    # 输出结果
    print(f"检测了 {len(image_files)} 张图片，发现 {len(to_delete)} 张需要删除")
    for img in to_delete:
        print(f"- {img}: {reasons[img]['reason']}")
    
    # 如果指定了删除模式，则删除文件
    if args.delete:
        for img in to_delete:
            os.remove(img)
            print(f"已删除: {img}")

def setup_parser(parser):
    """设置命令行参数"""
    parser.add_argument('input', help='输入图片文件或目录')
    parser.add_argument('--hash-file', help='哈希文件路径')
    parser.add_argument('--hamming-threshold', type=int, default=12, help='汉明距离阈值')
    parser.add_argument('--min-size', type=int, default=630, help='最小图片尺寸')
    parser.add_argument('--text-threshold', type=float, default=0.5, help='文本图片阈值')
    parser.add_argument('--dup-mode', choices=['quality', 'watermark', 'hash'], default='quality', help='重复图片处理模式')
    
    # 开启哪些过滤器
    parser.add_argument('--small', action='store_true', help='开启小图过滤')
    parser.add_argument('--grayscale', action='store_true', help='开启灰度图过滤')
    parser.add_argument('--duplicate', action='store_true', help='开启重复图片过滤')
    parser.add_argument('--text', action='store_true', help='开启纯文本图片过滤')
    parser.add_argument('--all', action='store_true', help='开启所有过滤器')
    
    parser.add_argument('--delete', action='store_true', help='删除匹配的文件')
    
    parser.set_defaults(func=filter_images)