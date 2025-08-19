import time
from pathlib import Path
from itertools import combinations
from PIL import Image
import pillow_avif
import pillow_jxl 
import imagehash
import json
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console
from rich.table import Table
from rich.prompt  import Prompt
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

def find_similar_groups(pairs, threshold):
    """
    根据阈值找出相似图片组
    Args:
        pairs: [(img1, img2, distance), ...] 图片对列表
        threshold: 汉明距离阈值，小于等于此值认为相似
    Returns:
        list: 相似图片组列表，每组是一个包含相似图片路径的集合
    """
    # 筛选出相似的图片对
    similar_pairs = [(img1, img2) for img1, img2, dist in pairs if dist <= threshold]
    
    if not similar_pairs:
        return []
    
    # 使用并查集算法将相似的图片归类到同一组
    groups = []
    processed = set()
    
    for img1, img2 in similar_pairs:
        if img1 in processed and img2 in processed:
            continue
            
        # 找到包含这两个图片的组
        group_for_img1 = None
        group_for_img2 = None
        
        for group in groups:
            if img1 in group:
                group_for_img1 = group
            if img2 in group:
                group_for_img2 = group
                
        if group_for_img1 is None and group_for_img2 is None:
            # 创建新组
            new_group = {img1, img2}
            groups.append(new_group)
        elif group_for_img1 is not None and group_for_img2 is None:
            # 将img2加入img1所在的组
            group_for_img1.add(img2)
        elif group_for_img1 is None and group_for_img2 is not None:
            # 将img1加入img2所在的组
            group_for_img2.add(img1)
        elif group_for_img1 != group_for_img2:
            # 合并两个组
            group_for_img1.update(group_for_img2)
            groups.remove(group_for_img2)
            
        processed.add(img1)
        processed.add(img2)
    
    return groups

