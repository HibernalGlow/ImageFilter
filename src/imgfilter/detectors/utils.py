import os
import logging
from typing import List, Dict, Tuple, Set, Union, Optional
import json
from PIL import Image
import pillow_avif
import pillow_jxl 
from io import BytesIO
import mmap
from hashu.core.calculate_hash_custom import ImageHashCalculator, PathURIGenerator
from hashu.utils.hash_accelerator import HashAccelerator
from loguru import logger


def calculate_hash_worker(img_path: str, archive_path: str = None, temp_dir: str = None, 
                         image_archive_map: Dict[str, Union[str, Dict]] = None) -> Tuple[str, Optional[Tuple[str, str]]]:
    """
    多进程工作函数：为单张图片计算哈希值
    
    Args:
        img_path: 图片文件路径
        archive_path: 原始压缩包路径
        temp_dir: 临时解压目录
        image_archive_map: 图片到压缩包内信息的映射
        
    Returns:
        Tuple[str, Optional[Tuple[str, str]]]: (图片路径, (URI, 哈希值)) 或 (图片路径, None)
    """
    try:
        # 从映射中获取压缩包信息，如果不存在则尝试从路径推导
        zip_path = None
        internal_path = None
        
        if image_archive_map and img_path in image_archive_map:
            # 检查映射中的数据类型
            map_data = image_archive_map[img_path]
            if isinstance(map_data, dict):
                # 新格式：直接从字典中获取路径信息
                zip_path = map_data.get('zip_path')
                internal_path = map_data.get('internal_path')
                # 如果字典中有哈希值，可以直接使用
                if 'hash' in map_data and map_data['hash']:
                    uri = map_data.get('archive_uri') or PathURIGenerator.generate(f"{zip_path}!{internal_path}")
                    return img_path, (uri, map_data['hash'])
        elif temp_dir and archive_path and os.path.exists(img_path):
            # 计算相对于临时目录的路径
            if img_path.startswith(temp_dir):
                internal_path = os.path.relpath(img_path, temp_dir)
                internal_path = internal_path.replace('\\', '/')
                zip_path = archive_path
        elif '!' in img_path:
            # 处理压缩包内的图片路径
            # 检查是否是压缩包路径
            archive_extensions = ['.zip!','.cbz!','.cbr!', '.rar!', '.7z!', '.tar!']
            is_archive = any(ext in img_path for ext in archive_extensions)
            
            if is_archive:
                # 找到最后一个压缩文件扩展名的位置
                positions = [img_path.find(ext) for ext in archive_extensions if ext in img_path]
                split_pos = max([pos + len(ext) - 1 for pos, ext in zip(positions, [ext for ext in archive_extensions if ext in img_path])])
                
                # 分割压缩包路径和内部路径
                zip_path = img_path[:split_pos]
                internal_path = img_path[split_pos+1:]
        
        # 调用静态版本的哈希计算函数
        result = get_image_hash_static(img_path, internal_path, zip_path)
        if result:
            return img_path, result
        return img_path, None
    except Exception as e:
        logger.error(f"[#hash_calc]计算哈希值失败 {img_path}: {e}")
        return img_path, None


