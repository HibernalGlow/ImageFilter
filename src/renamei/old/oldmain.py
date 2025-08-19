import os
import re
import zipfile
import tempfile
import shutil
import argparse
import pyperclip
import sys
import subprocess
import time  # 添加time模块导入
import hashlib
from PIL import Image
import io
from concurrent.futures import ProcessPoolExecutor, as_completed
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from queue import Queue
from threading import Lock
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
        enqueue=True,     )
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

logger, config_info = setup_logger(app_name="app_name", console_output=True)

class InputHandler:
    """输入处理类"""
    @staticmethod
    def parse_arguments():
        parser = argparse.ArgumentParser(description='图片文件名清理工具')
        parser.add_argument('--clipboard', '-c', action='store_true', help='从剪贴板读取路径')
        parser.add_argument('--mode', '-m', choices=['image', 'zip'], help='处理模式：image(图片文件) 或 zip(压缩包)')
        parser.add_argument('path', nargs='*', help='要处理的文件或目录路径')
        return parser.parse_args()

    @staticmethod
    def get_paths_from_clipboard():
        """从剪贴板读取多行路径"""
        try:
            clipboard_content = pyperclip.paste()
            if not clipboard_content:
                return []
            paths = [path.strip().strip('"') for path in clipboard_content.splitlines() if path.strip()]
            valid_paths = [path for path in paths if os.path.exists(path)]
            if valid_paths:
                print(f'从剪贴板读取到 {len(valid_paths)} 个有效路径')
            else:
                print('剪贴板中没有有效路径')
            return valid_paths
        except Exception as e:
            print(f'读取剪贴板时出错: {e}')
            return []

    @staticmethod
    def get_input_paths(args):
        """获取输入路径"""
        paths = []
        
        # 从命令行参数获取路径
        if args.path:
            paths.extend(args.path)
            
        # 从剪贴板获取路径
        if args.clipboard:
            paths.extend(InputHandler.get_paths_from_clipboard())
            
        # 如果没有路径，提示用户输入
        if not paths:
            print("请输入要处理的文件夹或压缩包路径（每行一个，输入空行结束）：")
            while True:
                line = input().strip()
                if not line:
                    break
                path = line.strip().strip('"').strip("'")
                if os.path.exists(path):
                    paths.append(path)
                    print(f"✅ 已添加有效路径: {path}")
                else:
                    print(f"❌ 路径不存在: {path}")
                
        return [p for p in paths if os.path.exists(p)]

def backup_file(file_path, original_path, input_base_path):
    """备份文件到统一回收站目录，保持从输入路径开始的完整目录结构"""
    try:
        # 构建备份路径
        backup_base = r"E:\2EHV\.trash"
        # 计算相对路径（从输入路径开始）
        rel_path = os.path.relpath(os.path.dirname(original_path), input_base_path)
        backup_dir = os.path.join(backup_base, rel_path)
        
        # 确保备份目录存在
        os.makedirs(backup_dir, exist_ok=True)
        
        # 复制文件到备份目录
        backup_path = os.path.join(backup_dir, os.path.basename(original_path))
        shutil.copy2(file_path, backup_path)
        print(f"已备份: {backup_path}")
    except Exception as e:
        print(f"备份失败 {original_path}: {e}")

def is_ad_image(filename):
    """检查文件名是否匹配广告图片模式"""
    # 广告图片的关键词模式
    ad_patterns = [
        r'招募',
        r'credit',
        r'广告',
        r'[Cc]redit[s]?',
        r'宣传',
        r'招新',
        r'ver\.\d+\.\d+',
        r'YZv\.\d+\.\d+',
        r'绅士快乐',
        r'粉丝群',
        r'z{3,}',
        r'無邪気'
    ]
    
    # 合并所有模式为一个正则表达式
    combined_pattern = '|'.join(ad_patterns)
    if not is_image_file(filename):
        return False
    result = bool(re.search(combined_pattern, filename))
    return result

