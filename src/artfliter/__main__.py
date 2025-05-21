import os
import sys
import json
import hashlib
import argparse
import subprocess
from pathlib import Path
from typing import Optional, List
from datetime import datetime
# 添加TextualLogger导入

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from textual_logger import TextualLoggerManager
from hashu.utils.hash_process_config import get_latest_hash_file_path, process_artist_folder, process_duplicates
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

logger, config_info = setup_logger(app_name="artbook_dedup", console_output=True)


# 参数配置
DEFAULT_PARAMS = {
    'ref_hamming_distance': 16,  # 与外部参考文件比较的汉明距离阈值
    'hash_size': 10,  # 哈希值大小
    'filter_white_enabled': False,  # 是否启用白图过滤
}

# TextualLogger布局配置
TEXTUAL_LAYOUT = {
    "current_stats": {
        "ratio": 2,
        "title": "📊 总体进度",
        "style": "lightyellow"
    },
    "current_progress": {
        "ratio": 2,
        "title": "🔄 当前进度",
        "style": "lightcyan"
    },
    "process_log": {
        "ratio": 3,
        "title": "📝 处理日志",
        "style": "lightpink"
    },
    "update_log": {
        "ratio": 3,
        "title": "ℹ️ 更新日志",
        "style": "lightblue"
    },
}

# 常量设置
WORKER_COUNT = 2  # 线程数
FORCE_UPDATE = False  # 是否强制更新哈希值

def init_TextualLogger():
    TextualLoggerManager.set_layout(TEXTUAL_LAYOUT, config_info['log_file'])

def get_artist_folder_from_path(path: Path) -> Optional[Path]:
    """从给定路径获取画师文件夹
    
    Args:
        path: 输入路径（可以是压缩包或文件夹）
        
    Returns:
        Optional[Path]: 画师文件夹路径
    """
    def is_artist_folder(p: Path) -> bool:
        """判断是否为画师文件夹"""
        return '[' in p.name and ']' in p.name
    
    try:
        path = Path(path).resolve()
        
        # 如果是压缩包，使用其所在目录
        if path.is_file() and path.suffix.lower() in ['.zip', '.7z', '.rar']:
            base_path = path.parent
        else:
            base_path = path
            
        # 向上查找画师文件夹
        current_path = base_path
        while current_path != current_path.parent:
            if is_artist_folder(current_path):
                if current_path.exists():
                    logger.info(f'✅ 找到画师文件夹: {current_path}')
                    confirm = input('是否使用该画师文件夹？(Y/n/输入新路径): ').strip()
                    if not confirm or confirm.lower() == 'y':
                        return current_path
                    elif confirm.lower() == 'n':
                        break  # 继续搜索当前目录下的其他画师文件夹
                    elif os.path.exists(confirm):
                        new_path = Path(confirm)
                        if is_artist_folder(new_path):
                            return new_path
                        else:
                            logger.info('❌ 输入的路径不是画师文件夹（需要包含[]标记）')
                            break
                    else:
                        logger.info('❌ 输入的路径不存在')
                        break
            current_path = current_path.parent
        
        # 如果向上查找没有找到或用户拒绝了，则搜索当前目录下的画师文件夹
        artist_folders = []
        for entry in base_path.iterdir():
            if entry.is_dir() and is_artist_folder(entry):
                artist_folders.append(entry)
                    
        if not artist_folders:
            logger.info(f'❌ 在路径 {base_path} 下未找到画师文件夹')
            return None
            
        if len(artist_folders) == 1:
            logger.info(f'✅ 找到画师文件夹: {artist_folders[0]}')
            confirm = input('是否使用该画师文件夹？(Y/n/输入新路径): ').strip()
            if not confirm or confirm.lower() == 'y':
                return artist_folders[0]
            elif confirm.lower() == 'n':
                return None
            elif os.path.exists(confirm):
                new_path = Path(confirm)
                if is_artist_folder(new_path):
                    return new_path
                else:
                    logger.info('❌ 输入的路径不是画师文件夹（需要包含[]标记）')
                    return None
            else:
                logger.info('❌ 输入的路径不存在')
                return None
            
        logger.info("\n找到以下画师文件夹:")
        for i, folder in enumerate(artist_folders, 1):
            logger.info(f"{i}. {folder}")
            
        # 让用户选择或输入新路径
        while True:
            choice = input("\n请选择画师文件夹编号或直接输入新路径 (输入n跳过，直接回车确认第一个): ").strip()
            if not choice:
                return artist_folders[0]
            elif choice.lower() == 'n':
                return None
                
            # 如果输入的是路径
            if os.path.exists(choice):
                new_path = Path(choice)
                if is_artist_folder(new_path):
                    return new_path
                else:
                    logger.info('❌ 输入的路径不是画师文件夹（需要包含[]标记）')
                    continue
                    
            # 如果输入的是编号
            try:
                index = int(choice) - 1
                if 0 <= index < len(artist_folders):
                    folder = artist_folders[index]
                    logger.info(f'✅ 已选择: {folder}')
                    confirm = input('是否使用该画师文件夹？(Y/n/输入新路径): ').strip()
                    if not confirm or confirm.lower() == 'y':
                        return folder
                    elif confirm.lower() == 'n':
                        continue
                    elif os.path.exists(confirm):
                        new_path = Path(confirm)
                        if is_artist_folder(new_path):
                            return new_path
                        else:
                            logger.info('❌ 输入的路径不是画师文件夹（需要包含[]标记）')
                            continue
                    else:
                        logger.info('❌ 输入的路径不存在')
                        continue
                logger.info('❌ 无效的选择，请重试')
            except ValueError:
                logger.info('❌ 请输入有效的数字或路径')
                
    except Exception as e:
        logger.info(f'❌ 获取画师文件夹时出错: {e}')
        return None

