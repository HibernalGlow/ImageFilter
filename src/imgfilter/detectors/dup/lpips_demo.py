import os
import sys
import time
import argparse
from pathlib import Path
from typing import List
from loguru import logger

# 添加项目根目录到路径


# 导入优化后的LPIPS模块
from imgfilter.detectors.dup.lpips import find_similar_images_by_lpips_legacy, extract_features

# 支持的图片扩展名
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.avif', '.jxl'}

def get_image_files(folder: str) -> List[str]:
    """递归获取文件夹及其子文件夹下所有图片文件路径"""
    return [str(p) for p in Path(folder).rglob('*') if p.suffix.lower() in IMG_EXTS and p.is_file()]

def test_feature_extraction(image_files: List[str], use_gpu: bool = False):
    """测试特征提取功能"""
    logger.info(f"测试特征提取功能，共 {len(image_files)} 张图片")
    
    # 记录开始时间
    start_time = time.time()
    
    # 提取特征
    for i, img_path in enumerate(image_files):
        logger.info(f"提取特征 [{i+1}/{len(image_files)}]: {os.path.basename(img_path)}")
        feature = extract_features(img_path, use_gpu)
        if feature is not None:
            logger.info(f"特征维度: {feature.shape}")
        else:
            logger.error(f"特征提取失败: {img_path}")
    
    # 计算总耗时
    elapsed_time = time.time() - start_time
    logger.info(f"特征提取完成，总耗时: {elapsed_time:.2f}秒，平均每张: {elapsed_time/len(image_files):.2f}秒")

def test_feature_cache(image_files: List[str], use_gpu: bool = False):
    """测试特征缓存功能"""
    logger.info(f"测试特征缓存功能，共 {len(image_files)} 张图片")
    
    # 第一次提取特征（写入缓存）
    logger.info("第一次提取特征（写入缓存）...")
    start_time = time.time()
    for img_path in image_files[:5]:  # 只测试前5张图片
        extract_features(img_path, use_gpu)
    first_time = time.time() - start_time
    
    # 第二次提取特征（从缓存读取）
    logger.info("第二次提取特征（从缓存读取）...")
    start_time = time.time()
    for img_path in image_files[:5]:  # 测试相同的图片
        extract_features(img_path, use_gpu)
    second_time = time.time() - start_time
    
    logger.info(f"第一次提取耗时: {first_time:.2f}秒")
    logger.info(f"第二次提取耗时: {second_time:.2f}秒")
    logger.info(f"缓存加速比: {first_time/second_time:.2f}倍")

def test_similar_images(image_files: List[str], threshold: float = 0.1, use_gpu: bool = False):
    """测试相似图片查找功能"""
    logger.info(f"测试相似图片查找功能，共 {len(image_files)} 张图片，阈值: {threshold}")
    
    # 记录开始时间
    start_time = time.time()
    
    # 查找相似图片
    similar_groups = find_similar_images_by_lpips_legacy(
        image_files, 
        lpips_threshold=threshold,
        use_gpu=use_gpu,
        lpips_max_workers=4
    )
    
    # 计算总耗时
    elapsed_time = time.time() - start_time
    
    # 输出结果
    logger.info(f"查找完成，总耗时: {elapsed_time:.2f}秒")
    logger.info(f"找到 {len(similar_groups)} 组相似图片")
    
    # 打印每组相似图片
    for i, group in enumerate(similar_groups):
        logger.info(f"相似组 #{i+1}，共 {len(group)} 张图片:")
        for img_path in group:
            logger.info(f"  - {os.path.basename(img_path)}")

def main():
    parser = argparse.ArgumentParser(description="LPIPS特征提取和相似图片查找演示")
    parser.add_argument("folder", help="图片文件夹路径")
    parser.add_argument("--mode", choices=["extract", "cache", "similar", "all"], default="all", 
                        help="测试模式: extract-特征提取, cache-缓存测试, similar-相似图片查找, all-全部测试")
    parser.add_argument("--threshold", type=float, default=0.1, help="相似度阈值，越小要求越相似")
    parser.add_argument("--gpu", action="store_true", help="是否使用GPU")
    parser.add_argument("--max-images", type=int, default=20, help="最大处理图片数量")
    
    args = parser.parse_args()
    
    # 获取图片文件
    image_files = get_image_files(args.folder)
    
    # 限制图片数量
    if len(image_files) > args.max_images:
        logger.info(f"图片数量超过限制，从 {len(image_files)} 张随机选择 {args.max_images} 张")
        import random
        random.shuffle(image_files)
        image_files = image_files[:args.max_images]
    
    logger.info(f"找到 {len(image_files)} 张图片")
    
    # 根据模式执行测试
    if args.mode in ["extract", "all"]:
        test_feature_extraction(image_files, args.gpu)
    
    if args.mode in ["cache", "all"]:
        test_feature_cache(image_files, args.gpu)
    
    if args.mode in ["similar", "all"]:
        test_similar_images(image_files, args.threshold, args.gpu)

if __name__ == "__main__":
    main() 