def handle_ad_file(file_path, input_base_path):
    """处理广告文件：备份并删除"""
    try:
        print(f"⚠️ 检测到广告图片: {os.path.basename(file_path)}")
        # 备份文件操作已移到调用处
        # 删除文件
        os.remove(file_path)
        print(f"✅ 已删除广告图片")
        return True
    except Exception as e:
        print(f"❌ 删除广告图片失败: {str(e)}")
        return False

def rename_images_in_directory(dir_path):
    processed_count = 0
    skipped_count = 0
    removed_ads_count = 0  # 新增广告图片计数
    
    # 获取总文件数
    total_files = sum(1 for root, _, files in os.walk(dir_path) 
                     for f in files if f.lower().endswith(('.jpg', '.png', '.avif', '.jxl', 'webp')))
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("处理图片文件...", total=total_files)
        
        # 遍历目录中的所有文件
        for root, dirs, files in os.walk(dir_path):
            for filename in files:
                if filename.lower().endswith(('.jpg', '.png', '.avif', '.jxl', 'webp')):
                    progress.update(task, description=f"处理: {filename}")
                    
                    # 检查是否为广告图片
                    file_path = os.path.join(root, filename)
                    if is_ad_image(filename):
                        # 只有删除前才备份
                        backup_file(file_path, file_path, dir_path)
                        if handle_ad_file(file_path, dir_path):
                            removed_ads_count += 1
                        progress.advance(task)
                        continue
                    
                    # 匹配文件名中的 [hash-xxxxxx] 模式
                    new_filename = re.sub(r'\[hash-[0-9a-fA-F]+\]', '', filename)
                    
                    # 如果文件名发生了变化
                    if new_filename != filename:
                        old_path = os.path.join(root, filename)
                        new_path = os.path.join(root, new_filename)
                        print(f"\n📝 处理文件: {filename}")
                        print(f"   新文件名: {new_filename}")
                        
                        # 如果目标文件已存在，先删除它
                        if os.path.exists(new_path):
                            try:
                                print(f"⚠️ 目标文件已存在，进行备份...")
                                backup_file(new_path, new_path, dir_path)
                                os.remove(new_path)
                            except Exception as e:
                                print(f"❌ 处理已存在的文件失败: {str(e)}")
                                skipped_count += 1
                                continue
                        
                        try:
                            # 只有确定要重命名时才备份原文件
                            backup_file(old_path, old_path, dir_path)
                            # 直接重命名
                            os.rename(old_path, new_path)
                            processed_count += 1
                            print(f"✅ 重命名成功")
                        except Exception as e:
                            print(f"❌ 重命名失败: {str(e)}")
                            skipped_count += 1
                    else:
                        skipped_count += 1
                    progress.advance(task)
    
    print(f"\n📊 处理完成:")
    print(f"   - 成功处理: {processed_count} 个文件")
    print(f"   - 删除广告: {removed_ads_count} 个文件")
    print(f"   - 跳过处理: {skipped_count} 个文件")

def has_hash_files_in_zip(zip_path):
    """快速检查压缩包中是否有包含[hash-]的文件"""
    try:
        # 使用7z列出文件
        list_cmd = ['7z', 'l', zip_path]
        result = subprocess.run(list_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"⚠️ 检查压缩包失败 {zip_path}: {result.stderr}")
            return True  # 如果检查失败，仍然继续处理
            
        # 检查文件名中是否包含[hash-]
        return '[hash-' in result.stdout
        
    except Exception as e:
        print(f"⚠️ 检查压缩包失败 {zip_path}: {e}")
        return True  # 如果出现异常，仍然继续处理