def get_image_hash_static(image_path: str, internal_path: str = None, zip_path: str = None) -> Optional[Tuple[str, str]]:
    """
    静态版本的哈希计算函数，用于多进程
    
    Args:
        image_path: 图片文件路径
        internal_path: 压缩包内的相对路径（可选）
        zip_path: 压缩包路径（可选）
        
    Returns:
        Optional[Tuple[str, str]]: (uri, hash_value) 或 None
    """
    try:
        # 检查路径
        if not image_path:
            logger.error("[#hash_calc]图片路径为空")
            return None

        # 生成标准URI
        uri = None
        if zip_path and internal_path:
            uri = PathURIGenerator.generate(f"{zip_path}!{internal_path}")
        else:
            # 检查是否是压缩包中的图片
            if '!' in image_path:
                # 检查是否是压缩包路径
                archive_extensions = ['.zip!','.cbz!','.cbr!', '.rar!', '.7z!', '.tar!']
                is_archive = any(ext in image_path for ext in archive_extensions)
                
                if is_archive:
                    # 找到最后一个压缩文件扩展名的位置
                    positions = [image_path.find(ext) for ext in archive_extensions if ext in image_path]
                    split_pos = max([pos + len(ext) - 1 for pos, ext in zip(positions, [ext for ext in archive_extensions if ext in image_path])])
                    
                    # 分割压缩包路径和内部路径
                    zip_path = image_path[:split_pos]
                    internal_path = image_path[split_pos+1:]
                if not os.path.exists(zip_path):
                    return None
                uri = PathURIGenerator.generate(f"{zip_path}!{internal_path}")
            elif not os.path.exists(image_path):
                logger.error(f"[#hash_calc]图片路径不存在: {image_path}")
                return None
            else:
                uri = PathURIGenerator.generate(image_path)

        if not uri:
            logger.error(f"[#hash_calc]生成图片URI失败: {image_path}")
            return None

        # 查询全局缓存
        from hashu.core.calculate_hash_custom import ImageHashCalculator
        cached_hash = ImageHashCalculator.get_hash_from_url(uri)
        if cached_hash:
            logger.info(f"[#hash_calc]使用缓存的哈希值: {uri}")
            return uri, cached_hash

        # 直接读取图片数据（多进程环境下不能使用mmap缓存）
        img_data = None
        try:
            if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                with open(image_path, 'rb') as f:
                    img_data = f.read()
            else:
                logger.error(f"[#hash_calc]图片不存在或为空: {image_path}")
                return None
        except Exception as e:
            logger.error(f"[#hash_calc]读取图片数据失败 {image_path}: {e}")
            return None

        if not img_data:
            logger.error(f"[#hash_calc]获取图片数据失败: {image_path}")
            return None

        # 计算哈希值
        hash_result = ImageHashCalculator.calculate_phash(img_data, url=uri)

        if not hash_result:
            logger.error(f"[#hash_calc]计算图片哈希失败: {image_path}")
            return None

        hash_value = hash_result.get('hash') if isinstance(hash_result, dict) else hash_result
        if not hash_value:
            logger.error(f"[#hash_calc]获取哈希值失败: {image_path}")
            return None

        return uri, hash_value

    except Exception as e:
        logger.error(f"[#hash_calc]获取图片哈希异常 {image_path}: {str(e)}")
        return None


def get_image_data(image_path: str, mmap_cache: Dict = None) -> Optional[Union[mmap.mmap, bytes]]:
    """
    从mmap缓存或文件中获取图片数据
    
    Args:
        image_path: 图片路径
        mmap_cache: mmap缓存字典
        
    Returns:
        图片数据(mmap或字节)或None
    """
    # 检查是否在mmap缓存中
    if mmap_cache and image_path in mmap_cache:
        mm, _ = mmap_cache[image_path]
        # 将文件指针重置到开头
        mm.seek(0)
        return mm
    
    # 如果不在缓存中，尝试读取文件
    try:
        if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
            with open(image_path, 'rb') as f:
                return f.read()
        else:
            logger.error(f"[#hash_calc]图片不存在或为空: {image_path}")
            return None
    except Exception as e:
        logger.error(f"[#hash_calc]读取图片数据失败 {image_path}: {e}")
        return None


