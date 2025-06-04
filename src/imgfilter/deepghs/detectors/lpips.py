import os
import logging
from typing import List, Dict, Tuple, Set, Union, Optional
import json
from PIL import Image
import pillow_avif
import pillow_jxl
import numpy as np
import torch
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

from loguru import logger

# Import LPIPS from imgutils.metrics
from imgutils.metrics import lpips_difference, lpips_clustering

# Import LPIPS model
try:
    import lpips as lpips_module
except ImportError:
    logger.error("LPIPS module not found. Please install it with: pip install lpips")
    lpips_module = None

def _calculate_lpips_worker(img_path1: str, img_path2: str) -> Tuple[Tuple[str, str], float]:
    """
    Worker function for calculating LPIPS distance between two images
    
    Args:
        img_path1: Path to first image
        img_path2: Path to second image
        
    Returns:
        Tuple[Tuple[str, str], float]: ((img_path1, img_path2), lpips_distance)
    """
    try:
        distance = _calculate_lpips_static(img_path1, img_path2)
        return (img_path1, img_path2), distance
    except Exception as e:
        logger.error(f"[#hash_calc]计算LPIPS距离失败 {img_path1} vs {img_path2}: {e}")
        return (img_path1, img_path2), None

def _calculate_lpips_static(img_path1: str, img_path2: str) -> float:
    """
    Static function to calculate LPIPS distance between two images
    
    Args:
        img_path1: Path to first image
        img_path2: Path to second image
        
    Returns:
        float: LPIPS distance value
    """
    if lpips_module is None:
        raise ImportError("LPIPS module not installed")
        
    try:
        # Load images
        img1 = _load_and_preprocess_image(img_path1)
        img2 = _load_and_preprocess_image(img_path2)
        
        if img1 is None or img2 is None:
            logger.error(f"[#hash_calc]无法加载图像: {img_path1} 或 {img_path2}")
            return None
        
        # Initialize LPIPS model (with caching to avoid reloading)
        loss_fn = _get_lpips_model()
        
        # Calculate distance
        with torch.no_grad():
            distance = loss_fn.forward(img1, img2)
            
        # Convert from tensor to float
        return float(distance.item())
        
    except Exception as e:
        logger.error(f"[#hash_calc]计算LPIPS距离异常: {e}")
        return None

# Cache for LPIPS model
_lpips_model = None

def _get_lpips_model():
    """Get cached LPIPS model or initialize a new one"""
    global _lpips_model
    if _lpips_model is None:
        # Check if CUDA is available
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        _lpips_model = lpips_module.LPIPS(net='alex', verbose=False).to(device)
    return _lpips_model

def _load_and_preprocess_image(img_path: str) -> Optional[torch.Tensor]:
    """
    Load and preprocess image for LPIPS calculation
    
    Args:
        img_path: Path to image
        
    Returns:
        torch.Tensor: Preprocessed image tensor
    """
    try:
        # Check if file exists
        if not os.path.exists(img_path):
            logger.error(f"[#hash_calc]图像文件不存在: {img_path}")
            return None
            
        # Load image
        img = Image.open(img_path).convert('RGB')
        
        # Resize if too large (optional, to save memory)
        max_size = 512  # Can be adjusted based on memory constraints
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        # Convert to tensor and normalize to [-1, 1]
        img_np = np.array(img).astype(np.float32) / 127.5 - 1
        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0)
        
        # Move to appropriate device
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        img_tensor = img_tensor.to(device)
        
        return img_tensor
        
    except Exception as e:
        logger.error(f"[#hash_calc]加载图像失败 {img_path}: {e}")
        return None

