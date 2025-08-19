import os
import re
import shutil
import random
import zipfile
import io
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional, Union
from PIL import Image
from hashu.core.calculate_hash_custom import ImageClarityEvaluator
from loguru import logger
from .utils import (
    handle_multi_main_file, create_shortcut
)

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

def get_image_count(archive_path: str) -> int:
    try:
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                count = sum(1 for f in zf.namelist() 
                           if os.path.splitext(f.lower())[1] in IMAGE_EXTENSIONS)
                return count
        except zipfile.BadZipFile:
            return 0
    except Exception as e:
        logger.error("[#error_log] ❌ 统计图片数量失败 %s: %s", archive_path, str(e))
        return 0

def calculate_representative_width(archive_path: str, sample_count: int = 3) -> int:
    try:
        ext = os.path.splitext(archive_path)[1].lower()
        if ext not in {'.zip', '.cbz'}:
            return 0
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
        image_files.sort(key=lambda x: x[1], reverse=True)
        samples = []
        if image_files:
            samples.append(image_files[0][0])
            if len(image_files) > 2:
                samples.append(image_files[len(image_files)//2][0])
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
        return int(sorted(widths)[len(widths)//2])
    except Exception as e:
        logger.info("[#error_log] ❌ 计算代表宽度失败 %s: %s", archive_path, str(e))
        return 0
def shorten_number_cn(
    number: int, 
    precision: int = 1,
    use_w: bool = True
) -> str:
    """
    将大数字转换为中文习惯的缩写格式
    
    Args:
        number: 要转换的数字
        precision: 小数位精度（默认1位）
        use_w: 是否使用"万"为单位（True时万进制，False时千进制）
    
    Returns:
        str: 格式化后的字符串
        
    Examples:
        >>> shorten_number_cn(18500)
        '1.8w'
        >>> shorten_number_cn(215_0000)
        '215w'
        >>> shorten_number_cn(3_5000_0000)
        '3.5亿'
    """
    number=round(number)
    if number < 1000:
        return str(number)
        
    if use_w:
        # 万进制处理
        if number >= 1_0000_0000:
            # 亿单位处理
            value = number / 1_0000_0000
            unit = '亿'
        elif number >= 1_0000:
            # 万单位处理
            value = number / 1_0000
            unit = 'w'
        else:
            # 千单位处理（当小于1万时）
            value = number / 1000
            unit = 'k'
    else:
        # 千进制处理
        if number >= 1_000_000_000:
            value = number / 1_000_000_000
            unit = 'B'
        elif number >= 1_000_000:
            value = number / 1_000_000
            unit = 'M'
        else:
            value = number / 1000
            unit = 'k'

    # 处理精度
    if value == int(value):
        # 整数情况省略小数部分
        return f"{int(value)}{unit}"
    else:
        # 保留指定位数小数
        return f"{value:.{precision}f}{unit}".rstrip('0').rstrip('.') 


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
        self.group_details.append({'name': group_name, 'details': details})
    def update_stats(self, key: str, value: int = 1):
        self.stats[key] = self.stats.get(key, 0) + value
    def add_section(self, title: str, content: str):
        self.report_sections.append({'title': title, 'content': content})
    def generate_report(self, base_dir: str) -> str:
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
                report.append("")
        for section in self.report_sections:
            report.append(f"## {section['title']}")
            report.append(section['content'])
            report.append("")
        return "\n".join(report)
    def save_report(self, base_dir: str, filename: Optional[str] = None):
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
            logger.exception("[#error_log] 异常堆栈:")
            logger.info("[#process] 💥 遇到严重错误，请检查error_log面板")
            return None

def process_file_with_count(file_path: str, name_only_mode: bool = False) -> Tuple[str, str, Dict[str, Union[int, float]]]:
    import re, os, zipfile, random
    from PIL import Image
    from hashu.core.calculate_hash_custom import ImageClarityEvaluator
    from rawfilter.run import shorten_number_cn
    from loguru import logger
    full_path = file_path
    dir_name = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    name, ext = os.path.splitext(file_name)
    name = re.sub(r'\{[^}]*\}', '', name)
    metrics = {'width': 0, 'page_count': 0, 'clarity_score': 0.0}

    # 如果是仅名称模式，跳过所有内部分析
    if name_only_mode:
        logger.info("[#name_only] 🏷️ 仅名称模式，跳过内部分析: %s", file_name)
        # 直接返回原始文件名（已移除{}标记）
        new_name = f"{name}{ext}"
        new_path = os.path.join(dir_name, new_name) if dir_name else new_name
        return file_path, new_path, metrics

    page_match = re.search(r'\{(\d+)@PX\}', file_name)
    if page_match:
        metrics['page_count'] = int(page_match.group(1))
    else:
        metrics['page_count'] = get_image_count(full_path)
    metrics['width'] = calculate_representative_width(full_path)
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

def process_file_group(group_files: List[str], base_dir: str, trash_dir: str, create_shortcuts: bool = False, enable_multi_main: bool = False, name_only_mode: bool = False) -> Dict:
    from .utils import handle_multi_main_file, create_shortcut
    from rawfilter.__main__ import clean_filename, is_in_blacklist, is_chinese_version, has_original_keywords, group_similar_files, safe_move_file
    from rawfilter.run import shorten_number_cn
    from loguru import logger
    result_stats = {'moved_to_trash': 0, 'moved_to_multi': 0, 'created_shortcuts': 0}
    group_base_name, _ = clean_filename(group_files[0])
    group_id = abs(hash(group_base_name)) % 10000
    filtered_files = [f for f in group_files if not is_in_blacklist(f)]
    if not filtered_files:
        logger.info("[#group_info] ⏭️ 组[%s]跳过: 所有文件都在黑名单中", group_base_name)
        return result_stats
    chinese_versions = []
    other_versions = []
    for f in filtered_files:
        full_path = os.path.join(base_dir, f)
        if is_chinese_version(f):
            chinese_versions.append(full_path)
        else:
            other_versions.append(full_path)
    chinese_has_original = any(has_original_keywords(f) for f in chinese_versions)
    if not chinese_has_original:
        original_keyword_versions = [f for f in other_versions if has_original_keywords(os.path.basename(f))]
        if original_keyword_versions:
            chinese_versions.extend(original_keyword_versions)
            other_versions = [f for f in other_versions if not has_original_keywords(os.path.basename(f))]
            logger.info(f"[#file_ops] 📝 将{len(original_keyword_versions)}个包含原版关键词的文件归入保留列表")
    processed_files = []
    file_metrics = {}
    for file in chinese_versions + other_versions:
        old_path, new_path, metrics = process_file_with_count(file, name_only_mode)
        processed_files.append((old_path, new_path))
        file_metrics[old_path] = metrics
    best_metrics = {
        'width': max((m['width'] for m in file_metrics.values()), default=0),
        'page_count': min((m['page_count'] for m in file_metrics.values() if m['page_count'] > 0), default=0),
        'clarity_score': max((m['clarity_score'] for m in file_metrics.values()), default=0)
    }
    metrics_same = {
        'width': len(set(m['width'] for m in file_metrics.values() if m['width'] > 0)) <= 1,
        'page_count': len(set(m['page_count'] for m in file_metrics.values() if m['page_count'] > 0)) <= 1,
        'clarity_score': len(set(m['clarity_score'] for m in file_metrics.values() if m['clarity_score'] > 0)) <= 1
    }
    updated_files = []
    if name_only_mode:
        # 仅名称模式：跳过重命名，保持原始文件名
        logger.info("[#name_only] 🏷️ 仅名称模式，跳过组号和指标添加")
        updated_files = [(old_path, old_path) for old_path, _ in processed_files]
    else:
        # 标准模式：添加组号和指标
        for old_path, _ in processed_files:
            metrics = file_metrics[old_path]
            parts = []
            parts.append(f"🪆G{group_id:04d}")
            if metrics['width'] > 0:
                width_str = f"{shorten_number_cn(metrics['width'], use_w=True)}@WD"
                if not metrics_same['width'] and metrics['width'] == best_metrics['width']:
                    width_str = f"📏{width_str}"
                parts.append(width_str)
            if metrics['page_count'] > 0:
                page_str = f"{shorten_number_cn(metrics['page_count'], use_w=True)}@PX"
                if not metrics_same['page_count'] and metrics['page_count'] == best_metrics['page_count']:
                    page_str = f"📄{page_str}"
                parts.append(page_str)
            if metrics['clarity_score'] > 0:
                clarity_str = f"{shorten_number_cn(int(metrics['clarity_score']), use_w=True)}@DE"
                if not metrics_same['clarity_score'] and metrics['clarity_score'] == best_metrics['clarity_score']:
                    clarity_str = f"🔍{clarity_str}"
                parts.append(clarity_str)
            dir_name = os.path.dirname(old_path)
            file_name = os.path.basename(old_path)
            name, ext = os.path.splitext(file_name)
            name = re.sub(r'\{[^}]*\}', '', name)
            metrics_str = "{" + ",".join(parts) + "}" if parts else ""
            new_name = f"{metrics_str}{name}{ext}"
            new_path = os.path.join(dir_name, new_name)
            old_full_path = os.path.join(base_dir, old_path)
            new_full_path = os.path.join(base_dir, new_path)
            try:
                os.rename(old_full_path, new_full_path)
                updated_files.append((old_path, new_path))
                logger.info(f"[#file_ops] ✅ 已重命名: {old_path} -> {new_path}")
            except Exception as e:
                logger.error(f"[#error_log] ❌ 重命名失败 {old_path}: {str(e)}")
                updated_files.append((old_path, old_path))
    chinese_versions = [new_path for old_path, new_path in updated_files if old_path in chinese_versions]
    other_versions = [new_path for old_path, new_path in updated_files if old_path in other_versions]

    # 统一调用公共版本裁剪逻辑
    from .version_pruner import prune_version_files
    chinese_versions, other_versions = prune_version_files(
        chinese_versions,
        other_versions,
        base_dir,
        trash_dir,
        result_stats,
        safe_move_file,
        logger
    )
    if chinese_versions:
        if len(chinese_versions) > 1:
            multi_dir = os.path.join(base_dir, 'multi')
            os.makedirs(multi_dir, exist_ok=True)
            if enable_multi_main:
                main_file = max(chinese_versions, key=lambda x: os.path.getsize(os.path.join(base_dir, x)))
                if handle_multi_main_file(main_file, base_dir):
                    logger.info(f"[#file_ops] ✅ 已处理multi-main文件: {main_file}")
            for file in chinese_versions:
                src_path = os.path.join(base_dir, file)
                rel_path = os.path.relpath(src_path, base_dir)
                dst_path = os.path.join(multi_dir, rel_path)
                if safe_move_file(src_path, dst_path):
                    logger.info(f"[#file_ops] ✅ 已移动到multi: {file}")
                    result_stats['moved_to_multi'] += 1
            for other_file in other_versions:
                src_path = os.path.join(base_dir, other_file)
                rel_path = os.path.relpath(src_path, base_dir)
                dst_path = os.path.join(trash_dir, rel_path)
                if create_shortcuts:
                    shortcut_path = os.path.splitext(dst_path)[0]
                    if create_shortcut(src_path, shortcut_path):
                        logger.info(f"[#file_ops] ✅ 已创建快捷方式: {other_file}")
                        result_stats['created_shortcuts'] += 1
                else:
                    if safe_move_file(src_path, dst_path):
                        logger.info(f"[#file_ops] ✅ 已移动到trash: {other_file}")
                        result_stats['moved_to_trash'] += 1
        else:
            logger.info(f"[#group_info] 🔍 组[{group_base_name}]处理: 发现1个需要保留的版本，保持原位置")
            for other_file in other_versions:
                src_path = os.path.join(base_dir, other_file)
                rel_path = os.path.relpath(src_path, base_dir)
                dst_path = os.path.join(trash_dir, rel_path)
                if create_shortcuts:
                    shortcut_path = os.path.splitext(dst_path)[0]
                    if create_shortcut(src_path, shortcut_path):
                        logger.info(f"[#file_ops] ✅ 已创建快捷方式: {other_file}")
                        result_stats['created_shortcuts'] += 1
                else:
                    if safe_move_file(src_path, dst_path):
                        logger.info(f"[#file_ops] ✅ 已移动到trash: {other_file}")
                        result_stats['moved_to_trash'] += 1
    else:
        if len(other_versions) > 1:
            multi_dir = os.path.join(base_dir, 'multi')
            os.makedirs(multi_dir, exist_ok=True)
            if enable_multi_main:
                main_file = max(other_versions, key=lambda x: os.path.getsize(os.path.join(base_dir, x)))
                if handle_multi_main_file(main_file, base_dir):
                    logger.info(f"[#file_ops] ✅ 已处理multi-main文件: {main_file}")
            for file in other_versions:
                src_path = os.path.join(base_dir, file)
                rel_path = os.path.relpath(src_path, base_dir)
                dst_path = os.path.join(multi_dir, rel_path)
                if safe_move_file(src_path, dst_path):
                    logger.info(f"[#file_ops] ✅ 已移动到multi: {file}")
                    result_stats['moved_to_multi'] += 1
            logger.info(f"[#group_info] 🔍 组[{group_base_name}]处理: 未发现汉化版本，发现{len(other_versions)}个原版，已移动到multi")
        else:
            logger.info(f"[#group_info] 🔍 组[{group_base_name}]处理: 未发现汉化版本，仅有1个原版，保持原位置")
    return result_stats

def process_directory(directory: str, report_generator: ReportGenerator, dry_run: bool = False, create_shortcuts: bool = False, enable_multi_main: bool = False, name_only_mode: bool = False) -> None:
    from rawfilter.__main__ import group_similar_files
    from loguru import logger
    import os
    trash_dir = os.path.join(directory, 'trash')
    if not dry_run:
        os.makedirs(trash_dir, exist_ok=True)
    all_files = []
    logger.info("[#process] 🔍 正在扫描文件...")
    for root, _, files in os.walk(directory):
        if 'trash' in root or 'multi' in root:
            logger.info("[#file_ops] ⏭️ 跳过目录: %s", root)
            continue
        for file in files:
            if os.path.splitext(file.lower())[1] in ARCHIVE_EXTENSIONS:
                rel_path = os.path.relpath(os.path.join(root, file), directory)
                all_files.append(rel_path)
                logger.info("[@process] 扫描进度: %d/%d", len(all_files), len(all_files))
    if not all_files:
        logger.info("[#error_log] ⚠️ 目录 %s 中未找到压缩文件", directory)
        return
    report_generator.update_stats('total_files', len(all_files))
    groups = group_similar_files(all_files)
    logger.info("[#stats] 📊 总计: %d个文件, %d个组", len(all_files), len(groups))
    report_generator.update_stats('total_groups', len(groups))
    logger.info("[#process] 🔄 开始处理文件组...")
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import os
    with ProcessPoolExecutor(max_workers=min(os.cpu_count() * 2, 8)) as executor:
        futures = {}
        for group_base_name, group_files in groups.items():
            if len(group_files) > 1:
                future = executor.submit(
                    process_file_group,
                    group_files,
                    directory,
                    trash_dir,
                    create_shortcuts,
                    enable_multi_main,
                    name_only_mode
                )
                futures[future] = group_base_name
        completed = 0
        for future in as_completed(futures.keys()):
            completed += 1
            future_count = len(futures)
            scan_percent = completed / future_count * 100
            try:
                result_stats = future.result()
                for key, value in result_stats.items():
                    if value > 0:
                        report_generator.update_stats(key, value)
            except Exception as e:
                logger.error(f"[#error_log] ❌ 处理组时出错: {futures[future]}, 错误: {str(e)}")
            logger.info(f"[@stats] 组进度: ({completed}/{future_count}) {scan_percent:.2f}%")
