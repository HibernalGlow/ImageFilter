"""图像处理模块，包含图像尺寸检测功能"""

import io
import os
import zipfile
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Tuple, Set, Optional
from PIL import Image
import pillow_avif
import pillow_jxl
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from loguru import logger

class ImageProcessor:
    """图像处理器，用于检测和处理图像尺寸"""
    
    def __init__(self, source_dir, target_dir, dimension_rules=None, cut_mode=False, max_workers=16, 
                 threshold_count=1):
        """
        初始化图像处理器
        
        Args:
            source_dir: 源目录
            target_dir: 目标目录
            dimension_rules: 尺寸规则列表
            cut_mode: 是否剪切模式（True为移动，False为复制）
            max_workers: 最大工作线程数
            threshold_count: 匹配阈值计数
        """
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        
        # 兼容旧版本参数
        if dimension_rules is None:
            # 默认使用单个宽度范围
            self.dimension_rules = [{
                "min_width": 1800,
                "max_width": -1,
                "min_height": -1,
                "max_height": -1,
                "mode": "or",
                "folder": ""
            }]
        else:
            self.dimension_rules = dimension_rules
            
        self.cut_mode = cut_mode
        self.max_workers = max_workers
        self.threshold_count = threshold_count
        self.logger = logger  # 使用全局logger
        
        # 添加排除关键词列表
        self.exclude_paths = [
            '画集', '日原版', 'pixiv', '图集', '作品集', 'FANTIA', 'cg', 'multi', 'trash', '小说', 'cg'
        ]
        # 将所有排除路径转换为小写，并确保是独立的词
        self.exclude_paths = [path.lower().strip() for path in self.exclude_paths]
        # 添加需要排除的文件格式
        self.exclude_formats = { '.gif', '.mp4', '.webm', '.mkv', '.mov'}
        # 添加7z路径
        self.seven_zip_path = r"C:\Program Files\7-Zip\7z.exe"
        
        # 记录初始化信息到Textual日志
        self.logger.info(f"[#current_stats]初始化处理器 - 模式: 尺寸分组, 动作: {'移动' if self.cut_mode else '复制'}")
        for i, rule in enumerate(self.dimension_rules, 1):
            min_width = rule["min_width"]
            max_width = "不限" if rule["max_width"] == -1 else rule["max_width"]
            
            min_height = "不限" if rule["min_height"] == -1 else rule["min_height"]
            max_height = "不限" if rule["max_height"] == -1 else rule["max_height"]
            
            folder = rule["folder"] or "根目录"
            mode = "AND" if rule.get("mode", "or") == "and" else "OR"
            
            width_info = f"宽: {min_width}-{max_width}px"
            height_info = f"高: {min_height}-{max_height}px"
            self.logger.info(f"[#update_log]规则 {i}: {width_info} {mode} {height_info} -> {folder}")

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

    def get_image_size_from_zip(self, zip_file, image_path):
        """
        从ZIP文件中获取图像尺寸
        
        Args:
            zip_file: ZIP文件对象
            image_path: 图像在ZIP中的路径
            
        Returns:
            tuple: (宽度, 高度)
        """
        try:
            with zip_file.open(image_path) as file:
                img_data = io.BytesIO(file.read())
                with Image.open(img_data) as img:
                    return img.size  # 返回(宽度, 高度)
        except Exception as e:
            self.logger.error(f"[#update_log]读取图片出错 {image_path}: {str(e)}")
            return (0, 0)
    
    def sort_images_by_size(self, zip_file, image_files):
        """
        按文件大小排序图像文件，一般文件越大，尺寸越大
        
        Args:
            zip_file: ZIP文件对象
            image_files: 图像文件列表
            
        Returns:
            list: 排序后的图像文件列表
        """
        try:
            # 收集文件大小信息
            file_sizes = {}
            for img_path in image_files:
                info = zip_file.getinfo(img_path)
                file_sizes[img_path] = info.file_size
            
            # 按文件大小从大到小排序
            sorted_images = sorted(image_files, key=lambda x: file_sizes[x], reverse=True)
            return sorted_images
        except Exception as e:
            self.logger.error(f"[#update_log]排序图片出错: {str(e)}")
            return image_files  # 如果排序失败，返回原始列表

    def get_zip_images_info(self, zip_path):
        """
        获取ZIP文件中图像的尺寸信息
        
        Args:
            zip_path: ZIP文件路径
            
        Returns:
            tuple: (平均宽度, 平均高度, 匹配数量, 最佳匹配规则索引)
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                image_files = [f for f in zf.namelist() if f.lower().endswith(
                    ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.avif', '.jxl'))]
                
                if not image_files:
                    self.logger.warning(f"[#update_log]ZIP文件 {zip_path} 中没有找到图片")
                    return 0, 0, 0, -1
                
                # 改进: 按文件大小排序图片，大文件通常是大图片
                image_files = self.sort_images_by_size(zf, image_files)
                total_images = len(image_files)
                
                # 计算抽样间隔
                sample_size = min(20, total_images)  # 最多抽样20张图片
                if total_images <= sample_size:
                    sampled_files = image_files  # 如果图片数量较少，使用所有图片
                else:
                    # 确保抽样包含：
                    # 1. 前几张大图片
                    # 2. 最后几张小图片
                    # 3. 均匀分布的中间图片
                    head_count = min(5, total_images)  # 开头取5张大图
                    tail_count = min(3, total_images)  # 结尾取3张小图
                    middle_count = sample_size - head_count - tail_count  # 中间的图片数量
                    
                    # 获取头部图片（大图）
                    head_files = image_files[:head_count]
                    # 获取尾部图片（小图）
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

                # 用于每个尺寸规则的匹配计数
                rule_matches = {i: 0 for i in range(len(self.dimension_rules))}
                
                # 收集所有有效图片的尺寸
                widths = []
                heights = []
                
                for img in sampled_files:
                    width, height = self.get_image_size_from_zip(zf, img)
                    if width > 0 and height > 0:
                        widths.append(width)
                        heights.append(height)
                        
                        # 检查每个尺寸规则 - 规则按优先级从高到低排列
                        matched_rule = False
                        for i, rule in enumerate(self.dimension_rules):
                            # 如果已经匹配到一个规则，不再检查后续规则
                            if matched_rule:
                                break
                                
                            # 获取规则参数
                            min_width = rule["min_width"]
                            max_width = rule["max_width"]
                            min_height = rule["min_height"]
                            max_height = rule["max_height"]
                            mode = rule.get("mode", "or")  # 默认为"or"
                            
                            # 检查宽度
                            if max_width == -1:
                                width_match = width >= min_width
                            else:
                                width_match = min_width <= width <= max_width
                                
                            # 检查高度
                            if min_height == -1 or max_height == -1:
                                height_match = True  # 如果没有设置高度限制，视为匹配
                            else:
                                height_match = min_height <= height <= max_height
                                
                            # 根据模式判断是否匹配
                            if mode == "and":
                                matches_rule = width_match and height_match
                            else:  # "or"
                                matches_rule = width_match or height_match
                                
                            if matches_rule:
                                rule_matches[i] += 1
                                matched_rule = True  # 标记已经匹配到规则
                                self.logger.debug(f"[#process_log]图片 {img} 符合规则 {i+1}: {width}x{height}px")
                
                # 没有有效的图像尺寸
                if not widths or not heights:
                    self.logger.warning(f"[#update_log]ZIP文件 {zip_path} 中没有有效的图像尺寸")
                    return 0, 0, 0, -1
                
                # 计算平均尺寸
                avg_width = sum(widths) / len(widths)
                avg_height = sum(heights) / len(heights)
                
                # 找出匹配数量最多的规则
                best_rule_idx = max(rule_matches, key=rule_matches.get)
                best_match_count = rule_matches[best_rule_idx]
                
                self.logger.info(f"[#process_log]ZIP文件 {zip_path} - 平均尺寸: {avg_width:.1f}x{avg_height:.1f}px, "
                               f"最佳匹配规则: {best_rule_idx+1}, 匹配数量: {best_match_count}/{self.threshold_count}")
                
                return avg_width, avg_height, best_match_count, best_rule_idx
                
        except Exception as e:
            self.logger.error(f"[#update_log]处理ZIP文件出错 {zip_path}: {str(e)}")
            return 0, 0, 0, -1

    def should_process_zip(self, avg_width, avg_height, match_count, rule_idx, zip_path):
        """
        判断是否应该处理ZIP文件
        
        Args:
            avg_width: 平均宽度
            avg_height: 平均高度
            match_count: 匹配计数
            rule_idx: 规则索引
            zip_path: ZIP文件路径
            
        Returns:
            tuple: (是否处理, 规则索引)
        """
        if avg_width == 0 or avg_height == 0 or rule_idx < 0:
            self.logger.warning(f"[#update_log]跳过处理 {zip_path}: 无效的尺寸或规则")
            return False, rule_idx
        
        should_process = match_count >= self.threshold_count
        
        if rule_idx >= len(self.dimension_rules):
            self.logger.warning(f"[#update_log]跳过处理 {zip_path}: 规则索引无效 {rule_idx}")
            return False, -1
            
        rule = self.dimension_rules[rule_idx]
        min_width = rule["min_width"]
        max_width = "不限" if rule["max_width"] == -1 else rule["max_width"]
        
        min_height = "不限" if rule["min_height"] == -1 else rule["min_height"]
        max_height = "不限" if rule["max_height"] == -1 else rule["max_height"]
        
        mode = "AND" if rule.get("mode", "or") == "and" else "OR"
        
        self.logger.info(f"[#process_log]文件 {zip_path} - 平均尺寸: {avg_width:.1f}x{avg_height:.1f}px, "
                       f"规则: 宽{min_width}-{max_width}px {mode} 高{min_height}-{max_height}px, "
                       f"匹配数量: {match_count}/{self.threshold_count}, "
                       f"结果: {'处理' if should_process else '跳过'}")
        return should_process, rule_idx

    def process_single_zip(self, zip_path):
        """
        处理单个ZIP文件
        
        Args:
            zip_path: ZIP文件路径
            
        Returns:
            tuple: (ZIP路径, 是否处理, 规则索引)
        """
        try:
            # 0. 检查压缩包是否有效
            if not self.is_valid_zip(zip_path):
                self.logger.info(f"[#update_log]跳过损坏的压缩包: {zip_path}")
                return zip_path, False, -1
                
            # 1. 首先检查是否包含排除格式
            if self.has_excluded_formats(zip_path):
                self.logger.info(f"[#update_log]跳过包含排除格式的文件: {zip_path}")
                return zip_path, False, -1
            
            # 2. 只有不包含排除格式的文件才检查尺寸
            avg_width, avg_height, match_count, rule_idx = self.get_zip_images_info(zip_path)
            should_process, rule_idx = self.should_process_zip(avg_width, avg_height, match_count, rule_idx, zip_path)
            
            return zip_path, should_process, rule_idx
            
        except Exception as e:
            self.logger.error(f"[#update_log]处理压缩包时出错 {zip_path}: {str(e)}")
            return zip_path, False, -1

    def run_7z_command(self, command, zip_path, operation="", additional_args=None):
        """
        执行7z命令的通用函数
        
        Args:
            command: 主命令 (如 'a', 'x', 'l' 等)
            zip_path: 压缩包路径
            operation: 操作描述（用于日志）
            additional_args: 额外的命令行参数
            
        Returns:
            tuple: (是否成功, 输出内容)
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
        """
        使用7z检查压缩包内容
        
        Args:
            zip_path: 压缩包路径
            
        Returns:
            bool: 是否包含排除的格式
        """
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
        """
        检查压缩包中是否包含需要排除的文件格式
        
        Args:
            zip_path: 压缩包路径
            
        Returns:
            bool: 是否包含排除的格式
        """
        return self.check_7z_contents(zip_path)

    def is_valid_zip(self, zip_path):
        """
        检查压缩包是否有效（非损坏）
        
        Args:
            zip_path: 压缩包路径
            
        Returns:
            bool: 压缩包是否有效
        """
        try:
            # 使用7z测试压缩包完整性
            success, output = self.run_7z_command('t', zip_path, "测试压缩包完整性")
            return success
        except Exception as e:
            self.logger.error(f"[#update_log]检查压缩包有效性时出错 {zip_path}: {str(e)}")
            return False

    def process(self):
        """
        处理所有符合条件的ZIP文件
        """
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
        
        # 输出尺寸规则信息
        for i, rule in enumerate(self.dimension_rules, 1):
            min_width = rule["min_width"]
            max_width = "不限" if rule["max_width"] == -1 else rule["max_width"]
            
            min_height = "不限" if rule["min_height"] == -1 else rule["min_height"]
            max_height = "不限" if rule["max_height"] == -1 else rule["max_height"]
            
            folder = rule["folder"] or "根目录"
            mode = "AND" if rule.get("mode", "or") == "and" else "OR"
            
            width_info = f"宽: {min_width}-{max_width}px"
            height_info = f"高: {min_height}-{max_height}px"
            self.logger.info(f"[#performance]规则 {i}: {width_info} {mode} {height_info} -> {folder}")
            
        self.logger.info(f"[#performance]操作: {'移动' if self.cut_mode else '复制'}")
        
        processed_folders = set()
        processed_count = 0

        # 处理文件
        operation = "移动" if self.cut_mode else "复制"
        moved_count = 0
        total_files = len(zip_files)
        
        # 按规则统计处理的文件数
        rule_counts = {i: 0 for i in range(len(self.dimension_rules))}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for zip_path, should_process, rule_idx in tqdm(
                executor.map(self.process_single_zip, zip_files),
                total=total_files,
                desc="处理文件"
            ):
                processed_count += 1
                self.logger.info(f"[@current_progress]总体进度 ({processed_count}/{total_files}) {processed_count/total_files*100:.1f}%")
                
                if should_process and rule_idx >= 0:
                    processed_folders.add(zip_path.parent)
                    rule_counts[rule_idx] += 1
                    
                    # 获取该规则的子文件夹名称
                    subfolder = self.dimension_rules[rule_idx].get("folder", "")
                    
                    # 处理文件
                    rel_path = zip_path.relative_to(self.source_dir)
                    
                    # 如果有子文件夹，则将文件放在对应的子文件夹中
                    if subfolder:
                        new_folder = self.target_dir / subfolder / rel_path.parent
                    else:
                        new_folder = self.target_dir / rel_path.parent
                        
                    new_folder.mkdir(parents=True, exist_ok=True)

                    try:
                        if self.cut_mode:
                            shutil.move(str(zip_path), str(new_folder / zip_path.name))
                        else:
                            shutil.copy2(str(zip_path), str(new_folder / zip_path.name))
                        moved_count += 1
                        
                        # 获取规则信息用于日志
                        rule = self.dimension_rules[rule_idx]
                        min_width = rule["min_width"]
                        max_width = "不限" if rule["max_width"] == -1 else rule["max_width"]
                        
                        min_height = "不限" if rule["min_height"] == -1 else rule["min_height"]
                        max_height = "不限" if rule["max_height"] == -1 else rule["max_height"]
                        
                        target_folder = rule["folder"] or "根目录"
                        mode = "AND" if rule.get("mode", "or") == "and" else "OR"
                        
                        width_info = f"宽: {min_width}-{max_width}px"
                        height_info = f"高: {min_height}-{max_height}px"
                        
                        self.logger.info(f"[#process_log]成功{operation}: {zip_path.name} -> {target_folder} (规则: {width_info} {mode} {height_info})")
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

        # 打印每个规则处理的文件数
        for i, count in rule_counts.items():
            if i >= 0 and i < len(self.dimension_rules):
                rule = self.dimension_rules[i]
                min_width = rule["min_width"]
                max_width = "不限" if rule["max_width"] == -1 else rule["max_width"]
                
                min_height = "不限" if rule["min_height"] == -1 else rule["min_height"]
                max_height = "不限" if rule["max_height"] == -1 else rule["max_height"]
                
                folder = rule["folder"] or "根目录"
                mode = "AND" if rule.get("mode", "or") == "and" else "OR"
                
                width_info = f"宽: {min_width}-{max_width}px"
                height_info = f"高: {min_height}-{max_height}px"
                
                self.logger.info(f"[#current_stats]规则 {i+1} ({width_info} {mode} {height_info} -> {folder}): 处理了 {count} 个文件")

        self.logger.info(f"[#current_stats]处理完成: 成功{operation} {moved_count} 个文件") 