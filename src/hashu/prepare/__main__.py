import os
import argparse
import logging
import loguru
import yaml

import numpy as np
import cv2
from PIL import Image
import pillow_jxl
import pillow_avif
import tempfile
import subprocess
import logging
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Dict, Tuple, Union, List, Optional
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse, ParseResult
import re
import json
import zipfile
import io
import sys
from datetime import datetime
import warnings  # 新增：导入warnings模块
from PIL.Image import DecompressionBombWarning  # 新增：导入PIL的警告类
import orjson
# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from textual_preset import create_config_app
from hashu.core.calculate_hash_custom import ImageHashCalculator
from textual_logger import TextualLoggerManager
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

logger, config_info = setup_logger(app_name="hashpre", console_output=False)

# 在全局配置部分添加以下内容
# ================= 日志配置 =================

# 添加默认配置常量
DEFAULT_PROCESS_CONFIG = {
    'max_workers': 16,        # 最大工作线程数
    'force_update': False,   # 是否强制更新
    'dry_run': False,        # 是否仅预览
    'extract_dir': r"E:\2400EHV\extracted_archives",  # 解压目录
    'hash_size': 10,        # 哈希大小
    'hash_version': 1       # 哈希版本
}
# 哈希计算参数
params = {
    'hash_size': 10,  # 默认哈希大小
    'hash_version': 1  # 哈希版本号，用于后续兼容性处理
}

# 禁用PIL的DecompressionBombWarning警告
warnings.filterwarnings("ignore", category=DecompressionBombWarning)
# 设置PIL的日志级别为ERROR
logging.getLogger("PIL").setLevel(logging.ERROR)
# 全局配置
GLOBAL_HASH_CACHE = os.path.expanduser(r"E:\999EHV\image_hashes_global.json")
HASH_FILES_LIST = os.path.expanduser(r"E:\999EHV\hash_files_list.txt")  # 新增：保存所有哈希文件路径的文件

# 退出码定义
EXIT_SUCCESS = 0  # 成功完成
EXIT_NO_FILES = 1  # 没有找到需要处理的文件
EXIT_PATH_NOT_EXIST = 2  # 输入路径不存在
EXIT_PROCESS_ERROR = 3  # 处理过程出错

# 必须显式定义完整布局配置
FULL_LAYOUT_CONFIG = {
    "current_stats": {
        "ratio": 2, 
        "title": "📊 总体进度",
        "style": "lightblue"
    },
    # "current_progress": {
    #     "ratio": 2,
    #     "title": "🔄 当前进度",
    #     "style": "lightgreen"
    # },
    "hash_progress": {  # 新增哈希进度面板
        "ratio": 2,
        "title": "⏳ 哈希进度",
        "style": "lightcyan"
    },
    "hash_calc": {  # 新增哈希计算面板
        "ratio": 3,
        "title": "🧮 哈希计算",
        "style": "lightyellow"
    },

    "file_ops": {  # 新增文件操作面板
        "ratio": 2,
        "title": "📂 文件操作",
        "style": "lightpink"
    }
}

# 添加黑名单关键词常量
BLACKLIST_KEYWORDS = ['temp', 'trash', '画集', '图集', 'cg', '00不需要', '动画']

@dataclass
class ProcessResult:
    """处理结果的数据类"""
    uri: str  # 标准化的URI
    hash_value: dict  # 图片哈希值（新格式：包含hash、size和url）
    file_type: str  # 文件类型（'image' 或 'archive'）
    original_path: str  # 原始文件路径



# 全局变量定义
global_hashes = {}

