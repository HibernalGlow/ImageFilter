import time
from pathlib import Path
from itertools import combinations
from PIL import Image
import pillow_avif
import pillow_jxl 
import imagehash
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console
from rich.table import Table

# 创建控制台
console = Console()

def calc_hashes_for_images(image_files, hash_size, progress=None, task_id=None):
    """批量计算图片哈希（不依赖ImageHashCalculator，使用传入的progress实例）"""
    hashes = {}
    
    if progress is None:
        # 如果没有传入progress，创建一个新的
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[bold green]{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as local_progress:
            task = local_progress.add_task(f"[cyan]计算哈希(size={hash_size})", total=len(image_files))
            for img in image_files:
                try:
                    with Image.open(img) as im:
                        h = imagehash.phash(im, hash_size=hash_size)
                        hashes[str(img)] = h
                except Exception as e:
                    console.print(f"[red]图片处理失败: {img}，原因: {e}")
                local_progress.update(task, advance=1)
    else:
        # 使用传入的progress实例
        for img in image_files:
            try:
                with Image.open(img) as im:
                    h = imagehash.phash(im, hash_size=hash_size)
                    hashes[str(img)] = h
            except Exception as e:
                console.print(f"[red]图片处理失败: {img}，原因: {e}")
            if task_id is not None:
                progress.update(task_id, advance=1)
    return hashes

def calc_hamming_pairs(hashes, progress=None, task_id=None):
    """计算所有图片两两汉明距离"""
    dists = []
    pairs = []
    items = list(hashes.items())
    # 计算总对数以显示进度
    total_pairs = len(items) * (len(items) - 1) // 2
    
    if progress is None:
        # 如果没有传入progress，创建一个新的
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[bold green]{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as local_progress:
            task = local_progress.add_task("[cyan]计算汉明距离", total=total_pairs)
            for i, (img1, h1) in enumerate(items):
                for j in range(i + 1, len(items)):
                    img2, h2 = items[j]
                    dist = h1 - h2  # imagehash对象直接支持汉明距离
                    dists.append(dist)
                    pairs.append((img1, img2, dist))
                    local_progress.update(task, advance=1)
    else:
        # 使用传入的progress实例
        for i, (img1, h1) in enumerate(items):
            for j in range(i + 1, len(items)):
                img2, h2 = items[j]
                dist = h1 - h2  # imagehash对象直接支持汉明距离
                dists.append(dist)
                pairs.append((img1, img2, dist))
                if task_id is not None:
                    progress.update(task_id, advance=1)
    return dists, pairs

def benchmark_phash_sizes(image_dir, hash_sizes=(10, 12, 16)):
    image_dir = Path(image_dir)
    # 修改为递归查找所有子文件夹中的图片
    image_extensions = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".jxl", ".avif"]
    console.print("[bold]开始递归查找所有图片...[/bold]")
    image_files = []
    for ext in image_extensions:
        image_files.extend(list(image_dir.rglob(f"*{ext}")))
        image_files.extend(list(image_dir.rglob(f"*{ext.upper()}")))  # 兼容大写扩展名
    
    console.print(f"[bold green]共找到 {len(image_files)} 张图片[/bold green]")
    results = {}

    # 创建单一的Progress实例
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[bold green]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        
        for size in hash_sizes:
            console.print(f"\n[bold yellow]=== phash size={size} ===[/bold yellow]")
            start = time.time()
            
            # 添加计算哈希的任务
            hash_task = progress.add_task(f"[cyan]计算哈希(size={size})", total=len(image_files))
            hashes = calc_hashes_for_images(image_files, size, progress, hash_task)
            elapsed = time.time() - start
            console.print(f"[bold]计算耗时: [green]{elapsed:.2f}[/green] 秒[/bold]")
            
            console.print("[bold]开始计算汉明距离...[/bold]")
            # 计算汉明距离对数
            total_pairs = len(hashes) * (len(hashes) - 1) // 2
            hamming_task = progress.add_task("[cyan]计算汉明距离", total=total_pairs)
            dists, pairs = calc_hamming_pairs(hashes, progress, hamming_task)
            
            if dists:
                avg_dist = sum(dists) / len(dists)
                console.print(f"[bold]平均汉明距离: [green]{avg_dist:.2f}[/green]，最大: [red]{max(dists)}[/red]，最小: [blue]{min(dists)}[/blue][/bold]")
            else:
                console.print("[bold red]图片数量过少，无法对比汉明距离[/bold red]")
            results[size] = {
                "hashes": hashes,
                "time": elapsed,
                "dists": dists,
                "pairs": pairs
            }
    return results, image_files

def generate_html_report(results, image_files, output_path="phash_benchmark_report.html"):
    console.print("[bold]正在生成HTML报告...[/bold]")
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
        ".folder{font-size:10px;color:#888;word-break:break-all;}",
        ".filter-controls{margin:15px 0; padding:10px; background:#f5f5f5; border-radius:5px;}",
        ".filter-controls input{margin-right:10px; padding:5px;}",
        ".filter-controls button{padding:5px 10px; background:#4CAF50; color:white; border:none; cursor:pointer; border-radius:3px;}",
        "</style>",
        "<script>",
        "function filterTable(tableId) {",
        "  const input = document.getElementById('filter-' + tableId);",
        "  const filterValue = parseFloat(input.value);",
        "  const table = document.getElementById(tableId);",
        "  const rows = table.getElementsByTagName('tr');",
        "  for (let i = 1; i < rows.length; i++) {",
        "    const distanceCell = rows[i].cells[2];",
        "    if (distanceCell) {",
        "      const distance = parseFloat(distanceCell.textContent);",
        "      rows[i].style.display = !isNaN(filterValue) && distance <= filterValue ? '' : 'none';",
        "    }",
        "  }",
        "}",
        "</script>",
        "</head><body>",
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
        
        # 添加过滤控件
        table_id = f"table-size-{size}"
        html.append("<div class='filter-controls'>")
        html.append(f"仅显示汉明距离 ≤ <input type='number' id='filter-{table_id}' min='0' max='64' value=''>")
        html.append(f"<button onclick=\"filterTable('{table_id}')\">过滤</button>")
        html.append("</div>")
        
        html.append(f"<table id='{table_id}'><tr><th>图片1</th><th>图片2</th><th>汉明距离</th></tr>")
        
        # 对汉明距离进行排序（升序）
        sorted_pairs = sorted(info["pairs"], key=lambda x: x[2])
        
        # 使用rich进度条
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[bold green]{task.completed}/{task.total}"),
        ) as progress:
            task = progress.add_task(f"[cyan]生成size={size}报告", total=len(sorted_pairs))
            
            for img1, img2, dist in sorted_pairs:
                img1_path = Path(img1).resolve()
                img2_path = Path(img2).resolve()
                # 显示文件名和相对路径
                img1_name = img1_path.name
                img2_name = img2_path.name
                img1_folder = str(img1_path.parent)
                img2_folder = str(img2_path.parent)
                
                html.append(
                    f"<tr>"
                    f"<td><img class='thumb' src='file:///{img1_path}'>"
                    f"<div class='filename'>{img1_name}</div>"
                    f"<div class='folder'>{img1_folder}</div></td>"
                    f"<td><img class='thumb' src='file:///{img2_path}'>"
                    f"<div class='filename'>{img2_name}</div>"
                    f"<div class='folder'>{img2_folder}</div></td>"
                    f"<td>{dist}</td>"
                    f"</tr>"
                )
                progress.update(task, advance=1)
        html.append("</table></div>")
    html.append("</body></html>")
    
    # 使用rich美化文件保存过程
    console.print(f"[bold]正在保存HTML报告到 [cyan]{output_path}[/cyan]...[/bold]")
    Path(output_path).write_text('\n'.join(html), encoding="utf-8")
    console.print(f"\n[bold green]HTML报告已保存至: {Path(output_path).resolve()}[/bold green]")

    # 显示结果摘要表格
    table = Table(title="哈希尺寸对比结果摘要")
    table.add_column("哈希尺寸", style="cyan")
    table.add_column("计算耗时(秒)", style="green", justify="right")
    table.add_column("平均汉明距离", style="yellow", justify="right")
    table.add_column("最大距离", style="red", justify="right")
    table.add_column("最小距离", style="blue", justify="right")
    
    for size, info in results.items():
        dists = info["dists"]
        avg = f"{sum(dists)/len(dists):.2f}" if dists else "-"
        maxv = f"{max(dists)}" if dists else "-"
        minv = f"{min(dists)}" if dists else "-"
        table.add_row(str(size), f"{info['time']:.2f}", avg, str(maxv), str(minv))
    
    console.print(table)

if __name__ == "__main__":
    folder = r"E:\2EHV\test"  # 替换为你的图片文件夹路径
    results, image_files = benchmark_phash_sizes(folder, hash_sizes=(10, 12, 16))
    output_path = Path(folder) / "phash_benchmark_report.html"
    generate_html_report(results, image_files, output_path=output_path)