"""
imgu 命令行工具入口点
"""
import sys
import argparse
import logging
from pathlib import Path
from .cli import commands
from .utils.logger import setup_logger

def main():
    """执行命令行功能"""
    # 设置日志记录
    logger = setup_logger("imgu", console_output=True)
    logger.info(f"Starting imgu v{__import__('imgu').__version__}")
    
    parser = argparse.ArgumentParser(
        description="imgu - 基于 imgutils 的高级图像处理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands.setup_parser(parser)
    
    # 如果没有参数，显示帮助
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
        
    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        try:
            return args.func(args)
        except Exception as e:
            logger.error(f"执行命令时出错: {str(e)}", exc_info=True)
            return 1
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())
