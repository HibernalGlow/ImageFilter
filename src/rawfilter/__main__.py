import sys
import os
import logging
logging.basicConfig()  # 初始化标准库logging

# 标准库导入
import re
import shutil
from datetime import datetime
import argparse
import io
import functools
import subprocess
import threading
from functools import partial
import random
import zipfile
import win32com.client  # 用于创建快捷方式

# 第三方库导入
import pyperclip
from PIL import Image
import pillow_avif
import pillow_jxl
from pathlib import Path
from colorama import init, Fore, Style
from typing import List, Dict, Set, Tuple, Optional, Union
from opencc import OpenCC  # 用于繁简转换
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashu.core.calculate_hash_custom import ImageClarityEvaluator
from textual_logger import TextualLoggerManager
from rawfilter.core.number_shortener import shorten_number_cn
import json
from rawfilter.core.group_analyzer import GroupAnalyzer

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

logger, config_info = setup_logger(app_name="no_translate_find", console_output=True)

    # 设置Textual日志布局
TEXTUAL_LAYOUT = {
    "stats": {
        "ratio": 2,
        "title": "📊 处理统计",
        "style": "lightgreen"
    },
    "process": {
        "ratio": 2, 
        "title": "🔄 进度",
        "style": "lightcyan",
    },
    "file_ops": {
        "ratio": 3,
        "title": "📂 文件操作",
        "style": "lightblue",
    },
    "group_info": {
        "ratio": 3,
        "title": "🔍 组处理信息",
        "style": "lightpink",
    },
    "error_log": {
        "ratio": 2,
        "title": "⚠️ 错误日志",
        "style": "lightred",
    }
}

