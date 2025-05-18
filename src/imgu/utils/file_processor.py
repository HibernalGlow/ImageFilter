"""
文件处理工具模块
"""
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional, Generator, Union
import os
import logging
from loguru import logger
import json
import zipfile
import tempfile
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
import threading
from tqdm import tqdm

# 图像文件扩展名集合
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', 
    '.tiff', '.tif', '.jxl', '.avif'
}

# 压缩文件扩展名集合
ARCHIVE_EXTENSIONS = {
    '.zip', '.cbz', '.rar', '.cbr', '.7z', '.cb7'
}

class FileProcessor:
    """文件处理工具类"""
    
    @staticmethod
    def is_image_file(file_path: Union[str, Path]) -> bool:
        """
        判断文件是否为图像文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            True 如果是图像文件，否则False
        """
        return Path(file_path).suffix.lower() in IMAGE_EXTENSIONS
    
    @staticmethod
    def is_archive_file(file_path: Union[str, Path]) -> bool:
        """
        判断文件是否为压缩文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            True 如果是压缩文件，否则False
        """
        return Path(file_path).suffix.lower() in ARCHIVE_EXTENSIONS
    
    @staticmethod
    def list_files(
        path: Union[str, Path], 
        recursive: bool = False,
        file_types: Set[str] = None
    ) -> List[Path]:
        """
        列出目录中的文件
        
        Args:
            path: 目录路径
            recursive: 是否递归搜索子目录
            file_types: 文件类型（扩展名）的集合，例如 {'.jpg', '.png'}
            
        Returns:
            文件路径列表
        """
        path = Path(path)
        if not path.exists():
            logger.error(f"路径不存在: {path}")
            return []
        
        if path.is_file():
            if file_types is None or path.suffix.lower() in file_types:
                return [path]
            return []
        
        result = []
        if recursive:
            for item in path.rglob('*'):
                if item.is_file() and (file_types is None or item.suffix.lower() in file_types):
                    result.append(item)
        else:
            for item in path.iterdir():
                if item.is_file() and (file_types is None or item.suffix.lower() in file_types):
                    result.append(item)
                    
        return result
    
    @staticmethod
    def get_image_files(path: Union[str, Path], recursive: bool = False) -> List[Path]:
        """
        获取目录中的所有图像文件
        
        Args:
            path: 目录路径
            recursive: 是否递归搜索子目录
            
        Returns:
            图像文件路径列表
        """
        return FileProcessor.list_files(path, recursive, IMAGE_EXTENSIONS)
    
    @staticmethod
    def get_archive_files(path: Union[str, Path], recursive: bool = False) -> List[Path]:
        """
        获取目录中的所有压缩文件
        
        Args:
            path: 目录路径
            recursive: 是否递归搜索子目录
            
        Returns:
            压缩文件路径列表
        """
        return FileProcessor.list_files(path, recursive, ARCHIVE_EXTENSIONS)
    
    @staticmethod
    def save_results_to_json(results: Dict, output_path: Union[str, Path]):
        """
        保存结果到JSON文件
        
        Args:
            results: 结果数据
            output_path: 输出文件路径
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
            logger.info(f"结果已保存到: {output_path}")
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
    
    @staticmethod
    def save_results_to_txt(results: List[str], output_path: Union[str, Path]):
        """
        保存文本结果到TXT文件
        
        Args:
            results: 文本行列表
            output_path: 输出文件路径
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                for line in results:
                    f.write(f"{line}\n")
                    
            logger.info(f"结果已保存到: {output_path}")
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
    
    @staticmethod
    def extract_images_from_archive(
        archive_path: Union[str, Path], 
        output_dir: Union[str, Path] = None,
        temp_dir: Union[str, Path] = None
    ) -> List[Path]:
        """
        从压缩文件中提取图像
        
        Args:
            archive_path: 压缩文件路径
            output_dir: 输出目录，如果为None则创建临时目录
            temp_dir: 临时目录位置，如果为None则使用系统临时目录
            
        Returns:
            提取的图像文件路径列表
        """
        if not FileProcessor.is_archive_file(archive_path):
            logger.error(f"不是支持的压缩文件: {archive_path}")
            return []
        
        # 创建临时目录或使用指定的输出目录
        is_temp = output_dir is None
        if is_temp:
            if temp_dir:
                temp_base = Path(temp_dir)
                temp_base.mkdir(parents=True, exist_ok=True)
                output_dir = tempfile.mkdtemp(dir=temp_base)
            else:
                output_dir = tempfile.mkdtemp()
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        output_dir = Path(output_dir)
        archive_path = Path(archive_path)
        
        try:
            # 只处理 .zip 和 .cbz 格式，其他格式需要使用外部工具
            if archive_path.suffix.lower() in ('.zip', '.cbz'):
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    # 过滤出图像文件
                    image_files = [f for f in zf.namelist() 
                                 if any(f.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)]
                    
                    # 提取图像文件
                    for image_file in image_files:
                        zf.extract(image_file, output_dir)
                
                # 返回提取的图像文件路径
                return FileProcessor.get_image_files(output_dir, recursive=True)
            else:
                logger.error(f"不支持的压缩文件格式: {archive_path}")
                if is_temp:
                    shutil.rmtree(output_dir, ignore_errors=True)
                return []
                
        except Exception as e:
            logger.error(f"提取图像失败: {e}")
            if is_temp:
                shutil.rmtree(output_dir, ignore_errors=True)
            return []
    
    @staticmethod
    def move_files(files: List[Union[str, Path]], target_dir: Union[str, Path]) -> int:
        """
        移动文件到目标目录
        
        Args:
            files: 要移动的文件列表
            target_dir: 目标目录
            
        Returns:
            成功移动的文件数量
        """
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        for file_path in files:
            file_path = Path(file_path)
            target_path = target_dir / file_path.name
            
            # 如果目标文件已存在，添加时间戳
            if target_path.exists():
                timestamp = int(time.time())
                target_path = target_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
            
            try:
                shutil.move(str(file_path), str(target_path))
                success_count += 1
            except Exception as e:
                logger.error(f"移动文件失败 {file_path}: {e}")
                
        return success_count
    
    @staticmethod
    def process_files_parallel(
        files: List[Union[str, Path]],
        process_func: callable,
        max_workers: int = None,
        **kwargs
    ) -> List[Tuple[Path, any]]:
        """
        并行处理文件
        
        Args:
            files: 要处理的文件列表
            process_func: 处理函数，接受文件路径作为第一个参数
            max_workers: 最大工作线程数，默认为CPU核心数的2倍
            **kwargs: 传递给处理函数的其他参数
            
        Returns:
            (file_path, result)元组的列表
        """
        if not max_workers:
            max_workers = os.cpu_count() * 2 or 4
            
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for file_path in files:
                future = executor.submit(process_func, file_path, **kwargs)
                futures[future] = file_path
            
            # 使用tqdm显示进度
            total = len(files)
            with tqdm(total=total, desc="处理文件") as pbar:
                for future in futures:
                    file_path = futures[future]
                    try:
                        result = future.result()
                        results.append((file_path, result))
                    except Exception as e:
                        logger.error(f"处理文件失败 {file_path}: {e}")
                    pbar.update(1)
                    
        return results
