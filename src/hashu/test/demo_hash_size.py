import time
from pathlib import Path
from itertools import combinations
from PIL import Image
import pillow_avif
import pillow_jxl 
import imagehash

def calc_hashes_for_images(image_files, hash_size):
    """批量计算图片哈希（不依赖ImageHashCalculator）"""
    hashes = {}
    for img in image_files:
        try:
            with Image.open(img) as im:
                h = imagehash.phash(im, hash_size=hash_size)
                hashes[str(img)] = h
        except Exception as e:
            print(f"图片处理失败: {img}，原因: {e}")
    return hashes

def calc_hamming_pairs(hashes):
    """计算所有图片两两汉明距离"""
    dists = []
    pairs = []
    items = list(hashes.items())
    for (img1, h1), (img2, h2) in combinations(items, 2):
        dist = h1 - h2  # imagehash对象直接支持汉明距离
        dists.append(dist)
        pairs.append((img1, img2, dist))
    return dists, pairs

def benchmark_phash_sizes(image_dir, hash_sizes=(8, 12, 16)):
    image_dir = Path(image_dir)
    image_files = [f for f in image_dir.glob("*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".jxl", ".avif"]]
    print(f"共找到 {len(image_files)} 张图片")
    results = {}

    for size in hash_sizes:
        print(f"\n=== phash size={size} ===")
        start = time.time()
        hashes = calc_hashes_for_images(image_files, size)
        elapsed = time.time() - start
        print(f"计算耗时: {elapsed:.2f} 秒")
        dists, pairs = calc_hamming_pairs(hashes)
        if dists:
            avg_dist = sum(dists) / len(dists)
            print(f"平均汉明距离: {avg_dist:.2f}，最大: {max(dists)}，最小: {min(dists)}")
        else:
            print("图片数量过少，无法对比汉明距离")
        results[size] = {
            "hashes": hashes,
            "time": elapsed,
            "dists": dists,
            "pairs": pairs
        }
    return results, image_files

def generate_html_report(results, image_files, output_path="phash_benchmark_report.html"):
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>pHash Size Benchmark Report</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;margin:30px;}",
        "table{border-collapse:collapse;width:100%;margin:20px 0;}",
        "th,td{border:1px solid #ddd;padding:8px;text-align:center;}",
        "th{background:#f2f2f2;}",
        "tr:hover{background:#f9f9f9;}",
        ".section{margin-bottom:40px;}",
        "img.thumb{max-width:120px;max-height:120px;display:block;margin:auto;box-shadow:0 2px 8px #aaa;}",
        ".filename{font-size:12px;color:#555;word-break:break-all;}",
        "</style></head><body>",
        "<h1>pHash Size Benchmark Report</h1>",
        f"<p>图片总数：{len(image_files)}</p>"
    ]
    # 总览表
    html.append("<div class='section'><h2>总体对比</h2><table>")
    html.append("<tr><th>pHash Size</th><th>计算耗时(秒)</th><th>平均汉明距离</th><th>最大</th><th>最小</th></tr>")
    for size, info in results.items():
        dists = info["dists"]
        avg = f"{sum(dists)/len(dists):.2f}" if dists else "-"
        maxv = f"{max(dists)}" if dists else "-"
        minv = f"{min(dists)}" if dists else "-"
        html.append(f"<tr><td>{size}</td><td>{info['time']:.2f}</td><td>{avg}</td><td>{maxv}</td><td>{minv}</td></tr>")
    html.append("</table></div>")

    # 详细对比
    for size, info in results.items():
        html.append(f"<div class='section'><h2>pHash Size: {size} 详细对比</h2>")
        html.append("<table><tr><th>图片1</th><th>图片2</th><th>汉明距离</th></tr>")
        for img1, img2, dist in info["pairs"]:
            img1_path = Path(img1).resolve()
            img2_path = Path(img2).resolve()
            html.append(
                f"<tr>"
                f"<td><img class='thumb' src='file:///{img1_path}'><div class='filename'>{img1_path.name}</div></td>"
                f"<td><img class='thumb' src='file:///{img2_path}'><div class='filename'>{img2_path.name}</div></td>"
                f"<td>{dist}</td>"
                f"</tr>"
            )
        html.append("</table></div>")
    html.append("</body></html>")
    Path(output_path).write_text('\n'.join(html), encoding="utf-8")
    print(f"\nHTML报告已保存至: {Path(output_path).resolve()}")

if __name__ == "__main__":
    folder = r"E:\2EHV\test"  # 替换为你的图片文件夹路径
    results, image_files = benchmark_phash_sizes(folder, hash_sizes=(8, 12, 16))
    generate_html_report(results, image_files, output_path="phash_benchmark_report.html")