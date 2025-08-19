import os
import shutil
from typing import Set, Dict, Tuple
import subprocess

from loguru import logger

class BackupHandler:
    """处理文件备份和删除的类"""
    
    @staticmethod
    def backup_removed_files(
        zip_path: str, 
        removed_files: Set[str], 
        removal_reasons: Dict[str, Dict],
        trash_folder_name: str = "trash",
        temp_dir: str = None  # 添加临时解压目录参数
    ) -> Dict[str, bool]:
        """
        将删除的文件备份到trash文件夹中，按删除原因分类，同时保持原始文件夹结构
        
        Args:
            zip_path: 原始压缩包路径
            removed_files: 被删除的文件集合
            removal_reasons: 文件删除原因的字典
            trash_folder_name: 垃圾箱文件夹名称
            temp_dir: 临时解压目录，用于计算相对路径
            
        Returns:
            Dict[str, bool]: 文件路径到备份是否成功的映射
        """
        backup_results = {}
        
        try:
            if not removed_files:
                return backup_results
                
            zip_name = os.path.splitext(os.path.basename(zip_path))[0]
            trash_dir = os.path.join(os.path.dirname(zip_path), f'{zip_name}.{trash_folder_name}')
            logger.info(f"[#file_ops]removal_reasons: {removal_reasons}")
            # 按删除原因分类
            for file_path in removed_files:
                try:
                    reason = removal_reasons.get(file_path, {}).get('reason', 'unknown')
                    reason_dir = os.path.join(trash_dir, reason)
                    
                    # 计算文件的相对路径以保持文件夹结构
                    if temp_dir and os.path.exists(temp_dir):
                        rel_path = os.path.relpath(file_path, temp_dir)
                    else:
                        # 如果没有提供temp_dir或不存在，则使用文件名
                        rel_path = os.path.basename(file_path)
                    
                    # 目标路径结合原始的相对路径
                    dest_path = os.path.join(reason_dir, rel_path)
                    
                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    
                    # 复制文件到对应子目录，保持原始结构
                    shutil.copy2(file_path, dest_path)
                    backup_results[file_path] = True
                    
                except Exception as e:
                    logger.error(f"[#file_ops]备份文件失败 {file_path}: {e}")
                    backup_results[file_path] = False
                    continue
                    
            return backup_results
            
        except Exception as e:
            logger.error(f"[#file_ops]备份删除文件时出错: {e}")
            return {file: False for file in removed_files}
    
    @staticmethod
    def remove_files(files_to_remove: Set[str]) -> Dict[str, bool]:
        """
        删除指定的文件
        
        Args:
            files_to_remove: 要删除的文件集合
            
        Returns:
            Dict[str, bool]: 文件路径到删除是否成功的映射
        """
        results = {}
        for file_path in files_to_remove:
            try:
                os.remove(file_path)
                results[file_path] = True
            except Exception as e:
                logger.error(f"[#file_ops]删除文件失败 {file_path}: {e}")
                results[file_path] = False
        return results 

    @staticmethod
    def backup_source_file(source_path: str, max_backups: int = 5) -> Tuple[bool, str]:
        """
        在原始路径下创建带序号的备份文件（保留原始文件）
        例如：file.zip -> file.zip.bak, file.zip.bak1, ...
        
        Args:
            source_path: 原始文件路径
            max_backups: 最大备份数量
        Returns:
            (是否成功, 备份路径)
        """
        if not os.path.exists(source_path):
            return False, "源文件不存在"

        backup_path = source_path + ".bak"
        counter = 1
        
        # 查找可用的备份文件名
        while os.path.exists(backup_path) and counter <= max_backups:
            backup_path = f"{source_path}.bak{counter}"
            counter += 1

        try:
            shutil.copy2(source_path, backup_path)
            return True, backup_path
        except Exception as e:
            logger.error(f"[#file_ops]源文件备份失败 {source_path}: {e}")
            return False, str(e) 

    @staticmethod
    def process_archive_delete(zip_path: str, to_delete: Set[str], removal_reasons: Dict[str, Dict], extract_dir: str, config: Dict = None) -> Tuple[bool, str]:
        """
        处理压缩包文件的删除和备份
        
        Args:
            zip_path: 压缩包路径
            to_delete: 要删除的文件集合
            removal_reasons: 删除原因字典
            extract_dir: 临时解压目录
            config: 配置字典，包含backup.enabled等配置项
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        try:
            if not to_delete:
                logger.info("[#sys_log]没有需要删除的图片")
                return True, "没有需要删除的图片"
                
            # 备份要删除的文件，传入临时解压目录以保持结构
            backup_results = BackupHandler.backup_removed_files(
                zip_path, to_delete, removal_reasons, temp_dir=extract_dir
            )
            
            # 从压缩包中删除文件
            files_to_delete = [os.path.relpath(file_path, extract_dir) for file_path in to_delete]
            
            # 使用7z删除文件
            delete_list_file = os.path.join(extract_dir, '@delete.txt')
            with open(delete_list_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(files_to_delete))
            
            # 在执行删除操作前备份原始压缩包
            backup_enabled = False
            if config:
                # 检查config是否为Namespace对象
                if hasattr(config, '__dict__'):  # Namespace对象通常有__dict__属性
                    # 使用hasattr和getattr来从Namespace对象获取值
                    if hasattr(config, 'backup') and hasattr(config.backup, 'enabled'):
                        backup_enabled = config.backup.enabled
                else:
                    # 作为字典处理
                    backup_enabled = config.get('backup', {}).get('enabled', False)
                    
            if backup_enabled:
                backup_success, backup_path = BackupHandler.backup_source_file(zip_path)
                if backup_success:
                    logger.info(f"[#sys_log]✅ 源文件备份成功: {backup_path}")
                else:
                    logger.warning(f"[#sys_log]⚠️ 源文件备份失败: {backup_path}")
                    return False, "源文件备份失败"
            else:
                logger.info("[#sys_log]ℹ️ 备份功能已禁用，跳过备份")

            # 使用7z删除文件
            cmd = ['7z', 'd', zip_path, f'@{delete_list_file}']
            result = subprocess.run(cmd, capture_output=True, text=True)
            os.remove(delete_list_file)
            
            if result.returncode != 0:
                logger.error(f"[#sys_log]从压缩包删除文件失败: {result.stderr}")
                return False, f"从压缩包删除文件失败: {result.stderr}"
                
            logger.info(f"[#file_ops]成功处理压缩包: {zip_path}")
            return True, ""
            
        except Exception as e:
            logger.error(f"[#sys_log]处理压缩包失败 {zip_path}: {e}")
            return False, f"处理过程出错: {str(e)}"