def get_artist_folder_path(base_path):
    """获取画师文件夹路径"""
    try:
        base_path = Path(base_path).resolve()
        
        if '[' in str(base_path) and ']' in str(base_path):
            if base_path.exists():
                return base_path
            else:
                logging.info( f'❌ 指定的路径不存在: {base_path}')
                return None
        
        artist_folders = []
        for entry in base_path.iterdir():
            if entry.is_dir() and '[' in entry.name and ']' in entry.name:
                artist_folders.append(entry)
                    
        if not artist_folders:
            logging.info( f'❌ 在路径 {base_path} 下未找到画师文件夹')
            return None
            
        if len(artist_folders) == 1:
            logging.info( f'✅ 找到画师文件夹: {artist_folders[0]}')
            return artist_folders[0]
            
        logging.info( f"\n找到以下画师文件夹:")
        for i, folder in enumerate(artist_folders, 1):
            logging.info( f"{i}. {folder}")
            
        # 使用普通终端输入
        valid_paths = []
        print("请输入要处理的文件夹编号(直接回车确认第一个):")
        while True:
            choice = input().strip()
            if not choice:
                break
            try:
                index = int(choice) - 1
                if 0 <= index < len(artist_folders):
                    return artist_folders[index]
                logging.info( f'❌ 无效的选择，请重试')
                return None
            except ValueError:
                logging.info( f'❌ 请输入有效的数字')
                return None

            return None
    except Exception as e:
        logging.info( f'❌ 获取画师文件夹时出错: {e}')
        return None

def process_single_image(image_path, lock) -> Dict[str, ProcessResult]:
    """处理单个图片文件"""
    try:
        img_hash = ImageHashCalculator.calculate_phash(image_path)
        if img_hash and isinstance(img_hash, dict) and 'hash' in img_hash:
            uri = ImageHashCalculator.normalize_path(image_path)
            result = ProcessResult(
                uri=uri,
                hash_value=img_hash,  # img_hash 已经是字典格式
                file_type='image',
                original_path=str(image_path)
            )
            with lock:
                # 修改日志输出到哈希计算面板
                logging.info(f"[#hash_calc][✨新计算] 图片: {image_path}  哈希值: {img_hash['hash']}")  
                return {uri: result}
        return {}
    except Exception as e:
        logging.error(f"[#hash_calc]处理图片失败 {image_path}: {e}")
        return {}

def check_zip_integrity(zip_path: Path) -> bool:
    """检查压缩包完整性
    
    Args:
        zip_path: 压缩包路径
    
    Returns:
        bool: 压缩包是否完整
    """
    try:
        cmd = ['7z', 't', str(zip_path)]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if result.returncode != 0:
            logging.info(f"压缩包损坏或无法读取: {zip_path}")
            return False
        return True
    except Exception as e:
        logging.info(f"检查压缩包完整性时出错: {zip_path}: {e}")
        return False

def decode_zip_filename(name: bytes) -> str:
    """尝试使用不同编码解码zip文件名"""
    """增强版ZIP文件名解码"""
    zip_flags = 0x800
    # 检测ZIP的UTF-8标志位（第11位）
    if (zip_flags & 0x800) != 0:
        try:
            return name.decode('utf-8')
        except UnicodeDecodeError:
            pass
    # 其他编码回退逻辑...

    encodings = ['utf-8', 'gbk', 'cp437', 'shift-jis', 'gb18030', 'big5']


    try:
        import chardet
        detected = chardet.detect(name)
        if detected and detected['confidence'] > 0.6:  # 降低置信度阈值
            encodings = [detected['encoding']] + encodings
    except ImportError:
        pass
    
    # 去重并保持顺序
    seen = set()
    encodings = [x for x in encodings if not (x in seen or seen.add(x))]
    
    # 尝试不同的编码（使用surrogateescape错误处理）
    for encoding in encodings:
        try:
            return name.decode(encoding, errors='surrogateescape')
        except (UnicodeDecodeError, LookupError):
            continue
            
    # 使用surrogateescape模式回退
    return name.decode('utf-8', errors='surrogateescape')



def update_stats_panel(total_files, processed_files, success_files, total_size, processed_size):
    """统一统计信息显示"""
    progress_percent = int((processed_files / total_files * 100) if total_files > 0 else 0)
    stats_text = (
        f"总路径数: {total_files} 已处理: {processed_files} 成功: {success_files} "
        f"总大小: {total_size:.2f}MB 已处理大小: {processed_size:.2f}MB"
    )
    logging.info(f"[@current_stats]  总进度: {progress_percent}%")
    logging.info(f"[#current_stats]{stats_text}")


def update_performance_panel(thread_count, batch_size=None):
    """更新性能面板"""
    perf_text = (
        f"线程数: {thread_count}\n"
        f"批处理大小: {batch_size if batch_size else '未使用'}"
    )
    logging.info( perf_text)

