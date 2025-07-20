import os
import sys
from pathlib import Path
from typing import Dict, Any, List
from imgfilter.utils.archive import ArchiveHandler
from imgfilter.core.filter import ImageFilter
from imgfilter.utils.input import InputHandler
from loguru import logger
import os
import sys
from pathlib import Path
from datetime import datetime
from renamei.core.safe_exit import setup_safe_exit

def setup_logger(app_name="app", project_root=None, console_output=True):
    """配置 Loguru 日志系统
    
    Args:
        app_name: 应用名称，用于日志目录
        project_root: 项目根目录，默认为当前文件所在目录
        console_output: 是否输出到控制台，默认为True
        
    Returns:
        tuple: (logger, config_info)
            - logger: 配置好的 logger 实例
            - config_info: 包含日志配置信息的字典
    """
    # 获取项目根目录
    if project_root is None:
        project_root = Path(__file__).parent.resolve()
    
    # 清除默认处理器
    logger.remove()
    
    # 有条件地添加控制台处理器（简洁版格式）
    if console_output:
        logger.add(
            sys.stdout,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>{elapsed}</blue> | <level>{level.icon} {level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        )
    
    # 使用 datetime 构建日志路径
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")
    hour_str = current_time.strftime("%H")
    minute_str = current_time.strftime("%M%S")
    
    # 构建日志目录和文件路径
    log_dir = os.path.join(project_root, "logs", app_name, date_str, hour_str)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{minute_str}.log")
    
    # 添加文件处理器
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {elapsed} | {level.icon} {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,     )
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

logger, config_info = setup_logger(app_name="textfilter", console_output=True)

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
        logger.error(f"处理失败: {error_msg}")
        return
        
    if results:
        logger.info("\n".join(results))
    else:
        logger.info("没有需要过滤的图片")

def main():
    # 使用InputHandler获取输入路径
    paths = InputHandler.get_input_paths(
        cli_paths=sys.argv[1:] if len(sys.argv) > 1 else None,
        use_clipboard=False,
        allow_manual=True
    )
    if not paths:
        logger.error("未提供有效的压缩包路径")
        return
    
    # 处理每个压缩包
    for archive_path in paths:
        logger.info(f"\n处理压缩包: {archive_path}")
        process_archive(archive_path)

if __name__ == '__main__':
    main()