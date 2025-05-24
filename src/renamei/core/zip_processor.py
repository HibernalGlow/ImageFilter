"""压缩包处理器 - 负责处理压缩包的完整流程"""
import os
import shutil
from typing import List, Optional
from loguru import logger

from .processors import (
    AdImageDetector, FileRenamer, DuplicateFileHandler, 
    TempDirectoryManager, CompressionTool, SevenZipTool, BandizipTool
)


class ZipProcessor:
    """压缩包处理器"""
    def __init__(self, config_path=None):
        self.ad_detector = AdImageDetector(config_path)
        self.file_renamer = FileRenamer()
        self.duplicate_handler = DuplicateFileHandler(self.file_renamer)
        self.temp_manager = TempDirectoryManager()
        
        # 压缩工具优先级：7z -> Bandizip
        self.compression_tools = [SevenZipTool(), BandizipTool()]
    
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
            # 获取文件列表
            tool = self._get_available_tool()
            if not tool:
                return False
            
            files = tool.list_files(zip_path)
            ad_files = [f for f in files if self.ad_detector.is_ad_image(f)]
            
            if not ad_files:
                return True  # 没有广告图片，处理成功
            
            # 统计图片总数
            total_images = len([f for f in files if self.ad_detector._is_image_file(f)])
            delete_percentage = len(ad_files) / total_images if total_images > 0 else 0
            
            # 安全检查：防止误删除
            if delete_percentage > 0.8:
                logger.warning(f"检测到 {len(ad_files)} 个广告图片，占总图片数 {total_images} 的 {delete_percentage*100:.1f}%")
                logger.warning("为防止误删除，已取消删除操作（删除比例超过80%）")
                return True
            
            # 创建回收站目录
            os.makedirs(trash_dir, exist_ok=True)
            logger.info(f"创建回收站目录: {trash_dir}")
            
            # 解压整个压缩包到临时目录，然后复制广告图片到回收站
            temp_dir = self.temp_manager.create_temp_dir()
            if tool.extract(zip_path, temp_dir):
                # 复制广告图片到回收站
                for ad_file in ad_files:
                    src_path = os.path.join(temp_dir, ad_file)
                    if os.path.exists(src_path):
                        dst_path = os.path.join(trash_dir, os.path.basename(ad_file))
                        shutil.copy2(src_path, dst_path)
                        logger.info(f"已提取广告图片到回收站: {ad_file}")
                
                # 从压缩包中删除广告图片
                if tool.delete_files(zip_path, ad_files):
                    logger.info(f"已从压缩包中删除 {len(ad_files)} 个广告图片")
                    return True
                else:
                    logger.error("删除广告图片失败")
                    return False
            else:
                logger.error("解压文件失败，无法提取广告图片")
                return False
                
        except Exception as e:
            logger.error(f"处理广告图片失败: {e}")
            return False
    
    def _process_file_renaming(self, zip_path: str, trash_dir: str) -> bool:
        """处理文件重命名"""
        try:
            tool = self._get_available_tool()
            if not tool:
                return False
            
            # 检查是否有需要重命名的文件
            files = tool.list_files(zip_path)
            has_hash_files = any('[hash-' in f for f in files)
            
            if not has_hash_files:
                logger.info("无需处理文件名，跳过重新打包")
                return True
            
            # 解压到临时目录
            temp_dir = self.temp_manager.create_temp_dir()
            if not tool.extract(zip_path, temp_dir):
                logger.error("解压文件失败")
                return False
            
            # 检查重复文件
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
            
            # 重命名文件
            renamed_count = self._rename_files_in_directory(temp_dir)
            if renamed_count > 0:
                need_repack = True
                logger.info(f"重命名了 {renamed_count} 个文件")
            
            # 重新打包
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
