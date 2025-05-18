import os
import logging
from pathlib import Path
from PIL import Image, ImageFile
import shutil
from tqdm import tqdm
import pillow_avif
import pillow_jxl
import zipfile
import io
from concurrent.futures import ThreadPoolExecutor
import sys
import warnings
import subprocess
import argparse
import pyperclip

# 基础设置
warnings.filterwarnings('ignore', category=Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS = None
ImageFile.LOAD_TRUNCATED_IMAGES = True

# 加载环境变量
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

logger, config_info = setup_logger(app_name="width_filter", console_output=False)

# 导入正确路径的日志记录器配置
from textual_logger import TextualLoggerManager

# 设置Textual日志界面布局
TEXTUAL_LAYOUT = {
    "current_stats": {"ratio": 2, "title": "📊 总体进度", "style": "lightyellow"},
    "current_progress": {"ratio": 2, "title": "🔄 当前处理", "style": "lightcyan"},
    "process_log": {"ratio": 3, "title": "📝 处理日志", "style": "lightgreen"},
    "update_log": {"ratio": 2, "title": "ℹ️ 更新日志", "style": "lightblue"}
}


# 创建全局日志记录器


def init_TextualLogger():
    TextualLoggerManager.set_layout(TEXTUAL_LAYOUT, config_info['log_file'])
    
    

class ImageProcessor:
    def __init__(self, source_dir, target_dir, min_width=1800, cut_mode=False, max_workers=16, 
                 compare_larger=False, threshold_count=1):
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.min_width = min_width
        self.cut_mode = cut_mode
        self.max_workers = max_workers
        self.compare_larger = compare_larger
        self.threshold_count = threshold_count
        self.logger = logger  # 使用全局logger
        
        # 添加排除关键词列表
        self.exclude_paths = [
            '画集', '日原版', 'pixiv', '图集', '作品集', 'FANTIA', 'cg', 'multi', 'trash', '小说', 'cg'
        ]
        # 将所有排除路径转换为小写，并确保是独立的词
        self.exclude_paths = [path.lower().strip() for path in self.exclude_paths]
        # 添加需要排除的文件格式
        # self.exclude_formats = { '.gif', '.mp4', '.webm', '.mkv', '.mov'}
        self.exclude_formats = {'.avif', '.jxl', '.gif', '.mp4', '.webm', '.mkv', '.mov'}
        # 添加7z路径
        self.seven_zip_path = r"C:\Program Files\7-Zip\7z.exe"
        init_TextualLogger()

        # 记录初始化信息到Textual日志
        self.logger.info(f"[#current_stats]初始化处理器 - 模式: {'大于等于' if self.compare_larger else '小于'} {self.min_width}px, 动作: {'移动' if self.cut_mode else '复制'}")

    def should_exclude_path(self, path_str):
        """检查路径是否应该被排除"""
        path_str = path_str.lower()
        path_parts = path_str.replace('\\', '/').split('/')
        
        # 检查路径的每一部分
        for part in path_parts:
            # 移除常见的分隔符
            clean_part = part.replace('-', ' ').replace('_', ' ').replace('.', ' ')
            words = set(clean_part.split())
            
            # 检查每个排除关键词
            for keyword in self.exclude_paths:
                # 如果关键词作为独立的词出现
                if keyword in words:
                    self.logger.info(f"[#update_log]排除文件 {path_str} 因为包含关键词: {keyword}")
                    return True
                # 或者作为路径的一部分完整出现
                if keyword in part:
                    self.logger.info(f"[#update_log]排除文件 {path_str} 因为包含关键词: {keyword}")
                    return True
        return False

    def get_image_width_from_zip(self, zip_file, image_path):
        try:
            with zip_file.open(image_path) as file:
                img_data = io.BytesIO(file.read())
                with Image.open(img_data) as img:
                    return img.size[0]
        except Exception as e:
            self.logger.error(f"[#update_log]读取图片出错 {image_path}: {str(e)}")
            return 0

    def get_zip_images_info(self, zip_path):
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                image_files = [f for f in zf.namelist() if f.lower().endswith(
                    ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.avif', '.jxl'))]
                
                if not image_files:
                    self.logger.warning(f"[#update_log]ZIP文件 {zip_path} 中没有找到图片")
                    return 0, 0
                
                # 改进的抽样算法
                image_files.sort()  # 确保文件顺序一致
                total_images = len(image_files)
                
                # 计算抽样间隔
                sample_size = min(20, total_images)  # 最多抽样20张图片
                if total_images <= sample_size:
                    sampled_files = image_files  # 如果图片数量较少，使用所有图片
                else:
                    # 确保抽样包含：
                    # 1. 开头的几张图片
                    # 2. 结尾的几张图片
                    # 3. 均匀分布的中间图片
                    head_count = min(3, total_images)  # 开头取3张
                    tail_count = min(3, total_images)  # 结尾取3张
                    middle_count = sample_size - head_count - tail_count  # 中间的图片数量
                    
                    # 获取头部图片
                    head_files = image_files[:head_count]
                    # 获取尾部图片
                    tail_files = image_files[-tail_count:]
                    # 获取中间的图片
                    if middle_count > 0:
                        step = (total_images - head_count - tail_count) // (middle_count + 1)
                        middle_indices = range(head_count, total_images - tail_count, step)
                        middle_files = [image_files[i] for i in middle_indices[:middle_count]]
                    else:
                        middle_files = []
                    
                    sampled_files = head_files + middle_files + tail_files
                    self.logger.debug(f"[#process_log]抽样数量: {len(sampled_files)}/{total_images} (头部:{len(head_files)}, 中间:{len(middle_files)}, 尾部:{len(tail_files)})")

                match_count = 0
                large_image_count = 0
                min_width = float('inf')
                
                for img in sampled_files:
                    width = self.get_image_width_from_zip(zf, img)
                    if width > 0:
                        min_width = min(min_width, width)
                        
                        # 检查是否大于1800
                        if width >= 1800:
                            large_image_count += 1
                            if large_image_count > 3:  # 如果超过3张图片宽度大于1800，提前返回
                                self.logger.info(f"[#process_log]ZIP文件 {zip_path} 超过3张图片宽度大于1800px")
                                return min_width if min_width != float('inf') else 0, 0
                        
                        matches_condition = (self.compare_larger and width >= self.min_width) or \
                                         (not self.compare_larger and width < self.min_width)
                        if matches_condition:
                            match_count += 1
                            self.logger.debug(f"[#process_log]图片 {img} 符合条件: {width}px")
                        
                        # 如果已经达到阈值，可以提前返回
                        if match_count >= self.threshold_count:
                            self.logger.info(f"[#process_log]ZIP文件 {zip_path} 已达到阈值 ({match_count}/{self.threshold_count})")
                            return min_width if min_width != float('inf') else 0, match_count

                final_width = min_width if min_width != float('inf') else 0
                self.logger.info(f"[#process_log]ZIP文件 {zip_path} - 最小宽度: {final_width}px, 符合条件数量: {match_count}/{self.threshold_count}, "
                               f"大于1800px的图片数量: {large_image_count}, 总图片: {total_images}, 抽样: {len(sampled_files)}")
                return final_width, match_count
                
        except Exception as e:
            self.logger.error(f"[#update_log]处理ZIP文件出错 {zip_path}: {str(e)}")
            return 0, 0

    def should_process_zip(self, width, match_count, zip_path):
        if width == 0:
            self.logger.warning(f"[#update_log]跳过处理 {zip_path}: 无效的宽度")
            return False
        
        should_process = match_count >= self.threshold_count
        
        self.logger.info(f"[#process_log]文件 {zip_path} - 宽度: {width}px, 符合条件数量: {match_count}/{self.threshold_count}, "
                        f"{'大于等于' if self.compare_larger else '小于'}模式, "
                        f"结果: {'处理' if should_process else '跳过'}")
        return should_process

    def process_single_zip(self, zip_path):
        """处理单个压缩包，返回是否需要处理"""
        try:
            # 0. 检查压缩包是否有效
            if not self.is_valid_zip(zip_path):
                self.logger.info(f"[#update_log]跳过损坏的压缩包: {zip_path}")
                return zip_path, False
                
            # 1. 首先检查是否包含排除格式
            if self.has_excluded_formats(zip_path):
                self.logger.info(f"[#update_log]跳过包含排除格式的文件: {zip_path}")
                return zip_path, False
            
            # 2. 只有不包含排除格式的文件才检查宽度
            width, match_count = self.get_zip_images_info(zip_path)
            should_process = self.should_process_zip(width, match_count, zip_path)
            
            return zip_path, should_process
            
        except Exception as e:
            self.logger.error(f"[#update_log]处理压缩包时出错 {zip_path}: {str(e)}")
            return zip_path, False

    def run_7z_command(self, command, zip_path, operation="", additional_args=None):
        """
        执行7z命令的通用函数
        
        Args:
            command: 主命令 (如 'a', 'x', 'l' 等)
            zip_path: 压缩包路径
            operation: 操作描述（用于日志）
            additional_args: 额外的命令行参数
        """
        try:
            cmd = ['7z', command, str(zip_path)]
            if additional_args:
                cmd.extend(additional_args)
            
            result = subprocess.run(cmd, capture_output=True, text=False)  # 使用二进制模式
            
            if result.returncode == 0:
                try:
                    # 尝试用cp932解码（适用于Windows日文系统）
                    output = result.stdout.decode('cp932')
                except UnicodeDecodeError:
                    try:
                        # 如果cp932失败，尝试用utf-8解码
                        output = result.stdout.decode('utf-8')
                    except UnicodeDecodeError:
                        # 如果两种编码都失败，使用errors='replace'
                        output = result.stdout.decode('utf-8', errors='replace')
            
                return True, output
            else:
                error_output = result.stderr
                try:
                    error_text = error_output.decode('cp932')
                except UnicodeDecodeError:
                    try:
                        error_text = error_output.decode('utf-8')
                    except UnicodeDecodeError:
                        error_text = error_output.decode('utf-8', errors='replace')
                    
                self.logger.error(f"7z {operation}失败: {zip_path}\n错误: {error_text}")
                return False, error_text
            
        except Exception as e:
            self.logger.error(f"[#update_log]执行7z命令出错: {e}")
            return False, str(e)

    def check_7z_contents(self, zip_path):
        """使用7z检查压缩包内容"""
        try:
            success, output = self.run_7z_command('l', zip_path, "列出内容")
            if not success:
                return True  # 如果出错，保守起见返回True
            
            # 检查输出中是否包含排除的格式
            output = output.lower()
            for ext in self.exclude_formats:
                if ext in output:
                    self.logger.info(f"[#update_log]跳过压缩包 {zip_path.name} 因为包含排除格式: {ext}")
                    return True
            return False
            
        except Exception as e:
            self.logger.error(f"[#update_log]检查压缩包格式时出错 {zip_path}: {str(e)}")
            return True

    def has_excluded_formats(self, zip_path):
        """检查压缩包中是否包含需要排除的文件格式"""
        return self.check_7z_contents(zip_path)

    def is_valid_zip(self, zip_path):
        """检查压缩包是否有效（非损坏）"""
        try:
            # 使用7z测试压缩包完整性
            success, output = self.run_7z_command('t', zip_path, "测试压缩包完整性")
            return success
        except Exception as e:
            self.logger.error(f"[#update_log]检查压缩包有效性时出错 {zip_path}: {str(e)}")
            return False

    def process(self):
        # 获取目标目录中所有zip文件的名称（不区分大小写）
        existing_files = {f.name.lower() for f in self.target_dir.rglob("*.zip")}
        
        # 收集需要处理的文件
        zip_files = []
        for f in self.source_dir.rglob("*.zip"):
            if f.name.lower() in existing_files or self.should_exclude_path(str(f)):
                continue
            zip_files.append(f)

        if not zip_files:
            self.logger.info("[#update_log]没有找到需要处理的文件")
            return

        self.logger.info(f"[#current_stats]开始处理 {len(zip_files)} 个文件")
        self.logger.info(f"[#performance]已排除包含关键词的路径: {', '.join(self.exclude_paths)}")
        self.logger.info(f"[#performance]模式: {'大于等于' if self.compare_larger else '小于'} {self.min_width}px")
        self.logger.info(f"[#performance]操作: {'移动' if self.cut_mode else '复制'}")
        
        processed_folders = set()
        processed_count = 0

        # 处理文件
        operation = "移动" if self.cut_mode else "复制"
        moved_count = 0
        total_files = len(zip_files)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for zip_path, should_process in tqdm(
                executor.map(self.process_single_zip, zip_files),
                total=total_files,
                desc="处理文件"
            ):
                processed_count += 1
                self.logger.info(f"[@current_progress]总体进度 ({processed_count}/{total_files}) {processed_count/total_files*100:.1f}%")
                
                if should_process:
                    processed_folders.add(zip_path.parent)
                    
                    # 处理文件
                    rel_path = zip_path.relative_to(self.source_dir)
                    new_folder = self.target_dir / rel_path.parent
                    new_folder.mkdir(parents=True, exist_ok=True)

                    try:
                        if self.cut_mode:
                            shutil.move(str(zip_path), str(new_folder / zip_path.name))
                        else:
                            shutil.copy2(str(zip_path), str(new_folder / zip_path.name))
                        moved_count += 1
                        self.logger.info(f"[#process_log]成功{operation}: {zip_path.name}")
                    except Exception as e:
                        self.logger.error(f"[#update_log]{operation}失败 {zip_path}: {str(e)}")

        # 如果是移动模式，清理空文件夹
        if self.cut_mode:
            for folder in processed_folders:
                if not any(folder.iterdir()):
                    try:
                        folder.rmdir()
                        self.logger.info(f"[#update_log]删除空文件夹: {folder}")
                    except Exception as e:
                        self.logger.error(f"[#update_log]删除文件夹失败 {folder}: {str(e)}")

        self.logger.info(f"[#current_stats]处理完成: 成功{operation} {moved_count} 个文件")

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='图片宽度过滤工具')
    parser.add_argument('-c', '--clipboard', action='store_true', help='从剪贴板读取源目录路径')
    parser.add_argument('-s', '--source', type=str, help='源目录路径', default=r"E:\999EHV")
    parser.add_argument('-t', '--target', type=str, help='目标目录路径', default=r"E:\7EHV")
    parser.add_argument('-w', '--width', type=int, help='宽度阈值', default=1800)
    parser.add_argument('-l', '--larger', action='store_true', help='选择大于等于指定宽度的文件')
    parser.add_argument('-m', '--move', action='store_true', help='移动文件而不是复制')
    parser.add_argument('-j', '--jobs', type=int, help='并行处理线程数', default=16)
    parser.add_argument('-n', '--number', type=int, help='符合条件的图片数量阈值', default=3)

    args = parser.parse_args()

    # 配置参数
    config = {
        "source_dir": pyperclip.paste().strip() if args.clipboard else args.source,
        "target_dir": args.target,
        "min_width": args.width,
        "cut_mode": args.move,
        "max_workers": args.jobs,
        "compare_larger": args.larger,
        "threshold_count": args.number
    }

    # 验证源目录路径
    if not os.path.exists(config["source_dir"]):
        logger.error(f"[#update_log]源目录不存在: {config['source_dir']}")
        return

    try:
        logger.info(f"[#current_stats]开始处理 - 源: {config['source_dir']} 目标: {config['target_dir']}")
        processor = ImageProcessor(**config)
        processor.process()
    except Exception as e:
        logger.exception(f"[#update_log]程序执行出错: {e}")

if __name__ == "__main__":
    # Windows长路径支持
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, 1)
        except Exception as e:
            logger.error(f"[#update_log]无法启用长路径支持: {e}")
    
    main()