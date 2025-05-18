import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional
from common.archive import ArchiveHandler,SUPPORTED_ARCHIVE_FORMATS
from common.input import InputHandler
from textual_preset import create_config_app
from .utils.merge import ArchiveMerger
from textual_logger import TextualLoggerManager
import shutil
import time
import logging
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
from send2trash import send2trash
# 配置日志
from loguru import logger
import os
import sys
from pathlib import Path
from datetime import datetime

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
    )
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

logger, config_info = setup_logger(app_name="batch_img_filter", console_output=False)


# TextualLogger布局配置
TEXTUAL_LAYOUT = {
    "cur_stats": {
        "ratio": 1,
        "title": "📊 总体进度",
        "style": "lightyellow"
    },
    "cur_progress": {
        "ratio": 1,
        "title": "🔄 当前进度",
        "style": "lightcyan"
    },
    "file_ops": {
        "ratio": 2,
        "title": "📂 文件操作",
        "style": "lightpink"
    },
    "hash_calc": {
        "ratio": 2,
        "title": "🔢 哈希计算",
        "style": "lightblue"
    },
    "update_log": {
        "ratio": 1,
        "title": "🔧 系统消息",
        "style": "lightwhite"
    }
}

# 初始化TextualLogger
HAS_TUI = True

# 常量定义
DEFAULT_MIN_SIZE = 631
DEFAULT_HAMMING_DISTANCE = 12

def initialize_textual_logger():
    """初始化日志布局，确保在所有模式下都能正确初始化"""
    try:
        TextualLoggerManager.set_layout(TEXTUAL_LAYOUT, config_info['log_file'])
        logger.info("[#update_log]✅ 日志系统初始化完成")
    except Exception as e:
        print(f"❌ 日志系统初始化失败: {e}")
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

class FilterConfig:
    """过滤配置管理类"""
    
    @staticmethod
    def create_parser() -> argparse.ArgumentParser:
        """创建命令行参数解析器"""
        parser = argparse.ArgumentParser(description='批量图片过滤工具')
        parser.add_argument('--min_size', type=int, 
                        help=f'最小图片尺寸(像素)')
        parser.add_argument('--enable_small_filter', action='store_true',
                        help='启用小图过滤')
        parser.add_argument('--enable_grayscale_filter', action='store_true',
                        help='启用黑白图过滤')
        parser.add_argument('--enable_duplicate_filter', action='store_true',
                        help='启用重复图片过滤')
        parser.add_argument('--enable_text_filter', action='store_true',
                        help='启用纯文本图片过滤')
        parser.add_argument('--merge_archives', action='store_true',
                        help='启用压缩包合并处理')
        parser.add_argument('--ref_hamming_threshold', type=int, 
                        help=f'内部去重的汉明距离阈值 ')
        parser.add_argument('--duplicate_filter_mode', type=str, default='quality',
                        choices=['quality', 'watermark', 'hash'],
                        help='重复图片过滤模式 (quality, watermark 或 hash)')
        parser.add_argument('--hash_file', type=str,
                        help='哈希文件路径')
        parser.add_argument('--max_workers', type=int,
                        help='最大工作线程数')
        parser.add_argument('--clipboard', '-c', action='store_true',
                        help='从剪贴板读取路径')
        parser.add_argument('paths', nargs='*', help='输入路径')
        return parser
    
    @staticmethod
    def build_filter_params(args) -> Dict[str, Any]:
        """从命令行参数构建过滤参数字典"""
        params = {
            'min_size': args.min_size,
            'enable_small_filter': args.enable_small_filter,
            'enable_grayscale_filter': args.enable_grayscale_filter,
            'enable_duplicate_filter': args.enable_duplicate_filter,
            'enable_text_filter': args.enable_text_filter,
            'duplicate_filter_mode': args.duplicate_filter_mode,
            'merge_archives': args.merge_archives,
            # 注意这里的参数名保持与ImageFilter一致
            'ref_hamming_threshold': args.ref_hamming_threshold,
            'hash_file': args.hash_file,
            'max_workers': args.max_workers if args.max_workers else os.cpu_count() * 2,  # 默认CPU核心数2倍
            'config': args  # 保留原始参数对象以兼容现有代码
        }
        
        # 处理水印关键词列表
        # if hasattr(args, 'watermark_keywords') and args.watermark_keywords:
        #     params['watermark_keywords'] = [kw.strip() for kw in args.watermark_keywords.split(',')]
            
        return params
    
    @staticmethod
    def get_preset_configs() -> Dict[str, Dict[str, Any]]:
        """获取预设配置"""
        return {
            "去小图": {
                "description": "仅去除小尺寸图片",
                "checkbox_options": ["enable_small_filter", "clipboard"],
                "input_values": {
                    "min_size": str(DEFAULT_MIN_SIZE) 
                }
            },
            "去重复": {
                "description": "仅去除重复图片",
                "checkbox_options": ["enable_duplicate_filter", "clipboard"],
                "input_values": {
                    "ref_hamming_threshold": str(DEFAULT_HAMMING_DISTANCE),
                    "duplicate_filter_mode": "quality"
                }
            },
            "去水印图": {
                "description": "去除带水印的图片",
                "checkbox_options": ["enable_duplicate_filter", "clipboard"],
                "input_values": {
                    "ref_hamming_threshold": str(DEFAULT_HAMMING_DISTANCE),
                    "duplicate_filter_mode": "watermark",
                }
            },
            "去黑白": {
                "description": "仅去除黑白/白图",
                "checkbox_options": ["enable_grayscale_filter", "clipboard"],
            },
            "哈希比对": {
                "description": "使用哈希文件比对去重",
                "checkbox_options": ["enable_duplicate_filter", "clipboard"],
                "input_values": {
                    "duplicate_filter_mode": "hash",
                    "hash_file": "",
                    "ref_hamming_threshold": str(DEFAULT_HAMMING_DISTANCE)
                }
            },
            "合并": {
                "description": "合并多个压缩包并处理",
                "checkbox_options": ["merge_archives", "enable_duplicate_filter","clipboard"],
                "input_values": {
                    "duplicate_filter_mode": "quality",
                    "ref_hamming_threshold": str(1)
                }
            },
            "完整过滤": {
                "description": "完整过滤(去重+去小图+去黑白+去文本)",
                "checkbox_options": ["merge_archives", "enable_small_filter", "enable_duplicate_filter", "enable_grayscale_filter", "clipboard"],
                "input_values": {
                    "min_size": str(DEFAULT_MIN_SIZE),
                    "ref_hamming_threshold": str(DEFAULT_HAMMING_DISTANCE),
                    "duplicate_filter_mode": "quality",
                }
            }
        }
