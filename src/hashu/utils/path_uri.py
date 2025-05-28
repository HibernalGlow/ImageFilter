"""URI 路径处理模块"""
from pathlib import Path
from typing import Tuple, Optional, Dict
from urllib.parse import unquote
import os
from loguru import logger

class URIParser:
    """URI解析工具类"""
    
    @staticmethod
    def parse_uri(uri: str) -> Dict[str, Optional[str]]:
        """
        解析URI获取详细信息
        
        Args:
            uri: 标准化的URI
            
        Returns:
            Dict: 包含文件名、格式、去掉格式的URL、压缩包名等信息
        """
        try:
            result = {
                'filename': None,
                'file_format': None,
                'uri_without_format': None,
                'archive_name': None
            }
            
            if uri.startswith('file:///'):
                # 普通文件处理
                file_path = unquote(uri[8:])  # 去掉file:///前缀
                path_obj = Path(file_path)
                
                result['filename'] = path_obj.name
                result['file_format'] = path_obj.suffix.lower().lstrip('.')
                # 去掉格式的URL：移除文件扩展名
                if result['file_format']:
                    base_path = str(path_obj.with_suffix(''))
                    result['uri_without_format'] = f"file:///{base_path}"
                else:
                    result['uri_without_format'] = uri
                    
            elif uri.startswith('archive://'):
                # 压缩包文件处理 - 支持两种格式
                # 确定前缀长度 (archive:// 或 archive:///)
                prefix_length = 10  # 默认为 archive://
                if uri.startswith('archive:///'):
                    prefix_length = 11  # archive:///
                
                archive_part = unquote(uri[prefix_length:])  # 去掉前缀
                
                # 处理分隔符 (! 或 !/)
                if '!/' in archive_part:
                    archive_path, internal_path = archive_part.split('!/', 1)
                elif '!' in archive_part:
                    archive_path, internal_path = archive_part.split('!', 1)
                    # 如果internal_path不以/开头，添加一个/以保持一致性
                    if internal_path and not internal_path.startswith('/'):
                        internal_path = '/' + internal_path
                else:
                    # 没有内部路径的情况
                    archive_path = archive_part
                    internal_path = ''
                
                # 压缩包名
                result['archive_name'] = Path(archive_path).name
                
                # 内部文件信息
                if internal_path:
                    internal_obj = Path(internal_path)
                    result['filename'] = internal_obj.name
                    result['file_format'] = internal_obj.suffix.lower().lstrip('.')
                    
                    # 去掉格式的URL：移除内部文件扩展名
                    if result['file_format']:
                        base_internal = str(internal_obj.with_suffix(''))
                        # 使用与输入URI相同的格式
                        prefix = uri[:prefix_length]
                        separator = '!/' if '!/' in uri else '!'
                        result['uri_without_format'] = f"{prefix}{archive_path}{separator}{base_internal}"
                    else:
                        result['uri_without_format'] = uri
                else:
                    result['uri_without_format'] = uri
                    
            return result
            
        except Exception as e:
            logger.warning(f"URI解析失败 {uri}: {e}")
            return {
                'filename': None,
                'file_format': None,
                'uri_without_format': uri,  # 降级返回原URI
                'archive_name': None
            }

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
        
        注意: 使用统一的格式 archive:///path!internal_path
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
            
            # 返回新的URI (使用统一格式 archive:///path!internal_path)
            return f"archive:///{resolved_path}!{remaining_path}"
        
        # 普通压缩包处理
        resolved_path = str(Path(archive_path).resolve()).replace('\\', '/')
        # 仅替换反斜杠为正斜杠，不做任何编码
        normalized_internal = internal_path.replace('\\', '/')
        
        # 使用统一的格式 archive:///path!internal_path (无斜杠分隔)
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
                
            elif uri.startswith('archive://'):
                # 压缩包路径处理 - 支持两种格式
                # 确定前缀长度 (archive:// 或 archive:///)
                prefix_length = 10  # 默认为 archive://
                if uri.startswith('archive:///'):
                    prefix_length = 11  # archive:///
                
                archive_part = decoded_uri[prefix_length:]  # 去掉前缀
                
                if '!' not in archive_part:
                    raise ValueError("无效的压缩包URI格式")
                
                # 处理分隔符 (! 或 !/)
                if '!/' in archive_part:
                    archive_path, internal_path = archive_part.split('!/', 1)
                else:
                    archive_path, internal_path = archive_part.split('!', 1)
                
                # 直接保留原始结构
                full_path = f"{archive_path}{os.sep}{internal_path}"  # 将!转换为系统路径分隔符
                normalized_path = os.path.normpath(full_path)
                return (normalized_path, )

            raise ValueError("未知的URI协议类型")
            
        except Exception as e:
            logger.error(f"URI解析失败: {uri} - {str(e)}")
            return uri, None  # 返回原始URI作为降级处理




