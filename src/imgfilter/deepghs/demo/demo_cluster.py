import os
import sys
import ctypes
from PIL import Image
import pillow_avif
import pillow_jxl
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from imgutils.metrics import lpips_clustering
from pathlib import Path
from hashu.core.calculate_hash_custom import ImageHashCalculator
from loguru import logger
import time
import psutil
import gc
from datetime import datetime
import platform

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

def get_memory_usage():
    """获取当前进程的内存使用情况"""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    return {
        'rss': memory_info.rss / (1024 * 1024),  # RSS (常驻内存), MB
        'vms': memory_info.vms / (1024 * 1024),  # VMS (虚拟内存), MB
    }

def log_system_info():
    """记录系统信息"""
    logger.info(f"系统信息: {platform.system()} {platform.version()}")
    logger.info(f"Python版本: {platform.python_version()}")
    logger.info(f"处理器: {platform.processor()}")
    
    # 记录CUDA环境
    cuda_path = os.environ.get('CUDA_PATH', '未设置')
    logger.info(f"CUDA_PATH: {cuda_path}")
    
    # 记录环境变量
    logger.info(f"LPIPS_USE_GPU: {os.environ.get('LPIPS_USE_GPU', '未设置')}")
    
    # 尝试获取GPU信息
    try:
        import torch
        logger.info(f"PyTorch版本: {torch.__version__}")
        logger.info(f"CUDA可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"GPU设备: {torch.cuda.get_device_name(0)}")
    except ImportError:
        logger.warning("PyTorch未安装，无法获取GPU信息")
    
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        logger.info(f"ONNXRuntime版本: {ort.__version__}")
        logger.info(f"ONNXRuntime可用providers: {providers}")
    except ImportError:
        logger.warning("ONNXRuntime未安装")
    
    # 记录内存信息
    memory = get_memory_usage()
    logger.info(f"初始内存占用: RSS={memory['rss']:.1f}MB, VMS={memory['vms']:.1f}MB")

# 初始化日志系统
logger, config_info = setup_logger(app_name="demo_cluster", console_output=True)

# 记录系统信息
log_system_info()

# ===== DLL 路径设置（确保 cudnn64_9.dll 能被找到）=====
# 将 CUDA 的 bin 目录添加到 DLL 搜索路径
cuda_path = os.environ.get('CUDA_PATH')
if cuda_path:
    cuda_bin = os.path.join(cuda_path, 'bin')
    if os.path.exists(cuda_bin):
        # 添加到 PATH 环境变量
        os.environ['PATH'] = cuda_bin + os.pathsep + os.environ.get('PATH', '')
        # 使用 SetDllDirectory 明确告诉 Windows 在哪里查找 DLL
        try:
            ctypes.windll.kernel32.SetDllDirectoryW(cuda_bin)
            logger.info(f"已添加 CUDA bin 目录到 DLL 搜索路径: {cuda_bin}")
        except Exception as e:
            logger.error(f"设置 DLL 目录失败: {e}")

# 设置环境变量
os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ['LPIPS_USE_GPU'] = '1'

# 支持的图片扩展名
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.avif', '.jxl'}

def get_image_files(folder):
    """递归获取文件夹及其子文件夹下所有图片文件路径"""
    logger.info(f"开始扫描文件夹: {folder}")
    start_time = time.time()
    files = [str(p) for p in Path(folder).rglob('*') if p.suffix.lower() in IMG_EXTS and p.is_file()]
    logger.info(f"文件扫描完成，耗时: {time.time() - start_time:.2f}秒，找到 {len(files)} 个图片文件")
    return files

def prepare_thumbnails(image_files, thumb_dir, size=(256, 256), max_workers=8):
    """并行生成所有图片的缩略图"""
    logger.info(f"开始生成缩略图: 尺寸={size}, 线程数={max_workers}")
    os.makedirs(thumb_dir, exist_ok=True)
    start_time = time.time()
    
    def process_image(img_path):
        try:
            img = Image.open(img_path)
            img.thumbnail(size)
            thumb_path = os.path.join(thumb_dir, os.path.basename(img_path))
            img.save(thumb_path)
            return thumb_path
        except Exception as e:
            logger.error(f"处理图片失败: {img_path}, 错误: {e}")
            return None
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        thumb_paths = list(executor.map(process_image, image_files))
    
    # 过滤掉处理失败的图片
    thumb_paths = [p for p in thumb_paths if p]
    
    elapsed = time.time() - start_time
    logger.info(f"缩略图生成完成，耗时: {elapsed:.2f}秒, 平均每张: {elapsed/len(image_files):.3f}秒")
    return thumb_paths

def generate_html_report(cluster_dict, output_html):
    """生成聚类结果的HTML报告（用原图，表格展示图片和路径）"""
    logger.info(f"开始生成HTML报告: {output_html}")
    start_time = time.time()
    
    html = [
        '<!DOCTYPE html>',
        '<html lang="zh-CN">',
        '<head>',
        '<meta charset="UTF-8">',
        '<title>图片聚类报告</title>',
        '<style>body{font-family:sans-serif;} .cluster{margin-bottom:40px;} table{border-collapse:collapse;} td,th{border:1px solid #ccc;padding:6px;} img{max-width:240px;max-height:240px;}</style>',
        '</head>',
        '<body>',
        '<h1>图片聚类报告</h1>',
        f'<p>生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>'
    ]
    
    # 添加聚类统计信息
    total_images = sum(len(images) for images in cluster_dict.values())
    clusters_count = len(cluster_dict)
    html.append(f'<p>共 {total_images} 张图片，分为 {clusters_count} 个聚类</p>')
    
    for cluster, images in sorted(cluster_dict.items(), key=lambda x: (x[0] == -1, x[0])):
        label = f"噪声/未归类" if cluster == -1 else f"聚类 {cluster}"
        html.append(f'<div class="cluster"><h2>{label}（{len(images)}张）</h2>')
        html.append('<table>')
        html.append('<tr><th>图片</th><th>路径</th></tr>')
        for img_path in images:
            html.append(f'<tr><td><img src="{img_path}" alt="{os.path.basename(img_path)}"></td><td>{img_path}</td></tr>')
        html.append('</table></div>')
    html.append('</body></html>')
    
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html))
    
    logger.info(f"HTML报告生成完成，耗时: {time.time() - start_time:.2f}秒")
    return output_html

