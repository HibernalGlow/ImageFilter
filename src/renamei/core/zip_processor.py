"""压缩包处理器 - 负责处理压缩包的完整流程"""
import os
import shutil
from typing import List, Optional
from loguru import logger

from .processors import (
    AdImageDetector, FileRenamer, DuplicateFileHandler, 
    TempDirectoryManager, CompressionTool, SevenZipTool, BandizipTool
)
from bakf.core.backup import BackupHandler


class ZipProcessor:
    """压缩包处理器"""
    def __init__(self, config_path=None):
        self.ad_detector = AdImageDetector(config_path)
        self.file_renamer = FileRenamer()
        self.duplicate_handler = DuplicateFileHandler(self.file_renamer)
        self.temp_manager = TempDirectoryManager()
        
        # 压缩工具优先级：7z -> Bandizip
        self.compression_tools = [SevenZipTool(), BandizipTool()]
        # self.compression_tools = SevenZipTool()
    def needs_modification(self, zip_path: str) -> bool:
        """检查压缩包是否需要进行修改"""
        try:
            # 使用第一个可用的工具检查
            for tool in self.compression_tools:
                try:
                    files = tool.list_files(zip_path)
                    if not files:
                        continue
                    
                    # 检查是否有广告图片或hash文件
                    for file_path in files:
                        if self.ad_detector.is_ad_image(file_path):
                            return True
                        if '[hash-' in file_path:
                            return True
                    
                    return False
                except Exception:
                    continue
            
            logger.warning(f"无法检查压缩包是否需要修改: {zip_path}")
            return True  # 保险起见，假设需要修改
            
        except Exception as e:
            logger.error(f"检查压缩包失败: {e}")
            return True
    
    def process_zip(self, zip_path: str, input_base_path: str) -> bool:
        """处理压缩包的主函数"""
        try:
            # 检查是否需要修改
            if not self.needs_modification(zip_path):
                logger.info(f"压缩包不需要修改，跳过: {os.path.basename(zip_path)}")
                return True
            
            # 创建回收站目录
            trash_dir = self._get_trash_dir(zip_path)
            
            # 处理广告图片
            ad_processed = self._process_ad_images(zip_path, trash_dir)
            
            # 处理文件名重命名
            rename_processed = self._process_file_renaming(zip_path, trash_dir)
            
            return ad_processed and rename_processed
            
        except Exception as e:
            logger.error(f"处理压缩包失败 {zip_path}: {e}")
            return False
        finally:
            # 清理临时目录
            self.temp_manager.cleanup_all()
            # 清理空的回收站目录
            self._cleanup_empty_trash_dir(zip_path)
    
    def _get_trash_dir(self, zip_path: str) -> str:
        """获取回收站目录路径"""
        zip_basename = os.path.basename(zip_path)
        zip_dirname = os.path.dirname(zip_path)
        return os.path.join(zip_dirname, f"{zip_basename}.trash")
    def _process_ad_images(self, zip_path: str, trash_dir: str) -> bool:
        """处理广告图片"""
        try:
            tool = self._get_available_tool()
            if not tool:
                return False
            files = tool.list_files(zip_path)
            ad_files = [f for f in files if self.ad_detector.is_ad_image(f)]
            if not ad_files:
                return True  # 没有广告图片，处理成功
            total_images = len([f for f in files if self.ad_detector._is_image_file(f)])
            delete_percentage = len(ad_files) / total_images if total_images > 0 else 0
            if delete_percentage > self.ad_detector.max_delete_percentage:
                logger.warning(f"检测到 {len(ad_files)} 个广告图片，占总图片数 {total_images} 的 {delete_percentage*100:.1f}%")
                logger.warning(f"为防止误删除，已取消删除操作（删除比例超过{self.ad_detector.max_delete_percentage*100:.1f}%）")
                return True
            removal_reasons = {f: {"reason": "ad"} for f in ad_files}
            to_delete = set(ad_files)
            options = {"backup": {"enabled": True}}
            ok, msg = BackupHandler.process_archive_delete(
                zip_path, to_delete, removal_reasons, options
            )
            if ok:
                logger.info(f"已从压缩包中删除 {len(ad_files)} 个广告图片")
                return True
            else:
                logger.error(f"删除广告图片失败: {msg}")
                return False
        except Exception as e:
            logger.error(f"处理广告图片失败: {e}")
            return False
    
    def _process_file_renaming(self, zip_path: str, trash_dir: str) -> bool:
        """处理文件重命名和hash文件删除"""
        try:
            tool = self._get_available_tool()
            if not tool:
                return False
            files = tool.list_files(zip_path)
            # 1. 先处理hash文件删除
            hash_files = [f for f in files if '[hash-' in f]
            if hash_files:
                removal_reasons = {f: {"reason": "hash"} for f in hash_files}
                to_delete = set(hash_files)
                options = {"backup": {"enabled": True}}
                ok, msg = BackupHandler.process_archive_delete(
                    zip_path, to_delete, removal_reasons, options
                )
                if not ok:
                    logger.error(f"删除hash文件失败: {msg}")
                    return False
                files = tool.list_files(zip_path)
            has_hash_files = any('[hash-' in f for f in files)
            if not has_hash_files:
                logger.info("无需处理文件名，跳过重新打包")
                return True
            zip_dir = os.path.dirname(zip_path)
            temp_dir = self.temp_manager.create_temp_dir(base_dir=zip_dir)
            if not tool.extract(zip_path, temp_dir):
                logger.error("解压文件失败")
                return False
            duplicate_files = self.duplicate_handler.find_duplicate_files(temp_dir)
            need_repack = False
            if duplicate_files:
                logger.info("检测到重名文件，开始处理")
                os.makedirs(trash_dir, exist_ok=True)
                dupes_trash_dir = os.path.join(trash_dir, "duplicates")
                os.makedirs(dupes_trash_dir, exist_ok=True)
                if self.duplicate_handler.handle_duplicates(duplicate_files, temp_dir, dupes_trash_dir):
                    need_repack = True
                else:
                    logger.error("处理重名文件失败")
                    return False
            renamed_count = self._rename_files_in_directory(temp_dir)
            if renamed_count > 0:
                need_repack = True
                logger.info(f"重命名了 {renamed_count} 个文件")
            if need_repack:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                if tool.create(zip_path, temp_dir):
                    logger.info(f"压缩包处理完成: {zip_path}")
                    return True
                else:
                    logger.error("重新打包失败")
                    return False
            else:
                logger.info("无需修改，跳过重新打包")
                return True
        except Exception as e:
            logger.error(f"处理文件重命名失败: {e}")
            return False
    
    def _rename_files_in_directory(self, directory: str) -> int:
        """在目录中重命名文件，返回重命名的文件数量"""
        renamed_count = 0
        
        for root, _, files in os.walk(directory):
            for filename in files:
                new_filename = self.file_renamer.remove_hash_from_filename(filename)
                if new_filename != filename:
                    old_path = os.path.join(root, filename)
                    new_path = os.path.join(root, new_filename)
                    
                    try:
                        if os.path.exists(new_path):
                            logger.warning(f"目标文件已存在，跳过重命名: {new_filename}")
                            continue
                        
                        os.rename(old_path, new_path)
                        logger.debug(f"重命名: {filename} -> {new_filename}")
                        renamed_count += 1
                        
                    except Exception as e:
                        logger.error(f"重命名失败 {filename}: {e}")
        
        return renamed_count
    
    def _get_available_tool(self) -> Optional[CompressionTool]:
        """获取第一个可用的压缩工具"""
        for tool in self.compression_tools:
            try:
                # 简单测试工具是否可用
                if isinstance(tool, SevenZipTool):
                    # 测试7z
                    import subprocess
                    subprocess.run(['7z'], capture_output=True, timeout=5)
                    return tool
                elif isinstance(tool, BandizipTool):
                    # 测试Bandizip
                    subprocess.run(['bz'], capture_output=True, timeout=5)
                    return tool
            except:
                continue
        
        logger.error("没有可用的压缩工具")
        return None
    
    def _cleanup_empty_trash_dir(self, zip_path: str):
        """清理空的回收站目录"""
        trash_dir = self._get_trash_dir(zip_path)
        if os.path.exists(trash_dir) and not os.listdir(trash_dir):
            try:
                os.rmdir(trash_dir)
                logger.debug(f"删除空回收站目录: {trash_dir}")
            except Exception as e:
                logger.warning(f"删除空回收站目录失败: {e}")
