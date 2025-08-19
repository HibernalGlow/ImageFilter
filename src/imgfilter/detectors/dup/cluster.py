import os
import argparse
from PIL import Image
import pillow_avif
import pillow_jxl 
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import psutil
import platform
import sys
from datetime import datetime
import ctypes
from loguru import logger
import importlib.util

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

def cudain():
    """初始化CUDA环境"""
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

# 设置基础环境变量
os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# CPU 模式下的聚类函数 - 修改为可导出的版本
def lpips_clustering_cpu(image_files, threshold=0.04):
    """CPU 模式下的图片聚类实现
    
    Args:
        image_files: 图片文件路径列表
        threshold: 聚类阈值
        
    Returns:
        list: 每个图片对应的聚类标签
    """
    # 保存原始环境变量
    old_env = os.environ.get('LPIPS_USE_GPU', '1')
    
    # 设置环境变量强制使用CPU
    os.environ['LPIPS_USE_GPU'] = '0'
    
    try:
        # 延迟导入，确保环境变量生效
        from imgutils.metrics import lpips_clustering
        result = lpips_clustering(image_files, threshold=threshold)
        return result
    finally:
        # 恢复原来的环境变量
        os.environ['LPIPS_USE_GPU'] = old_env

# GPU 模式下的聚类函数 - 修改为可导出的版本
def lpips_clustering_gpu(image_files, threshold=0.04):
    """GPU 模式下的图片聚类实现
    
    Args:
        image_files: 图片文件路径列表
        threshold: 聚类阈值
        
    Returns:
        list: 每个图片对应的聚类标签
    """
    # 保存原始环境变量
    old_env = os.environ.get('LPIPS_USE_GPU', '0')
    
    # 初始化CUDA环境
    cudain()
    
    # 设置环境变量以使用GPU
    os.environ['LPIPS_USE_GPU'] = '1'
    
    try:
        # 延迟导入，确保环境变量生效
        from imgutils.metrics import lpips_clustering
        result = lpips_clustering(image_files, threshold=threshold)
        return result
    finally:
        # 恢复原来的环境变量
        os.environ['LPIPS_USE_GPU'] = old_env

# 以下为命令行工具的代码，在被导入时不会执行
# 命令行参数解析
def parse_args():
    parser = argparse.ArgumentParser(description="图片聚类工具")
    parser.add_argument("--gpu", action="store_true", help="使用GPU模式运行（默认使用CPU）")
    parser.add_argument("--folder", type=str, help="图片文件夹路径")
    parser.add_argument("--threshold", type=float, default=0.04, help="聚类相似度阈值（默认0.04）")
    return parser.parse_args()

# 支持的图片扩展名
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.avif', '.jxl'}

def get_memory_usage():
    """获取当前进程的内存使用情况"""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    return {
        'rss': memory_info.rss / (1024 * 1024),  # RSS (常驻内存), MB
        'vms': memory_info.vms / (1024 * 1024),  # VMS (虚拟内存), MB
    }

def log_system_info(use_gpu_mode):
    """记录系统信息"""
    logger.info(f"系统信息: {platform.system()} {platform.version()}")
    logger.info(f"Python版本: {platform.python_version()}")
    logger.info(f"处理器: {platform.processor()}")
    
    # 记录CUDA环境
    cuda_path = os.environ.get('CUDA_PATH', '未设置')
    logger.info(f"CUDA_PATH: {cuda_path}")
    
    # 记录环境变量和CPU/GPU模式
    logger.info(f"运行模式: {'GPU模式' if use_gpu_mode else 'CPU模式'}")
    logger.info(f"LPIPS_USE_GPU: {os.environ.get('LPIPS_USE_GPU', '未设置')}")
    
    # 尝试获取GPU信息
    # if use_gpu_mode:
    #     try:
    #         import torch
    #         logger.info(f"PyTorch版本: {torch.__version__}")
    #         logger.info(f"CUDA可用: {torch.cuda.is_available()}")
    #         if torch.cuda.is_available() and use_gpu_mode:
    #             logger.info(f"GPU设备: {torch.cuda.get_device_name(0)}")
    #     except ImportError:
    #         logger.warning("PyTorch未安装，无法获取GPU信息")
    
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
    
