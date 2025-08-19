import os
from PIL import Image
import pillow_avif
import pillow_jxl
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from hashu.core.calculate_hash_custom import ImageHashCalculator

os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ['LPIPS_USE_GPU'] = '1'
from imgutils.metrics import lpips_clustering

# 支持的图片扩展名
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.avif', '.jxl'}

def get_image_files(folder):
    """递归获取文件夹及其子文件夹下所有图片文件路径"""
    return [str(p) for p in Path(folder).rglob('*') if p.suffix.lower() in IMG_EXTS and p.is_file()]

def group_by_phash(image_files, hash_size=10, threshold=16, max_workers=8):
    """用phash+汉明距离分大组"""
    # 1. 计算所有图片的phash
    def calc_phash(path):
        return ImageHashCalculator.calculate_phash(path, hash_size=hash_size)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        phash_list = list(executor.map(calc_phash, image_files))
    # 2. 分组
    groups = []  # 每组是[(idx, phash)]
    assigned = [False] * len(image_files)
    for i, h1 in enumerate(phash_list):
        if assigned[i]:
            continue
        group = [i]
        assigned[i] = True
        for j in range(i+1, len(image_files)):
            if assigned[j]:
                continue
            h2 = phash_list[j]
            dist = ImageHashCalculator.calculate_hamming_distance(h1, h2)
            if dist <= threshold:
                group.append(j)
                assigned[j] = True
        groups.append(group)
    # 返回：{组号: [图片路径列表]}
    return {gi: [image_files[idx] for idx in g] for gi, g in enumerate(groups)}

def generate_html_report(nested_clusters, output_html):
    """生成分层聚类HTML报告：外层phash大组，内层lpips小组"""
    html = [
        '<!DOCTYPE html>',
        '<html lang="zh-CN">',
        '<head>',
        '<meta charset="UTF-8">',
        '<title>分层图片聚类报告</title>',
        '<style>body{font-family:sans-serif;} .big-group{margin-bottom:60px;} .cluster{margin-bottom:30px;} table{border-collapse:collapse;} td,th{border:1px solid #ccc;padding:6px;} img{max-width:200px;max-height:200px;}</style>',
        '</head>',
        '<body>',
        '<h1>分层图片聚类报告</h1>'
    ]
    for big_idx, clusters in nested_clusters.items():
        html.append(f'<div class="big-group"><h2>哈希大组 {big_idx+1}（共{sum(len(imgs) for imgs in clusters.values())}张）</h2>')
        for cluster_idx, images in sorted(clusters.items(), key=lambda x: (x[0] == -1, x[0])):
            label = f"噪声/未归类" if cluster_idx == -1 else f"聚类 {cluster_idx}"
            html.append(f'<div class="cluster"><h3>{label}（{len(images)}张）</h3>')
            html.append('<table>')
            html.append('<tr><th>图片</th><th>路径</th></tr>')
            for img_path in images:
                html.append(f'<tr><td><img src="{img_path}" alt="{os.path.basename(img_path)}"></td><td>{img_path}</td></tr>')
            html.append('</table></div>')
        html.append('</div>')
    html.append('</body></html>')
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html))
    print(f"HTML报告已生成: {output_html}")

def main():
    print("=== 分层图片聚类 HTML 报告生成器 ===")
    folder = input("请输入图片文件夹路径: ").strip()
    if not os.path.isdir(folder):
        print("错误：文件夹不存在！")
        return
    image_files = get_image_files(folder)
    if len(image_files) < 2:
        print("错误：图片数量不足，至少需要2张图片！")
        return
    print(f"共检测到 {len(image_files)} 张图片，正在进行哈希大分组...")
    big_groups = group_by_phash(image_files, hash_size=10, threshold=16, max_workers=8)
    print(f"共分为 {len(big_groups)} 个哈希大组，正在组内细聚类...")
    nested_clusters = {}
    for big_idx, group_imgs in big_groups.items():
        if len(group_imgs) < 2:
            # 只有一张图，直接作为一个小组
            nested_clusters[big_idx] = {0: [os.path.relpath(p, start=folder) for p in group_imgs]}
            continue
        clusters = lpips_clustering(group_imgs, threshold=0.01)
        # 分组：{小组号: [图片相对路径]}
        cluster_dict = {}
        for img_path, cluster in zip(group_imgs, clusters):
            rel_path = os.path.relpath(img_path, start=folder)
            cluster_dict.setdefault(cluster, []).append(rel_path)
        nested_clusters[big_idx] = cluster_dict
    # 生成HTML报告
    output_html = os.path.join(folder, "cluster_report_hierarchical.html")
    generate_html_report(nested_clusters, output_html)
    print("全部完成！请用浏览器打开报告查看分层聚类结果。")

if __name__ == "__main__":
    main() 