class FilterProcessor:
    """过滤处理类"""
    
    @staticmethod
    def process_group(paths: Set[str], filter_params: Dict[str, Any]) -> bool:
        """处理单个路径组
        
        Args:
            paths: 路径集合
            filter_params: 过滤参数
            
        Returns:
            bool: 处理是否成功
        """
        # 检查是否启用合并模式
        if filter_params.get('merge_archives', False):
            # 合并模式处理
            return FilterProcessor._process_with_merge(paths, filter_params)
        else:
            # 单独处理模式
            return FilterProcessor._process_individually(paths, filter_params)
    
    @staticmethod
    def _process_with_merge(paths: Set[str], filter_params: Dict[str, Any]) -> bool:
        """合并模式处理多个压缩包
        
        Args:
            paths: 路径集合
            filter_params: 过滤参数
            
        Returns:
            bool: 处理是否成功
        """
        import shutil
        
        # 创建图片过滤器和压缩包处理器实例
        archive_handler = ArchiveHandler()
        archive_merger = ArchiveMerger()
        
        logger.info("[#update_log]启用合并模式处理多个压缩包")
        # 将paths转换为列表
        paths_list = list(paths)
        
        # 合并压缩包
        temp_dir, merged_zip, original_archives = archive_merger.merge_archives(paths_list)
        
        if not temp_dir or not merged_zip:
            logger.error("[#update_log]压缩包合并失败，将回退到单独处理模式")
            return FilterProcessor._process_individually(paths, filter_params)
            
        try:
            # 处理合并后的压缩包
            logger.info(f"[#cur_progress]处理合并压缩包: {merged_zip}")
            success, error_msg, results = archive_handler.process_archive(merged_zip, filter_params)
            
            if not success:
                logger.error(f'[#update_log]处理合并压缩包失败: {error_msg}')
                return False
                
            # 拆分处理后的压缩包回原始压缩包
            logger.info(f"[#cur_progress]正在拆分处理后的压缩包...")
            split_success = archive_merger.split_merged_archive(
                merged_zip, original_archives, temp_dir, filter_params
            )
            
            if not split_success:
                logger.error("[#update_log]拆分合并压缩包失败")
                return False
                
            logger.info("[#cur_stats]合并处理模式完成")
            for result in results:
                logger.info(f"[#file_ops]{result}")
                
            return True
            
        except Exception as e:
            logger.error(f"[#update_log]合并模式处理出错: {e}")
            return False
            
        finally:
            # 清理临时文件
            try:
                if os.path.exists(merged_zip):
                    os.remove(merged_zip)
                    logger.info(f"[#file_ops]已删除临时压缩包: {merged_zip}")
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    logger.info(f"[#file_ops]已删除临时目录: {temp_dir}")
            except Exception as e:
                logger.error(f"[#update_log]清理临时文件失败: {e}")
    
    @staticmethod
    def _process_individually(paths: Set[str], filter_params: Dict[str, Any]) -> bool:
        """单独处理每个路径
        
        Args:
            paths: 路径集合
            filter_params: 过滤参数
            
        Returns:
            bool: 处理是否成功
        """
        # 创建图片过滤器和压缩包处理器实例
        archive_handler = ArchiveHandler()
        
        # 处理结果收集
        all_results = []
        process_failed = False
        
        # 统计总数
        total_paths = len(paths)
        completed = 0

        # 处理每个路径（此时paths已经是压缩包路径，不再需要目录遍历）
        for path in paths:
            completed += 1
            progress_percent = int((completed / total_paths) * 100)
            logger.info(f"[@cur_stats]处理进度 ({completed}/{total_paths}) {progress_percent}%")
            logger.info(f"[#cur_progress]处理: {path}")
            
            # 由于路径已经是压缩包文件路径，直接调用process_archive
            if Path(path).is_file() and Path(path).suffix.lower() in SUPPORTED_ARCHIVE_FORMATS:
                success, error_msg, results = archive_handler.process_archive(path, filter_params)
            else:
                # 对于不符合条件的路径，使用原来的process_directory处理
                success, error_msg, results = archive_handler.process_directory(path, filter_params)
            
            if not success:
                logger.error(f'[#update_log]处理失败 {path}: {error_msg}')
                process_failed = True
            else:
                for result in results:
                    logger.info(f"[#file_ops]{result}")
                all_results.extend(results)
                
        return not process_failed    
    @staticmethod
    def merge_results(paths: Set[str], results: List) -> bool:
        """合并处理结果
        
        Args:
            paths: 源路径集合
            results: 处理结果
            
        Returns:
            bool: 合并是否成功
        """
        merger = ArchiveMerger()
        try:
            # 选择保存目录(单个目录或第一个压缩包所在目录)
            save_dir = next(iter(paths))
            if len(paths) > 1:
                # 使用第一个压缩包所在的目录
                save_dir = os.path.dirname(save_dir)
                
            merger.merge_archives(results, save_dir)
            logger.info(f"[#file_ops]合并处理完成，结果保存在: {save_dir}")
            return True
        except Exception as e:
            logger.error(f"[#update_log]合并处理失败: {str(e)}")
            return False

