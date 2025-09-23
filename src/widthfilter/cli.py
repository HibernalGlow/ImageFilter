"""命令行参数解析模块"""

import os
import sys
import argparse
import pyperclip
from pathlib import Path
from typing import Dict, Any, Optional, List
from rich.console import Console
from loguru import logger

from .config import load_presets, select_preset
from .logger_setup import setup_logger, init_textual_logger
from .__init__ import __version__

console = Console()

def parse_command_line() -> Dict[str, Any]:
    """解析命令行参数
    
    Returns:
        Dict[str, Any]: 配置字典
    """
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='图片宽度/高度过滤工具')
    parser.add_argument('-c', '--clipboard', action='store_true', help='从剪贴板读取源目录路径')
    parser.add_argument('-s', '--source', type=str, help='源目录路径', default=r"E:\999EHV")
    parser.add_argument('-t', '--target', type=str, help='目标目录路径', default=r"E:\1Hub\EH\7EHV")
    parser.add_argument('-w', '--width', type=int, help='宽度阈值', default=1800)
    parser.add_argument('-l', '--larger', action='store_true', help='选择大于等于指定宽度的文件')
    parser.add_argument('-m', '--move', action='store_true', help='移动文件而不是复制')
    parser.add_argument('-j', '--jobs', type=int, help='并行处理线程数', default=16)
    parser.add_argument('-n', '--number', type=int, help='符合条件的图片数量阈值', default=3)
    parser.add_argument('-i', '--interactive', action='store_true', help='启用交互式选择预设')
    parser.add_argument('-v', '--version', action='store_true', help='显示版本信息')

    args = parser.parse_args()

    # 显示版本信息
    if args.version:
        console.print(f"[bold cyan]图片宽度/高度过滤工具 v{__version__}")
        sys.exit(0)

    # 配置参数
    config = {}
    
    # 如果启用了交互式模式，或者没有提供源目录，则进入交互式模式
    if args.interactive or (len(sys.argv) <= 1):
        # 显示欢迎信息
        console.print("[bold cyan]===== 图片宽度/高度过滤工具 =====")
        console.print(f"[bold]版本: {__version__}")
        console.print("[bold]功能: 支持宽度和高度范围分组")
        console.print("[bold yellow]注意: 预设文件位于程序同目录的presets.json中[/]")
        
        # 加载预设
        presets = load_presets()
        
        # 直接选择预设，跳过管理选项
        preset_name, preset = select_preset(presets)
        
        # 移除与图像处理无关的字段，如description
        process_config = preset.copy()
        if 'description' in process_config:
            del process_config['description']
        
        config = process_config
        
        # 检查是否从剪贴板读取
        if args.clipboard:
            config["source_dir"] = pyperclip.paste().strip()
    else:
        # 使用命令行参数
        source_dir = pyperclip.paste().strip() if args.clipboard else args.source
        
        # 构建尺寸规则
        if args.larger:
            dimension_rules = [{
                "min_width": args.width, 
                "max_width": -1, 
                "min_height": -1, 
                "max_height": -1, 
                "mode": "or", 
                "folder": ""
            }]
        else:
            dimension_rules = [{
                "min_width": 0, 
                "max_width": args.width - 1, 
                "min_height": -1, 
                "max_height": -1, 
                "mode": "or", 
                "folder": ""
            }]
            
        config = {
            "source_dir": source_dir,
            "target_dir": args.target,
            "dimension_rules": dimension_rules,
            "cut_mode": args.move,
            "max_workers": args.jobs,
            "threshold_count": args.number
        }
    
    return config

def run():
    """运行主程序"""
    # 启用Windows长路径支持
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, 1)
        except Exception as e:
            console.print(f"[bold red]无法启用长路径支持: {e}")
    
    # 如果没有提供任何参数，则启用交互式模式
    if len(sys.argv) <= 1:
        sys.argv.append('--interactive')
    
    # 解析命令行参数
    config = parse_command_line()
    
    # 验证源目录路径
    if not os.path.exists(config["source_dir"]):
        console.print(f"[bold red]源目录不存在: {config['source_dir']}")
        return
    
    # 设置日志
    logger_instance, config_info = setup_logger(app_name="width_filter", console_output=False)
    
    # 初始化Textual日志
    init_textual_logger(config_info)
    
    try:
        logger.info(f"[#current_stats]开始处理 - 源: {config['source_dir']} 目标: {config['target_dir']}")
        
        # 导入图像处理器
        from .image_processor import ImageProcessor
        
        # 创建处理器并处理
        processor = ImageProcessor(**config)
        processor.process()
    except Exception as e:
        logger.exception(f"[#update_log]程序执行出错: {e}")
        console.print(f"[bold red]处理过程中出错: {e}")

if __name__ == "__main__":
    run()