class ProcessingStats:
    """处理统计类"""
    def __init__(self):
        self.total_files = 0
        self.processed_files = 0
        self.total_size = 0
        self.processed_size = 0
        self.current_file = ""
        self.current_progress = 0
        self._lock = threading.Lock()
        
    def update(self, processed_files=None, total_size=None, processed_size=None, 
               current_file=None, current_progress=None):
        """更新统计信息"""
        with self._lock:
            if processed_files is not None:
                self.processed_files = processed_files
            if total_size is not None:
                self.total_size = total_size
            if processed_size is not None:
                self.processed_size = processed_size
            if current_file is not None:
                self.current_file = current_file
            if current_progress is not None:
                self.current_progress = current_progress
                
            # 更新面板
            update_stats_panel(self.total_files, self.processed_files, 
                             self.total_size, self.processed_size)
            if current_progress is not None:
                size_info = f" ({self.processed_size:.2f}MB)" if self.processed_size else ""
                # logging.info(f"[@current_progress] 进度 {size_info} {current_progress}%")


def process_single_zip(zip_path, extract_base_dir, lock, force_update=False, inner_workers=4) -> Dict[str, ProcessResult]:
    """处理单个压缩包中的图片"""
    try:
        # 确保zip_path是字符串类型
        zip_path = str(zip_path)
        
        # 首先检查压缩包完整性
        if not check_zip_integrity(Path(zip_path)):
            logging.error(f"[#hash_calc]压缩包损坏或无法读取: {zip_path}")
            return {}
            
        # 检查全局哈希缓存中是否已有该压缩包的记录
        if not force_update:
            results = ImageHashCalculator.match_existing_hashes(Path(zip_path), global_hashes, is_global=True)
            if results:
                return results

        zip_hashes = {}
        
        def process_image(args):
            """处理单个图片的函数"""
            filename, img_data = args
            try:
                # 构造压缩包内图片的完整路径
                img_path = f"{zip_path}!/{filename}"
                # 生成标准化的URI
                uri = ImageHashCalculator.normalize_path(zip_path, filename)
                # 计算哈希值时传入URI
                img_hash = ImageHashCalculator.calculate_phash(io.BytesIO(img_data), url=uri)
                if img_hash and isinstance(img_hash, dict) and 'hash' in img_hash:
                    result = ProcessResult(
                        uri=uri,
                        hash_value=img_hash,  # img_hash 已经是字典格式
                        file_type='archive',
                        original_path=str(zip_path)
                    )
                    with lock:
                        zip_hashes[uri] = result
            except Exception as e:
                logging.error(f"[#hash_calc]处理压缩包内图片失败，跳过: {filename}: {e}")

        
        # 首先尝试使用zipfile
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # 获取所有图片文件，处理文件名编码
            image_files = []
            for info in zf.filelist:
                # 处理文件名编码
                filename = decode_zip_filename(info.filename.encode('utf8'))
                if any(filename.lower().endswith(ext) for ext in 
                        ('.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif', '.bmp')):
                    # 直接读取文件数据到内存
                    with zf.open(info) as f:
                        image_files.append((filename, f.read()))
            
            total_files = len(image_files)
            if total_files == 0:
                logging.info(f"[#file_ops]压缩包内无图片文件: {zip_path}")
                return {}
                
            logging.info(f"[#file_ops]开始处理压缩包: {zip_path.encode('utf-8', 'replace').decode('utf-8')}  共 {total_files} 个图片文件")
            
            # 使用线程池处理图片
            processed_count = 0
            with ThreadPoolExecutor(max_workers=inner_workers) as executor:
                futures = []
                for filename, img_data in image_files:
                    futures.append(executor.submit(process_image, (filename, img_data)))
            
            for future in futures:
                future.result()
                processed_count += 1
                progress = int((processed_count / total_files) * 100)
                with lock:
                    # 修改为专用进度条格式
                    logging.info(f"[@hash_progress] 进度{progress}%")  # 压缩包内进度

                
        return zip_hashes
                        
    except Exception as e:
        logging.error(f"[#hash_calc]处理压缩包失败，跳过: {str(zip_path).encode('utf-8', 'replace').decode('utf-8')}: {e}")
        return {}

