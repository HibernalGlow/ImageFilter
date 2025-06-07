import os
import sys
import ctypes
from PIL import Image
import pillow_avif
import pillow_jxl
import numpy as np
from concurrent.futures import ThreadPoolExecutor
os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ['LPIPS_USE_GPU'] = '1'
from imgutils.metrics import lpips_clustering
from pathlib import Path
from hashu.core.calculate_hash_custom import ImageHashCalculator

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
            print(f"已添加 CUDA bin 目录到 DLL 搜索路径: {cuda_bin}")
        except Exception as e:
            print(f"设置 DLL 目录失败: {e}")

# 设置环境变量



# 支持的图片扩展名
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.avif', '.jxl'}

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
    print(f"HTML报告已生成: {output_html}")

def load_image(path):
    return Image.open(path).copy()  # .copy() 避免文件句柄未关闭

def batch_load_images(image_files, max_workers=8):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        images = list(executor.map(load_image, image_files))
    return images

def main():
    print("=== 图片聚类 HTML 报告生成器 ===")
    folder = input("请输入图片文件夹路径: ").strip()
    if not os.path.isdir(folder):
        print("错误：文件夹不存在！")
        return
    image_files = get_image_files(folder)
    if len(image_files) < 2:
        print("错误：图片数量不足，至少需要2张图片！")
        return
    print(f"共检测到 {len(image_files)} 张图片，正在进行聚类...")
    clusters = lpips_clustering(image_files, threshold=0.01)
    # 按聚类分组
    cluster_dict = {}
    for img_path, cluster in zip(image_files, clusters):
        # 路径用相对路径，方便HTML浏览
        rel_path = os.path.relpath(img_path, start=folder)
        cluster_dict.setdefault(cluster, []).append(rel_path)
    # 生成HTML报告
    output_html = os.path.join(folder, "cluster_report.html")
    generate_html_report(cluster_dict, output_html)
    print("全部完成！请用浏览器打开报告查看聚类结果。")

if __name__ == "__main__":
    main() 