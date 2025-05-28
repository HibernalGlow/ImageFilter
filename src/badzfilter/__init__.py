"""
BadZipfilter 包 - 用于检查压缩文件的完整性

此包提供了检查压缩文件是否损坏的功能，并可以将损坏的文件重命名
"""

__version__ = "0.1.0"

# 导出主要功能
from .__main__ import  run_check
from .archive_checker import check_archive, process_directory, get_archive_files

# 导出为公共 API
__all__ = [
    "run_check",         # 主函数入口
    "check_archive",     # 检查单个压缩文件
    "process_directory", # 处理整个目录
    "get_archive_files"  # 获取压缩文件列表
]