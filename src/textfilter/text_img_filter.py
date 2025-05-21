import os
import sys
from pathlib import Path
from typing import Dict, Any, List
from imgfilter.utils.archive import ArchiveHandler
from imgfilter.core.filter import ImageFilter
from imgfilter.utils.input import InputHandler

def process_archive(archive_path: str, filter_params: Dict[str, Any] = None) -> None:
    """处理单个压缩包
    
    Args:
        archive_path: 压缩包路径
        filter_params: 过滤参数
    """
    # 创建图片过滤器实例
    
    # 创建压缩包处理器实例
    
    # 创建压缩包处理器实例
    processor = ArchiveHandler()
    
    # 处理压缩包
    success, error_msg, results = processor.process_directory(
        archive_path,
        filter_params={
            'enable_text_filter': True,  # 启用文本过滤
            **(filter_params or {})
        }
    )
    
    # 输出处理结果
    if not success:
        print(f"处理失败: {error_msg}")
        return
        
    if results:
        print("\n".join(results))
    else:
        print("没有需要过滤的图片")

def main():
    # 使用InputHandler获取输入路径
    paths = InputHandler.get_input_paths(
        cli_paths=sys.argv[1:] if len(sys.argv) > 1 else None,
        use_clipboard=False,
        allow_manual=True
    )
    if not paths:
        print("未提供有效的压缩包路径")
        return
    
    # 处理每个压缩包
    for archive_path in paths:
        print(f"\n处理压缩包: {archive_path}")
        process_archive(archive_path)

if __name__ == '__main__':
    main()