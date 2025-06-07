import os
import ctypes
import numpy as np
from typing import List, Tuple, Dict, Set
from concurrent.futures import ProcessPoolExecutor, as_completed
from loguru import logger

# 设置基础环境变量
os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# CUDA 初始化函数
def cudain():
    """初始化CUDA环境"""
    cuda_path = os.environ.get('CUDA_PATH')
    if cuda_path:
        cuda_bin = os.path.join(cuda_path, 'bin')
        if os.path.exists(cuda_bin):
        # 添加到 PATH 环境变量
            os.environ['PATH'] = cuda_bin + os.pathsep + os.environ.get('PATH', '')
        # 使用 SetDllDirectory 明确告诉 Windows 在哪里查找 DLL
            try:
                ctypes.windll.kernel32.SetDllDirectoryW(cuda_bin)
                logger.info(f"已添加 CUDA bin 目录到 DLL 搜索路径: {cuda_bin}")
            except Exception as e:
                logger.error(f"设置 DLL 目录失败: {e}")

# 延迟导入，以确保环境变量生效
def _lazy_import_lpips_difference():
    from imgutils.metrics import lpips_difference
    return lpips_difference

def calculate_lpips_worker(img_path1: str, img_path2: str) -> Tuple[Tuple[str, str], float]:
    """
    计算两张图片的LPIPS距离的工作函数
    
    Args:
        img_path1: 第一张图片路径
        img_path2: 第二张图片路径
        
    Returns:
        Tuple[Tuple[str, str], float]: ((img_path1, img_path2), lpips_distance)
    """
    try:
        # 使用imgutils.metrics中的lpips_difference函数
        lpips_difference = _lazy_import_lpips_difference()
        distance = lpips_difference(img_path1, img_path2)
        return (img_path1, img_path2), distance
    except Exception as e:
        logger.error(f"[#hash_calc]计算LPIPS距离失败 {img_path1} vs {img_path2}: {e}")
        return (img_path1, img_path2), float('inf')

def find_similar_images_by_lpips_legacy(images: List[str], lpips_threshold: float = 0.02, 
                                       use_gpu: bool = False, lpips_max_workers: int = 16) -> List[List[str]]:
    """
    使用传统LPIPS距离计算方法查找相似的图片组
    
    Args:
        images: 图片文件列表
        lpips_threshold: LPIPS距离阈值
        use_gpu: 是否使用GPU
        lpips_max_workers: 最大工作进程数
            
    Returns:
        List[List[str]]: 相似图片组列表
    """
    similar_groups = []
    processed = set()
    
    # 设置环境变量
    old_env = os.environ.get('LPIPS_USE_GPU', '0')
    if use_gpu:
        os.environ['LPIPS_USE_GPU'] = '1'
        if use_gpu and old_env != '1':
            logger.info("[#hash_calc]切换到GPU模式计算LPIPS")
            cudain()
    else:
        os.environ['LPIPS_USE_GPU'] = '0'
        if not use_gpu and old_env != '0':
            logger.info("[#hash_calc]切换到CPU模式计算LPIPS")
    
    # 计算图片间的差异矩阵
    n = len(images)
    diff_matrix = np.zeros((n, n))
    
    # 创建图片对列表
    image_pairs = []
    for i in range(n):
        for j in range(i+1, n):
            image_pairs.append((i, j, images[i], images[j]))
    
    # 初始化工作进程数
    current_workers = lpips_max_workers
    logger.info(f"[#hash_calc]开始计算 {n} 张图像的LPIPS距离，使用 {current_workers} 个进程")
    
    # 跟踪失败的对和重试次数
    failed_pairs = []
    retry_count = 0
    max_retries = 3
    
    try:
        while retry_count <= max_retries and (image_pairs or failed_pairs):
            # 如果是重试，减少进程数并使用失败的对
            if retry_count > 0:
                current_workers = max(1, current_workers // 2)
                logger.warning(f"[#hash_calc]第 {retry_count} 次重试，降低进程数至 {current_workers}")
                image_pairs = failed_pairs
                failed_pairs = []
            
            # 使用进程池计算LPIPS距离
            with ProcessPoolExecutor(max_workers=current_workers) as executor:
                # 创建任务列表
                future_to_pair = {}
                for i, j, img1, img2 in image_pairs:
                    future = executor.submit(
                        calculate_lpips_worker,
                        img1,
                        img2
                    )
                    future_to_pair[future] = (i, j, img1, img2)
                
                # 收集结果
                completed = 0
                total_pairs = len(future_to_pair)
                
                # 如果没有任务，直接跳过
                if total_pairs == 0:
                    break
                    
                for future in as_completed(future_to_pair):
                    i, j, img1, img2 = future_to_pair[future]
                    completed += 1
                    
                    try:
                        (path1, path2), diff = future.result()
                        diff_matrix[i, j] = diff
                        diff_matrix[j, i] = diff
                        
                        # 每处理10%的图像对输出一次进度
                        if completed % max(1, total_pairs // 10) == 0 or completed == total_pairs:
                            progress = (completed / total_pairs) * 100
                            logger.info(f"[#hash_calc]LPIPS计算进度: {completed}/{total_pairs} ({progress:.1f}%)")
                        
                        logger.info(f"[#hash_calc]LPIPS距离: {os.path.basename(img1)} vs {os.path.basename(img2)} = {diff:.4f}")
                    except Exception as e:
                        logger.error(f"[#hash_calc]计算LPIPS距离失败 {img1} vs {img2}: {e}")
                        diff_matrix[i, j] = float('inf')
                        diff_matrix[j, i] = float('inf')
                        # 将失败的对添加到重试列表
                        failed_pairs.append((i, j, img1, img2))
            
            # 如果没有失败的对，或者已经是CPU模式（只有1个进程），就退出循环
            if not failed_pairs or current_workers <= 1:
                break
                
            retry_count += 1
            
            # 如果是最后一次重试，尝试使用CPU模式
            if retry_count == max_retries and failed_pairs:
                # 强制使用CPU模式进行最后一次尝试
                logger.warning("[#hash_calc]最后一次尝试：切换到CPU模式计算LPIPS")
                os.environ['LPIPS_USE_GPU'] = '0'  # 临时切换到CPU模式
                current_workers = 1  # 使用单进程避免内存问题
        
        # 构建相似性图
        similarity_graph = {img: [] for img in images}
        for i in range(n):
            for j in range(i+1, n):
                if diff_matrix[i, j] <= lpips_threshold:
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
        processed.clear()  # 重置处理标记
        for img in images:
            if img not in processed:
                current_group = []
                dfs(img, current_group)
                if len(current_group) > 1:
                    similar_groups.append(current_group)
                    logger.info(f"找到相似图像组: {len(current_group)}张")
    
    finally:
        # 恢复原始环境变量
        os.environ['LPIPS_USE_GPU'] = old_env
    
    return similar_groups