def get_default_output_path(input_path: Path) -> Path:
    """获取默认的输出文件路径
    
    Args:
        input_path: 输入路径
        
    Returns:
        默认的输出文件路径
    """
    input_path = Path(input_path)
    
    # 如果是画师模式，获取画师文件夹
    artist_folder = get_artist_folder_path(input_path)
    if artist_folder:
        base_dir = artist_folder
    else:
        # 如果是压缩包，使用其所在目录
        if input_path.is_file() and input_path.suffix.lower() == '.zip':
            base_dir = input_path.parent
        else:
            base_dir = input_path
        
    # 当路径包含特殊字符（如用户路径中的 [ ] 和 、）时可能需要处理
    return base_dir / 'image_hashes.json'  # 需要确保 base_dir 正确

def should_process_path(path: Path, base_path: Path) -> bool:
    """检查路径是否应该被处理
    
    Args:
        path: 要检查的路径
        base_path: 基准路径（输入路径）
        
    Returns:
        bool: 是否应该处理该路径
    """
    # 转换为相对路径进行检查
    try:
        path_str = str(path).lower()
        # 检查完整路径是否包含黑名单关键词
        if any(keyword.lower() in path_str for keyword in BLACKLIST_KEYWORDS):
            logging.info(f"[#hash_calc]跳过文件（黑名单）: {path}")
            return False
            
        # 如果是相对路径，也检查一下
        try:
            rel_path = path.relative_to(base_path)
            for part in rel_path.parts:
                if any(keyword.lower() in part.lower() for keyword in BLACKLIST_KEYWORDS):
                    logging.info(f"[#hash_calc]跳过文件（黑名单）: {path}")
                    return False
        except ValueError:
            pass
            
        return True
            
    except Exception as e:
        logging.error(f"[#hash_calc]检查路径时出错: {e}")
        return False

def process_path(path: str, config: dict = None) -> Dict[str, ProcessResult]:
    """处理指定路径的文件或目录
    
    Args:
        path: 要处理的路径
        config: 处理配置，包含以下可选项：
            - max_workers: 最大工作线程数
            - force_update: 是否强制更新
            - dry_run: 是否仅预览
            - extract_dir: 解压目录
            - hash_size: 哈希大小
            - hash_version: 哈希版本
    
    Returns:
        Dict[str, ProcessResult]: 处理结果
    """
    try:
        # 合并配置
        cfg = DEFAULT_PROCESS_CONFIG.copy()
        if config:
            cfg.update(config)
            
        path = Path(path)
        if not path.exists():
            logging.error(f"[#hash_calc]路径不存在: {path}")
            return {}
        
        # 使用配置的解压目录
        extract_base_dir = Path(cfg['extract_dir'])
        extract_base_dir.mkdir(exist_ok=True, parents=True)
        logging.info(f"[#hash_calc]解压目录: {extract_base_dir}")
        
        # 加载全局哈希缓存
        if global_hashes:
            logging.info(f"[#hash_calc]已加载 {len(global_hashes)} 个缓存哈希值")
            
        # 如果不是强制更新，先尝试匹配全局哈希
        if not cfg['force_update']:
            # 过滤掉包含黑名单关键词的全局哈希
            filtered_global_hashes = {}
            for uri, hash_value in global_hashes.items():
                if not any(keyword.lower() in uri.lower() for keyword in BLACKLIST_KEYWORDS):
                    filtered_global_hashes[uri] = hash_value
            
            # 使用过滤后的全局哈希进行匹配
            results = ImageHashCalculator.match_existing_hashes(path, filtered_global_hashes, is_global=True)
            if results:
                return results
                
            # 再尝试本地哈希匹配
            try:
                with open(get_default_output_path(path), 'rb') as f:
                    local_hashes = orjson.loads(f.read()).get('hashes', {})
                    if local_hashes:
                        results = ImageHashCalculator.match_existing_hashes(path, local_hashes)
                        if results:
                            return results
            except:
                pass
        
        # 创建线程锁
        lock = threading.Lock()
        results: Dict[str, ProcessResult] = {}
        
        # 根据路径类型处理
        if path.is_file():
            results.update(process_single_file(path, cfg, lock, extract_base_dir))
        elif path.is_dir():
            results.update(process_directory(path, cfg, lock, extract_base_dir))
        
        # 保存结果
        if results and not cfg['dry_run']:
            save_results(results, path, cfg)
            
        logging.info(f"[#hash_calc]处理完成")
        return results
        
    except Exception as e:
        logging.error(f"[#hash_calc]处理路径时出错: {e}")
        return {}