def main():
    logger.info("=== 图片聚类 HTML 报告生成器 ===")
    
    # 设置GPU/CPU配置
    use_gpu = os.environ.get('LPIPS_USE_GPU') == '1'
    logger.info(f"当前配置: {'GPU模式' if use_gpu else 'CPU模式'}")
    
    # 输入文件夹路径
    folder = input("请输入图片文件夹路径: ").strip()
    if not os.path.isdir(folder):
        logger.error(f"错误：文件夹不存在！{folder}")
        return
    
    
    # 获取所有图片文件
    image_files = get_image_files(folder)
    if len(image_files) < 2:
        logger.error("错误：图片数量不足，至少需要2张图片！")
        return
    
    # 生成缩略图目录
    logger.info("准备聚类处理...")
    
    # 记录初始内存使用
    memory_before = get_memory_usage()
    logger.info(f"聚类前内存占用: RSS={memory_before['rss']:.1f}MB, VMS={memory_before['vms']:.1f}MB")
    
    # 使用缩略图加速聚类（可选）
    use_thumbnails = False  # 设置为False使用原图
    if use_thumbnails:
        logger.info("使用缩略图模式进行聚类（更快、更省内存）")
        thumb_dir = os.path.join(folder, "thumbnails_for_cluster")
        thumb_files = prepare_thumbnails(image_files, thumb_dir, size=(256, 256))
        
        # 开始聚类
        logger.info(f"开始聚类处理，图片数量: {len(thumb_files)}")
        start_time = time.time()
        clusters = lpips_clustering(thumb_files, threshold=0.01)
        clustering_time = time.time() - start_time
        logger.info(f"聚类完成，耗时: {clustering_time:.2f}秒，平均每张: {clustering_time/len(thumb_files):.3f}秒")
    else:
        # 使用原图进行聚类（较慢）
        logger.info(f"开始聚类处理，图片数量: {len(image_files)}")
        start_time = time.time()
        clusters = lpips_clustering(image_files, threshold=0.01)
        clustering_time = time.time() - start_time
        logger.info(f"聚类完成，耗时: {clustering_time:.2f}秒，平均每张: {clustering_time/len(image_files):.3f}秒")
    
    # 强制进行垃圾回收
    gc.collect()
    memory_after = get_memory_usage()
    logger.info(f"聚类后内存占用: RSS={memory_after['rss']:.1f}MB, VMS={memory_after['vms']:.1f}MB")
    logger.info(f"内存增长: RSS={memory_after['rss']-memory_before['rss']:.1f}MB")
    
    # 按聚类分组（使用原图路径输出结果）
    cluster_dict = {}
    for i, cluster in enumerate(clusters):
        # 使用原图路径
        img_path = image_files[i]  
        # 路径用相对路径，方便HTML浏览
        rel_path = os.path.relpath(img_path, start=folder)
        cluster_dict.setdefault(cluster, []).append(rel_path)
    
    # 分析聚类结果
    cluster_sizes = {cluster: len(images) for cluster, images in cluster_dict.items()}
    logger.info(f"聚类结果: 共 {len(cluster_dict)} 个聚类")
    for cluster, size in sorted(cluster_sizes.items()):
        logger.info(f"聚类 {cluster}: {size} 张图片")
    
    # 生成HTML报告
    output_html = os.path.join(folder, "cluster_report.html")
    generate_html_report(cluster_dict, output_html)
    
    # 如果使用了缩略图，提示用户
    if use_thumbnails:
        logger.info(f"缩略图保存在: {thumb_dir}")
    
    logger.info("全部完成！请用浏览器打开报告查看聚类结果。")
    print(f"\n报告文件: {output_html}")
    print(f"日志文件: {config_info['log_file']}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"程序异常: {e}")
        print(f"程序出错，详情请查看日志: {config_info['log_file']}") 