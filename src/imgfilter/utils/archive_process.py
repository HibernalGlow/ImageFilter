import os
import shutil
import subprocess
import time
from typing import List, Set, Dict, Optional, Tuple
from loguru import logger

class ArchiveHandler:
    """压缩包处理类"""
    
    @staticmethod
    def list_archive_contents(archive_path: str, file_types: Set[str] = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif', '.jxl', '.heic', '.heif'}) -> List[str]:
        """
        列出压缩包中指定类型的文件
        
        Args:
            archive_path: 压缩包路径
            file_types: 要列出的文件类型集合
            
        Returns:
            List[str]: 文件路径列表
        """
        files = []
        try:
            cmd = ['7z', 'l', '-slt', archive_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"读取压缩包内容失败: {result.stderr}")
                return files
                
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('Path = '):
                    file_path = line[7:]
                    if any(file_path.lower().endswith(ext) for ext in file_types):
                        files.append(file_path)
                        
        except Exception as e:
            logger.error(f"列出压缩包内容时出错: {e}")
            
        return files
    
    @staticmethod
    def extract_files(
        archive_path: str,
        files_to_extract: List[str],
        output_dir: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        从压缩包中提取指定的文件
        
        Args:
            archive_path: 压缩包路径
            files_to_extract: 要提取的文件列表
            output_dir: 输出目录，如果为None则创建临时目录
            
        Returns:
            Tuple[bool, str]: (是否成功, 输出目录路径)
        """
        temp_dir = output_dir or os.path.join(
            os.path.dirname(archive_path), 
            f'temp_{int(time.time())}'
        )
        
        try:
            os.makedirs(temp_dir, exist_ok=True)
            
            # 创建文件列表
            list_file = os.path.join(temp_dir, '@files.txt')
            with open(list_file, 'w', encoding='utf-8') as f:
                for file in files_to_extract:
                    f.write(file + '\n')
                    
            # 解压文件
            cmd = ['7z', 'x', archive_path, f'-o{temp_dir}', f'@{list_file}', '-y']
            result = subprocess.run(cmd, capture_output=True, text=True)
            os.remove(list_file)
            
            if result.returncode != 0:
                logger.error(f"解压失败: {result.stderr}")
                if not output_dir:
                    shutil.rmtree(temp_dir)
                return False, ""
                
            return True, temp_dir
            
        except Exception as e:
            logger.error(f"提取文件时出错: {e}")
            if not output_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return False, ""
    
    @staticmethod
    def create_archive(
        archive_path: str,
        source_dir: str,
        delete_source: bool = False
    ) -> bool:
        """
        创建新的压缩包
        
        Args:
            archive_path: 目标压缩包路径
            source_dir: 源文件目录
            delete_source: 是否删除源文件目录
            
        Returns:
            bool: 是否成功
        """
        try:
            cmd = ['7z', 'a', archive_path, os.path.join(source_dir, '*')]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"创建压缩包失败: {result.stderr}")
                return False
                
            if delete_source:
                shutil.rmtree(source_dir)
                
            return True
            
        except Exception as e:
            logger.error(f"创建压缩包时出错: {e}")
            return False
    
    @staticmethod
    def replace_archive(
        original_archive: str,
        new_archive: str,
        create_backup: bool = True
    ) -> bool:
        """
        替换原有压缩包
        
        Args:
            original_archive: 原压缩包路径
            new_archive: 新压缩包路径
            create_backup: 是否创建备份
            
        Returns:
            bool: 是否成功
        """
        try:
            if create_backup:
                backup_path = original_archive + '.bak'
                shutil.copy2(original_archive, backup_path)
                
            os.replace(new_archive, original_archive)
            return True
            
        except Exception as e:
            logger.error(f"替换压缩包时出错: {e}")
            return False 