class ReportGenerator:
    """生成处理报告的类"""
    def __init__(self):
        self.report_sections = []
        self.stats = {
            'total_files': 0,
            'total_groups': 0,
            'moved_to_trash': 0,
            'moved_to_multi': 0,
            'skipped_files': 0,
            'created_shortcuts': 0
        }
        self.group_details = []
        
    def add_group_detail(self, group_name: str, details: Dict):
        """添加组处理详情"""
        self.group_details.append({
            'name': group_name,
            'details': details
        })
        
    def update_stats(self, key: str, value: int = 1):
        """更新统计信息"""
        self.stats[key] = self.stats.get(key, 0) + value
        
    def add_section(self, title: str, content: str):
        """添加报告章节"""
        self.report_sections.append({
            'title': title,
            'content': content
        })
        
    def generate_report(self, base_dir: str) -> str:
        """生成最终的MD报告"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = [
            f"# 文件处理报告",
            f"生成时间: {timestamp}",
            f"处理目录: {base_dir}",
            "",
            "## 处理统计",
            f"- 总文件数: {shorten_number_cn(self.stats['total_files'])}",
            f"- 总分组数: {shorten_number_cn(self.stats['total_groups'])}",
            f"- 移动到trash目录: {shorten_number_cn(self.stats['moved_to_trash'])}",
            f"- 移动到multi目录: {shorten_number_cn(self.stats['moved_to_multi'])}",
            f"- 跳过的文件: {shorten_number_cn(self.stats['skipped_files'])}",
            f"- 创建的快捷方式: {shorten_number_cn(self.stats['created_shortcuts'])}",
            ""
        ]
        
        # 添加组详情（改为列表形式）
        if self.group_details:
            report.append("## 处理详情列表")
            for group in self.group_details:
                report.append(f"- **{group['name']}**")
                details = group['details']
                if 'chinese_versions' in details:
                    report.append("  - 汉化版本:")
                    for file in details['chinese_versions']:
                        report.append(f"    - {file}")
                if 'other_versions' in details:
                    report.append("  - 其他版本:")
                    for file in details['other_versions']:
                        report.append(f"    - {file}")
                if 'actions' in details:
                    report.append("  - 执行操作:")
                    for action in details['actions']:
                        report.append(f"    - {action}")
                report.append("")  # 组间空行
        
        # 其他章节保持标题形式
        for section in self.report_sections:
            report.append(f"## {section['title']}")
            report.append(section['content'])
            report.append("")
            
        return "\n".join(report)
        
    def save_report(self, base_dir: str, filename: Optional[str] = None):
        """保存报告到文件"""
        if filename is None:
            filename = f"处理报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        report_path = os.path.join(base_dir, filename)
        report_content = self.generate_report(base_dir)
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            return report_path
        except Exception as e:
            logger.error("[#error_log] ❌ 保存报告失败: %s", str(e))
            logger.exception("[#error_log] 异常堆栈:")  # 自动记录堆栈信息
            # 在界面显示错误详情
            logger.info("[#process] 💥 遇到严重错误，请检查error_log面板")
            return None

# 初始化colorama
init()

# 添加自定义模块路径并导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 初始化OpenCC
cc_s2t = OpenCC('s2t')  # 创建简体到繁体转换器
cc_t2s = OpenCC('t2s')  # 创建繁体到简体转换器

# 支持的压缩包格式
ARCHIVE_EXTENSIONS = {
    '.zip', '.rar', '.7z', '.cbr', '.cbz', 
    '.cb7', '.cbt', '.tar', '.gz', '.bz2'
}

# 支持的图片格式
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.avif', '.jxl',
    '.gif', '.bmp', '.tiff', '.tif', '.heic', '.heif'
}

def preprocess_keywords(keywords: Set[str]) -> Set[str]:
    """预处理关键词集合，添加繁简体变体"""
    processed = set()
    for keyword in keywords:
        # 添加原始关键词（小写）
        processed.add(keyword.lower())
        # 添加繁体版本
        traditional = cc_s2t.convert(keyword)
        processed.add(traditional.lower())
        # 添加简体版本
        simplified = cc_t2s.convert(keyword)
        processed.add(simplified.lower())
    return processed

# 预处理汉化版本关键词集合
CHINESE_VERSION_KEYWORDS = {
    '汉化', '漢化',  # 汉化/漢化
    '翻译', '翻訳', '翻譯', # 翻译相关
    '中国翻译', '中国翻訳', '中国語','chinese','中文','中国', # 中文翻译
    '嵌字',  # 嵌字
    '掃圖', '掃', # 扫图相关
    '制作', '製作', # 制作相关
    '重嵌',  # 重新嵌入
    '个人', # 个人翻译
    '去码',
    '日语社',
    '制作',
    '机翻',
    '赞助',
    '汉', '漢', # 汉字相关
    '数位', '未来数位', '新视界', # 汉化相关
    '出版', '青文出版', # 翻译相关
    '脸肿', '无毒', '空気系', '夢之行蹤', '萌幻鴿鄉', '绅士仓库', 'Lolipoi', '靴下','CE家族社',
    '不可视', '一匙咖啡豆', '无邪气', '洨五', '白杨', '瑞树',  # 常见汉化组名
    '冊語草堂','淫书馆','是小狐狸哦','工房','工坊','基地'
    '汉化组', '漢化組', '汉化社', '漢化社', 'CE 家族社', 'CE 家族社',  # 常见后缀
    '个人汉化', '個人漢化'  # 个人汉化
}

# 预处理原版关键词集合
ORIGINAL_VERSION_KEYWORDS = {
    'Digital', 'DL版', 'DL', 'デジタル版',  # 数字版本相关
    '出版', '出版社', '書店版', '通常版',  # 出版相关
    '無修正', '无修正', '无修', '無修',  # 无修正版本
    '完全版', '完整版', # 完整版本
    '全彩', '官方', 'カラー', # 全彩版本
    'カラー', '彩色', '彩色版', '彩色版', # 彩色版本
}

# 预处理黑名单关键词集合
BLACKLIST_KEYWORDS = {
    # 画集/图集相关
    'trash', '画集', '畫集', 'artbook', 'art book', 'art works', 'illustrations',
    '图集', '圖集', 'illust', 'collection',
    '杂图', '雜圖', '杂图合集', '雜圖合集',
    # 其他不需要处理的类型
    'pixiv', 'fanbox', 'gumroad', 'twitter',
    '待分类', '待處理', '待分類',
    '图包', '圖包',
    '图片', '圖片',
    'cg', 'CG',
    '02cos',
}

# 预处理所有关键词集合
_CHINESE_VERSION_KEYWORDS_FULL = preprocess_keywords(CHINESE_VERSION_KEYWORDS)
_ORIGINAL_VERSION_KEYWORDS_FULL = preprocess_keywords(ORIGINAL_VERSION_KEYWORDS)
_BLACKLIST_KEYWORDS_FULL = preprocess_keywords(BLACKLIST_KEYWORDS)

# 添加线程本地存储
thread_local = threading.local()

def clean_filename(filename: str) -> str:
    """清理文件名，只保留主文件名部分进行比较"""
    # 移除扩展名
    name = os.path.splitext(filename)[0]
    
    # 提取括号中的内容
    pattern_brackets = re.compile(r'\[([^\[\]]+)\]')  # 匹配方括号
    pattern_parentheses = re.compile(r'\(([^\(\)]+)\)')  # 匹配圆括号
    pattern_curly_brackets = re.compile(r'\{(.*?)\}')  # 匹配花括号
    hanhua_match = re.search(r'\[(.*?汉化.*?)\]', name)
    hanhua_info = hanhua_match.group(1) if hanhua_match else ''
    
    # 移除所有括号内容
    name = pattern_brackets.sub('', name)  # 移除所有方括号内容
    name = pattern_parentheses.sub('', name)  # 移除所有圆括号内容
    name = pattern_curly_brackets.sub('', name)  # 移除所有花括号内容
    # 清理多余空格
    # name = re.sub(r'\s+', ' ', name)  # 多个空格替换为单个
    name = re.sub(r'\s+', '', name)  # 完全去除所有空格
    name = name.strip().lower()  # 转换为小写并去除首尾空格
    
    # 返回清理后的名称和汉化信息
    return name, hanhua_info

@functools.lru_cache(maxsize=10000)
def is_chinese_version(filename: str) -> bool:
    """判断是否为汉化版本"""
    # 转换文件名为小写
    filename_lower = filename.lower()
    # 直接使用预处理好的关键词集合进行检查
    return any(keyword in filename_lower for keyword in _CHINESE_VERSION_KEYWORDS_FULL)

@functools.lru_cache(maxsize=10000)
def has_original_keywords(filename: str) -> bool:
    """检查是否包含原版特殊关键字"""
    # 转换文件名为小写
    filename_lower = filename.lower()
    # 直接使用预处理好的关键词集合进行检查
    return any(keyword in filename_lower for keyword in _ORIGINAL_VERSION_KEYWORDS_FULL)

# 使用 functools.lru_cache 装饰器缓存结果
@functools.lru_cache(maxsize=10000)
def is_in_blacklist(filepath: str) -> bool:
    """检查文件名或路径是否包含黑名单关键词"""
    # 转换路径为小写，只转换一次
    filepath_lower = str(filepath).lower()
    # 直接使用预处理好的关键词集合进行检查
    return any(keyword in filepath_lower for keyword in _BLACKLIST_KEYWORDS_FULL)

def is_besscan_version(filename: str) -> bool:
    """判断是否为別スキャン版本"""
    return '別スキャン' in filename

def group_similar_files(files: List[str]) -> Dict[str, List[str]]:
    """将相似文件分组"""
    groups: Dict[str, List[str]] = {}
    
    for file in files:
        # 检查文件是否在黑名单中
        if is_in_blacklist(file):
            logger.info("[#file_ops] ⏭️ 跳过黑名单文件: %s", file)
            continue
            
        clean_name, _ = clean_filename(file)
        if clean_name not in groups:
            groups[clean_name] = []
        groups[clean_name].append(file)
        
    return groups

def get_7zip_path() -> str:
    """获取7zip可执行文件路径"""
    # 常见的7zip安装路径
    possible_paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        os.path.join(os.getenv("ProgramFiles", ""), "7-Zip", "7z.exe"),
        os.path.join(os.getenv("ProgramFiles(x86)", ""), "7-Zip", "7z.exe"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return f'"{path}"'  # 用引号包裹路径
            
    # 如果找不到7zip，尝试使用命令行的7z
    try:
        subprocess.run(['7z'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return '7z'
    except:
        return None

def get_image_count(archive_path: str) -> int:
    """计算压缩包中的图片总数"""
    try:
        # 先尝试使用zipfile模块
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                # 统计支持的图片格式文件数量
                count = sum(1 for f in zf.namelist() 
                           if os.path.splitext(f.lower())[1] in IMAGE_EXTENSIONS)
                return count
        except zipfile.BadZipFile:
            # zipfile失败，尝试使用7z
            if not hasattr(thread_local, '7z_path'):
                thread_local.seven_zip_path = get_7zip_path()
                
            if thread_local.seven_zip_path:
                cmd = f'{thread_local.seven_zip_path} l "{archive_path}"'
                result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode == 0:
                    # 解析7z命令输出，计算图片文件数
                    lines = result.stdout.splitlines()
                    count = 0
                    for line in lines:
                        for ext in IMAGE_EXTENSIONS:
                            if line.lower().strip().endswith(ext):
                                count += 1
                    return count
            
            # 如果7z也失败了，记录错误并返回0
            logger.error("[#error_log] ❌ 无法打开压缩文件 %s", archive_path)
            return 0
    except Exception as e:
        logger.error("[#error_log] ❌ 统计图片数量失败 %s: %s", archive_path, str(e))
        return 0
def get_sample_images(archive_path: str, temp_dir: str, sample_count: int = 3) -> List[str]:
    """从压缩包中提取样本图片到临时目录"""
    try:
        with zipfile.ZipFile(archive_path, 'r') as zf:
            # 获取所有图片文件
            image_files = [(f, info.file_size) for f, info in 
                         ((f, zf.getinfo(f)) for f in zf.namelist())
                         if os.path.splitext(f.lower())[1] in IMAGE_EXTENSIONS]
            
            if not image_files:
                return []
            
            # 按文件大小排序
            image_files.sort(key=lambda x: x[1], reverse=True)
            
            # 选择样本
            samples = []
            if image_files:
                samples.append(image_files[0][0])  # 最大的文件
                if len(image_files) > 2:
                    samples.append(image_files[len(image_files)//2][0])  # 中间的文件
                
                # 从前30%选择剩余样本
                top_30_percent = image_files[:max(3, len(image_files) // 3)]
                while len(samples) < sample_count and top_30_percent:
                    sample = random.choice(top_30_percent)[0]
                    if sample not in samples:
                        samples.append(sample)
            
            # 提取选中的样本到临时目录
            extracted_files = []
            for sample in samples:
                temp_file = os.path.join(temp_dir, os.path.basename(sample))
                with zf.open(sample) as source, open(temp_file, 'wb') as target:
                    shutil.copyfileobj(source, target)
                if os.path.exists(temp_file):
                    extracted_files.append(temp_file)
                    
            return extracted_files
            
    except Exception as e:
        logger.error("[#error_log] ❌ 提取样本图片失败 %s: %s", archive_path, str(e))
        return []

def calculate_representative_width(archive_path: str, sample_count: int = 3) -> int:
    """计算压缩包中图片的代表宽度（使用抽样和中位数）"""
    try:
        # 检查文件扩展名
        ext = os.path.splitext(archive_path)[1].lower()
        if ext not in {'.zip', '.cbz'}:  # 只处理zip格式
            return 0

        # 获取压缩包中的文件信息
        image_files = []
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for info in zf.infolist():
                    if os.path.splitext(info.filename.lower())[1] in IMAGE_EXTENSIONS:
                        image_files.append((info.filename, info.file_size))
        except zipfile.BadZipFile:
            logger.info("[#error_log] ⚠️ 无效的ZIP文件: %s", archive_path)
            return 0

        if not image_files:
            return 0

        # 按文件大小排序
        image_files.sort(key=lambda x: x[1], reverse=True)
        
        # 选择样本
        samples = []
        if image_files:
            samples.append(image_files[0][0])  # 最大的文件
            if len(image_files) > 2:
                samples.append(image_files[len(image_files)//2][0])  # 中间的文件
            
            # 从前30%选择剩余样本
            top_30_percent = image_files[:max(3, len(image_files) // 3)]
            while len(samples) < sample_count and top_30_percent:
                sample = random.choice(top_30_percent)[0]
                if sample not in samples:
                    samples.append(sample)

        widths = []
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for sample in samples:
                    try:
                        # 直接从zip读取到内存
                        with zf.open(sample) as file:
                            img_data = file.read()
                            with Image.open(io.BytesIO(img_data)) as img:
                                widths.append(img.width)
                    except Exception as e:
                        logger.info("[#error_log] ⚠️ 读取图片宽度失败 %s: %s", sample, str(e))
                        continue
        except Exception as e:
            logger.info("[#error_log] ⚠️ 打开ZIP文件失败: %s", str(e))
            return 0

        if not widths:
            return 0

        # 使用中位数作为代表宽度
        return int(sorted(widths)[len(widths)//2])

    except Exception as e:
        logger.info("[#error_log] ❌ 计算代表宽度失败 %s: %s", archive_path, str(e))
        return 0

def extract_width_from_filename(filename: str) -> int:
    """从文件名中提取宽度信息，如果没有则返回0"""
    # 匹配[数字px]格式
    match = re.search(r'\[(\d+)px\]', filename)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return 0
    return 0

def safe_move_file(src_path: str, dst_path: str, max_retries: int = 3, delay: float = 1.0) -> bool:
    """
    安全地移动文件，包含重试机制和完整性检查
    
    Args:
        src_path: 源文件路径
        dst_path: 目标文件路径
        handler: 日志处理器
        max_retries: 最大重试次数
        delay: 重试延迟时间(秒)
        
    Returns:
        bool: 移动是否成功
    """
    import time
    import os
    
    # 确保源文件存在
    if not os.path.exists(src_path):
        logger.info("[#error_log] ❌ 源文件不存在: %s", src_path)
        return False
        
    # 确保源文件可读
    if not os.access(src_path, os.R_OK):
        logger.info("[#error_log] ❌ 源文件无法读取: %s", src_path)
        return False
        
    # 确保目标目录存在
    dst_dir = os.path.dirname(dst_path)
    try:
        os.makedirs(dst_dir, exist_ok=True)
    except Exception as e:
        logger.info("[#error_log] ❌ 创建目标目录失败: %s, 错误: %s", dst_dir, str(e))
        return False
        
    # 检查目标目录是否可写
    if not os.access(dst_dir, os.W_OK):
        logger.info("[#error_log] ❌ 目标目录无写入权限: %s", dst_dir)
        return False
        
    # 获取源文件大小
    try:
        src_size = os.path.getsize(src_path)
    except Exception as e:
        logger.info("[#error_log] ❌ 无法获取源文件大小: %s, 错误: %s", src_path, str(e))
        return False
        
    # 重试机制
    for attempt in range(max_retries):
        try:
            # 如果目标文件已存在，先尝试删除
            if os.path.exists(dst_path):
                try:
                    os.remove(dst_path)
                except Exception as e:
                    # 记录错误但继续尝试移动
                    logger.info("[#error_log] ⚠️ 无法删除已存在的目标文件: %s, 错误: %s", dst_path, str(e))
                    # 尝试使用其他方式处理
                    try:
                        # 1. 尝试使用临时文件名
                        temp_dst_path = dst_path + f".temp_{attempt}"
                        shutil.move(src_path, temp_dst_path)
                        # 如果移动到临时文件成功，再尝试重命名
                        os.replace(temp_dst_path, dst_path)
                        return True
                    except Exception as move_error:
                        logger.info("[#error_log] ⚠️ 使用临时文件移动失败: %s", str(move_error))
                        # 如果不是最后一次尝试，继续重试
                        if attempt < max_retries - 1:
                            time.sleep(delay)
                            continue
                        return False
            
            # 执行移动操作
            shutil.move(src_path, dst_path)
            
            # 验证移动后的文件
            if not os.path.exists(dst_path):
                raise Exception("目标文件不存在")
                
            # 检查文件大小是否一致
            dst_size = os.path.getsize(dst_path)
            if dst_size != src_size:
                raise Exception(f"文件大小不匹配: 源文件 {src_size} 字节, 目标文件 {dst_size} 字节")
                
            return True
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.info("[#error_log] ⚠️ 移动文件失败，尝试重试 (%d/%d): %s", attempt + 1, max_retries, str(e))
                time.sleep(delay)
                continue
            else:
                logger.info("[#error_log] ❌ 移动文件失败，已达到最大重试次数: %s", str(e))
                # 如果最后一次尝试失败，检查源文件是否还存在
                if not os.path.exists(src_path):
                    logger.info("[#error_log] ❌ 源文件已不存在: %s", src_path)
                return False
                
    return False

def process_file_with_count(file_path: str) -> Tuple[str, str, Dict[str, Union[int, float]]]:
    """处理单个文件，返回原始路径、新路径和所有指标"""
    full_path = file_path
    dir_name = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    name, ext = os.path.splitext(file_name)
    
    # 移除已有的标记
    name = re.sub(r'\{[^}]*\}', '', name)  # 移除所有花括号内容
    
    # 计算所有指标
    metrics = {
        'width': 0,
        'page_count': 0,
        'clarity_score': 0.0
    }
    
    # 首先尝试从原文件名提取页数信息
    page_match = re.search(r'\{(\d+)@PX\}', file_name)
    if page_match:
        metrics['page_count'] = int(page_match.group(1))
    else:
        # 如果文件名中没有页数信息，才计算页数
        metrics['page_count'] = get_image_count(full_path)
    
    # 计算宽度
    metrics['width'] = calculate_representative_width(full_path)
    
    # 计算清晰度评分
    try:
        with zipfile.ZipFile(full_path, 'r') as zf:
            image_files = [f for f in zf.namelist() if os.path.splitext(f.lower())[1] in IMAGE_EXTENSIONS]
            if image_files:
                sample_files = random.sample(image_files, min(5, len(image_files)))
                scores = []
                for sample in sample_files:
                    with zf.open(sample) as f:
                        img_data = f.read()
                        scores.append(ImageClarityEvaluator.calculate_definition(img_data))
                metrics['clarity_score'] = sum(scores) / len(scores) if scores else 0.0
                
    except Exception as e:
        logger.error("[#error_log] 清晰度计算失败 %s: %s", file_path, str(e))
    
    # 生成属性字符串，所有属性放在一个大括号内
    parts = []
    if metrics['width'] > 0:
        parts.append(f"{shorten_number_cn(metrics['width'], use_w=True)}@WD")
    if metrics['page_count'] > 0:
        parts.append(f"{shorten_number_cn(metrics['page_count'], use_w=True)}@PX")
    if metrics['clarity_score'] > 0:
        parts.append(f"{shorten_number_cn(int(metrics['clarity_score']), use_w=True)}@DE")
    
    metrics_str = "{" + ",".join(parts) + "}" if parts else ""
    new_name = f"{name}{metrics_str}{ext}"
    new_path = os.path.join(dir_name, new_name) if dir_name else new_name
    
    return file_path, new_path, metrics

def process_file_group(group_files: List[str], base_dir: str, trash_dir: str, report_generator: ReportGenerator, create_shortcuts: bool = False, enable_multi_main: bool = False) -> None:
    """处理一组相似文件"""
    # 获取组的基础名称
    group_base_name, _ = clean_filename(group_files[0])
    
    # 生成组ID（使用组名的哈希值后4位作为组ID）
    group_id = abs(hash(group_base_name)) % 10000
    
    # 过滤掉黑名单文件
    filtered_files = [f for f in group_files if not is_in_blacklist(f)]
    if not filtered_files:
        logger.info("[#group_info] ⏭️ 组[%s]跳过: 所有文件都在黑名单中", group_base_name)
        return
        
    # 分离汉化版本和其他版本，并使用完整路径
    chinese_versions = []
    other_versions = []
    for f in filtered_files:
        full_path = os.path.join(base_dir, f)
        if is_chinese_version(f):
            chinese_versions.append(full_path)
        else:
            other_versions.append(full_path)
    
    # 检查汉化版本中是否有包含原版关键词的
    chinese_has_original = any(has_original_keywords(f) for f in chinese_versions)
    
    # 如果汉化版本中没有原版关键词，则将其他版本中包含原版关键词的也归为需要保留的版本
    if not chinese_has_original:
        original_keyword_versions = [f for f in other_versions if has_original_keywords(os.path.basename(f))]
        if original_keyword_versions:
            chinese_versions.extend(original_keyword_versions)
            other_versions = [f for f in other_versions if not has_original_keywords(os.path.basename(f))]
            logger.info("[#file_ops] 📝 将%d个包含原版关键词的文件归入保留列表", len(original_keyword_versions))
    
    # 为每个文件添加图片数量标记和计算宽度
    processed_files = []
    file_metrics = {}  # 存储每个文件的指标
    
    # 第一轮：计算所有文件的指标，直接使用完整路径
    for file in chinese_versions + other_versions:
        old_path, new_path, metrics = process_file_with_count(file)  # 现在传入的是完整路径
        processed_files.append((old_path, new_path))
        file_metrics[old_path] = metrics
    
    # 找出最优指标
    best_metrics = {
        'width': max((m['width'] for m in file_metrics.values()), default=0),
        'page_count': min((m['page_count'] for m in file_metrics.values() if m['page_count'] > 0), default=0),
        'clarity_score': max((m['clarity_score'] for m in file_metrics.values()), default=0)
    }
    
    # 检查指标是否统一
    metrics_same = {
        'width': len(set(m['width'] for m in file_metrics.values() if m['width'] > 0)) <= 1,
        'page_count': len(set(m['page_count'] for m in file_metrics.values() if m['page_count'] > 0)) <= 1,
        'clarity_score': len(set(m['clarity_score'] for m in file_metrics.values() if m['clarity_score'] > 0)) <= 1
    }
    
    # 第二轮：重命名文件，添加带emoji的指标
    updated_files = []
    for old_path, _ in processed_files:
        metrics = file_metrics[old_path]
        parts = []
        
        # 添加组ID
        parts.append(f"🪆G{group_id:04d}")
        
        # 添加宽度（如果不是统一值且是最优值则添加表情）
        if metrics['width'] > 0:
            width_str = f"{shorten_number_cn(metrics['width'], use_w=True)}@WD"
            if not metrics_same['width'] and metrics['width'] == best_metrics['width']:
                width_str = f"📏{width_str}"
            parts.append(width_str)
        
        # 添加页数（如果不是统一值且是最优值则添加表情）
        if metrics['page_count'] > 0:
            page_str = f"{shorten_number_cn(metrics['page_count'], use_w=True)}@PX"
            if not metrics_same['page_count'] and metrics['page_count'] == best_metrics['page_count']:
                page_str = f"📄{page_str}"
            parts.append(page_str)
        
        # 添加清晰度（如果不是统一值且是最优值则添加表情）
        if metrics['clarity_score'] > 0:
            clarity_str = f"{shorten_number_cn(int(metrics['clarity_score']), use_w=True)}@DE"
            if not metrics_same['clarity_score'] and metrics['clarity_score'] == best_metrics['clarity_score']:
                clarity_str = f"🔍{clarity_str}"
            parts.append(clarity_str)
        
        # 构建新文件名
        dir_name = os.path.dirname(old_path)
        file_name = os.path.basename(old_path)
        name, ext = os.path.splitext(file_name)
        name = re.sub(r'\{[^}]*\}', '', name)  # 移除已有的指标
        metrics_str = "{" + ",".join(parts) + "}" if parts else ""
        new_name = f"{metrics_str}{name}{ext}"
        new_path = os.path.join(dir_name, new_name)
        
        # 重命名文件
        old_full_path = os.path.join(base_dir, old_path)
        new_full_path = os.path.join(base_dir, new_path)
        try:
            os.rename(old_full_path, new_full_path)
            updated_files.append((old_path, new_path))
            logger.info("[#file_ops] ✅ 已重命名: %s -> %s", old_path, new_path)
        except Exception as e:
            logger.error("[#error_log] ❌ 重命名失败 %s: %s", old_path, str(e))
            updated_files.append((old_path, old_path))
    
    # 更新文件路径
    chinese_versions = [new_path for old_path, new_path in updated_files if old_path in chinese_versions]
    other_versions = [new_path for old_path, new_path in updated_files if old_path in other_versions]
    
    # 处理文件移动逻辑
    if chinese_versions:
        # 有汉化版本的情况
        if len(chinese_versions) > 1:
            # 多个汉化版本，移动到multi
            multi_dir = os.path.join(base_dir, 'multi')
            os.makedirs(multi_dir, exist_ok=True)
            
            # 如果启用了multi-main功能，找到最大的文件作为主文件
            if enable_multi_main:
                main_file = max(chinese_versions, key=lambda x: os.path.getsize(os.path.join(base_dir, x)))
                if handle_multi_main_file(main_file, base_dir):
                    logger.info("[#file_ops] ✅ 已处理multi-main文件: %s", main_file)
            
            # 移动所有文件到multi目录
            for file in chinese_versions:
                src_path = os.path.join(base_dir, file)
                rel_path = os.path.relpath(src_path, base_dir)
                dst_path = os.path.join(multi_dir, rel_path)
                if safe_move_file(src_path, dst_path):
                    logger.info("[#file_ops] ✅ 已移动到multi: %s", file)
                    report_generator.update_stats('moved_to_multi')
            
            # 移动其他非原版到trash
            for other_file in other_versions:
                src_path = os.path.join(base_dir, other_file)
                rel_path = os.path.relpath(src_path, base_dir)
                dst_path = os.path.join(trash_dir, rel_path)
                if create_shortcuts:
                    shortcut_path = os.path.splitext(dst_path)[0]
                    if create_shortcut(src_path, shortcut_path):
                        logger.info("[#file_ops] ✅ 已创建快捷方式: %s", other_file)
                        report_generator.update_stats('created_shortcuts')
                else:
                    if safe_move_file(src_path, dst_path):
                        logger.info("[#file_ops] ✅ 已移动到trash: %s", other_file)
                        report_generator.update_stats('moved_to_trash')
        else:
            # 只有一个需要保留的版本
            logger.info("[#group_info] 🔍 组[%s]处理: 发现1个需要保留的版本，保持原位置", group_base_name)
            # 移动其他版本到trash
            for other_file in other_versions:
                src_path = os.path.join(base_dir, other_file)
                rel_path = os.path.relpath(src_path, base_dir)
                dst_path = os.path.join(trash_dir, rel_path)
                if create_shortcuts:
                    shortcut_path = os.path.splitext(dst_path)[0]
                    if create_shortcut(src_path, shortcut_path):
                        logger.info("[#file_ops] ✅ 已创建快捷方式: %s", other_file)
                        report_generator.update_stats('created_shortcuts')
                else:
                    if safe_move_file(src_path, dst_path):
                        logger.info("[#file_ops] ✅ 已移动到trash: %s", other_file)
                        report_generator.update_stats('moved_to_trash')
    else:
        # 没有汉化版本的情况
        if len(other_versions) > 1:
            # 多个原版，移动到multi
            multi_dir = os.path.join(base_dir, 'multi')
            os.makedirs(multi_dir, exist_ok=True)
            
            # 如果启用了multi-main功能，找到最大的文件作为主文件
            if enable_multi_main:
                main_file = max(other_versions, key=lambda x: os.path.getsize(os.path.join(base_dir, x)))
                # 创建主文件的副本
                if handle_multi_main_file(main_file, base_dir):
                    logger.info("[#file_ops] ✅ 已处理multi-main文件: %s", main_file)
            
            # 移动所有文件到multi目录
            for file in other_versions:
                src_path = os.path.join(base_dir, file)
                rel_path = os.path.relpath(src_path, base_dir)
                dst_path = os.path.join(multi_dir, rel_path)
                if safe_move_file(src_path, dst_path):
                    logger.info("[#file_ops] ✅ 已移动到multi: %s", file)
                    report_generator.update_stats('moved_to_multi')
            logger.info("[#group_info] 🔍 组[%s]处理: 未发现汉化版本，发现%d个原版，已移动到multi", group_base_name, len(other_versions))
        else:
            # 单个原版，保持原位置
            logger.info("[#group_info] 🔍 组[%s]处理: 未发现汉化版本，仅有1个原版，保持原位置")

def process_directory(directory: str, report_generator: ReportGenerator, dry_run: bool = False, create_shortcuts: bool = False, enable_multi_main: bool = False) -> None:
    """处理单个目录"""
    # 创建trash目录
    trash_dir = os.path.join(directory, 'trash')
    if not dry_run:
        os.makedirs(trash_dir, exist_ok=True)
    
    # 收集所有压缩文件
    all_files = []
    logger.info("[#process] 🔍 正在扫描文件...")
    
    for root, _, files in os.walk(directory):
        # 跳过trash和multi目录
        if 'trash' in root or 'multi' in root:
            logger.info("[#file_ops] ⏭️ 跳过目录: %s", root)
            continue
            
        for file in files:
            # 使用新定义的ARCHIVE_EXTENSIONS
            if os.path.splitext(file.lower())[1] in ARCHIVE_EXTENSIONS:
                rel_path = os.path.relpath(os.path.join(root, file), directory)
                all_files.append(rel_path)
                # 更新扫描进度
                logger.info("[@process] 扫描进度: %d/%d", len(all_files), len(all_files))
    
    if not all_files:
        logger.info("[#error_log] ⚠️ 目录 %s 中未找到压缩文件", directory)
        return
        
    # 更新报告统计
    report_generator.update_stats('total_files', len(all_files))
    
    # 对文件进行分组
    groups = group_similar_files(all_files)
    logger.info("[#stats] 📊 总计: %d个文件, %d个组", len(all_files), len(groups))
    
    # 更新报告统计
    report_generator.update_stats('total_groups', len(groups))
    
    # 创建进程池进行并行处理
    logger.info("[#process] 🔄 开始处理文件组...")
    
    with ThreadPoolExecutor(max_workers=min(os.cpu_count() * 2, 8)) as executor:
        # 创建任务列表
        futures = []
        for _, group_files in groups.items():
            if len(group_files) > 1:  # 只处理有多个版本的组
                future = executor.submit(
                    process_file_group,
                    group_files,
                    directory,
                    trash_dir,
                    report_generator,
                    create_shortcuts,
                    enable_multi_main
                )
                futures.append(future)
        
        # 更新组处理进度
        completed = 0
        for _ in as_completed(futures):
            completed += 1
            future_count = len(futures)
            scan_percent = completed / future_count * 100
            
            logger.info("[@stats] 组进度: (%d/%d) %.2f%%", completed, future_count, scan_percent)

def get_paths_from_clipboard():
    """从剪贴板读取多行路径"""
    try:
        clipboard_content = pyperclip.paste()
        if not clipboard_content:
            return []
            
        # 分割多行内容并清理
        paths = [
            path.strip().strip('"').strip("'")
            for path in clipboard_content.splitlines() 
            if path.strip()
        ]
        
        # 验证路径是否存在
        valid_paths = [
            path for path in paths 
            if os.path.exists(path)
        ]
        
        if valid_paths:
            logger.info("[#file_ops] 📋 从剪贴板读取到 %d 个有效路径", len(valid_paths))
        else:
            logger.info("[#error_log] ⚠️ 剪贴板中没有有效路径")
            
        return valid_paths
        
    except Exception as e:
        logger.info("[#error_log] ❌ 读取剪贴板时出错: %s", e)
        return []

def get_long_path_name(path_str: str) -> str:
    """转换为长路径格式"""
    if not path_str.startswith("\\\\?\\"):
        if os.path.isabs(path_str):
            return "\\\\?\\" + path_str
    return path_str

def safe_path(path: str) -> str:
    """确保路径支持长文件名"""
    try:
        abs_path = os.path.abspath(path)
        return get_long_path_name(abs_path)
    except Exception as e:
        # add_error_log(f"❌ 处理路径时出错 {path}: {e}")
        return path

def process_paths(paths: List[str]) -> List[str]:
    """处理输入的路径列表"""
    TextualLoggerManager.set_layout(TEXTUAL_LAYOUT,config_info['log_file'])

    # 过滤掉空路径和引号
    valid_paths = []
    for path in paths:
        # 移除路径两端的引号和空白字符
        path = path.strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        elif path.startswith("'") and path.endswith("'"):
            path = path[1:-1]
        
        if path:
            # 尝试转换路径编码
            try:
                # 使用安全的路径处理
                safe_path_str = safe_path(path)
                if os.path.exists(safe_path_str):
                    valid_paths.append(safe_path_str)
                else:
                    logger.info("[#error_log] ❌ 路径不存在或无法访问: %s", path)
            except Exception as e:
                logger.info("[#error_log] ❌ 处理路径时出错: %s, 错误: %s", path, str(e))
    
    if not valid_paths:
        logger.info("[#error_log] ⚠️ 没有有效的路径")
        
    return valid_paths

def create_shortcut(src_path: str, dst_path: str) -> bool:
    """创建指向源文件的快捷方式"""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(dst_path + ".lnk")
        shortcut.Targetpath = src_path
        shortcut.save()
        return True
    except Exception as e:
        logger.error("[#error_log] 创建快捷方式失败: %s", str(e))
        return False

def handle_multi_main_file(file_path: str, base_dir: str) -> Optional[str]:
    """
    处理multi主文件：创建副本并添加[multi-main]标记
    
    Args:
        file_path: 文件的相对路径
        base_dir: 基础目录
        
    Returns:
        Optional[str]: 成功时返回新文件的相对路径，失败时返回None
    """
    try:
        # 构建完整路径
        full_path = os.path.join(base_dir, file_path)
        dir_name = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        name, ext = os.path.splitext(file_name)
        
        # 创建新文件名（添加[multi-main]标记）
        new_name = f"{name}[multi-main]{ext}"
        new_rel_path = os.path.join(dir_name, new_name) if dir_name else new_name
        new_full_path = os.path.join(base_dir, new_rel_path)
        
        # 复制文件
        shutil.copy2(full_path, new_full_path)
        logger.info("[#file_ops] ✅ 已创建multi-main副本: %s", new_rel_path)
        return new_rel_path
    except Exception as e:
        logger.error("[#error_log] ❌ 创建multi-main副本失败 %s: %s", file_path, str(e))
        return None

def setup_cli_parser():
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(description='处理重复压缩包文件')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-c', '--clipboard', action='store_true', help='从剪贴板读取路径')
    group.add_argument('-p', '--paths', nargs='+', help='要处理的目录路径')
    parser.add_argument('-s', '--sample-count', type=int, default=3, help='每个压缩包抽取的图片样本数量（默认3）')
    parser.add_argument('--create-shortcuts', action='store_true', help='创建快捷方式而不是移动文件')
    parser.add_argument('--enable-multi-main', action='store_true', help='为每个multi组创建主文件副本')
    parser.add_argument('--report', type=str, help='指定报告文件名（默认为"处理报告_时间戳.md"）')
    return parser

def run_application(args):
    """运行应用程序的主函数"""
    # 获取要处理的路径
    paths = []
    
    # 从剪贴板读取
    if hasattr(args, 'clipboard') and args.clipboard:
        paths.extend(get_paths_from_clipboard())
    # 从命令行参数读取
    elif hasattr(args, 'paths') and args.paths:
        if isinstance(args.paths, str):
            # 如果是TUI模式传入的字符串，按逗号分割
            paths.extend([p.strip() for p in args.paths.split(',') if p.strip()])
        else:
            # 命令行模式传入的列表
            paths.extend(args.paths)
    # 默认从终端输入
    else:
        print("请输入要处理的路径（每行一个，输入空行结束）：")
        while True:
            try:
                line = input().strip()
                if not line:  # 空行结束输入
                    break
                paths.append(line)
            except EOFError:
                break
            except KeyboardInterrupt:
                print("用户取消输入")
                return False
        
    if not paths:
        logger.info("[#error_log] ❌ 未提供任何路径")
        return False
        
    # 处理和验证所有路径
    valid_paths = process_paths(paths)
    
    if not valid_paths:
        logger.info("[#error_log] ❌ 没有有效的路径可处理")
        return False
    
    # 创建报告生成器
    report_generator = ReportGenerator()
    
    # 处理每个路径
    for path in valid_paths:
        logger.info("[#process] 🚀 开始处理目录: %s", path)
        process_directory(
            path,
            report_generator,
            create_shortcuts=args.create_shortcuts if hasattr(args, 'create_shortcuts') else False,
            enable_multi_main=args.enable_multi_main if hasattr(args, 'enable_multi_main') else False
        )
        logger.info("[#process] ✨ 目录处理完成: %s", path)
        
        # 生成并保存报告
        if hasattr(args, 'report') and args.report:
            report_path = report_generator.save_report(path, args.report)
        else:
            report_path = report_generator.save_report(path)
            
        if report_path:
            logger.info("[#process] 📝 报告已保存到: %s", report_path)
        else:
            logger.info("[#error_log] ❌ 保存报告失败")
    
    return True

def main():
    """主函数"""
    parser = setup_cli_parser()
    
    # 创建预设配置
    preset_configs = {
        "基本模式": {
            "description": "从剪贴板读取路径，执行标准处理",
            "checkbox_options": ["--clipboard"],
            "input_values": {}
        },
        "快捷方式模式": {
            "description": "创建快捷方式而不是移动文件",
            "checkbox_options": ["--clipboard", "--create-shortcuts"],
            "input_values": {}
        },
        "多文件保留模式": {
            "description": "为每个multi组创建主文件副本",
            "checkbox_options": ["--clipboard", "--enable-multi-main"],
            "input_values": {}
        },
        "完整模式": {
            "description": "启用所有高级功能",
            "checkbox_options": ["--clipboard", "--create-shortcuts", "--enable-multi-main"],
            "input_values": {
                "--sample-count": "5"
            }
        }
    }
    
    # 检查是否有命令行参数
    has_args = len(sys.argv) > 1
    
    if has_args:
        # 直接通过命令行参数运行
        args = parser.parse_args(sys.argv[1:])
        run_application(args)
    else:
        # 使用rich_preset配置界面
        from rich_preset import create_config_app
        
        result = create_config_app(
            program=sys.argv[0],
            title="文件去重工具配置",
            parser=parser,
            preset_configs=preset_configs
        )
        
        if result:
            run_application(result.args)
        else:
            print("操作已取消")

if __name__ == "__main__":
    main()