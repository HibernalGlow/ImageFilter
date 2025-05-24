"""处理器类 - 将复杂的处理逻辑分解为独立的处理器"""
import os
import re
import hashlib
import shutil
import uuid
import time
import subprocess
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from loguru import logger


class AdImageDetector:
    """广告图片检测器"""
    
    def __init__(self):
        self.ad_patterns = [
            r'招募',
            r'credit',
            r'广告',
            r'[Cc]redit[s]',
            r'宣传',
            r'招新',
            r'ver\.\d+\.\d+',
            r'YZv\.\d+\.\d+',
            r'绅士快乐',
            r'粉丝群',
            r'z{3,}',
            r'無邪気'
        ]
        self.combined_pattern = '|'.join(self.ad_patterns)
    
    def is_ad_image(self, filename: str) -> bool:
        """检查文件名是否匹配广告图片模式"""
        if not self._is_image_file(filename):
            return False
        
        result = bool(re.search(self.combined_pattern, filename))
        if result:
            logger.debug(f"检测到广告图片: {filename}")
        return result
    
    def _is_image_file(self, filename: str) -> bool:
        """检查文件是否为图片文件"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.avif', '.jxl', '.tiff', '.tif'}
        ext = os.path.splitext(filename.lower())[1]
        return ext in image_extensions


class FileRenamer:
    """文件重命名处理器"""
    
    @staticmethod
    def remove_hash_from_filename(filename: str) -> str:
        """从文件名中移除[hash-xxxxxx]模式"""
        return re.sub(r'\[hash-[0-9a-fA-F]+\]', '', filename)
    
    @staticmethod
    def get_file_content_hash(file_path: str) -> Optional[str]:
        """获取文件内容的哈希值"""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                return hashlib.sha256(content).hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败 {file_path}: {e}")
            return None
    
    @staticmethod
    def get_file_creation_time(file_path: str) -> float:
        """获取文件创建时间"""
        try:
            return os.path.getctime(file_path)
        except Exception:
            return 0


class DuplicateFileHandler:
    """重复文件处理器"""
    
    def __init__(self, file_renamer: FileRenamer):
        self.file_renamer = file_renamer
    
    def find_duplicate_files(self, temp_dir: str) -> Dict[str, int]:
        """查找重复的文件名"""
        filename_count = {}
        
        for root, _, files in os.walk(temp_dir):
            for filename in files:
                new_filename = self.file_renamer.remove_hash_from_filename(filename)
                filename_count[new_filename] = filename_count.get(new_filename, 0) + 1
        
        return {name: count for name, count in filename_count.items() if count > 1}
    
    def handle_duplicates(self, duplicate_files: Dict[str, int], temp_dir: str, trash_dir: str) -> bool:
        """处理重名文件，比较内容并保留最早的版本"""
        for filename, count in duplicate_files.items():
            logger.info(f"处理重名文件: {filename} (共{count}个)")
            
            # 收集所有同名文件
            same_name_files = []
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    new_name = self.file_renamer.remove_hash_from_filename(f)
                    if new_name == filename:
                        full_path = os.path.join(root, f)
                        creation_time = self.file_renamer.get_file_creation_time(full_path)
                        same_name_files.append((full_path, creation_time, f))
            
            if not same_name_files:
                continue
            
            # 按创建时间排序
            same_name_files.sort(key=lambda x: x[1])
            
            # 获取第一个文件的哈希值作为参考
            reference_hash = self.file_renamer.get_file_content_hash(same_name_files[0][0])
            if reference_hash is None:
                logger.error(f"无法比较文件内容，跳过处理: {filename}")
                continue
            
            # 保留最早的文件，处理其他文件
            keep_file = same_name_files[0][0]
            for file_path, _, orig_filename in same_name_files[1:]:
                current_hash = self.file_renamer.get_file_content_hash(file_path)
                if current_hash == reference_hash:
                    # 相同内容，移到回收站
                    logger.info(f"保存重复文件到回收站: {orig_filename}")
                    shutil.copy2(file_path, os.path.join(trash_dir, orig_filename))
                    os.remove(file_path)
                else:
                    # 不同内容，重命名
                    logger.warning(f"发现内容不同的同名文件: {os.path.basename(file_path)}")
                    self._rename_with_suffix(file_path, filename)
            
            logger.info(f"保留最早的文件: {os.path.basename(keep_file)}")
        
        return True
    
    def _rename_with_suffix(self, file_path: str, target_filename: str):
        """为文件添加序号后缀"""
        dir_path = os.path.dirname(file_path)
        base_name, ext = os.path.splitext(target_filename)
        counter = 1
        new_name = f"{base_name}_{counter}{ext}"
        
        while os.path.exists(os.path.join(dir_path, new_name)):
            counter += 1
            new_name = f"{base_name}_{counter}{ext}"
        
        new_path = os.path.join(dir_path, new_name)
        os.rename(file_path, new_path)
        logger.info(f"重命名为: {new_name}")


class TempDirectoryManager:
    """临时目录管理器 - 使用固定目录代替临时目录"""
    
    def __init__(self):
        self.temp_dirs = []
        self.base_dir = r"E:\2400EHV\extracted_archives"
        # 确保基础目录存在
        os.makedirs(self.base_dir, exist_ok=True)
    
    def create_temp_dir(self) -> str:
        """创建临时目录"""
        # 使用时间戳和UUID生成唯一目录名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        dir_name = f"{timestamp}_{unique_id}"
        
        # 创建目录
        temp_dir = os.path.join(self.base_dir, dir_name)
        os.makedirs(temp_dir, exist_ok=True)
        
        self.temp_dirs.append(temp_dir)
        logger.debug(f"创建解压目录: {temp_dir}")
        return temp_dir
    
    def cleanup_all(self):
        """清理所有临时目录"""
        for temp_dir in self.temp_dirs:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"清理目录: {temp_dir}")
            except Exception as e:
                logger.warning(f"清理目录失败 {temp_dir}: {e}")
        self.temp_dirs.clear()


class CompressionTool:
    """压缩工具抽象基类"""
    
    def extract(self, zip_path: str, extract_dir: str) -> bool:
        """解压文件"""
        raise NotImplementedError
    
    def create(self, zip_path: str, source_dir: str) -> bool:
        """创建压缩包"""
        raise NotImplementedError
    
    def list_files(self, zip_path: str) -> List[str]:
        """列出压缩包中的文件"""
        raise NotImplementedError
    
    def delete_files(self, zip_path: str, files_to_delete: List[str]) -> bool:
        """从压缩包中删除文件"""
        raise NotImplementedError


class SevenZipTool(CompressionTool):
    """7z工具实现"""
    
    def extract(self, zip_path: str, extract_dir: str) -> bool:
        """使用7z解压文件"""
        try:
            extract_cmd = ['7z', 'x', zip_path, f'-o{extract_dir}']
            result = subprocess.run(extract_cmd, check=True, capture_output=True, 
                                  encoding='utf-8', errors='ignore')
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"7z解压失败: {e}")
            return False
    
    def create(self, zip_path: str, source_dir: str) -> bool:
        """使用7z创建压缩包"""
        try:
            create_cmd = ['7z', 'a', '-tzip', zip_path, os.path.join(source_dir, '*')]
            result = subprocess.run(create_cmd, check=True, capture_output=True,
                                  encoding='utf-8', errors='ignore')
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"7z打包失败: {e}")
            return False
    
    def list_files(self, zip_path: str) -> List[str]:
        """使用7z列出文件"""
        try:
            list_cmd = ['7z', 'l', '-slt', zip_path]
            result = subprocess.run(list_cmd, capture_output=True, 
                                  encoding='utf-8', errors='ignore')
            
            files = []
            for line in result.stdout.split('\n'):
                if line.startswith('Path = '):
                    file_path = line[7:].strip()
                    if file_path:
                        files.append(file_path)
            return files
        except Exception as e:
            logger.error(f"7z列出文件失败: {e}")
            return []
    
    def delete_files(self, zip_path: str, files_to_delete: List[str]) -> bool:
        """使用7z删除文件"""
        try:
            delete_cmd = ['7z', 'd', zip_path] + files_to_delete
            result = subprocess.run(delete_cmd, capture_output=True,
                                  encoding='utf-8', errors='ignore')
            return result.returncode == 0
        except Exception as e:
            logger.error(f"7z删除文件失败: {e}")
            return False


class BandizipTool(CompressionTool):
    """Bandizip工具实现"""
    
    def extract(self, zip_path: str, extract_dir: str) -> bool:
        """使用Bandizip解压文件"""
        try:
            extract_cmd = ['bz', 'x', '-o:', f'"{extract_dir}"', f'"{zip_path}"']
            result = subprocess.run(' '.join(extract_cmd), shell=True, 
                                  capture_output=True, encoding='utf-8', errors='ignore')
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Bandizip解压失败: {e}")
            return False
    
    def create(self, zip_path: str, source_dir: str) -> bool:
        """使用Bandizip创建压缩包"""
        try:
            create_cmd = ['bz', 'c', '-l:9', f'"{zip_path}"', f'"{source_dir}\\*"']
            result = subprocess.run(' '.join(create_cmd), shell=True,
                                  capture_output=True, encoding='utf-8', errors='ignore')
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Bandizip打包失败: {e}")
            return False
    
    def list_files(self, zip_path: str) -> List[str]:
        """Bandizip不直接支持列出文件，使用7z代替"""
        seven_zip = SevenZipTool()
        return seven_zip.list_files(zip_path)
    
    def delete_files(self, zip_path: str, files_to_delete: List[str]) -> bool:
        """Bandizip不直接支持删除文件，使用7z代替"""
        seven_zip = SevenZipTool()
        return seven_zip.delete_files(zip_path, files_to_delete)