def group_images_by_hash(images: List[str], hamming_threshold: int, 
                        archive_path: str = None, temp_dir: str = None,
                        image_archive_map: Dict[str, Union[str, Dict]] = None,
                        calculate_hashes_func=None) -> List[List[str]]:
    """
    使用哈希值(汉明距离)对图片进行分组
    
    Args:
        images: 图片文件列表
        hamming_threshold: 汉明距离阈值
        archive_path: 原始压缩包路径
        temp_dir: 临时解压目录
        image_archive_map: 图片到压缩包内的映射
        calculate_hashes_func: 计算哈希值的函数，需要接收相同的参数并返回相同格式的结果
        
    Returns:
        List[List[str]]: 分组后的图片列表
    """
    # 计算所有图片的哈希值
    logger.info(f"[#hash_calc]计算 {len(images)} 张图片的哈希值...")
    
    # 如果提供了计算函数，使用它；否则报错
    if calculate_hashes_func is None:
        raise ValueError("必须提供计算哈希值的函数")
        
    image_hashes = calculate_hashes_func(images, archive_path, temp_dir, image_archive_map)
      # 提取哈希值用于比较
    hash_values = {img: hash_val for img, (uri, hash_val) in image_hashes.items()}
    uri_values = {img: uri for img, (uri, hash_val) in image_hashes.items()}
    
    # 准备分组
    groups = []
    processed = set()
    
    # 使用哈希值进行分组
    logger.info(f"[#hash_calc]使用汉明距离阈值 {hamming_threshold} 进行分组...")
    
    # 获取所有哈希值列表和对应的图片
    target_hashes = list(hash_values.values())
    img_by_hash = {hash_val: img for img, hash_val in hash_values.items()}
    hash_to_uri = {hash_val: uri_values[img] for img, hash_val in hash_values.items()}
    target_hash_to_uri = {hash_val: uri_values[img] for img, hash_val in hash_values.items()}
    
    # 批量查找相似哈希
    similar_results = HashAccelerator.batch_find_similar_hashes(
        target_hashes,
        target_hashes,
        hash_to_uri,
        hamming_threshold,
        target_hash_to_uri
    )
    
    # 处理结果，构建分组
    for target_hash, similar_hashes in similar_results.items():
        if target_hash not in processed:
            current_group = [img_by_hash[target_hash]]
            processed.add(target_hash)
            
            for similar_hash, uri, distance in similar_hashes:
                if similar_hash != target_hash and similar_hash not in processed:
                    current_group.append(img_by_hash[similar_hash])
                    processed.add(similar_hash)
            
            groups.append(current_group)
    
    # 添加未处理的图片（每张单独一组）
    for img_path, hash_val in hash_values.items():
        if hash_val not in processed:
            groups.append([img_path])
            processed.add(hash_val)
    
    return groups


def compare_hash_with_reference(current_hash: str, hash_data: Dict, threshold: int, 
                              current_uri: Optional[str] = None) -> Optional[Tuple[str, int]]:
    """
    比较哈希值与参考哈希值
    
    Args:
        current_hash: 当前哈希值
        hash_data: 参考哈希数据字典
        threshold: 汉明距离阈值
        current_uri: 当前文件的URI，用于排除自身匹配
        
    Returns:
        Optional[Tuple[str, int]]: (匹配的URI, 距离) 或 None
    """
    try:
        # 使用加速器进行批量比较
        ref_hashes = []
        uri_map = {}
        
        # 收集参考哈希值
        for uri, ref_data in hash_data.items():
            ref_hash = ref_data.get('hash') if isinstance(ref_data, dict) else str(ref_data)
            if not ref_hash:
                continue
                
            ref_hashes.append(ref_hash)
            uri_map[ref_hash] = uri
        
        # 使用加速器查找相似哈希
        similar_hashes = HashAccelerator.find_similar_hashes(
            current_hash,
            ref_hashes,
            uri_map,
            threshold,
            current_uri
        )
        
        # 如果找到相似哈希,返回第一个(最相似的)
        if similar_hashes:
            ref_hash, uri, distance = similar_hashes[0]
            return uri, distance
            
        return None
        
    except Exception as e:
        logger.error(f"[#hash_calc]比较哈希值失败: {e}")
        return None 


