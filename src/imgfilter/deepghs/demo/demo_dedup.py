import os
import numpy as np
from PIL import Image
import pillow_avif
import pillow_jxl 
import base64
import io
from pathlib import Path
import argparse
from typing import List, Dict, Tuple

from imgutils.metrics import lpips_difference, lpips_clustering

def image_to_base64(image_path):
    """Convert an image to base64 for HTML embedding"""
    img = Image.open(image_path)
    # Resize if too large
    if max(img.size) > 500:
        ratio = 500 / max(img.size)
        img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def generate_html_report(
    image_paths: List[str], 
    diff_matrix: np.ndarray, 
    clusters: List[int]
) -> str:
    """Generate HTML report for image difference detection"""
    # Create base64 images
    base64_images = [image_to_base64(img_path) for img_path in image_paths]
    image_names = [os.path.basename(img_path) for img_path in image_paths]
    
    # Start HTML content
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Image Difference Detection Results</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { display: flex; flex-direction: column; }
            .matrix-container { margin-bottom: 30px; }
            .image-grid { display: flex; flex-wrap: wrap; }
            .image-card { margin: 10px; border: 1px solid #ddd; padding: 10px; border-radius: 5px; }
            .cluster-0 { border-color: #ff6666; }
            .cluster-1 { border-color: #66ff66; }
            .cluster-2 { border-color: #6666ff; }
            .cluster-3 { border-color: #ffff66; }
            .cluster-4 { border-color: #ff66ff; }
            .cluster-5 { border-color: #66ffff; }
            .cluster-noise { border-color: #999999; }
            table { border-collapse: collapse; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
            .highlight { background-color: #ffffcc; }
        </style>
    </head>
    <body>
        <h1>Image Difference Detection Results</h1>
        <div class="container">
            <div class="matrix-container">
                <h2>Difference Matrix</h2>
                <table>
                    <tr>
                        <th></th>
    """
    
    # Add column headers
    for name in image_names:
        html += f"<th>{name}</th>"
    html += "</tr>"
    
    # Add matrix rows
    for i, name in enumerate(image_names):
        html += f"<tr><th>{name}</th>"
        for j in range(len(image_names)):
            cell_class = "highlight" if i == j else ""
            html += f"<td class='{cell_class}'>{diff_matrix[i, j]:.4f}</td>"
        html += "</tr>"
    
    html += """
                </table>
            </div>
            
            <h2>Clustering Results</h2>
            <div class="image-grid">
    """
    
    # Add image cards with clustering info
    for i, (img_b64, name, cluster) in enumerate(zip(base64_images, image_names, clusters)):
        cluster_class = f"cluster-{cluster}" if cluster >= 0 else "cluster-noise"
        cluster_label = f"Cluster {cluster}" if cluster >= 0 else "Noise"
        html += f"""
            <div class="image-card {cluster_class}">
                <img src="data:image/png;base64,{img_b64}" alt="{name}" style="max-width: 200px; max-height: 200px;">
                <p><strong>{name}</strong></p>
                <p>Cluster: {cluster_label}</p>
            </div>
        """
    
    # Close HTML
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

def process_image_folder(folder_path: str, output_html: str = "difference_results.html"):
    """Process all images in a folder and generate HTML report"""
    # Get all image files
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp','.avif', '.jxl']
    image_paths = []
    
    # 支持扫描文件夹下的所有子文件夹
    for ext in image_extensions:
        # 扫描当前文件夹
        image_paths.extend(list(Path(folder_path).glob(f"*{ext}")))
        # 扫描所有子文件夹 (使用 rglob 递归扫描)
        image_paths.extend(list(Path(folder_path).rglob(f"*/*{ext}")))
    
    # 去重
    image_paths = list(set([str(p) for p in image_paths]))
    # 排序以保证结果一致性
    image_paths.sort()
    
    if not image_paths:
        print(f"在 {folder_path} 中未找到图片")
        return
    
    print(f"在 {folder_path} 中找到 {len(image_paths)} 张图片")
    
    # 询问用户是否继续处理
    if len(image_paths) > 10:
        print(f"警告：找到了 {len(image_paths)} 张图片，处理可能需要较长时间")
        confirm = input("是否继续处理？(y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消操作")
            return
    
    # Calculate difference matrix
    n = len(image_paths)
    diff_matrix = np.zeros((n, n))
    
    print("正在计算图片差异...")
    # 显示进度信息
    total_comparisons = n * (n - 1) // 2
    current_comparison = 0
    
    for i in range(n):
        for j in range(i, n):
            if i == j:
                diff = 0.0
            else:
                current_comparison += 1
                progress = current_comparison / total_comparisons * 100
                print(f"\r进度: {progress:.1f}% - 正在比较 {os.path.basename(image_paths[i])} 和 {os.path.basename(image_paths[j])}", end="")
                
                diff = lpips_difference(image_paths[i], image_paths[j])
            
            diff_matrix[i, j] = diff
            diff_matrix[j, i] = diff
    
    print("\n差异计算完成")
    
    # Perform clustering
    print("正在执行聚类分析...")
    clusters = lpips_clustering(image_paths)
    print(f"聚类结果: {clusters}")
    
    # 统计每个聚类的图片数量
    cluster_counts = {}
    for cluster in clusters:
        if cluster not in cluster_counts:
            cluster_counts[cluster] = 0
        cluster_counts[cluster] += 1
    
    print("聚类统计:")
    for cluster, count in cluster_counts.items():
        cluster_name = f"聚类 {cluster}" if cluster >= 0 else "噪声点"
        print(f"{cluster_name}: {count} 张图片")
    
    # Generate HTML report
    html_content = generate_html_report(image_paths, diff_matrix, clusters)
    
    # Save HTML file
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"结果已保存至 {output_html}")
    
    # 自动打开HTML文件
    try:
        import webbrowser
        webbrowser.open(output_html)
        print("已自动打开结果页面")
    except Exception as e:
        print(f"无法自动打开结果页面: {e}")
        print(f"请手动打开文件: {os.path.abspath(output_html)}")

if __name__ == "__main__":
    import sys
    
    # 检查是否有命令行参数
    if len(sys.argv) > 1:
        # 使用命令行参数
        parser = argparse.ArgumentParser(description="Image Difference Detection")
        parser.add_argument("folder", help="Folder containing images to analyze")
        parser.add_argument("--output", "-o", default="difference_results.html", 
                            help="Output HTML file (default: difference_results.html)")
        
        args = parser.parse_args()
        folder_path = args.folder
        output_path = args.output
    else:
        # 交互式输入
        print("=== 图片差分检测工具 ===")
        folder_path = input("请输入图片文件夹路径: ").strip()
        
        # 验证文件夹路径是否存在
        while not os.path.isdir(folder_path):
            print(f"错误：路径 '{folder_path}' 不存在或不是文件夹")
            folder_path = input("请重新输入图片文件夹路径 (或输入 'q' 退出): ").strip()
            if folder_path.lower() == 'q':
                sys.exit(0)
        
        # 询问输出HTML文件路径
        default_output = "difference_results.html"
        output_path_input = input(f"请输入输出HTML文件路径 (默认: {default_output}): ").strip()
        output_path = output_path_input if output_path_input else default_output
    
    # 处理图片文件夹
    process_image_folder(folder_path, output_path)