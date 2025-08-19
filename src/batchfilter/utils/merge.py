import os
import shutil
import time
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
from send2trash import send2trash
from loguru import logger
class ArchiveMerger:
    # 黑名单关键词列表，用于过滤不需要处理的文件
    BLACKLIST_KEYWORDS = ['merged_', 'temp_', 'backup_', '.new', '.trash']
    
    @staticmethod
    def merge_archives(paths: List[str]) -> Tuple[Optional[str], Optional[str], List[str]]:
        """
        将多个压缩包合并为一个临时压缩包
        
        Args:
            paths: 压缩包路径列表
            
        Returns:
            Tuple[str, str, List[str]]: (临时目录路径, 合并后的压缩包路径, 原始压缩包路径列表)
            如果失败则返回 (None, None, [])
            如果只有一个压缩包，则返回 (None, 原始压缩包路径, [原始压缩包路径])
        """
        temp_dir = None
        try:
            # 收集所有ZIP文件路径，同时排除黑名单中的关键词
            archive_paths = []
            for path in paths:
                # 检查路径是否包含黑名单关键词
                if any(keyword in path for keyword in ArchiveMerger.BLACKLIST_KEYWORDS):
                    logger.info(f"[#file_ops]跳过黑名单文件: {path}")
                    continue
                    
                if os.path.isdir(path):
                    for root, _, files in os.walk(path):
                        for f in files:
                            file_path = os.path.join(root, f)
                            # 检查文件是否是zip并且不在黑名单中
                            if f.lower().endswith('.zip') and not any(keyword in f for keyword in ArchiveMerger.BLACKLIST_KEYWORDS):
                                archive_paths.append(file_path)
                            elif f.lower().endswith('.zip'):
                                logger.info(f"[#file_ops]跳过黑名单压缩包: {f}")
                elif path.lower().endswith('.zip'):
                    archive_paths.append(path)
            
            if not archive_paths:
                logger.info("[#file_ops]没有找到要处理的压缩包")
                return (None, None, [])
            
            # 如果只有一个压缩包，直接返回它
            if len(archive_paths) == 1:
                logger.info(f"[#file_ops]只有一个压缩包，无需合并: {archive_paths[0]}")
                return (None, archive_paths[0], archive_paths)
            
            # 确保所有压缩包在同一目录
            directories = {os.path.dirname(path) for path in archive_paths}
            if len(directories) > 1:
                logger.info("[#file_ops]所选压缩包不在同一目录")
                return (None, None, [])
                
            base_dir = list(directories)[0]
            timestamp = int(time.time() * 1000)
            temp_dir = os.path.join(base_dir, f'temp_merge_{timestamp}')
            os.makedirs(temp_dir, exist_ok=True)
            
            # 解压所有压缩包
            for zip_path in archive_paths:
                logger.info(f'[#file_ops]解压: {zip_path}')
                archive_name = os.path.splitext(os.path.basename(zip_path))[0]
                archive_temp_dir = os.path.join(temp_dir, archive_name)
                os.makedirs(archive_temp_dir, exist_ok=True)
                
                cmd = ['7z', 'x', zip_path, f'-o{archive_temp_dir}', '-y']
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    logger.info(f"[#file_ops]解压失败: {zip_path}\n错误: {result.stderr}")
                    return (None, None, [])
            
            # 创建合并后的压缩包
            merged_zip_path = os.path.join(base_dir, f'merged_{timestamp}.zip')
            logger.info('[#file_ops]创建合并压缩包')
            
            cmd = ['7z', 'a', '-tzip', merged_zip_path, os.path.join(temp_dir, '*')]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.info(f"[#file_ops]创建合并压缩包失败: {result.stderr}")
                return (None, None, [])
                
            return (temp_dir, merged_zip_path, archive_paths)
            
        except Exception as e:
            logger.info(f"[#file_ops]合并压缩包时出错: {e}")
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return (None, None, [])
    @staticmethod
    def split_merged_archive(processed_zip, original_archives, temp_dir, params):
        """
        将处理后的合并压缩包拆分回原始压缩包
        
        Args:
            processed_zip: 处理后的合并压缩包路径
            original_archives: 原始压缩包路径列表
            temp_dir: 临时目录路径
            params: 参数字典
        """
        try:
            logger.info('开始拆分处理后的压缩包')
            extract_dir = os.path.join(temp_dir, 'processed')
            os.makedirs(extract_dir, exist_ok=True)
            
            # 解压处理后的压缩包
            cmd = ['7z', 'x', processed_zip, f'-o{extract_dir}', '-y']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.info(f"❌ 解压处理后的压缩包失败: {result.stderr}")
                return False
                
            for original_zip in original_archives:
                archive_name = os.path.splitext(os.path.basename(original_zip))[0]
                source_dir = os.path.join(extract_dir, archive_name)
                
                if not os.path.exists(source_dir):
                    logger.info(f"⚠️ 找不到对应的目录: {source_dir}")
                    continue
                    
                new_zip = original_zip + '.new'
                
                # 创建新压缩包
                cmd = ['7z', 'a', '-tzip', new_zip, os.path.join(source_dir, '*')]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    try:
                        # 默认使用回收站删除
                        send2trash(original_zip)
                        os.rename(new_zip, original_zip)
                        logger.info(f'成功更新压缩包: {original_zip}')
                    except Exception as e:
                        logger.info(f"❌ 替换压缩包失败 {original_zip}: {e}")
                else:
                    logger.info(f"❌ 创建新压缩包失败 {new_zip}: {result.stderr}")
            
            return True
        except Exception as e:
            logger.info(f"❌ 拆分压缩包时出错: {e}")
            return False