def get_image_files(folder):
    """递归获取文件夹及其子文件夹下所有图片文件路径"""
    return [str(p) for p in Path(folder).rglob('*') if p.suffix.lower() in IMG_EXTS and p.is_file()]

def save_thumbnail(image_path, thumb_dir, size=(256, 256)):
    """保存缩略图，返回缩略图路径"""
    img = Image.open(image_path)
    img.thumbnail(size)
    thumb_path = os.path.join(thumb_dir, os.path.basename(image_path))
    img.save(thumb_path)
    return thumb_path

def generate_html_report(cluster_dict, output_html):
    """生成聚类结果的HTML报告（用原图，表格展示图片和路径）"""
    html = [
        '<!DOCTYPE html>',
        '<html lang="zh-CN">',
        '<head>',
        '<meta charset="UTF-8">',
        '<title>图片聚类报告</title>',
        '<style>body{font-family:sans-serif;} .cluster{margin-bottom:40px;} table{border-collapse:collapse;} td,th{border:1px solid #ccc;padding:6px;} img{max-width:240px;max-height:240px;}</style>',
        '</head>',
        '<body>',
        '<h1>图片聚类报告</h1>'
    ]
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
    logger.info(f"HTML报告已生成: {output_html}")

def load_image(path):
    return Image.open(path).copy()  # .copy() 避免文件句柄未关闭

def batch_load_images(image_files, max_workers=8):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        images = list(executor.map(load_image, image_files))
    return images

def main():
    # 初始化日志系统
    logger, config_info = setup_logger(app_name="demo_cluster", console_output=True)
    
    # 获取命令行参数以决定CPU/GPU模式
    args = parse_args()
    USE_GPU_MODE = args.gpu  # 默认为CPU模式
    
    # 根据模式初始化环境
    if USE_GPU_MODE:
        logger.info("使用GPU模式")
        cudain()
    else:
        logger.info("使用CPU模式")
        os.environ['LPIPS_USE_GPU'] = '0'
        
    logger.info("=== 图片聚类 HTML 报告生成器 ===")
    logger.info(f"当前运行模式: {'GPU模式' if USE_GPU_MODE else 'CPU模式'}")
    log_system_info(USE_GPU_MODE)
    memory_info = get_memory_usage()
    logger.info(f"内存占用: RSS={memory_info['rss']:.1f}MB, VMS={memory_info['vms']:.1f}MB")
    
    # 获取图片文件夹路径，优先使用命令行参数
    folder = args.folder if args.folder else input("请输入图片文件夹路径: ").strip()
    if not os.path.isdir(folder):
        logger.error("错误：文件夹不存在！")
        return
    image_files = get_image_files(folder)
    if len(image_files) < 2:
        logger.error("错误：图片数量不足，至少需要2张图片！")
        return
    logger.info(f"共检测到 {len(image_files)} 张图片，正在进行聚类...")
    
    # 执行聚类，记录开始时间
    start_time = datetime.now()
    # 使用命令行参数中的阈值
    threshold = args.threshold
    logger.info(f"使用聚类阈值: {threshold}")
    
    # 根据模式选择不同的聚类实现
    if USE_GPU_MODE:
        clusters = lpips_clustering_gpu(image_files, threshold=threshold)
    else:
        clusters = lpips_clustering_cpu(image_files, threshold=threshold)
        
    elapsed_time = (datetime.now() - start_time).total_seconds()
    logger.info(f"聚类完成，耗时: {elapsed_time:.2f}秒 (模式: {'GPU' if USE_GPU_MODE else 'CPU'})")
    
    # 按聚类分组
    cluster_dict = {}
    for img_path, cluster in zip(image_files, clusters):
        # 路径用相对路径，方便HTML浏览
        rel_path = os.path.relpath(img_path, start=folder)
        cluster_dict.setdefault(cluster, []).append(rel_path)
    
    # 计算聚类统计信息
    num_clusters = len(set(clusters) - {-1})
    noise_count = clusters.count(-1) if -1 in clusters else 0
    logger.info(f"聚类结果: {num_clusters} 个聚类, {noise_count} 个未归类项")
    
    # 生成HTML报告 - 包含所有项（包括噪音和未聚类项）
    output_html = os.path.join(folder, "cluster_report.html")
    generate_html_report(cluster_dict, output_html)
    logger.info("全部完成！请用浏览器打开报告查看聚类结果。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("用户中断程序")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序执行出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1) 