def find_similar_images_by_phash_lpips_cluster(images: List[str], 
                                              lpips_threshold: float,
                                              hash_threshold: int,
                                              calculate_hashes_func=None,
                                              lpips_cluster_func=None,
                                              archive_path: str = None, 
                                              temp_dir: str = None, 
                                              image_archive_map: Dict[str, Union[str, Dict]] = None,
                                              use_gpu: bool = False) -> List[List[str]]:
    """
    使用两阶段策略查找相似图片组：
    1. 首先用哈希(汉明距离)对图片进行预分组，减少LPIPS计算量
    2. 然后对每个预分组内的图片进行LPIPS聚类
    
    Args:
        images: 图片文件列表
        lpips_threshold: LPIPS距离阈值
        hash_threshold: 哈希预分组的汉明距离阈值
        calculate_hashes_func: 计算哈希值的函数
        lpips_cluster_func: LPIPS聚类函数
        archive_path: 原始压缩包路径
        temp_dir: 临时解压目录
        image_archive_map: 图片到压缩包内的映射
        use_gpu: 是否使用GPU
        
    Returns:
        List[List[str]]: 相似图片组列表
    """
    from datetime import datetime
    
    # 检查图片数量
    if len(images) < 2:
        logger.warning("[#hash_calc]图片数量不足，至少需要2张图片进行聚类")
        return []
    
    # 检查必要的函数是否提供
    if calculate_hashes_func is None:
        raise ValueError("必须提供计算哈希值的函数")
    
    if lpips_cluster_func is None:
        raise ValueError("必须提供LPIPS聚类函数")
    
    logger.info(f"[#hash_calc]开始两阶段相似图片检测：哈希预分组(阈值:{hash_threshold})+LPIPS聚类(阈值:{lpips_threshold})")
    
    # 记录开始时间
    start_time = datetime.now()
    
    # 阶段1: 使用哈希(汉明距离)进行预分组
    logger.info(f"[#hash_calc]阶段1: 开始使用哈希值对 {len(images)} 张图片进行预分组...")
    hash_groups = group_images_by_hash(
        images, 
        hash_threshold, 
        archive_path, 
        temp_dir, 
        image_archive_map, 
        calculate_hashes_func
    )
    
    # 统计预分组结果
    num_groups = len(hash_groups)
    total_grouped = sum(len(group) for group in hash_groups)
    single_image_groups = sum(1 for group in hash_groups if len(group) == 1)
    multi_image_groups = num_groups - single_image_groups
    
    logger.info(f"[#hash_calc]哈希预分组完成: 共 {num_groups} 组, {multi_image_groups} 个多图片组, {single_image_groups} 个单图片组")
    
    # 阶段2: 对每个包含多张图片的预分组进行LPIPS聚类
    all_similar_groups = []
    
    if multi_image_groups > 0:
        logger.info(f"[#hash_calc]阶段2: 开始对 {multi_image_groups} 个多图片组进行LPIPS聚类...")
        
        # 对每个多图片组进行LPIPS聚类
        group_count = 0
        for group in hash_groups:
            if len(group) < 2:
                continue  # 跳过只有一张图片的组
            
            group_count += 1
            logger.info(f"[#hash_calc]处理哈希组 {group_count}/{multi_image_groups}: {len(group)} 张图片")
            
            # 对当前组进行LPIPS聚类
            similar_groups = lpips_cluster_func(
                group, 
                threshold=lpips_threshold,
                use_gpu=use_gpu
            )
            
            # 将结果添加到总列表
            all_similar_groups.extend(similar_groups)
    
    # 计算总耗时
    elapsed_time = (datetime.now() - start_time).total_seconds()
    total_groups = len(all_similar_groups)
    total_images = sum(len(group) for group in all_similar_groups)
    
    logger.info(f"[#hash_calc]两阶段相似图片检测完成，耗时: {elapsed_time:.2f}秒")
    logger.info(f"[#hash_calc]最终结果: {total_groups} 个相似组, 共包含 {total_images} 张图片")
    
    return all_similar_groups 