class LPIPSImageFilter:
    """LPIPS图像过滤器，基于感知相似度检测和过滤"""
    
    def __init__(self, lpips_threshold: float = 0.02, max_workers: int = None):
        """
        初始化LPIPS图像过滤器
        
        Args:
            lpips_threshold: LPIPS距离阈值，小于此值的图像被视为相似
            max_workers: 最大工作进程数，默认为CPU核心数
        """
        self.lpips_threshold = lpips_threshold
        self.max_workers = max_workers or multiprocessing.cpu_count()
            
    def filter_similar_images(self, image_files: List[str], 
                             mode: str = 'quality',
                             keep_best: bool = True) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        过滤相似图像，返回要删除的图像集合和原因
        
        Args:
            image_files: 图像文件列表
            mode: 过滤模式 ('quality')
            keep_best: 是否保留最佳图像
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        if not image_files or len(image_files) < 2:
            return set(), {}
            
        # 查找相似图像组
        similar_groups = self._find_similar_images(image_files)
        
        # 对每个相似组应用过滤策略
        to_delete = set()
        removal_reasons = {}
        
        for group in similar_groups:
            if len(group) > 1:
                # 只使用质量模式
                group_results, group_reasons = self._process_quality_images(group)
                to_delete.update(group_results)
                removal_reasons.update(group_reasons)
                
        return to_delete, removal_reasons
        
    def _find_similar_images(self, images: List[str]) -> List[List[str]]:
        """
        查找相似图像组，使用imgutils.metrics中的lpips_difference
        
        Args:
            images: 图像文件列表
            
        Returns:
            List[List[str]]: 相似图像组列表
        """
        similar_groups = []
        processed = set()
        
        # 计算图片间的差异矩阵
        n = len(images)
        diff_matrix = np.zeros((n, n))
        logger.info(f"[#hash_calc]开始计算 {n} 张图像的LPIPS距离")
        
        # 使用进程池计算LPIPS距离
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # 创建任务列表
            future_to_pair = {}
            for i in range(n):
                for j in range(i+1, n):
                    future = executor.submit(
                        lpips_difference,
                        images[i],
                        images[j]
                    )
                    future_to_pair[future] = (i, j)
            
            # 收集结果
            completed = 0
            total_pairs = len(future_to_pair)
            for future in as_completed(future_to_pair):
                i, j = future_to_pair[future]
                completed += 1
                
                try:
                    diff = future.result()
                    diff_matrix[i, j] = diff
                    diff_matrix[j, i] = diff
                    
                    # 每处理10%的图像对输出一次进度
                    if completed % max(1, total_pairs // 10) == 0 or completed == total_pairs:
                        progress = (completed / total_pairs) * 100
                        logger.info(f"[#hash_calc]LPIPS计算进度: {completed}/{total_pairs} ({progress:.1f}%)")
                    
                    logger.info(f"[#hash_calc]LPIPS距离: {os.path.basename(images[i])} vs {os.path.basename(images[j])} = {diff:.4f}")
                except Exception as e:
                    logger.error(f"[#hash_calc]计算LPIPS距离失败 {images[i]} vs {images[j]}: {e}")
                    diff_matrix[i, j] = float('inf')
                    diff_matrix[j, i] = float('inf')
        
        # 构建相似性图
        similarity_graph = {img: [] for img in images}
        for i in range(n):
            for j in range(i+1, n):
                if diff_matrix[i, j] <= self.lpips_threshold:
                    similarity_graph[images[i]].append(images[j])
                    similarity_graph[images[j]].append(images[i])
                    logger.info(f"找到相似图像: {os.path.basename(images[i])} 与 {os.path.basename(images[j])} (距离: {diff_matrix[i, j]:.4f})")
        
        # 使用DFS查找连通分量（相似组）
        def dfs(node, component):
            processed.add(node)
            component.append(node)
            for neighbor in similarity_graph[node]:
                if neighbor not in processed:
                    dfs(neighbor, component)
        
        # 查找所有连通分量
        for img in images:
            if img not in processed:
                current_group = []
                dfs(img, current_group)
                if len(current_group) > 1:
                    similar_groups.append(current_group)
                    logger.info(f"找到相似图像组: {len(current_group)}张")
        
        return similar_groups
        
    def _process_quality_images(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理质量过滤，保留文件大小最大的图像"""
        to_delete = set()
        removal_reasons = {}
        
        # 获取文件大小
        file_sizes = {img: os.path.getsize(img) for img in group}
        # 保留最大的文件
        keep_image = max(group, key=lambda x: file_sizes[x])
        
        # 删除其他较小的文件
        for img in group:
            if img != keep_image:
                size_diff = file_sizes[keep_image] - file_sizes[img]
                to_delete.add(img)
                removal_reasons[img] = {
                    'reason': 'lpips_quality',
                    'kept_image': keep_image,
                    'size_diff': f"{size_diff} bytes"
                }
                logger.info(f"标记删除较小图像: {os.path.basename(img)} (保留: {os.path.basename(keep_image)}, 大小差: {size_diff} bytes)")
                
        return to_delete, removal_reasons
        
    def calculate_lpips_matrix(self, image_files: List[str]) -> Dict[Tuple[int, int], float]:
        """
        计算图像之间的LPIPS距离矩阵，使用imgutils.metrics中的lpips_difference
        
        Args:
            image_files: 图像文件列表
            
        Returns:
            Dict[Tuple[int, int], float]: {(i, j): lpips_distance}
        """
        n = len(image_files)
        distances = {}
        
        for i in range(n):
            for j in range(i+1, n):
                try:
                    diff = lpips_difference(image_files[i], image_files[j])
                    distances[(i, j)] = diff
                    logger.info(f"LPIPS距离: {os.path.basename(image_files[i])} vs {os.path.basename(image_files[j])} = {diff:.4f}")
                except Exception as e:
                    logger.error(f"计算LPIPS距离失败 {image_files[i]} vs {image_files[j]}: {e}")
                    
        return distances
    
    def cluster_images(self, image_files: List[str]) -> List[int]:
        """
        使用imgutils.metrics中的lpips_clustering对图像进行聚类
        
        Args:
            image_files: 图像文件列表
            
        Returns:
            List[int]: 聚类结果，每个图像对应的聚类ID
        """
        try:
            clusters = lpips_clustering(image_files)
            return clusters
        except Exception as e:
            logger.error(f"LPIPS聚类失败: {e}")
            return [-1] * len(image_files)  # 返回所有图像为噪声点
