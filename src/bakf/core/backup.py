import os
import shutil
from typing import Set, Dict, Tuple
import subprocess
import zipfile
from loguru import logger

class BackupHandler:
    """通用文件/压缩包备份与删除工具"""

    @staticmethod
    def backup_from_archive(
        zip_path: str,
        removed_files: Set[str],
        removal_reasons: Dict[str, Dict],
        trash_folder_name: str = "trash"
    ) -> Dict[str, bool]:
        """
        直接从压缩包（zip/7z）提取文件到 .trash/原因/压缩包内路径
        Args:
            zip_path: 压缩包路径
            removed_files: 压缩包内待备份文件路径集合
            removal_reasons: {压缩包内路径: {reason: 原因}}
            trash_folder_name: .trash 目录名
        Returns:
            {压缩包内路径: 是否成功}
        """
        backup_results = {}
        if not removed_files:
            return backup_results
        zip_name = os.path.splitext(os.path.basename(zip_path))[0]
        trash_dir = os.path.join(os.path.dirname(zip_path), f'{zip_name}.{trash_folder_name}')
        logger.info(f"[bakf]removal_reasons: {removal_reasons}")
        for arc_path in removed_files:
            try:
                reason = removal_reasons.get(arc_path, {}).get('reason', 'unknown')
                reason_dir = os.path.join(trash_dir, reason)
                rel_path = arc_path.replace('\\', '/').replace('/', os.sep)
                dest_path = os.path.join(reason_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                # 优先用7z
                extracted = False
                try:
                    cmd = ['7z', 'e', zip_path, arc_path, f'-o{os.path.dirname(dest_path)}', '-y']
                    result = subprocess.run(cmd, capture_output=True)
                    if result.returncode == 0 and os.path.exists(dest_path):
                        extracted = True
                except Exception as e:
                    logger.warning(f"7z提取失败: {arc_path}: {e}")
                # 7z失败则用zipfile
                if not extracted:
                    try:
                        with zipfile.ZipFile(zip_path, 'r') as zf:
                            with zf.open(arc_path) as src, open(dest_path, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
                        extracted = True
                    except Exception as e:
                        logger.error(f"[bakf]zipfile备份文件失败 {arc_path}: {e}")
                # zipfile也失败则用Bandizip
                if not extracted:
                    try:
                        # 查找bz.exe路径
                        bz_path = 'bz'  # 如果在PATH中
                        # 常见安装路径
                        common_paths = [
                            r'C:\Program Files\Bandizip\bz.exe',
                            r'C:\Program Files (x86)\Bandizip\bz.exe'
                        ]
                        for path in common_paths:
                            if os.path.exists(path):
                                bz_path = path
                                break
                                
                        bandizip_cmd = [
                            bz_path,
                            'x',  # 解压
                            f'-o:{os.path.dirname(dest_path)}',  # 输出目录
                            zip_path,  # 压缩包路径
                            arc_path  # 压缩包内文件路径
                        ]
                        result = subprocess.run(bandizip_cmd, capture_output=True)
                        if result.returncode == 0 and os.path.exists(dest_path):
                            extracted = True
                        else:
                            stderr = result.stderr.decode('utf-8', errors='ignore')
                            logger.error(f"[bakf]Bandizip提取失败 {arc_path}: {stderr}")
                    except Exception as e:
                        logger.error(f"[bakf]Bandizip备份文件失败 {arc_path}: {e}")
                backup_results[arc_path] = extracted
            except Exception as e:
                logger.error(f"[bakf]备份文件失败 {arc_path}: {e}")
                backup_results[arc_path] = False
        return backup_results

    @staticmethod
    def backup_source_file(source_path: str, max_backups: int = 5) -> Tuple[bool, str]:
        """
        在原始路径下创建带序号的备份文件（保留原始文件）
        """
        if not os.path.exists(source_path):
            return False, "源文件不存在"
        backup_path = source_path + ".bak"
        counter = 1
        while os.path.exists(backup_path) and counter <= max_backups:
            backup_path = f"{source_path}.bak{counter}"
            counter += 1
        try:
            shutil.copy2(source_path, backup_path)
            return True, backup_path
        except Exception as e:
            logger.error(f"[bakf]源文件备份失败 {source_path}: {e}")
            return False, str(e)

    @staticmethod
    def process_archive_delete(
        zip_path: str,
        to_delete: Set[str],
        removal_reasons: Dict[str, Dict],
        options: Dict = None
    ) -> Tuple[bool, str]:
        """
        备份并用7z删除压缩包内文件，无需解压，无需临时目录
        Args:
            zip_path: 压缩包路径
            to_delete: 压缩包内路径集合
            removal_reasons: {压缩包内路径: {reason: 原因}}
            options: 配置字典（如backup.enabled、trash_folder_name、force_delete等）
        Returns:
            (是否成功, 错误信息)
        """
        try:
            if not to_delete:
                logger.info("[bakf]没有需要删除的图片")
                return True, "没有需要删除的图片"
                
            # 获取选项参数
            trash_folder_name = options.get('trash_folder_name', 'trash') if options else 'trash'
            force_delete = False  # 默认即使备份失败也删除
            if options:
                if hasattr(options, '__dict__'):
                    force_delete = getattr(options.get('backup', {}), 'force_delete', True)
                else:
                    force_delete = options.get('backup', {}).get('force_delete', True)
                    
            # 备份
            backup_results = BackupHandler.backup_from_archive(
                zip_path, to_delete, removal_reasons, trash_folder_name=trash_folder_name
            )
            
            # 检查备份结果
            all_backed_up = all(backup_results.values()) if backup_results else False
            if not all_backed_up and not force_delete:
                logger.warning("[bakf]⚠️ 部分文件备份失败，根据设置取消删除操作")
                return False, "部分文件备份失败，已取消删除操作"
            elif not all_backed_up:
                logger.warning("[bakf]⚠️ 部分文件备份失败，但根据设置将继续删除")
                
            # delete.txt 路径
            delete_list_file = os.path.join(os.path.dirname(zip_path), '@delete.txt')
            with open(delete_list_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(to_delete))
                
            # 备份zip本体（可选）
            backup_enabled = False
            if options:
                if hasattr(options, '__dict__'):
                    if hasattr(options, 'backup') and hasattr(options.backup, 'enabled'):
                        backup_enabled = options.backup.enabled
                else:
                    backup_enabled = options.get('backup', {}).get('enabled', False)
            if backup_enabled:
                backup_success, backup_path = BackupHandler.backup_source_file(zip_path)
                if backup_success:
                    logger.info(f"[bakf]✅ 源文件备份成功: {backup_path}")
                else:
                    logger.warning(f"[bakf]⚠️ 源文件备份失败: {backup_path}")
                    if not force_delete:
                        return False, "源文件备份失败，已取消删除操作"
                    else:
                        logger.warning("[bakf]⚠️ 源文件备份失败，但根据设置将继续删除")
            else:
                logger.info("[bakf]ℹ️ 备份功能已禁用，跳过备份")
                
            # 用7z删除
            cmd = ['7z', 'd', zip_path, f'@{delete_list_file}']
            result = subprocess.run(cmd, capture_output=True, text=True)
            try:
                os.remove(delete_list_file)
            except Exception:
                pass
            if result.returncode != 0:
                logger.error(f"[bakf]从压缩包删除文件失败: {result.stderr}")
                return False, f"从压缩包删除文件失败: {result.stderr}"
            logger.info(f"[bakf]成功处理压缩包: {zip_path}")
            return True, ""
        except Exception as e:
            logger.error(f"[bakf]处理压缩包失败 {zip_path}: {e}")
            return False, f"处理过程出错: {str(e)}"