def process_single_file(path: Path, config: dict, lock: threading.Lock, extract_dir: Path) -> Dict[str, ProcessResult]:
    """处理单个文件"""
    results = {}
    if not should_process_path(path, path.parent):
        logging.info(f"[#hash_calc]跳过文件（黑名单）: {path}")
        return results
        
    file_size = path.stat().st_size / (1024 * 1024)
    logging.info(f"[@hash_progress] 进度 0% ")  # 初始进度
    
    # 检查是否需要使用分组信息
    if config.get('use_groups') and path.suffix.lower() in ['.zip']:
        # 尝试读取分组信息
        group_info_path = os.path.join(path.parent, 'group_info.json')
        if os.path.exists(group_info_path):
            try:
                with open(group_info_path, 'r', encoding='utf-8') as f:
                    group_info = json.load(f)
                    
                # 检查当前文件的分组信息
                rel_path = str(path.name)
                if rel_path in group_info:
                    file_info = group_info[rel_path]
                    if file_info['type'] == 'trash':
                        logging.info(f"[#hash_calc]跳过trash文件: {path}")
                        return results
                    elif file_info['type'] == 'multi' and not file_info.get('is_main', False):
                        logging.info(f"[#hash_calc]跳过非主要multi文件: {path}")
                        return results
                    else:
                        logging.info(f"[#hash_calc]处理{file_info['type']}文件: {path}")
            except Exception as e:
                logging.error(f"[#hash_calc]读取分组信息失败: {e}")
    
    # 继续原有的处理逻辑
    if path.suffix.lower() in ['.zip']:
        results = process_single_zip(path, extract_dir, lock, config['force_update'])
    elif path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif', '.bmp']:
        results = process_single_image(path, lock)
        
    return results

def process_directory(path: Path, config: dict, lock: threading.Lock, extract_dir: Path) -> Dict[str, ProcessResult]:
    """处理目录"""
    results = {}
    files_to_process = []
    skipped_files = []
    skipped_existing = []
    total_size = 0
    
    # 尝试加载本地哈希文件
    try:
        hash_file_path = str(get_default_output_path(path))
        with open(hash_file_path, 'rb') as f:
            local_hashes = orjson.loads(f.read()).get('hashes', {})
    except:
        local_hashes = {}
    
    # 收集文件
    for item in path.rglob("*"):
        if not item.is_file() or not should_process_path(item, path):
            continue
            
        item_path = str(item).replace('\\', '/')
        # 先尝试匹配现有哈希
        if local_hashes:
            results = ImageHashCalculator.match_existing_hashes(item, local_hashes)
            if results:
                skipped_existing.append(item)
                continue
                
        if item.suffix.lower() in ['.zip', '.jpg', '.jpeg', '.png', '.webp', '.jxl', '.avif', '.bmp']:
            files_to_process.append(('zip' if item.suffix.lower() == '.zip' else 'image', item))
            total_size += item.stat().st_size / (1024 * 1024)
    
    # 处理文件
    if files_to_process:
        results.update(process_file_batch(
            files_to_process, 
            config, 
            lock, 
            extract_dir, 
            total_size
        ))
    
    # 更新统计显示
    processed_size = 0
    for result in results.values():
        try:
            file_path = Path(result.original_path)
            if file_path.exists():
                processed_size += file_path.stat().st_size / (1024 * 1024)
        except:
            continue
            
    update_stats_panel(
        total_files=len(files_to_process),
        processed_files=len(results) - len(skipped_files),
        success_files=len(results) - len(skipped_files),
        total_size=total_size,
        processed_size=processed_size
    )
    
    return results

