import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional
from imgfilter.utils.archive import ArchiveHandler,SUPPORTED_ARCHIVE_FORMATS
from imgfilter.utils.input import InputHandler
# from textual_preset import create_config_app  # 已移除，使用 lata + Taskfile 替代
from batchfilter.utils.merge import ArchiveMerger
from textual_logger import TextualLoggerManager
import shutil
import time
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
from send2trash import send2trash
# 配置日志
from loguru import logger
from datetime import datetime
from batchfilter.config_manager import ConfigManager
from loguru import logger

# 创建配置管理器实例
config_manager = ConfigManager()

def initialize_textual_logger():
    """初始化日志布局，确保在所有模式下都能正确初始化"""
    try:
        if not config_manager.logger_config or 'log_file' not in config_manager.logger_config:
            logger.error("无法初始化TextualLogger: 日志文件路径未配置")
            return
            
        TextualLoggerManager.set_layout(config_manager.textual_layout, config_manager.logger_config['log_file'])
        logger.info("[#update_log]✅ 日志系统初始化完成")
    except Exception as e:
        logger.error(f"❌ 日志系统初始化失败: {e}")

class ArchiveMerger:
    """压缩包合并处理类"""
    
    @staticmethod
    def merge_archives(paths: List[str], blacklist_keywords=None) -> Tuple[Optional[str], Optional[str], List[str]]:
        """
        将多个压缩包合并为一个临时压缩包
        
        Args:
            paths: 压缩包路径列表
            blacklist_keywords: 黑名单关键词列表
            
        Returns:
            Tuple[str, str, List[str]]: (临时目录路径, 合并后的压缩包路径, 原始压缩包路径列表)
            如果失败则返回 (None, None, [])
            如果只有一个压缩包，则返回 (None, 原始压缩包路径, [原始压缩包路径])
        """
        # 如果未提供黑名单关键词，则使用配置管理器中的默认值
        if blacklist_keywords is None:
            blacklist_keywords = config_manager.blacklist_keywords
            
        temp_dir = None
        try:
            # 收集所有ZIP文件路径，同时排除黑名单中的关键词
            archive_paths = []
            for path in paths:
                # 检查路径是否包含黑名单关键词
                if any(keyword in path for keyword in blacklist_keywords):
                    logger.info(f"[#file_ops]跳过黑名单文件: {path}")
                    continue
                    
                if os.path.isdir(path):
                    for root, _, files in os.walk(path):
                        for f in files:
                            file_path = os.path.join(root, f)
                            # 检查文件是否是zip并且不在黑名单中
                            if f.lower().endswith('.zip') and not any(keyword in f for keyword in blacklist_keywords):
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
                        choices=['quality', 'watermark', 'hash', 'lpips'],
                        help='重复图片过滤模式 (quality, watermark, hash 或 lpips)')
        parser.add_argument('--hash_file', type=str,
                        help='哈希文件路径')
        parser.add_argument('--max_workers', type=int,
                        help='最大工作线程数')
        parser.add_argument('--lpips_threshold', type=float, default=config_manager.default_lpips_threshold,
                        help=f'LPIPS相似度阈值 (0.0-1.0)，值越小检测越严格')
        parser.add_argument('--clipboard', '-c', action='store_true',
                        help='从剪贴板读取路径')
        parser.add_argument('--path', '-p', action='append', 
                        help='指定输入路径，可多次使用此参数以指定多个路径')
        parser.add_argument('--notui', action='store_true',
                        help='禁用TUI界面，使用简单的控制台输出')
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
            'lpips_threshold': args.lpips_threshold,  # 添加LPIPS阈值
            'config': args  # 保留原始参数对象以兼容现有代码
        }
        
        # 处理水印关键词列表
        # if hasattr(args, 'watermark_keywords') and args.watermark_keywords:
        #     params['watermark_keywords'] = [kw.strip() for kw in args.watermark_keywords.split(',')]
            
        return params

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
    
    def process_with_args(self, args) -> bool:
        """处理命令行参数
        
        Args:
            args: 命令行参数
            
        Returns:
            bool: 处理是否成功
        """
        # 设置日志系统，根据命令行参数决定是否使用TUI
        use_tui = not args.notui
        config_manager.setup_logger(app_name="batch_img_filter", use_tui=use_tui, force_console=not use_tui)
        
        # 获取输入路径 (合并 paths 和 path 参数)
        cli_paths = args.paths
        if hasattr(args, 'path') and args.path:
            if cli_paths:
                cli_paths.extend(args.path)
            else:
                cli_paths = args.path
            
        paths = InputHandler.get_input_paths(
            cli_paths=cli_paths,
            use_clipboard=args.clipboard,
            allow_manual=True
        )
        if not paths:
            logger.error('[#update_log]未提供任何输入路径')
            return False
        if use_tui:
            # 使用TUI模式，初始化TextualLogger
            initialize_textual_logger()
        else:
            # 非TUI模式，输出提示
            logger.info("已启用控制台输出模式")

        # 构建过滤参数字典
        filter_params = FilterConfig.build_filter_params(args)
        
        # 日志记录参数
        logger.info(f"[#update_log]使用参数: duplicate_filter_mode={filter_params['duplicate_filter_mode']}, " +
                   f"lpips_threshold={filter_params['lpips_threshold']}")

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
        preset_configs = config_manager.get_preset_configs()

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
                    # 特殊处理 --path 参数，允许多个路径（用逗号分隔）
                    if arg == '--path':
                        for path in value.split(','):
                            path = path.strip()
                            if path:
                                sys.argv.append(arg)
                                sys.argv.append(path)
                    else:
                        sys.argv.append(arg)
                        sys.argv.append(value)
            
            # 使用全局的 parser 解析参数
            args = parser.parse_args()
            self.process_with_args(args)

        # 创建配置界面 - 尝试启动 lata
        try:
            script_dir = Path(__file__).parent
            result = subprocess.run("lata", cwd=script_dir)
            if result.returncode == 0:
                return
        except FileNotFoundError:
            print("\n图片过滤工具")
            print("=" * 50)
            print("未找到 'lata' 命令。请使用以下方式之一:\n")
            print("  1. 安装 lata: pip install lata")
            print("     然后运行: lata")
            print("\n  2. 使用命令行参数运行")
            print("     例如: batchfilter --help")
            print("\n  3. 直接使用 task 命令")
            print("     例如: task remove-small")
            print("=" * 50)
        except Exception as e:
            logger.error(f"启动 lata 失败: {e}")
    
    def run(self) -> int:
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
                
            # TUI模式处理 - 启动 lata 交互式任务选择器
            else:
                try:
                    script_dir = Path(__file__).parent
                    result = subprocess.run("lata", cwd=script_dir)
                    return result.returncode
                except FileNotFoundError:
                    print("\n图片过滤工具")
                    print("=" * 50)
                    print("未找到 'lata' 命令，请先安装: pip install lata")
                    print("\n或使用以下方式:")
                    print("  1. 使用命令行参数: batchfilter --help")
                    print("  2. 直接运行 task: task remove-small")
                    print("=" * 50)
                    return 1
                except Exception as e:
                    logger.error(f"启动 lata 失败: {e}")
                    return 1
                
        except Exception as e:
            # 确保异常也能正确记录到日志
            try:
                logger.exception(f"[#update_log]错误信息: {e}")
            except:
                # 如果logger未初始化，则直接输出到控制台
                print(f"错误信息: {e}")
            return 1

# 主程序入口
def main():
    app = Application()
    sys.exit(app.run())

if __name__ == '__main__':
    main()