def process_single_path(path: Path, workers: int = 4, force_update: bool = False, params: dict = None) -> bool:
    """处理单个路径
    
    Args:
        path: 输入路径
        workers: 线程数
        force_update: 是否强制更新
        params: 参数字典，包含处理参数
        
    Returns:
        bool: 是否处理成功
    """
    try:
        logger.info(f"[#process_log]\n🔄 处理路径: {path}")
        
        # 获取画师文件夹
        artist_folder = get_artist_folder_from_path(path)
        if not artist_folder:
            return False
            
        logger.info(f"[#update_log]✅ 使用画师文件夹: {artist_folder}")
        
        # 处理画师文件夹，生成哈希文件
        hash_file = process_artist_folder(artist_folder, workers, force_update)
        if not hash_file:
            return False
            
        logger.info(f"[#update_log]✅ 生成哈希文件: {hash_file}")
        
        # 处理重复文件
        logger.info(f"[#process_log]\n🔄 处理重复文件 {path}")
        process_duplicates(hash_file, [str(path)], params, workers)
        
        logger.info(f"[#update_log]✅ 处理完成: {path}")
        return True
        
    except Exception as e:
        logger.info(f"[#process_log]❌ 处理路径时出错: {path}: {e}")
        return False

def find_artist_folders_for_path(path: Path) -> List[Path]:
    """查找给定路径可能对应的画师文件夹列表
    
    Args:
        path: 输入路径
        
    Returns:
        List[Path]: 可能的画师文件夹列表
    """
    def is_artist_folder(p: Path) -> bool:
        """判断是否为画师文件夹"""
        return '[' in p.name and ']' in p.name
    
    try:
        path = Path(path).resolve()
        artist_folders = []
        
        # 如果是压缩包，使用其所在目录
        if path.is_file() and path.suffix.lower() in ['.zip', '.7z', '.rar']:
            base_path = path.parent
        else:
            base_path = path
            
        # 向上查找画师文件夹
        current_path = base_path
        while current_path != current_path.parent:
            if is_artist_folder(current_path) and current_path.exists():
                artist_folders.append(current_path)
            current_path = current_path.parent
        
        # 搜索当前目录下的画师文件夹
        for entry in base_path.iterdir():
            if entry.is_dir() and is_artist_folder(entry):
                artist_folders.append(entry)
                
        return artist_folders
        
    except Exception as e:
        print(f'❌ 查找画师文件夹时出错: {e}')
        return []