class Application:
    """批量图片过滤工具应用类"""
    
    def __init__(self):
        """初始化应用"""
        # 添加父目录到Python路径
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        # 初始化TextualLogger
    
    def process_with_args(self, args) -> bool:
        """处理命令行参数
        
        Args:
            args: 命令行参数
            
        Returns:
            bool: 处理是否成功
        """

        # 获取输入路径
        paths = InputHandler.get_input_paths(
            cli_paths=args.paths,
            use_clipboard=args.clipboard,
            allow_manual=True
        )
        if not paths:
            logger.error('[#update_log]未提供任何输入路径')
            return False
        
        if HAS_TUI:
            initialize_textual_logger()
        # 构建过滤参数字典
        filter_params = FilterConfig.build_filter_params(args)

        # 将路径分组处理
        path_groups = InputHandler.group_input_paths(paths)
        overall_success = True
        
        # 添加总体进度统计
        total_groups = len(path_groups)
        
        for i, group in enumerate(path_groups):
            group_progress = int(((i + 1) / total_groups) * 100)
            logger.info(f"[@cur_stats]路径组处理 ({i+1}/{total_groups}) {group_progress}%")
            logger.info(f"[#cur_progress]处理路径组 {i+1}/{total_groups}: {group}")
            success = FilterProcessor.process_group(group, filter_params)
            overall_success = overall_success and success
            
        # 处理完成提示
        if overall_success:
            logger.info("[#update_log]✅ 所有处理任务已完成")
        else:
            logger.info("[#update_log]⚠️ 处理完成，但有部分任务失败")
            
        return overall_success
    
    def run_tui_mode(self):
        """运行TUI界面模式"""
        parser = FilterConfig.create_parser()
        preset_configs = FilterConfig.get_preset_configs()

        def on_run(params: dict):
            """TUI配置界面的回调函数"""
            # 将TUI参数转换为命令行参数格式
            sys.argv = [sys.argv[0]]
            
            # 添加选中的复选框选项
            for arg, enabled in params['options'].items():
                if enabled:
                    sys.argv.append(arg)
                    
            # 添加输入框的值
            for arg, value in params['inputs'].items():
                if value.strip():
                    sys.argv.append(arg)
                    sys.argv.append(value)
            
            # 使用全局的 parser 解析参数
            args = parser.parse_args()
            self.process_with_args(args)

        # 创建配置界面
        app = create_config_app(
            program=__file__,
            parser=parser,
            title="图片过滤工具",
            preset_configs=preset_configs,
            # on_run=on_run
            # on_run=False
        )
        
        # 运行配置界面
        app.run()
    
    def main(self) -> int:
        """主函数入口
        
        Returns:
            int: 退出代码(0=成功)
        """
        try:
            parser = FilterConfig.create_parser()
            
            # 命令行模式处理
            if len(sys.argv) > 1:
                args = parser.parse_args()
                success = self.process_with_args(args)
                return 0 if success else 1
                
            # TUI模式处理
            else:
                self.run_tui_mode()
                return 0
                
        except Exception as e:
            logger.exception(f"[#update_log]错误信息: {e}")
            return 1

# 主程序入口
if __name__ == '__main__':
    app = Application()
    sys.exit(app.main())