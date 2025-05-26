import os
import shutil
import subprocess
import time
from typing import List, Set, Dict, Optional, Tuple
import pyperclip
import zipfile
import shutil
import zipfile
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any
from loguru import logger
from imgfilter.utils.backup import BackupHandler
from imgfilter.core.filter import ImageFilter

# 全局变量定义
SUPPORTED_ARCHIVE_FORMATS = ['.zip', '.rar', '.7z', '.cbz', '.cbr']

from loguru import logger
class ArchiveHandler:

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
                logger.error(f"[#file_ops]读取压缩包内容失败: {result.stderr}")
                return files
                
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('Path = '):
                    file_path = line[7:]
                    if any(file_path.lower().endswith(ext) for ext in file_types):
                        files.append(file_path)
                        
        except Exception as e:
            logger.error(f"[#file_ops]列出压缩包内容时出错: {e}")
            
        return files

    """通用压缩包处理工具类"""
    
    def __init__(self):
        """初始化压缩包处理器
        
        Args:
            image_filter: 图片过滤器实例，用于处理图片文件
        """
        self.image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif', '.bmp')
        # 定义黑名单关键词
        self.blacklist_keywords = ["画集", "CG", "02cos", "01杂", "图集"]
        self.image_filter = ImageFilter()
    
    def process_directory(self, path: str, filter_params: Dict[str, Any] = None) -> Tuple[bool, str, List[str]]:
        """处理目录或压缩包
        
        Args:
            path: 目录或压缩包路径
            filter_params: 图片过滤参数
            
        Returns:
            Tuple[bool, str, List[str]]: (是否成功, 错误信息, 处理结果列表)
        """
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(f"路径不存在: {path}")
                
            if not os.access(path, os.R_OK):
                raise PermissionError(f"路径无法访问: {path}")
            
            success = True
            error_msg = ""
            results = []
            
            # 处理目录
            if os.path.isdir(path):
                for root, _, files in os.walk(path):
                    root_lower = root.lower()
                    if any(kw in root_lower for kw in self.blacklist_keywords):
                        logger.info(f"跳过黑名单目录: {root}")
                        continue
                        
                    for file in files:
                        if not file.lower().endswith('.zip'):
                            continue
                            
                        zip_path = os.path.join(root, file)
                        if any(kw in os.path.basename(zip_path).lower() for kw in self.blacklist_keywords):
                            logger.info(f"跳过黑名单文件: {os.path.basename(zip_path)}")
                            continue
                            
                        if not zipfile.is_zipfile(zip_path):
                            logger.warning(f"跳过无效的ZIP文件: {zip_path}")
                            continue
                            
                        file_success, file_error, file_results = self.process_archive(zip_path, filter_params)
                        if not file_success:
                            logger.warning(f"处理返回失败: {os.path.basename(zip_path)}, 原因: {file_error}")
                            error_msg = file_error
                        success = success and file_success
                        results.extend(file_results)
                        
            # 处理单个zip文件
            elif path.lower().endswith('.zip'):
                if any(kw in os.path.basename(path).lower() for kw in self.blacklist_keywords):
                    return False, "黑名单文件", []
                    
                if not zipfile.is_zipfile(path):
                    return False, "无效的ZIP文件", []
                    
                return self.process_archive(path, filter_params)
            else:
                logger.warning(f"跳过非ZIP文件: {path}")
                return False, "非ZIP文件", []
                
            return success, error_msg, results
            
        except FileNotFoundError as e:
            logger.error(f"路径不存在: {path}")
            return False, str(e), []
        except PermissionError as e:
            logger.error(f"路径访问权限错误: {path}")
            return False, str(e), []
        except Exception as e:
            logger.error(f"处理过程出错: {path}: {str(e)}")
            return False, str(e), []

    def process_archive(self, archive_path: str, filter_params: Dict[str, Any] = None) -> Tuple[bool, str, List[str]]:
        """处理单个压缩包
        
        Args:
            archive_path: 压缩包路径
            filter_params: 图片过滤参数
            
        Returns:
            Tuple[bool, str, List[str]]: (是否成功, 错误信息, 处理结果列表)
        """
        if not self._check_archive_integrity(archive_path):
            return False, "压缩包损坏或无法读取", []
            
        # 准备环境
        temp_dir, backup_path = self._prepare_environment(archive_path)
        if not temp_dir:
            return False, "准备环境失败", []
            
        try:
            # 解压文件
            if not self._extract_archive(archive_path, temp_dir):
                return False, "解压失败", []
                
            # 处理图片
            results = []
            if self.image_filter and filter_params:
                # 直接传入原始压缩包路径
                results = self._process_images(temp_dir, archive_path, filter_params)
                
            return True, "", results
            
        except Exception as e:
            return False, f"处理失败: {str(e)}", []
            
        finally:
            # 清理临时文件
            self._cleanup(temp_dir)
    
    def _check_archive_integrity(self, archive_path: str) -> bool:
        """检查压缩包完整性
        
        Args:
            archive_path: 压缩包路径
            
        Returns:
            bool: 是否为有效的压缩包
        """
        try:
            # 首先检查路径是否为文件
            if not os.path.isfile(archive_path):
                logger.error(f"路径不是文件: {archive_path}")
                return False
                
            # 检查压缩包完整性
            with zipfile.ZipFile(archive_path, 'r') as zf:
                return not zf.testzip()
        except Exception as e:
            logger.error(f"检查压缩包完整性失败: {str(e)}")
            return False
    
    def _prepare_environment(self, archive_path: str) -> Tuple[Optional[str], Optional[str]]:
        """准备处理环境
        
        Returns:
            Tuple[str, str]: (临时目录路径, 备份文件路径)
        """
        try:
            # 创建临时目录
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            zip_name = os.path.splitext(os.path.basename(archive_path))[0]
            extract_dir = os.path.join(os.path.dirname(archive_path), f"temp_{zip_name}_{timestamp}")
            os.makedirs(extract_dir, exist_ok=True)
            
            # 检查是否为临时合并的文件（根据文件名前缀判断）
            is_merged_file = os.path.basename(archive_path).startswith('merged_')
            
            # 创建备份（仅当不是合并文件时）
            backup_path = None
            if not is_merged_file:
                backup_path = archive_path + '.bak'
                shutil.copy2(archive_path, backup_path)
                logger.info(f"创建备份: {backup_path}")
            else:
                logger.info(f"跳过为临时合并文件创建备份: {archive_path}")
            
            return extract_dir, backup_path
        except Exception as e:
            logger.error(f"准备环境失败: {str(e)}")
            return None, None
    
    def _extract_archive(self, archive_path: str, extract_path: str) -> bool:
        """解压压缩包
        
        Args:
            archive_path: 压缩包路径
            extract_path: 解压目标路径
            
        Returns:
            bool: 是否成功解压
        """
        try:
            # 优先使用7z解压
            cmd = [
                '7z', 'x',
                str(archive_path),
                f'-o{str(extract_path)}',
                '-aoa',       # 覆盖已存在的文件
                '-y'         # 自动确认
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            if result.returncode == 0:
                logger.info(f"使用7z成功解压: {archive_path}")
                return True
            else:
                logger.warning(f"使用7z解压失败，尝试使用zipfile作为备选: {result.stderr}")
                
            # 使用zipfile作为备选方案，尝试不同编码
            encodings = ['utf-8', 'cp932', 'shift_jis', 'euc_jp', 'cp437']
            
            for encoding in encodings:
                try:
                    with zipfile.ZipFile(archive_path, 'r') as zf:
                        # 尝试使用当前编码解压所有文件
                        for file in zf.namelist():
                            try:
                                # 解码文件名
                                filename = file.encode('cp437').decode(encoding)
                                # 构建完整路径
                                target_path = os.path.join(extract_path, filename)
                                # 确保目标目录存在
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                # 解压文件
                                with zf.open(file) as source, open(target_path, 'wb') as target:
                                    shutil.copyfileobj(source, target)
                            except:
                                continue
                    
                    logger.info(f"使用zipfile成功解压（编码：{encoding}）: {archive_path}")
                    return True
                        
                except Exception as e:
                    logger.debug(f"使用编码 {encoding} 解压失败: {e}")
                    continue
            
            logger.error("所有编码尝试均失败")
            return False
                
        except Exception as e:
            logger.error(f"解压失败: {str(e)}")
            return False
    
    def _process_images(self, directory: str, archive_path: str, filter_params: Dict[str, Any]) -> List[str]:
        """处理目录中的图片
        
        Args:
            directory: 图片所在目录
            archive_path: 原始压缩包路径
            filter_params: 过滤参数
            
        Returns:
            List[str]: 处理结果列表
        """
        results = []
        image_files = self._get_image_files(directory)
        
        try:
            # 为每个图片创建对应的压缩包内信息映射（JSON格式）
            image_archive_map = {}
            for img_path in image_files:
                # 计算图片相对于临时目录的路径
                rel_path = os.path.relpath(img_path, directory)
                # 替换反斜杠为正斜杠，符合压缩包内路径格式
                rel_path = rel_path.replace('\\', '/')
                # 生成标准URI
                archive_uri = f"{archive_path}!{rel_path}"
                # 使用JSON格式存储更多信息
                image_archive_map[img_path] = {
                    'archive_uri': archive_uri,
                    'zip_path': archive_path,
                    'internal_path': rel_path
                }
            
            # 复制过滤参数，避免修改原始参数
            local_params = filter_params.copy() if filter_params else {}
            # 添加压缩包路径和内部图片映射关系
            local_params['archive_path'] = archive_path
            local_params['temp_dir'] = directory
            local_params['image_archive_map'] = image_archive_map
            
            # 调用图片过滤器处理整个图片文件列表
            to_delete_files, removal_reasons = self.image_filter.process_images(
                image_files,
                **local_params
            )
            
            if to_delete_files:
                # 将结果添加到处理结果列表
                for file_path in to_delete_files:
                    reason = removal_reasons.get(file_path, "未知原因")
                    results.append(f"已过滤: {os.path.basename(file_path)} - {reason}")
                
                # 调用process_archive_delete处理文件删除
                success, error = BackupHandler.process_archive_delete(
                    archive_path,
                    to_delete_files,
                    removal_reasons,
                    directory,
                    filter_params.get('config')  # 传入配置信息
                )
                if not success:
                    logger.error(f"删除文件失败: {error}")
                    
        except Exception as e:
            logger.error(f"处理图片失败: {str(e)}")
            
        return results
    
    def _get_image_files(self, directory: str) -> List[str]:
        """获取目录中的所有图片文件"""
        image_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(self.image_extensions):
                    image_files.append(os.path.join(root, file))
        return image_files
    
    def _cleanup(self, temp_dir: str):
        """清理临时文件"""
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            logger.error(f"清理临时文件失败: {str(e)}")
        
    """通用输入处理类"""

