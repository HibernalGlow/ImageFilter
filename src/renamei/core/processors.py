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
    def __init__(self, config_path=None):
        """初始化广告图片检测器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        # 默认配置
        self.ad_keywords = [
            '招募',
            'credit',
            '广告',
            '宣传',
            '招新',
            '绅士快乐',
            '粉丝群',
            '無邪気'
        ]
        self.ad_regex_patterns = [
            r'[Cc]redit[s]',
            r'ver\.\d+\.\d+',
            r'YZv\.\d+\.\d+',
            r'z{3,}'
        ]
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.avif', '.jxl', '.tiff', '.tif'}
        
        # 默认阈值配置
        self.max_delete_percentage = 0.5  # 最大删除比例阈值
        
        # 尝试从配置文件加载
        if config_path is None:
            # 默认配置文件路径
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ad_detector_config.json')
        
        self._load_config(config_path)
        # 编译正则表达式模式
        self.combined_regex = None
        if self.ad_regex_patterns:
            self.combined_regex = re.compile('|'.join(self.ad_regex_patterns))
        logger.debug(f"广告图片检测器初始化完成，加载了{len(self.ad_keywords)}个关键词和{len(self.ad_regex_patterns)}个正则模式，删除阈值:{self.max_delete_percentage}")
    
    def _load_config(self, config_path):
        """从配置文件加载广告匹配模式
        
        Args:
            config_path: 配置文件路径
        """
        try:
            import json
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                if 'ad_keywords' in config:
                    self.ad_keywords = config['ad_keywords']
                    # logger.info(f"从配置文件 {config_path} 加载了 {len(self.ad_keywords)} 个广告关键词")
                
                if 'ad_regex_patterns' in config:
                    self.ad_regex_patterns = config['ad_regex_patterns']
                    # logger.info(f"从配置文件 {config_path} 加载了 {len(self.ad_regex_patterns)} 个广告正则模式")
                
                # 向后兼容，支持旧版配置
                elif 'ad_patterns' in config:
                    self.ad_keywords = config['ad_patterns']
                    # logger.info(f"从配置文件 {config_path} 加载了 {len(self.ad_keywords)} 个广告匹配模式（旧版格式）")
                
                if 'image_extensions' in config:
                    self.image_extensions = set(config['image_extensions'])
                    # logger.info(f"从配置文件 {config_path} 加载了 {len(self.image_extensions)} 个图片扩展名")
                
                # 加载阈值配置
                if 'thresholds' in config:
                    thresholds = config['thresholds']
                    if 'max_delete_percentage' in thresholds:
                        self.max_delete_percentage = thresholds['max_delete_percentage']
                        logger.info(f"从配置文件加载删除阈值: {self.max_delete_percentage}")
            else:
                logger.warning(f"配置文件 {config_path} 不存在，使用默认配置")
        except Exception as e:
            logger.error(f"加载配置文件 {config_path} 失败: {e}")
            logger.warning("使用默认广告匹配模式配置")
    def is_ad_image(self, filename: str) -> bool:
        """检查文件名是否匹配广告图片模式"""
        if not self._is_image_file(filename):
            return False
        
        # 方法1: 直接字符串关键词匹配
        for keyword in self.ad_keywords:
            if keyword in filename:
                logger.info(f"检测到广告关键词 '{keyword}' 在文件: {filename}")
                return True
        
        # 方法2: 正则表达式匹配
        if self.combined_regex and self.combined_regex.search(filename):
            logger.info(f"检测到正则匹配广告图片: {filename}")
            return True
        
        logger.debug(f"文件不匹配任何广告模式: {filename}")
        return False
    
    def _is_image_file(self, filename: str) -> bool:
        """检查文件是否为图片文件"""
        ext = os.path.splitext(filename.lower())[1]
        return ext in self.image_extensions


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
    """临时目录管理器 - 支持指定基础目录"""
    def __init__(self):
        self.temp_dirs = []
        self.base_dir = r"E:\2400EHV\extracted_archives"
        os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"使用固定解压目录: {self.base_dir}")

    def create_temp_dir(self, base_dir=None) -> str:
        """创建临时目录，支持指定基础目录"""
        if base_dir is None:
            base_dir = self.base_dir
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        dir_name = f"{timestamp}_{unique_id}"
        temp_dir = os.path.join(base_dir, dir_name)
        os.makedirs(temp_dir, exist_ok=True)
        self.temp_dirs.append(temp_dir)
        logger.debug(f"创建解压目录: {temp_dir}")
        return temp_dir
    
    def cleanup_all(self):
        """清理所有临时目录"""
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
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
            logger.debug(f"开始使用7z解压 {zip_path} 到 {extract_dir}")
            extract_cmd = ['7z', 'x', '-y', zip_path, f'-o{extract_dir}']
            result = subprocess.run(extract_cmd, check=True, capture_output=True, 
                                  encoding='utf-8', errors='ignore')
            logger.debug(f"7z解压完成，返回码: {result.returncode}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"7z解压失败: {e}")
            logger.error(f"7z错误输出: {e.stderr if hasattr(e, 'stderr') else ''}")
            return False
        except Exception as e:
            logger.error(f"7z解压过程发生异常: {e}")
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

    def list_files_zipfile(self, zip_path: str) -> List[str]:
        """使用zipfile模块列出压缩包中的文件，支持中英日文字符"""
        try:
            logger.debug(f"列出压缩包中的文件: {zip_path}")
            import zipfile
            # 尝试不同的编码方式解析文件名
            encodings = ['utf-8']
            files = []
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                namelist = zip_ref.namelist()
                
                for name in namelist:
                    # 尝试不同编码方式解码文件名
                    decoded_name = None
                    for encoding in encodings:
                        try:
                            # 对于非UTF-8编码的文件名，需要先将bytes解码
                            if encoding != 'utf-8':
                                # 将文件名视为bytes并以指定编码解码
                                decoded_name = name.encode('cp437').decode(encoding)
                            else:
                                decoded_name = name
                            break
                        except UnicodeDecodeError:
                            continue
                    
                    if decoded_name:
                        files.append(decoded_name)
                    else:
                        # 如果所有编码都失败，使用原始名称
                        files.append(name)
                        
            return files
        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            # 如果zipfile失败，回退到7z方法
            return self.list_files(zip_path)

    def list_files(self, zip_path: str) -> List[str]:
        """使用7z列出压缩包中的文件，支持中英日文字符"""
        try:
            # 使用系统默认编码处理中文文件名
            list_cmd = ['7z', 'l', '-slt', zip_path]
            result = subprocess.run(list_cmd, capture_output=True, 
                                  text=False)  # 获取bytes输出
            
            files = []
            # 尝试多种编码解析输出
            encodings = ['utf-8', 'gbk', 'shift-jis', 'cp936']
            stdout_text = None
            
            for encoding in encodings:
                try:
                    stdout_text = result.stdout.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if stdout_text is None:
                stdout_text = result.stdout.decode('utf-8', errors='ignore')
                
            for line in stdout_text.split('\n'):
                if line.startswith('Path = '):
                    file_path = line[7:].strip()
                    if file_path:
                        files.append(file_path)
            return files
        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            # 如果失败，回退到zipfile方法
            return self.list_files_zipfile(zip_path)
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
            logger.debug(f"开始使用Bandizip解压 {zip_path} 到 {extract_dir}")
            # 确保提取路径存在
            os.makedirs(extract_dir, exist_ok=True)
            # 注意：Bandizip可能需要路径带引号
            extract_cmd = ['bz', 'x', '-o:', f'"{extract_dir}"', f'"{zip_path}"']
            command_str = ' '.join(extract_cmd)
            logger.debug(f"执行命令: {command_str}")
            result = subprocess.run(command_str, shell=True, 
                                  capture_output=True, encoding='utf-8', errors='ignore')
            logger.debug(f"Bandizip解压完成，返回码: {result.returncode}")
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