def process_file_batch(files: list, config: dict, lock: threading.Lock, 
                      extract_dir: Path, total_size: float) -> Dict[str, ProcessResult]:
    """批量处理文件"""
    results = {}
    processed_count = 0
    processed_size = 0
    success_count = 0  # 添加成功计数器初始化
    total_count = len(files)
    
    # 初始化统计面板
    update_stats_panel(
        total_files=total_count,
        processed_files=0,
        success_files=0,
        total_size=total_size,
        processed_size=0
    )

    with ThreadPoolExecutor(max_workers=config['max_workers']) as executor:
        # 修改futures元组携带文件类型信息
        futures = []
        for file_type, file_path in files:
            if file_type == 'zip':
                future = executor.submit(process_single_zip, file_path, extract_dir, lock, config['force_update'])
            else:
                future = executor.submit(process_single_image, file_path, lock)
            futures.append((future, file_path, file_path.stat().st_size / (1024 * 1024), file_type))
        
        # 处理完成时更新总体进度
        for future, file_path, file_size, file_type in futures:
            try:
                file_results = future.result()
                if file_results:  # 有结果表示处理成功
                    success_count += 1
                    results.update(file_results)
                    
                # 实时更新统计（每次循环都更新）
                update_stats_panel(
                    total_files=total_count,
                    processed_files=processed_count,
                    success_files=success_count,
                    total_size=total_size,
                    processed_size=processed_size
                )
                
            except Exception as e:
                logging.error(f"[#hash_calc]处理文件失败: {e}")
            finally:
                processed_count += 1
                processed_size += file_size
                progress = int(processed_count/total_count*100)
                # 新进度格式
                logging.info(f"[@hash_progress] 进度 {progress}%")
                
    return results

def save_results(results: Dict[str, ProcessResult], path: Path, config: dict) -> None:
    """保存处理结果"""
    output_path = get_default_output_path(path)
    output = {
        "_hash_params": f"hash_size={config['hash_size']};hash_version={config['hash_version']}",
        "dry_run": config['dry_run'],
        "input_paths": [str(path)],
        "hashes": {}
    }
    
    # 正确处理hash_value字段
    for uri, result in results.items():
        if isinstance(result.hash_value, dict):
            # 如果是字典格式，直接使用hash字段
            output["hashes"][uri] = {'hash': result.hash_value['hash']}
        else:
            # 如果是字符串格式，直接使用
            output["hashes"][uri] = {'hash': result.hash_value}
    
    # 修改保存日志到文件操作面板
    logging.info(f"[#file_ops]准备保存 {len(output['hashes'])} 个哈希值")
    logging.info(f"[#file_ops]✅ 已保存哈希结果到: {output_path}")
    logging.info(f"[#file_ops]已更新缓存，现有 {len(global_hashes)} 个哈希值")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    ImageHashCalculator.save_hash_file_path(str(output_path))
    
    # 更新全局缓存
    hash_dict = {k: v['hash'] for k, v in output["hashes"].items()}
    global_hashes.update(hash_dict)
    ImageHashCalculator.save_global_hashes(global_hashes)

