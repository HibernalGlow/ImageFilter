"""URI 路径处理模块"""
from pathlib import Path
import logging
from typing import Tuple, Optional
from urllib.parse import unquote
import os


class PathURIGenerator:
    @staticmethod
    def generate(path: str) -> str:
        """
        统一生成标准化URI
        1. 普通文件路径：E:/data/image.jpg → file:///E:/data/image.jpg
        2. 压缩包内部路径：E:/data.zip!folder/image.jpg → archive:///E:/data.zip!folder/image.jpg
        """
        # 检查是否是压缩包路径(判断标准: 路径中包含.zip!或.rar!等常见压缩格式)
        archive_extensions = ['.zip!','.cbz!','.cbr!', '.rar!', '.7z!', '.tar!']
        is_archive = any(ext in path for ext in archive_extensions)
        
        if is_archive:
            # 找到最后一个压缩文件扩展名的位置
            positions = [path.find(ext) for ext in archive_extensions if ext in path]
            split_pos = max([pos + len(ext) - 1 for pos, ext in zip(positions, [ext for ext in archive_extensions if ext in path])])
            
            # 分割压缩包路径和内部路径
            archive_path = path[:split_pos]
            internal_path = path[split_pos+1:]
            
            return PathURIGenerator._generate_archive_uri(archive_path, internal_path)
        return PathURIGenerator._generate_external_uri(path)

    @staticmethod
    def _generate_external_uri(path: str) -> str:
        """处理外部文件路径"""
        # 不使用Path.as_uri()，因为它会编码特殊字符
        resolved_path = str(Path(path).resolve()).replace('\\', '/')
        return f"file:///{resolved_path}"

    @staticmethod
    def _generate_archive_uri(archive_path: str, internal_path: str) -> str:
        """
        处理压缩包内部路径
        
        支持两种情况:
        1. 普通压缩包: E:/data.zip!folder/image.jpg → archive:///E:/data.zip!folder/image.jpg
        2. 合并压缩包: E:/path/merged_1742363623326.zip!PIXIV FANBOX/2022-08-10/1.avif 
        → archive:///E:/path/PIXIV FANBOX.zip!/2022-08-10/1.avif
        """
        # 检查是否为合并压缩包格式 (merged_开头的zip)
        base_name = os.path.basename(archive_path)
        if base_name.startswith('merged_') and base_name.endswith('.zip'):
            # 处理合并压缩包
            base_dir = os.path.dirname(archive_path)
            # 获取内部路径的第一级目录作为新的压缩包名称
            parts = internal_path.replace('\\', '/').split('/', 1)
            first_level_dir = parts[0]
            remaining_path = parts[1] if len(parts) > 1 else ''
            
            # 构建新的压缩包路径和内部路径
            new_archive_path = os.path.join(base_dir, f"{first_level_dir}.zip")
            resolved_path = str(Path(new_archive_path).resolve()).replace('\\', '/')
            
            # 返回新的URI
            return f"archive:///{resolved_path}!{remaining_path}"
        
        # 普通压缩包处理
        resolved_path = str(Path(archive_path).resolve()).replace('\\', '/')
        # 仅替换反斜杠为正斜杠，不做任何编码
        normalized_internal = internal_path.replace('\\', '/')
        return f"archive:///{resolved_path}!{normalized_internal}"
    @staticmethod
    def back_to_original_path(uri: str) -> Tuple[str, Optional[str]]:
        """
        将标准化URI解析回原始路径
        格式：
        1. 普通文件：file:///E:/data/image.jpg → E:\data\image.jpg
        2. 压缩包文件：archive:///E:/data.zip!folder/image.jpg → (E:\data.zip, folder/image.jpg)
        """
        try:
            # 移除协议头并解码URL编码
            decoded_uri = unquote(uri).replace('\\', '/')
            
            if uri.startswith('file:///'):
                # 普通文件路径处理
                file_path = decoded_uri[8:]  # 去掉file:///前缀
                return Path(file_path).resolve().as_posix(), None
                
            elif uri.startswith('archive:///'):
                # 压缩包路径处理
                archive_part = decoded_uri[11:]  # 去掉archive:///前缀
                if '!' not in archive_part:
                    raise ValueError("无效的压缩包URI格式")
                
                # 直接保留原始结构
                full_path = archive_part.replace('!', os.sep)  # 将!转换为系统路径分隔符
                normalized_path = os.path.normpath(full_path)
                return (normalized_path, )

            raise ValueError("未知的URI协议类型")
            
        except Exception as e:
            logging.error(f"URI解析失败: {uri} - {str(e)}")
            return uri, None  # 返回原始URI作为降级处理