def batch_get_artist_folders(paths: List[str]) -> dict:
    """批量获取所有路径对应的画师文件夹
    
    Args:
        paths: 输入路径列表
        
    Returns:
        dict: 路径到画师文件夹的映射
    """
    path_to_folders = {}
    path_to_selected = {}
    
    # 首先收集所有路径可能的画师文件夹
    for path in paths:
        if not os.path.exists(path):
            logger.info(f"❌ 路径不存在: {path}")
            continue
            
        folders = find_artist_folders_for_path(Path(path))
        if not folders:
            logger.info(f"❌ 未找到画师文件夹: {path}")
            continue
            
        path_to_folders[path] = folders
        # 默认选择第一个找到的画师文件夹
        path_to_selected[path] = folders[0]
    
    # 显示所有路径和对应的画师文件夹
    while True:
        print("\n当前所有路径及其对应的画师文件夹:")
        for i, path in enumerate(path_to_folders.keys(), 1):
            print(f"\n{i}. 路径: {path}")
            print(f"   当前选择的画师文件夹: {path_to_selected[path]}")
            print("   可选的画师文件夹:")
            for j, folder in enumerate(path_to_folders[path], 1):
                print(f"      {j}. {folder}")
        
        # 让用户选择是否需要修改

        choice = input("\n请输入'序号 画师文件夹序号'来修改对应关系（例如：'1 2'表示修改第1个路径为其第2个画师文件夹）\n直接回车确认所有选择，输入q退出: ").strip()
        
        if not choice:
            break
        elif choice.lower() == 'q':
            return None
            
        try:
            path_idx, folder_idx = map(int, choice.split())
            if 1 <= path_idx <= len(paths):
                path = list(path_to_folders.keys())[path_idx - 1]
                folders = path_to_folders[path]
                if 1 <= folder_idx <= len(folders):
                    path_to_selected[path] = folders[folder_idx - 1]
                    logger.info(f"✅ 已更新: {path} -> {folders[folder_idx - 1]}")
                else:
                    logger.info("❌ 无效的画师文件夹序号")
            else:
                logger.info("❌ 无效的路径序号")
        except ValueError:
            logger.info("❌ 输入格式错误，请使用'序号 画师文件夹序号'的格式")
    
    return path_to_selected

def main():
    """主函数"""
    # 获取路径列表
    print("请输入要处理的路径（每行一个，输入空行结束）:")
    paths = []
    while True:
        path = input().strip().replace('"', '')
        if not path:
            break
        paths.append(path)
    if not paths:
        print("[#process_log]❌ 未输入任何路径")
        return
        
    print("[#process_log]\n🚀 开始处理...")
    
    # 批量获取并确认画师文件夹
    path_to_artist = batch_get_artist_folders(paths)
    if not path_to_artist:
        print("[#process_log]❌ 用户取消操作")
        return
    
    # 处理每个路径
    success_count = 0
    total_count = len(path_to_artist)
    # init_TextualLogger()
    # 准备参数
    params = DEFAULT_PARAMS.copy()
    
    for i, (path, artist_folder) in enumerate(path_to_artist.items(), 1):
        logger.info(f"[#process_log]\n=== 处理第 {i}/{total_count} 个路径 ===")
        logger.info(f"[#process_log]路径: {path}")
        logger.info(f"[#process_log]画师文件夹: {artist_folder}")
        
        # 更新进度
        progress = int((i - 1) / total_count * 100)
        logger.debug(f"[#current_progress]当前进度: [{('=' * int(progress/5))}] {progress}%")
        logger.info(f"[#current_stats]总路径数: {total_count} 已处理: {i-1} 成功: {success_count} 总进度: [{('=' * int(progress/5))}] {progress}%")
        
        # 处理画师文件夹，生成哈希文件
        hash_file = process_artist_folder(artist_folder, WORKER_COUNT, FORCE_UPDATE)
        if not hash_file:
            # 更新失败状态
            logger.info(f"[#current_stats]总路径数: {total_count} 已处理: {i} 成功: {success_count} 总进度: [{('=' * int(progress/5))}] {progress}%")
            continue
            
        # 处理重复文件
        process_duplicates(hash_file, [str(path)], params, WORKER_COUNT)
        success_count += 1
        
        # 更新最终进度
        progress = int(i / total_count * 100)
        logger.debug(f"[#current_progress]当前进度: [{('=' * int(progress/5))}] {progress}%")
        logger.info(f"[#current_stats]总路径数: {total_count}\n已处理: {i}\n成功: {success_count}\n总进度: [{('=' * int(progress/5))}] {progress}%")
            
    logger.info(f"[#update_log]\n✅ 所有处理完成: 成功 {success_count}/{total_count}")

if __name__ == "__main__":
    main() 