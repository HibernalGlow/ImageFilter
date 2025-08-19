import os
import logging
from typing import List, Dict, Tuple, Set, Union, Optional
import json
from PIL import Image
import pillow_avif
import pillow_jxl 
from io import BytesIO
import multiprocessing
import mmap  # 添加 mmap 导入
import tempfile
import shutil

from regex import F
from hashu.core.calculate_hash_custom import ImageHashCalculator, PathURIGenerator
from hashu.utils.hash_accelerator import HashAccelerator
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger
from imgutils.metrics import lpips_difference, lpips_clustering, find_similar_images_lpips

class DuplicateImageDetector:
    """重复图片检测器，支持多种检测策略"""
    
    def __init__(self, hash_file: str = None, hamming_threshold: int = 12, 
                 ref_hamming_threshold: int = None, max_workers: int = None,
                 use_lpips: bool = False, lpips_threshold: float = 0.3):
        """
        初始化重复图片检测器
        
        Args:
            hash_file: 哈希文件路径，用于哈希模式
            hamming_threshold: 汉明距离阈值，用于相似图片组检测
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值，默认使用hamming_threshold
            max_workers: 最大工作线程数，默认为CPU核心数
            use_lpips: 是否使用LPIPS进行图片相似度比较
            lpips_threshold: LPIPS相似度阈值，低于此值被视为相似图片
        """
        self.hash_file = hash_file
        self.hamming_threshold = hamming_threshold
        self.ref_hamming_threshold = ref_hamming_threshold if ref_hamming_threshold is not None else hamming_threshold
        self.max_workers = max_workers or multiprocessing.cpu_count()*2
        self.hash_cache = {}
        self.mmap_cache = {}  # 添加mmap缓存
        self.use_lpips = use_lpips
        self.lpips_threshold = lpips_threshold
        if hash_file:
            self.hash_cache = self._load_hash_file()
    
    def _cleanup_mmap_cache(self):
        """清理mmap缓存"""
        for path, (mm, f) in self.mmap_cache.items():
            try:
                if mm:
                    mm.close()
                if f:
                    f.close()
            except Exception as e:
                logger.error(f"[#hash_calc]清理mmap缓存失败 {path}: {e}")
        self.mmap_cache = {}
            
    def detect_duplicates(self, 
                         image_files: List[str],
                         archive_path: str = None, 
                         temp_dir: str = None,
                         image_archive_map: Dict[str, Union[str, Dict]] = None,
                         mode: str = 'quality', 
                         watermark_keywords: List[str] = None,
                         ref_hamming_threshold: int = None,
                         *args, **kwargs) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        检测重复图片
        
        Args:
            image_files: 图片文件列表
            archive_path: 原始压缩包路径
            temp_dir: 临时解压目录
            image_archive_map: 图片到压缩包内URI的映射
            mode: 重复过滤模式 ('quality', 'watermark' 或 'hash')
            watermark_keywords: 水印关键词列表，用于watermark模式
            ref_hamming_threshold: 哈希文件过滤的汉明距离阈值
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        if not image_files:
            return set(), {}
        
        # 先清理之前可能的缓存
        self._cleanup_mmap_cache()
        
        # 预加载所有图片到mmap缓存
        self._preload_images_to_mmap(image_files)
        
        try:
            duplicate_results = set()
            duplicate_reasons = {}
            
            # 使用哈希文件模式
            if mode == 'hash':
                # Try to get hash_file from kwargs if not already set
                hash_file_from_kwargs = kwargs.get('hash_file')
                if hash_file_from_kwargs :
                    self.hash_file = hash_file_from_kwargs
                    # Load hash file data if it wasn't loaded before
                    self.hash_cache = self._load_hash_file()
                
                if self.hash_cache:
                    return self._process_hash_images(image_files, archive_path, temp_dir, image_archive_map, ref_hamming_threshold)
                else:
                    logger.warning("[#hash_calc]Hash mode selected but no hash file provided")
            
            # 其他模式: 先找出相似图片组，然后按不同策略处理
            similar_groups = self._find_similar_images(image_files, archive_path, temp_dir, image_archive_map)
            
            # 对每个相似组应用过滤策略
            for group in similar_groups:
                if len(group) > 1:
                    if mode == 'watermark':
                        group_results, group_reasons = self._process_watermark_images(group, watermark_keywords)
                    else:  # 默认使用quality模式
                        group_results, group_reasons = self._process_quality_images(group)
                        
                    duplicate_results.update(group_results)
                    duplicate_reasons.update(group_reasons)
            
            return duplicate_results, duplicate_reasons
        finally:
            # 清理mmap缓存
            self._cleanup_mmap_cache()
    
    def _preload_images_to_mmap(self, image_files: List[str]):
        """
        预加载所有图片文件到mmap缓存
        
        Args:
            image_files: 图片文件列表
        """
        logger.info(f"预加载 {len(image_files)} 张图片到内存映射...")
        
        for img_path in image_files:
            try:
                # 检查是否为压缩包内文件
                if '!' in img_path:
                    # 压缩包内文件不用预加载，会通过其他方式读取
                    continue
                
                # 检查文件是否存在且可读
                if not os.path.exists(img_path) or not os.path.isfile(img_path):
                    logger.warning(f"[#hash_calc]跳过不存在或非文件: {img_path}")
                    continue
                
                file_size = os.path.getsize(img_path)
                if file_size == 0:
                    logger.warning(f"[#hash_calc]跳过空文件: {img_path}")
                    continue
                
                # 打开文件并创建内存映射
                f = open(img_path, 'rb')
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                self.mmap_cache[img_path] = (mm, f)
                
            except Exception as e:
                logger.error(f"[#hash_calc]预加载图片失败 {img_path}: {e}")
                # 如果失败，确保任何已打开的资源被关闭
                if img_path in self.mmap_cache:
                    mm, f = self.mmap_cache.pop(img_path)
                    if mm:
                        try: mm.close()
                        except: pass
                    if f:
                        try: f.close()
                        except: pass
    
    def _get_image_data(self, image_path: str) -> Optional[Union[mmap.mmap, bytes]]:
        """
        从mmap缓存或文件中获取图片数据
        
        Args:
            image_path: 图片路径
            
        Returns:
            图片数据(mmap或字节)或None
        """
        # 检查是否在mmap缓存中
        if image_path in self.mmap_cache:
            mm, _ = self.mmap_cache[image_path]
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
    
    def _calculate_hashes_for_images(self, images: List[str], archive_path: str = None, temp_dir: str = None, 
                                    image_archive_map: Dict[str, Union[str, Dict]] = None) -> Dict[str, Tuple[str, str]]:
        """
        为图片列表计算哈希值
        
        Args:
            images: 图片文件列表
            archive_path: 原始压缩包路径
            temp_dir: 临时解压目录
            image_archive_map: 图片到压缩包内信息的映射，可以是字符串URI或包含详细信息的字典
            
        Returns:
            Dict[str, Tuple[str, str]]: {图片路径: (URI, 哈希值)}
        """
        hash_values = {}
        for img in images:
            try:
                # 从映射中获取压缩包信息，如果不存在则尝试从路径推导
                zip_path = None
                internal_path = None
                
                if image_archive_map and img in image_archive_map:
                    # 检查映射中的数据类型
                    map_data = image_archive_map[img]
                    if isinstance(map_data, dict):
                        # 新格式：直接从字典中获取路径信息
                        zip_path = map_data.get('zip_path')
                        internal_path = map_data.get('internal_path')
                        # 如果字典中有哈希值，可以直接使用
                        if 'hash' in map_data and map_data['hash']:
                            uri = map_data.get('archive_uri') or PathURIGenerator.generate(f"{zip_path}!{internal_path}")
                            hash_values[img] = (uri, map_data['hash'])
                            continue
                elif temp_dir and archive_path and os.path.exists(img):
                    # 计算相对于临时目录的路径
                    if img.startswith(temp_dir):
                        internal_path = os.path.relpath(img, temp_dir)
                        internal_path = internal_path.replace('\\', '/')
                        zip_path = archive_path
                elif '!' in img:
                    # 处理压缩包内的图片路径
                    # 检查是否是压缩包路径
                    archive_extensions = ['.zip!','.cbz!','.cbr!', '.rar!', '.7z!', '.tar!']
                    is_archive = any(ext in img for ext in archive_extensions)
                    
                    if is_archive:
                        # 找到最后一个压缩文件扩展名的位置
                        positions = [img.find(ext) for ext in archive_extensions if ext in img]
                        split_pos = max([pos + len(ext) - 1 for pos, ext in zip(positions, [ext for ext in archive_extensions if ext in img])])
                        
                        # 分割压缩包路径和内部路径
                        zip_path = img[:split_pos]
                        internal_path = img[split_pos+1:]
                
                result = self._get_image_hash_with_preload(img, internal_path, zip_path)
                if result:
                    uri, hash_value = result
                    hash_values[img] = (uri, hash_value)
            except Exception as e:
                logger.error(f"[#hash_calc]计算哈希值失败 {img}: {e}")
        
        return hash_values

    def _get_image_hash_with_preload(self, image_path: str, internal_path: str = None, zip_path: str = None) -> Tuple[str, str]:
        """获取图片哈希值和URI，优先使用预加载的mmap数据
        
        Args:
            image_path: 图片文件路径
            internal_path: 压缩包内的相对路径（可选）
            zip_path: 压缩包路径（可选）
            
        Returns:
            Tuple[str, str]: (uri, hash_value) 或 None
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
            cached_hash = ImageHashCalculator.get_hash_from_url(uri)
            if cached_hash:
                logger.info(f"[#hash_calc]使用缓存的哈希值: {uri}")
                return uri, cached_hash

            # 获取预加载的图片数据或直接读取
            img_data = self._get_image_data(image_path)
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
    
    def _load_hash_file(self) -> Dict:
        """加载哈希文件"""
        if not self.hash_file:
            return {}
            
        # 移除可能存在的额外引号
        clean_path = self.hash_file.strip('"\'')
        
        # 确保使用绝对路径
        if not os.path.isabs(clean_path):
            clean_path = os.path.abspath(clean_path)
        
        try:
            if not os.path.exists(clean_path):
                logger.error(f"[#hash_calc]哈希文件不存在: \"{clean_path}\"")
                return {}
                
            with open(clean_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"成功加载哈希文件: {clean_path}")
                hash_cache_data = data.get('hashes', {})
                return hash_cache_data
        except Exception as e:
            logger.error(f"[#hash_calc]加载哈希文件失败: {e}")
            return {}
    def _find_similar_images(self, images: List[str], archive_path: str = None, temp_dir: str = None,image_archive_map: Dict[str, Union[str, Dict]] = None) -> List[List[str]]:
        """查找相似的图片组"""
        similar_groups = []
        processed = set()
        
        # 如果启用LPIPS，使用LPIPS进行相似度比较和聚类
        if self.use_lpips:
            logger.info(f"使用LPIPS查找相似图片，阈值: {self.lpips_threshold}")
            # 过滤出真实存在的图片路径
            valid_images = []
            for img_path in images:
                if '!' in img_path:
                    # 暂不支持压缩包内文件的LPIPS比较
                    logger.warning(f"[#hash_calc]暂不支持压缩包内文件的LPIPS比较: {img_path}")
                    continue
                if not os.path.exists(img_path) or not os.path.isfile(img_path):
                    logger.warning(f"[#hash_calc]跳过不存在或非文件: {img_path}")
                    continue
                valid_images.append(img_path)
            
            # 使用LPIPS查找相似图片组
            try:
                similar_groups = find_similar_images_lpips(valid_images, threshold=self.lpips_threshold)
                logger.info(f"LPIPS找到 {len(similar_groups)} 个相似图片组")
                return similar_groups
            except Exception as e:
                logger.error(f"[#hash_calc]LPIPS查找相似图片失败: {e}，将回退到哈希方法")
                # 回退到哈希方法
        
        # 计算所有图片的哈希值
        image_hashes = self._calculate_hashes_for_images(images, archive_path, temp_dir, image_archive_map)
        
        # 提取哈希值用于比较
        hash_values = {img: hash_val for img, (uri, hash_val) in image_hashes.items()}
        
        # 使用加速器进行批量比较
        target_hashes = list(hash_values.values())
        img_by_hash = {hash_val: img for img, hash_val in hash_values.items()}
        
        # 批量查找相似哈希
        similar_results = HashAccelerator.batch_find_similar_hashes(
            target_hashes,
            target_hashes,
            img_by_hash,
            self.hamming_threshold
        )
        
        # 处理结果,构建相似图片组
        for target_hash, similar_hashes in similar_results.items():
            if target_hash not in processed:
                current_group = [img_by_hash[target_hash]]
                processed.add(target_hash)
                
                for similar_hash, uri, distance in similar_hashes:
                    if similar_hash not in processed:
                        current_group.append(img_by_hash[similar_hash])
                        processed.add(similar_hash)
                        logger.info(f"找到相似图片: {os.path.basename(uri)} (距离: {distance})")
                
                if len(current_group) > 1:
                    similar_groups.append(current_group)
                    logger.info(f"找到相似图片组: {len(current_group)}张")
                
        return similar_groups
    
    def _process_watermark_images(self, group: List[str], watermark_keywords: List[str] = None) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理水印过滤"""
        to_delete = set()
        removal_reasons = {}
        
        deleted_files = self._apply_watermark_filter(group, watermark_keywords)
        for img, texts in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'watermark',
                'watermark_texts': texts,
                'matched_keywords': [kw for kw in (watermark_keywords or []) if any(kw in text for text in texts)]
            }
            logger.info(f"标记删除有水印图片: {os.path.basename(img)}")
            
        return to_delete, removal_reasons
    
    def _apply_watermark_filter(self, group: List[str], watermark_keywords: List[str] = None) -> List[Tuple[str, List[str]]]:
        """
        应用水印过滤，返回要删除的图片和水印文字
        
        Args:
            group: 相似图片组
            watermark_keywords: 水印关键词列表，None时使用默认列表
        """
        from imgfilter.detectors.watermark import WatermarkDetector

        watermark_detector = WatermarkDetector()
        to_delete = []
        watermark_results = {}
        
        # 检测每张图片的水印
        for img_path in group:
            has_watermark, texts = watermark_detector.detect_watermark(img_path, watermark_keywords)
            watermark_results[img_path] = (has_watermark, texts)
            if has_watermark:
                logger.info(f"发现水印: {os.path.basename(img_path)} -> {texts}")
            
        # 找出无水印的图片
        clean_images = [img for img, (has_mark, _) in watermark_results.items() if not has_mark]
        
        if clean_images:
            # 如果有无水印图片，保留其中最大的一张
            keep_image = max(clean_images, key=lambda x: os.path.getsize(x))
            # 删除其他有水印的图片
            for img in group:
                if img != keep_image and watermark_results[img][0]:
                    to_delete.append((img, watermark_results[img][1]))
                    
        return to_delete
        
    def _process_quality_images(self, group: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理质量过滤"""
        to_delete = set()
        removal_reasons = {}
        
        deleted_files = self._apply_quality_filter(group)
        for img, size_diff in deleted_files:
            to_delete.add(img)
            removal_reasons[img] = {
                'reason': 'quality',
                'size_diff': size_diff
            }
            logger.info(f"标记删除较小图片: {os.path.basename(img)}")
            
        return to_delete, removal_reasons

    def _apply_quality_filter(self, group: List[str]) -> List[Tuple[str, str]]:
        """应用质量过滤（基于文件大小），返回要删除的图片和大小差异"""
        to_delete = []
        # 获取文件大小
        file_sizes = {img: os.path.getsize(img) for img in group}
        # 保留最大的文件
        keep_image = max(group, key=lambda x: file_sizes[x])
        
        # 删除其他较小的文件
        for img in group:
            if img != keep_image:
                size_diff = f"{file_sizes[keep_image] - file_sizes[img]} bytes"
                to_delete.append((img, size_diff))
                
        return to_delete
    
    def _process_hash_images(self, group: List[str], archive_path: str = None, temp_dir: str = None, 
                           image_archive_map: Dict[str, Union[str, Dict]] = None, ref_hamming_threshold: int = None) -> Tuple[Set[str], Dict[str, Dict]]:
        """处理哈希文件过滤"""
        to_delete = set()
        removal_reasons = {}
        
        # 使用传入的阈值或默认值
        threshold = ref_hamming_threshold if ref_hamming_threshold is not None else self.ref_hamming_threshold
        
        # 计算哈希值
        image_hashes = self._calculate_hashes_for_images(group, archive_path, temp_dir, image_archive_map)
        
        # 读取哈希文件
        # try:
        #     with open(self.hash_file, 'r', encoding='utf-8') as f:
        #         hash_data = json.load(f).get('hashes', {})
        # except Exception as e:
        #     logger.error(f"[#hash_calc]读取哈希文件失败: {e}")
        #     return to_delete, removal_reasons
        hash_data = self.hash_cache
        # 比较哈希值
        for img_path, (current_uri, current_hash) in image_hashes.items():
            try:
                result = self._compare_hash_with_reference(
                    img_path, current_uri, current_hash,
                    hash_data, threshold
                )
                if result:
                    match_uri, distance = result
                    to_delete.add(img_path)
                    removal_reasons[img_path] = {
                        'reason': 'hash_duplicate',
                        'ref_uri': match_uri,
                        'distance': distance
                    }
                    logger.info(f"标记删除重复图片: {os.path.basename(img_path)} (参考URI: {match_uri}, 距离: {distance})")
            except Exception as e:
                logger.error(f"[#hash_calc]比较哈希值失败 {img_path}: {e}")
                    
        return to_delete, removal_reasons

    def _compare_hash_with_reference(self, img_path: str, current_uri: str, current_hash: str, 
                                   hash_data: Dict, threshold: int) -> Tuple[str, int]:
        """比较哈希值与参考哈希值"""
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
            logger.error(f"[#hash_calc]比较哈希值失败 {img_path}: {e}")
            return None