def export_similar_groups(results, threshold, output_dir, hash_size=None):
    """
    导出相似组，生成保留和删除文件列表
    Args:
        results: benchmark_phash_sizes的结果
        threshold: 汉明距离阈值
        output_dir: 输出目录
        hash_size: 指定使用哪个哈希尺寸的结果，如果为None则使用第一个
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    if hash_size is None:
        # 使用第一个哈希尺寸
        hash_size = list(results.keys())[0]
    
    if hash_size not in results:
        console.print(f"[red]错误：找不到哈希尺寸 {hash_size} 的结果[/red]")
        return
    
    pairs = results[hash_size]["pairs"]
    
    console.print(f"[bold]使用哈希尺寸: [cyan]{hash_size}[/cyan]，阈值: [yellow]{threshold}[/yellow][/bold]")
    
    # 找出相似图片组
    similar_groups = find_similar_groups(pairs, threshold)
    
    if not similar_groups:
        console.print("[bold red]在指定阈值下未找到相似图片组[/bold red]")
        return
    
    console.print(f"[bold green]找到 {len(similar_groups)} 个相似图片组[/bold green]")
    
    # 生成保留和删除列表
    keep_files = []
    delete_files = []
    group_info = []
    
    for i, group in enumerate(similar_groups, 1):
        # 按文件名排序，保留第一个
        sorted_files = sorted(list(group), key=lambda x: Path(x).name.lower())
        keep_file = sorted_files[0]
        delete_files_in_group = sorted_files[1:]
        
        keep_files.append(keep_file)
        delete_files.extend(delete_files_in_group)
        
        group_info.append({
            "group_id": i,
            "keep_file": keep_file,
            "delete_files": delete_files_in_group,
            "total_files": len(sorted_files)
        })
        
        console.print(f"[bold]组 {i}[/bold]: 保留 [green]{Path(keep_file).name}[/green], 删除 {len(delete_files_in_group)} 个文件")
    
    # 导出JSON格式的详细信息
    export_data = {
        "metadata": {
            "threshold": threshold,
            "hash_size": hash_size,
            "total_groups": len(similar_groups),
            "total_keep_files": len(keep_files),
            "total_delete_files": len(delete_files),
            "export_time": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        "groups": group_info
    }
    
    json_path = output_dir / f"similar_groups_threshold_{threshold}_hashsize_{hash_size}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    # 导出保留文件列表
    keep_list_path = output_dir / f"keep_files_threshold_{threshold}_hashsize_{hash_size}.txt"
    with open(keep_list_path, 'w', encoding='utf-8') as f:
        for file_path in keep_files:
            f.write(f"{file_path}\n")
    
    # 导出删除文件列表
    delete_list_path = output_dir / f"delete_files_threshold_{threshold}_hashsize_{hash_size}.txt"
    with open(delete_list_path, 'w', encoding='utf-8') as f:
        for file_path in delete_files:
            f.write(f"{file_path}\n")
    
    # 导出批处理删除脚本
    batch_script_path = output_dir / f"delete_similar_files_threshold_{threshold}_hashsize_{hash_size}.bat"
    with open(batch_script_path, 'w', encoding='utf-8') as f:
        f.write("@echo off\n")
        f.write(f"REM 删除相似图片脚本 - 阈值: {threshold}, 哈希尺寸: {hash_size}\n")
        f.write(f"REM 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("echo 准备删除以下相似图片文件:\n")
        f.write("pause\n\n")
        for file_path in delete_files:
            # 转换为Windows路径格式并添加引号处理空格
            win_path = str(Path(file_path)).replace('/', '\\')
            f.write(f'del "{win_path}"\n')
        f.write("\necho 删除完成!\npause\n")
    
    # 生成摘要表格
    summary_table = Table(title=f"相似组导出摘要 (阈值: {threshold}, 哈希尺寸: {hash_size})")
    summary_table.add_column("项目", style="cyan")
    summary_table.add_column("数量", style="green", justify="right")
    summary_table.add_column("文件路径", style="yellow")
    
    summary_table.add_row("相似组数量", str(len(similar_groups)), "")
    summary_table.add_row("保留文件", str(len(keep_files)), str(keep_list_path))
    summary_table.add_row("删除文件", str(len(delete_files)), str(delete_list_path))
    summary_table.add_row("详细信息", "", str(json_path))
    summary_table.add_row("删除脚本", "", str(batch_script_path))
    
    console.print(summary_table)
    
    console.print(f"\n[bold green]导出完成！文件保存在: {output_dir.resolve()}[/bold green]")
    
    return {
        "keep_files": keep_files,
        "delete_files": delete_files,
        "groups": similar_groups,
        "export_files": {
            "json": json_path,
            "keep_list": keep_list_path,
            "delete_list": delete_list_path,
            "batch_script": batch_script_path
        }
    }

def quick_export_from_existing_results(results_file_path, threshold, hash_size=None, output_dir=None):
    """
    从已有的结果文件快速导出相似组
    Args:
        results_file_path: 包含计算结果的pickle或json文件路径
        threshold: 汉明距离阈值
        hash_size: 指定使用哪个哈希尺寸的结果
        output_dir: 输出目录，如果为None则使用结果文件所在目录
    """
    import pickle
    
    results_path = Path(results_file_path)
    if not results_path.exists():
        console.print(f"[red]错误：结果文件不存在: {results_file_path}[/red]")
        return
    
    if output_dir is None:
        output_dir = results_path.parent
    
    try:
        # 尝试加载pickle文件
        with open(results_path, 'rb') as f:
            data = pickle.load(f)
            
        if isinstance(data, tuple) and len(data) == 2:
            results, image_files = data
        else:
            results = data
            
        console.print(f"[bold green]成功加载结果文件: {results_path}[/bold green]")
        
        # 导出相似组
        export_result = export_similar_groups(
            results, 
            threshold, 
            output_dir=output_dir,
            hash_size=hash_size
        )
        
        return export_result
        
    except Exception as e:
        console.print(f"[red]加载结果文件失败: {e}[/red]")
        return None

if __name__ == "__main__":
    
    
    # 交互式输入路径
    folder = Prompt.ask("请输入图片文件夹路径", default="E:\\2EHV\\test")
    
    # 交互式选择哈希尺寸
    hash_sizes_input = Prompt.ask("请输入要测试的哈希尺寸（用逗号分隔）", default="10,12,16")
    hash_sizes = tuple(int(x.strip()) for x in hash_sizes_input.split(','))
    
    console.print(f"[bold]将测试以下哈希尺寸: [cyan]{hash_sizes}[/cyan][/bold]")
    console.print(f"[bold]目标文件夹: [cyan]{folder}[/cyan][/bold]")
    
    results, image_files = benchmark_phash_sizes(folder, hash_sizes=hash_sizes)
    output_path = Path(folder) / "phash_benchmark_report.html"
    generate_html_report(results, image_files, output_path=output_path)
    
    # 询问是否需要导出相似组
    export_choice = Prompt.ask(
        "\n是否需要导出相似图片组用于删除重复文件？", 
        choices=["y", "n"], 
        default="y"
    )
    
    if export_choice == "y":
        # 选择使用哪个哈希尺寸的结果
        if len(hash_sizes) > 1:
            console.print("\n[bold]可用的哈希尺寸结果:[/bold]")
            for i, size in enumerate(hash_sizes, 1):
                dists = results[size]["dists"]
                avg_dist = f"{sum(dists)/len(dists):.2f}" if dists else "N/A"
                console.print(f"  {i}. 尺寸 {size} (平均汉明距离: {avg_dist})")
            
            size_choice = Prompt.ask(
                "请选择要用于导出的哈希尺寸", 
                choices=[str(i) for i in range(1, len(hash_sizes) + 1)],
                default="1"
            )
            selected_hash_size = hash_sizes[int(size_choice) - 1]
        else:
            selected_hash_size = hash_sizes[0]
        
        # 输入阈值
        dists = results[selected_hash_size]["dists"]
        if dists:
            max_dist = max(dists)
            min_dist = min(dists)
            avg_dist = sum(dists) / len(dists)
            console.print(f"\n[bold]当前数据集汉明距离统计 (哈希尺寸: {selected_hash_size}):[/bold]")
            console.print(f"  最小距离: [blue]{min_dist}[/blue]")
            console.print(f"  平均距离: [yellow]{avg_dist:.2f}[/yellow]")
            console.print(f"  最大距离: [red]{max_dist}[/red]")
            
            suggested_threshold = max(1, int(avg_dist * 0.3))  # 建议阈值为平均距离的30%
            
            threshold = int(Prompt.ask(
                f"请输入汉明距离阈值（小于等于此值认为相似，建议: {suggested_threshold}）",
                default=str(suggested_threshold)
            ))
            
            # 导出相似组
            export_result = export_similar_groups(
                results, 
                threshold, 
                output_dir=folder,
                hash_size=selected_hash_size
            )
            
            if export_result and export_result["delete_files"]:
                console.print(f"\n[bold yellow]注意：[/bold yellow]")
                console.print(f"- 已生成 [cyan]{len(export_result['delete_files'])}[/cyan] 个重复文件的删除列表")
                console.print(f"- 保留 [green]{len(export_result['keep_files'])}[/green] 个文件（每组中按名称排序的第一个）")
                console.print(f"- 请仔细检查删除列表后再执行删除操作")
                console.print(f"- 可以运行生成的 .bat 脚本进行批量删除")
        else:
            console.print("[bold red]无汉明距离数据，无法导出相似组[/bold red]")
    
    # 询问是否从已有结果文件导出相似组
    quick_export_choice = Prompt.ask(
        "\n是否需要从已有的结果文件快速导出相似组？", 
        choices=["y", "n"], 
        default="n"
    )
    
    if quick_export_choice == "y":
        results_file = Prompt.ask("请输入结果文件路径")
        if not Path(results_file).exists():
            console.print(f"[red]错误：结果文件不存在: {results_file}[/red]")
        else:
            # 选择哈希尺寸
            available_hash_sizes = list(results.keys())
            if len(available_hash_sizes) > 1:
                console.print("\n[bold]可用的哈希尺寸结果:[/bold]")
                for i, size in enumerate(available_hash_sizes, 1):
                    dists = results[size]["dists"]
                    avg_dist = f"{sum(dists)/len(dists):.2f}" if dists else "N/A"
                    console.print(f"  {i}. 尺寸 {size} (平均汉明距离: {avg_dist})")
                
                size_choice = Prompt.ask(
                    "请选择要用于导出的哈希尺寸", 
                    choices=[str(i) for i in range(1, len(available_hash_sizes) + 1)],
                    default="1"
                )
                selected_hash_size = available_hash_sizes[int(size_choice) - 1]
            else:
                selected_hash_size = available_hash_sizes[0]
            
            # 输入阈值
            dists = results[selected_hash_size]["dists"]
            if dists:
                max_dist = max(dists)
                min_dist = min(dists)
                avg_dist = sum(dists) / len(dists)
                console.print(f"\n[bold]当前数据集汉明距离统计 (哈希尺寸: {selected_hash_size}):[/bold]")
                console.print(f"  最小距离: [blue]{min_dist}[/blue]")
                console.print(f"  平均距离: [yellow]{avg_dist:.2f}[/yellow]")
                console.print(f"  最大距离: [red]{max_dist}[/red]")
                
                suggested_threshold = max(1, int(avg_dist * 0.3))  # 建议阈值为平均距离的30%
                
                threshold = int(Prompt.ask(
                    f"请输入汉明距离阈值（小于等于此值认为相似，建议: {suggested_threshold}）",
                    default=str(suggested_threshold)
                ))
                
                # 快速导出相似组
                export_result = quick_export_from_existing_results(
                    results_file, 
                    threshold, 
                    hash_size=selected_hash_size,
                    output_dir=folder
                )
                
                if export_result and export_result["delete_files"]:
                    console.print(f"\n[bold yellow]注意：[/bold yellow]")
                    console.print(f"- 已生成 [cyan]{len(export_result['delete_files'])}[/cyan] 个重复文件的删除列表")
                    console.print(f"- 保留 [green]{len(export_result['keep_files'])}[/green] 个文件（每组中按名称排序的第一个）")
                    console.print(f"- 请仔细检查删除列表后再执行删除操作")
                    console.print(f"- 可以运行生成的 .bat 脚本进行批量删除")
            else:
                console.print("[bold red]无汉明距离数据，无法导出相似组[/bold red]")