def main():
    """主函数
    
    Returns:
        int: 退出码
            0: 成功完成
            1: 没有找到需要处理的文件
            2: 输入路径不存在
            3: 处理过程出错
    """
    try:
        # 在main函数顶部设置标准流编码
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        
        # 在main函数顶部声明全局变量
        global global_hashes
        global_hashes = ImageHashCalculator.load_global_hashes()
        
        # 设置Python的默认编码为UTF-8
        import locale
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        
        # 设置标准输入输出的编码
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8')
            
        print("开始执行主函数...", flush=True)
        
        parser = argparse.ArgumentParser(description='图片哈希预热工具')
        parser.add_argument('-w', '--workers', type=int, default=4, help='线程数 (默认: 4)')
        parser.add_argument('-f', '--force', action='store_true', help='强制更新所有哈希值，忽略缓存')
        parser.add_argument('-d', '--dry-run', action='store_true', help='预览模式,不实际修改文件')
        parser.add_argument('--cache', type=str, default=GLOBAL_HASH_CACHE, help='缓存文件路径')
        parser.add_argument('--output', type=str, help='输出文件路径')
        parser.add_argument('--path', type=str, help='要处理的文件夹路径')
        parser.add_argument('--paths', type=str, nargs='+', help='要处理的多个文件夹路径')
        parser.add_argument('--hash-size', type=int, default=10, help='哈希大小 (默认: 10)')
        parser.add_argument('--use-groups', action='store_true', help='使用已有的分组信息JSON文件过滤文件')

        print("解析命令行参数...", flush=True)
        args = parser.parse_args()
        print(f"命令行参数: {args}", flush=True)
        
        # 收集所有有效路径
        valid_paths = []
        
        # 处理单个路径参数
        if args.path:
            if os.path.exists(args.path):
                valid_paths.append(args.path)
                print(f"添加有效路径: {args.path}")
            else:
                print(f"路径不存在: {args.path}")
                
        # 处理多个路径参数
        if args.paths:
            for path in args.paths:
                if os.path.exists(path):
                    valid_paths.append(path)
                    print(f"添加有效路径: {path}")
                else:
                    print(f"路径不存在: {path}")
        
        # 如果没有通过命令行参数指定路径，则使用交互式输入
        if not valid_paths:
            try:
                print("请输入要处理的文件夹或压缩包路径（每行一个，输入空行结束）:")
                while True:
                    path = input().strip().strip('"').strip("'")
                    if not path:
                        break
                    if os.path.exists(path):
                        valid_paths.append(path)
                        print(f"添加有效路径: {path}")
                    else:
                        print(f"路径不存在: {path}")
            except Exception as e:
                print(f"获取路径失败: {e}")
                return EXIT_PROCESS_ERROR
        
        if not valid_paths:
            print("没有找到有效的路径")
            return EXIT_NO_FILES
            
        print(f"共找到 {len(valid_paths)} 个有效路径")
        
        # 在这里初始化日志面板，因为已经收集完了所有路径
        TextualLoggerManager.set_layout(FULL_LAYOUT_CONFIG,config_info['log_file'])
        
        # 更新哈希参数
        params['hash_size'] = args.hash_size
        
        # 更新配置
        config = {
            'max_workers': args.workers,
            'force_update': args.force,
            'dry_run': args.dry_run,
            'use_groups': args.use_groups  # 添加分组配置
        }
        
        # 处理所有路径
        success_count = 0
        total_paths = len(valid_paths)
        
        # 更新总体进度
        
        for index, path in enumerate(valid_paths, 1):
            # 更新当前进度 - 只显示当前处理的文件，不显示进度
            try:
                file_size = Path(path).stat().st_size / (1024 * 1024)  # 转换为MB
            except:
                file_size = None
            logging.info(f"[@hash_progress] 进度 0%")  # 初始进度
            
            try:
                # 更新处理日志
                logging.info(f"[#hash_calc]开始处理路径: {path}")
                results = process_path(path, config)
                
                if results:
                    # 获取当前路径的输出文件路径
                    output_path = get_default_output_path(Path(path))
                    
                    # 过滤掉包含黑名单关键词的结果
                    filtered_results = {}
                    for uri, result in results.items():
                        if not any(keyword.lower() in uri.lower() for keyword in BLACKLIST_KEYWORDS):
                            filtered_results[uri] = result
                    
                    if filtered_results:
                        logging.info(f"[#hash_calc]准备保存 {len(filtered_results)} 个哈希值")
                        ImageHashCalculator.save_hash_results(filtered_results, output_path, args.dry_run)
                    else:
                        logging.info(f"[#hash_calc]没有需要保存的哈希值（全部被过滤）")
                    
                    success_count += 1
                    # 更新当前文件进度为完成
                    logging.info(f"[@hash_progress] 进度100%")
                    
            except Exception as e:
                logging.error(f"[#hash_calc]处理路径失败: {path}: {e}")
                # 更新总体进度
                continue
        
        if success_count == 0:
            logging.error("[#hash_calc]没有成功处理任何路径")
            return EXIT_NO_FILES
            
        logging.info(f"[#hash_calc]处理完成，成功处理 {success_count} 个路径")
        return EXIT_SUCCESS
            
    except Exception as e:
        logging.error(f"[#hash_calc]处理过程出错: {str(e)}")
        return EXIT_PROCESS_ERROR



if __name__ == "__main__":
    sys.exit(main()) 