def is_image_file(filename):
    """检查文件是否为图片文件"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.avif', '.jxl', '.tiff', '.tif'}
    ext = os.path.splitext(filename.lower())[1]
    return ext in image_extensions

def process_with_bandizip(zip_path, temp_dir, trash_dir=None):
    """使用 Bandizip 命令行工具处理压缩包"""
    try:
        # 准备trash_dir路径，但不创建
        if trash_dir is None:
            zip_basename = os.path.basename(zip_path)
            zip_dirname = os.path.dirname(zip_path)
            trash_dir = os.path.join(zip_dirname, f"{zip_basename}.trash")
        
        has_created_trash_dir = os.path.exists(trash_dir)  # 跟踪trash目录是否已创建
        
        # 使用 Bandizip 解压文件
        extract_cmd = ['bz', 'x', '-o:', f'"{temp_dir}"', f'"{zip_path}"']
        result = subprocess.run(' '.join(extract_cmd), shell=True, capture_output=True, encoding='utf-8', errors='ignore')
        
        if result.returncode != 0:
            print(f"❌ Bandizip 解压失败: {result.stderr}")
            return False
        
        # 处理广告图片
        ads_found = False
        for root, _, files in os.walk(temp_dir):
            files
            for filename in files:
                
                if is_ad_image(filename):
                    # 当找到第一个广告图片时创建trash目录
                    if not has_created_trash_dir:
                        os.makedirs(trash_dir, exist_ok=True)
                        print(f"📁 创建回收站目录: {trash_dir}")
                        has_created_trash_dir = True
                    
                    file_path = os.path.join(root, filename)
                    # 将广告图片复制到回收站
                    shutil.copy2(file_path, os.path.join(trash_dir, filename))
                    print(f"⚠️ 检测到广告图片并保存到回收站: {filename}")
                    # 删除原文件
                    os.remove(file_path)
                    print(f"✅ 已删除广告图片")
                    ads_found = True
            
        # 重命名文件
        renamed = False
        for root, _, files in os.walk(temp_dir):
            for filename in files:
                new_filename = re.sub(r'\[hash-[0-9a-fA-F]+\]', '', filename)
                if new_filename != filename:
                    old_path = os.path.join(root, filename)
                    new_path = os.path.join(root, new_filename)
                    try:
                        if os.path.exists(new_path):
                            # 只有在存在冲突时才创建trash目录
                            if not has_created_trash_dir:
                                os.makedirs(trash_dir, exist_ok=True)
                                print(f"📁 创建回收站目录: {trash_dir}")
                                has_created_trash_dir = True
                            
                            # 保存已存在的文件到回收站
                            hash_trash_dir = os.path.join(trash_dir, "hash_renamed")
                            os.makedirs(hash_trash_dir, exist_ok=True)
                            shutil.copy2(new_path, os.path.join(hash_trash_dir, new_filename))
                            print(f"已保存冲突文件到回收站: {new_filename}")
                            os.remove(new_path)
                        os.rename(old_path, new_path)
                        print(f"重命名: {filename} -> {new_filename}")
                        renamed = True
                    except Exception as e:
                        print(f"⚠️ 重命名失败 {filename}: {str(e)}")
                        continue
        
        if renamed or ads_found:  # 只在需要时重新打包
            # 使用 Bandizip 重新打包
            create_cmd = ['bz', 'c', '-l:9', f'"{zip_path}"', f'"{temp_dir}\\*"']
            result = subprocess.run(' '.join(create_cmd), shell=True, capture_output=True, encoding='utf-8', errors='ignore')
            
            if result.returncode == 0:
                print(f"✅ Bandizip 打包成功：{zip_path}")
                return True
            else:
                print(f"❌ Bandizip 打包失败: {result.stderr}")
                return False
        else:
            print("✅ 无需修改，跳过重新打包")
            return True
        
    except Exception as e:
        print(f"❌ Bandizip 处理出错: {str(e)}")
        return False

def get_image_content_hash(file_path):
    """获取图片内容的哈希值"""
    try:
        with open(file_path, 'rb') as f:
            # 读取文件内容
            content = f.read()
            # 计算SHA256哈希
            return hashlib.sha256(content).hexdigest()
    except Exception as e:
        print(f"⚠️ 计算图片哈希失败 {file_path}: {str(e)}")
        return None

def get_file_creation_time(file_path):
    """获取文件创建时间"""
    try:
        return os.path.getctime(file_path)
    except Exception:
        return 0

def handle_duplicate_files_with_trash(duplicate_files, temp_dir, trash_dir):
    """处理重名文件，比较内容并保留最早的版本，将删除的文件保存到回收站"""
    for filename, count in duplicate_files.items():
        print(f"\n检查重名文件: {filename}")
        # 收集所有同名文件
        same_name_files = []
        for root, _, files in os.walk(temp_dir):
            for f in files:
                new_name = re.sub(r'\[hash-[0-9a-fA-F]+\]', '', f)
                if new_name == filename:
                    full_path = os.path.join(root, f)
                    same_name_files.append((full_path, get_file_creation_time(full_path), f))
        
        if not same_name_files:
            continue
            
        # 按创建时间排序
        same_name_files.sort(key=lambda x: x[1])
        
        # 获取第一个文件的哈希值作为参考
        reference_hash = get_image_content_hash(same_name_files[0][0])
        if reference_hash is None:
            print(f"❌ 无法比较文件内容，跳过处理: {filename}")
            continue
            
        # 保留最早的文件，删除其他相同内容的文件
        keep_file = same_name_files[0][0]
        for file_path, _, orig_filename in same_name_files[1:]:
            current_hash = get_image_content_hash(file_path)
            if current_hash == reference_hash:
                print(f"保存重复文件到回收站: {orig_filename}")
                # 复制到回收站然后删除
                shutil.copy2(file_path, os.path.join(trash_dir, orig_filename))
                os.remove(file_path)
            else:
                print(f"⚠️ 发现内容不同的同名文件: {os.path.basename(file_path)}")
                # 为不同内容的文件添加序号
                dir_path = os.path.dirname(file_path)
                base_name, ext = os.path.splitext(filename)
                new_name = f"{base_name}_1{ext}"
                counter = 1
                while os.path.exists(os.path.join(dir_path, new_name)):
                    counter += 1
                    new_name = f"{base_name}_{counter}{ext}"
                os.rename(file_path, os.path.join(dir_path, new_name))
                print(f"重命名为: {new_name}")
        
        print(f"保留最早的文件: {os.path.basename(keep_file)}")
    return True

def needs_modification_in_zip(zip_path):
    """检查压缩包是否需要进行修改"""
    try:
        # 检查是否有广告图片
        list_cmd = ['7z', 'l', '-slt', zip_path]
        result = subprocess.run(list_cmd, capture_output=True, encoding='utf-8', errors='ignore')
        
        # 检查广告图片
        for line in result.stdout.split('\n'):
            if line.startswith('Path = '):
                current_file = line[7:].strip()
                if current_file and is_ad_image(current_file):
                    return True  # 有广告图片需要删除
        
        # 检查是否有hash文件
        if '[hash-' in result.stdout:
            return True  # 有hash文件需要重命名
            
        return False  # 不需要修改
    except Exception as e:
        print(f"⚠️ 检查压缩包是否需要修改失败: {str(e)}")
        return True  # 如果检查失败，假设需要修改以保险

def rename_images_in_zip(zip_path, input_base_path):
    # 先检查是否需要修改
    need_modification = needs_modification_in_zip(zip_path)
    if not need_modification:
        # print(f"✅ 压缩包不需要任何修改，跳过: {os.path.basename(zip_path)}")
        return
        
    # 确实需要修改时才备份
    backup_file(zip_path, zip_path, input_base_path)
    
    # 准备trash目录路径，但先不创建
    zip_basename = os.path.basename(zip_path)
    zip_dirname = os.path.dirname(zip_path)
    trash_dir = os.path.join(zip_dirname, f"{zip_basename}.trash")
    
    # 检查是否有广告图片
    try:
        # 使用7z列出文件
        list_cmd = ['7z', 'l', '-slt', zip_path]
        result = subprocess.run(list_cmd, capture_output=True, encoding='utf-8', errors='ignore')
        
        # 解析文件列表
        files_to_delete = []
        total_image_count = 0  # 用于统计压缩包中的图片总数
        current_file = None
        for line in result.stdout.split('\n'):
            if line.startswith('Path = '):
                current_file = line[7:].strip()
                if current_file and is_image_file(current_file):
                    total_image_count += 1
                    if is_ad_image(current_file):
                        files_to_delete.append(current_file)
                        print(f"⚠️ 检测到广告图片: {current_file}")
        
        # 添加安全检查：如果要删除的图片超过总图片的80%，则不执行删除操作
        if files_to_delete:
            delete_percentage = len(files_to_delete) / total_image_count if total_image_count > 0 else 0
            if delete_percentage > 0.8:
                print(f"⚠️ 警告：检测到 {len(files_to_delete)} 个广告图片，占总图片数 {total_image_count} 的 {delete_percentage*100:.1f}%")
                print(f"❌ 为防止误删除，已取消删除操作（删除比例超过80%）")
                # 虽然不删除，仍然要处理重命名
            else:
                # 只有在确实需要删除文件时才创建trash目录
                os.makedirs(trash_dir, exist_ok=True)
                print(f"📁 创建回收站目录: {trash_dir}")
                
                # 先提取广告图片到trash文件夹
                for ad_file in files_to_delete:
                    extract_cmd = ['7z', 'e', zip_path, ad_file, f'-o{trash_dir}', '-aoa']
                    extract_result = subprocess.run(extract_cmd, capture_output=True, encoding='utf-8', errors='ignore')
                    if extract_result.returncode == 0:
                        print(f"✅ 已提取广告图片到回收站: {ad_file}")
                    else:
                        print(f"⚠️ 提取广告图片失败: {ad_file}")
                
                # 只有当删除比例低于80%时才执行删除操作
                delete_cmd = ['7z', 'd', zip_path] + files_to_delete
                delete_result = subprocess.run(delete_cmd, capture_output=True, encoding='utf-8', errors='ignore')
                
                if delete_result.returncode == 0:
                    print(f"✅ 已从压缩包中删除 {len(files_to_delete)} 个广告图片")
                else:
                    print(f"❌ 删除文件失败: {delete_result.stderr}")
        
        # 如果没有hash文件，且已处理完广告图片，则提前返回
        if not has_hash_files_in_zip(zip_path):
            if files_to_delete and delete_percentage <= 0.8:
                print("✅ 广告图片已处理完成，无需处理文件名")
            else:
                print("✅ 无需处理文件名，跳过重新打包")
            return
    except Exception as e:
        print(f"❌ 检查广告图片失败: {str(e)}")
    
    # 处理hash文件名
    temp_dir = tempfile.mkdtemp()
    try:
        success = False
        need_repack = False  # 添加标志，表示是否需要重新打包
        has_created_trash_dir = os.path.exists(trash_dir)  # 跟踪trash目录是否已创建
        
        # 首先尝试使用7z
        try:
            # 解压文件
            extract_cmd = ['7z', 'x', zip_path, f'-o{temp_dir}']
            subprocess.run(extract_cmd, check=True, capture_output=True, encoding='utf-8', errors='ignore')
            
            # 重命名文件
            renamed = False
            # 用于检测重名文件
            filename_count = {}
            
            # 第一遍扫描，统计文件名
            for root, _, files in os.walk(temp_dir):
                for filename in files:
                    new_filename = re.sub(r'\[hash-[0-9a-fA-F]+\]', '', filename)
                    if new_filename in filename_count:
                        filename_count[new_filename] += 1
                    else:
                        filename_count[new_filename] = 1
            
            # 检查是否有重名文件
            duplicate_files = {name: count for name, count in filename_count.items() if count > 1}
            if duplicate_files:
                print(f"\n⚠️ 检测到压缩包内有重名文件，开始比较内容:")
                
                # 当发现有重复文件需要处理时才创建trash目录
                if not has_created_trash_dir:
                    os.makedirs(trash_dir, exist_ok=True)
                    print(f"📁 创建回收站目录: {trash_dir}")
                    has_created_trash_dir = True
                
                # 创建trash子目录用于存放重复文件
                dupes_trash_dir = os.path.join(trash_dir, "duplicates")
                os.makedirs(dupes_trash_dir, exist_ok=True)
                
                # 修改处理重名文件的函数调用，传入trash目录
                if handle_duplicate_files_with_trash(duplicate_files, temp_dir, dupes_trash_dir):
                    need_repack = True  # 如果成功处理了重名文件，需要重新打包
                else:
                    print("❌ 处理重名文件失败，跳过压缩包处理")
                    return
            
            # 重命名剩余文件
            for root, _, files in os.walk(temp_dir):
                for filename in files:
                    new_filename = re.sub(r'\[hash-[0-9a-fA-F]+\]', '', filename)
                    if new_filename != filename:
                        old_path = os.path.join(root, filename)
                        new_path = os.path.join(root, new_filename)
                        try:
                            # 如果目标文件已存在，需要处理冲突
                            if os.path.exists(new_path):
                                # 只有在需要处理冲突时才创建trash目录和子目录
                                if not has_created_trash_dir:
                                    os.makedirs(trash_dir, exist_ok=True)
                                    print(f"📁 创建回收站目录: {trash_dir}")
                                    has_created_trash_dir = True
                                
                                hash_trash_dir = os.path.join(trash_dir, "hash_renamed")
                                os.makedirs(hash_trash_dir, exist_ok=True)
                                shutil.copy2(new_path, os.path.join(hash_trash_dir, new_filename))
                                print(f"已保存冲突文件到回收站: {new_filename}")
                            
                            os.rename(old_path, new_path)
                            print(f"重命名: {filename} -> {new_filename}")
                            renamed = True
                            need_repack = True  # 如果有文件重命名，需要重新打包
                        except Exception as e:
                            print(f"⚠️ 重命名失败 {filename}: {str(e)}")
                            continue
            
            if need_repack:  # 只在需要时重新打包
                try:
                    # 重新打包前先删除原文件
                    os.remove(zip_path)
                    # 重新打包
                    create_cmd = ['7z', 'a', '-tzip', zip_path, os.path.join(temp_dir, '*')]
                    subprocess.run(create_cmd, check=True, capture_output=True, encoding='utf-8', errors='ignore')
                    print(f"✅ 7z处理完成：{zip_path}")
                    success = True
                except Exception as e:
                    print(f"❌ 7z打包失败: {str(e)}")
                    success = False
            else:
                print("✅ 无需修改，跳过重新打包")
                success = True
                
        except Exception as e:
            print(f"⚠️ 7z处理失败，尝试使用Bandizip: {str(e)}")
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir = tempfile.mkdtemp()
            
            # 尝试使用Bandizip
            success = process_with_bandizip(zip_path, temp_dir, trash_dir)
        
        if not success:
            print("❌ 压缩包处理失败")
        
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"⚠️ 清理临时目录失败: {str(e)}")
        
        # 如果回收站目录存在且为空，则删除它
        if os.path.exists(trash_dir) and not os.listdir(trash_dir):
            try:
                os.rmdir(trash_dir)
                print(f"删除空回收站目录: {trash_dir}")
            except Exception as e:
                print(f"⚠️ 删除空回收站目录失败: {str(e)}")
    
    print("继续处理下一个文件...")

class ProcessStats:
    """处理统计类"""
    def __init__(self):
        self.lock = Lock()
        self.processed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        
    def increment_processed(self):
        with self.lock:
            self.processed_count += 1
            
    def increment_failed(self):
        with self.lock:
            self.failed_count += 1
            
    def increment_skipped(self):
        with self.lock:
            self.skipped_count += 1

def process_zip_file(args):
    """处理单个压缩包的包装函数"""
    zip_path, input_base_path, stats = args
    try:
        rename_images_in_zip(zip_path, input_base_path)
        stats.increment_processed()
    except Exception as e:
        print(f"❌ 处理压缩包失败 {zip_path}: {str(e)}")
        stats.increment_failed()

def process_image_directory(args):
    """处理单个图片目录的包装函数"""
    directory, stats = args
    try:
        rename_images_in_directory(directory)
        stats.increment_processed()
    except Exception as e:
        print(f"❌ 处理目录失败 {directory}: {str(e)}")
        stats.increment_failed()

def process_with_threadpool(items, worker_func, max_workers=None):
    """使用线程池处理任务"""
    if not items:
        return
        
    # 如果没有指定线程数，使用处理器数量的2倍
    if max_workers is None:
        max_workers = os.cpu_count() * 2 or 4
        
    stats = ProcessStats()
    total = len(items)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("处理文件...", total=total)
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # 添加统计对象到每个任务的参数中
            tasks = [executor.submit(worker_func, (*item, stats) if isinstance(item, tuple) else (item, stats)) 
                    for item in items]
            
            # 等待所有任务完成
            for future in as_completed(tasks):
                progress.advance(task)
                try:
                    future.result()
                except Exception as e:
                    print(f"❌ 任务执行失败: {str(e)}")
                    stats.increment_failed()
    
    # 打印统计信息
    print(f"\n📊 处理完成:")
    print(f"   - 成功处理: {stats.processed_count} 个")
    print(f"   - 处理失败: {stats.failed_count} 个")
    print(f"   - 跳过处理: {stats.skipped_count} 个")

if __name__ == "__main__":
    # 获取输入路径
    args = InputHandler.parse_arguments()
    
    # 如果没有指定模式，让用户选择
    if not args.mode:
        print("\n请选择处理模式：")
        print("1. 处理图片文件")
        print("2. 处理压缩包")
        while True:
            # choice = input("请输入选项 (1/2): ").strip()
            choice = '2'
            if choice == '1':
                args.mode = 'image'
                break
            elif choice == '2':
                args.mode = 'zip'
                break
            else:
                print("无效的选项，请重新输入")
    
    target_paths = InputHandler.get_input_paths(args)
    
    if not target_paths:
        while True:
            print("\n没有有效的输入路径，请提供新路径或者退出")
            print("1. 输入新路径")
            print("2. 从剪贴板读取路径")
            print("3. 退出程序")
            option = input("请选择 (1/2/3): ").strip()
            
            if option == '1':
                print("请输入要处理的文件夹或压缩包路径（每行一个，输入空行结束）：")
                new_paths = []
                while True:
                    line = input().strip()
                    if not line:
                        break
                    path = line.strip().strip('"').strip("'")
                    if os.path.exists(path):
                        new_paths.append(path)
                        print(f"✅ 已添加有效路径: {path}")
                    else:
                        print(f"❌ 路径不存在: {path}")
                
                if new_paths:
                    target_paths = new_paths
                    break
            elif option == '2':
                new_paths = InputHandler.get_paths_from_clipboard()
                if new_paths:
                    target_paths = new_paths
                    break
            elif option == '3':
                print("退出程序")
                sys.exit(0)
            else:
                print("无效选项，请重新输入")

    # 收集需要处理的项目
    items_to_process = []
    
    for target_path in target_paths:
        print(f"\n收集路径: {target_path}")
        input_base_path = os.path.dirname(target_path)
        
        if os.path.isdir(target_path):
            if args.mode == 'image':
                # 收集所有需要处理的图片目录
                items_to_process.append(target_path)
            else:
                # 收集所有需要处理的压缩包
                for root, _, files in os.walk(target_path):
                    for file in files:
                        if file.lower().endswith('.zip'):
                            zip_path = os.path.join(root, file)
                            items_to_process.append((zip_path, input_base_path))
        elif zipfile.is_zipfile(target_path):
            if args.mode == 'zip':
                items_to_process.append((target_path, input_base_path))
            else:
                print(f"警告: 当前为图片处理模式，跳过压缩包 {target_path}")
        else:
            print(f"警告: '{target_path}' 不是有效的压缩包或文件夹，跳过处理")
    
    # 使用线程池处理收集到的项目
    if items_to_process:
        if args.mode == 'image':
            process_with_threadpool(items_to_process, process_image_directory)
        else:
            process_with_threadpool(items_to_process, process_zip_file)
    else:
        print("没有找到需要处理的文件")