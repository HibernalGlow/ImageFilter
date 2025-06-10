import time
import numpy as np
import pickle
import random
from pathlib import Path
from itertools import combinations
from PIL import Image
import pillow_avif
import pillow_jxl 
from skimage.metrics import structural_similarity as ssim
from skimage import io, color, transform
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm

# 创建控制台
console = Console()

class SSIMImageProcessor:
    """SSIM图像处理器"""
    
    def __init__(self, target_size=(256, 256), multichannel=True):
        """
        初始化SSIM处理器
        
        Args:
            target_size: 目标图像尺寸，SSIM要求两张图片尺寸相同
            multichannel: 是否处理多通道图片（彩色）
        """
        self.target_size = target_size
        self.multichannel = multichannel
        console.print(f"[bold green]SSIM处理器初始化完成 - 目标尺寸: {target_size}, 多通道: {multichannel}[/bold green]")
    
    def load_and_preprocess(self, img_path):
        """加载并预处理图片用于SSIM计算"""
        try:
            # 使用PIL加载图片
            with Image.open(img_path) as pil_img:
                # 转换为RGB（如果是RGBA或其他格式）
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')
                
                # 调整尺寸
                pil_img = pil_img.resize(self.target_size, Image.Resampling.LANCZOS)
                
                # 转换为numpy数组
                img_array = np.array(pil_img)
                
                # 如果不需要多通道，转换为灰度
                if not self.multichannel:
                    if len(img_array.shape) == 3:
                        img_array = color.rgb2gray(img_array)
                
                return img_array
                
        except Exception as e:
            console.print(f"[red]图片预处理失败: {img_path}，原因: {e}")
            return None
    
    def calculate_ssim(self, img1_path, img2_path):
        """计算两张图片的SSIM值"""
        img1 = self.load_and_preprocess(img1_path)
        img2 = self.load_and_preprocess(img2_path)
        
        if img1 is None or img2 is None:
            return None
        
        try:
            # 计算SSIM
            if self.multichannel and len(img1.shape) == 3:
                ssim_value = ssim(img1, img2, multichannel=True, channel_axis=-1)
            else:
                ssim_value = ssim(img1, img2)
            
            return float(ssim_value)
        except Exception as e:
            console.print(f"[red]SSIM计算失败: {img1_path} vs {img2_path}，原因: {e}")
            return None

def calc_ssim_pairs(image_files, processor, progress=None, task_id=None):
    """计算所有图片两两SSIM相似度"""
    similarities = []
    pairs = []
    # 计算总对数以显示进度
    total_pairs = len(image_files) * (len(image_files) - 1) // 2
    
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
            task = local_progress.add_task("[cyan]计算SSIM相似度", total=total_pairs)
            for i, img1 in enumerate(image_files):
                for j in range(i + 1, len(image_files)):
                    img2 = image_files[j]
                    ssim_value = processor.calculate_ssim(img1, img2)
                    if ssim_value is not None:
                        similarities.append(ssim_value)
                        pairs.append((str(img1), str(img2), ssim_value))
                    local_progress.update(task, advance=1)
    else:
        # 使用传入的progress实例
        for i, img1 in enumerate(image_files):
            for j in range(i + 1, len(image_files)):
                img2 = image_files[j]
                ssim_value = processor.calculate_ssim(img1, img2)
                if ssim_value is not None:
                    similarities.append(ssim_value)
                    pairs.append((str(img1), str(img2), ssim_value))
                if task_id is not None:
                    progress.update(task_id, advance=1)
    
    return similarities, pairs

def save_results(results, save_path):
    """保存SSIM结果到文件"""
    console.print(f"[bold]正在保存SSIM结果到 [cyan]{save_path}[/cyan]...[/bold]")
    with open(save_path, 'wb') as f:
        pickle.dump(results, f)
    console.print(f"[bold green]SSIM结果已保存至: {Path(save_path).resolve()}[/bold green]")

def load_results(load_path):
    """从文件加载SSIM结果"""
    console.print(f"[bold]正在从 [cyan]{load_path}[/cyan] 加载SSIM结果...[/bold]")
    with open(load_path, 'rb') as f:
        results = pickle.load(f)
    console.print(f"[bold green]成功加载SSIM结果[/bold green]")
    return results

def benchmark_ssim_similarity(image_dir, target_size=(256, 256), multichannel=True, 
                            save_results_file=None, load_results_file=None, max_images=None):
    """SSIM相似度基准测试"""
    image_dir = Path(image_dir)
    # 修改为递归查找所有子文件夹中的图片
    image_extensions = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".jxl", ".avif"]
    console.print("[bold]开始递归查找所有图片...[/bold]")
    image_files = []
    for ext in image_extensions:
        image_files.extend(list(image_dir.rglob(f"*{ext}")))
        image_files.extend(list(image_dir.rglob(f"*{ext.upper()}")))  # 兼容大写扩展名
    
    console.print(f"[bold green]共找到 {len(image_files)} 张图片[/bold green]")
    
    # 如果图片太多，进行采样
    if max_images and len(image_files) > max_images:
        console.print(f"[bold yellow]图片数量超过限制 ({max_images})，随机采样中...[/bold yellow]")
        image_files = random.sample(image_files, max_images)
        console.print(f"[bold green]采样后使用 {len(image_files)} 张图片[/bold green]")
    
    # 计算对比对数并给出预估时间
    total_pairs = len(image_files) * (len(image_files) - 1) // 2
    estimated_time = total_pairs * 0.1  # 假设每对需要0.1秒
    console.print(f"[bold cyan]需要计算 {total_pairs} 对比较，预估耗时: {estimated_time/60:.1f} 分钟[/bold cyan]")
    
    # 创建单一的Progress实例
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[bold green]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        
        if load_results_file and Path(load_results_file).exists():
            # 从文件加载结果
            results = load_results(load_results_file)
            elapsed = 0  # 加载时间忽略不计
        else:
            # 计算SSIM相似度
            console.print(f"\n[bold yellow]=== SSIM相似度计算 ===[/bold yellow]")
            console.print(f"[bold]参数设置:[/bold]")
            console.print(f"  - 目标尺寸: [cyan]{target_size}[/cyan]")
            console.print(f"  - 多通道模式: [cyan]{multichannel}[/cyan]")
            
            start = time.time()
            
            # 创建SSIM处理器
            processor = SSIMImageProcessor(target_size=target_size, multichannel=multichannel)
            
            # 计算SSIM对数
            total_pairs = len(image_files) * (len(image_files) - 1) // 2
            ssim_task = progress.add_task("[cyan]计算SSIM相似度", total=total_pairs)
            similarities, pairs = calc_ssim_pairs(image_files, processor, progress, ssim_task)
            
            elapsed = time.time() - start
            console.print(f"[bold]SSIM计算耗时: [green]{elapsed:.2f}[/green] 秒[/bold]")
            
            results = {
                "similarities": similarities,
                "pairs": pairs,
                "time": elapsed,
                "settings": {
                    "target_size": target_size,
                    "multichannel": multichannel
                }
            }
            
            # 保存结果
            if save_results_file:
                save_results(results, save_results_file)
        
        if results["similarities"]:
            similarities = results["similarities"]
            avg_sim = sum(similarities) / len(similarities)
            console.print(f"[bold]平均SSIM相似度: [green]{avg_sim:.4f}[/green]，最大: [red]{max(similarities):.4f}[/red]，最小: [blue]{min(similarities):.4f}[/blue][/bold]")
        else:
            console.print("[bold red]图片数量过少，无法对比相似度[/bold red]")
    
    return results, image_files

def generate_html_report(results, image_files, output_path="ssim_similarity_report.html"):
    """生成HTML SSIM相似度报告"""
    console.print("[bold]正在生成HTML报告...[/bold]")
    
    settings = results.get("settings", {})
    target_size = settings.get("target_size", "N/A")
    multichannel = settings.get("multichannel", "N/A")
    
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>SSIM Similarity Report</title>",
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
        ".high-similarity{background-color:#e6ffe6;}",
        ".medium-similarity{background-color:#fff2e6;}",
        ".low-similarity{background-color:#ffe6e6;}",
        ".info-box{background:#e7f3ff;padding:15px;border-radius:5px;margin:10px 0;}",
        "</style>",
        "<script>",
        "function filterTable() {",
        "  const minInput = document.getElementById('filter-min');",
        "  const maxInput = document.getElementById('filter-max');",
        "  const minValue = parseFloat(minInput.value) || -1;",
        "  const maxValue = parseFloat(maxInput.value) || 1;",
        "  const table = document.getElementById('ssim-table');",
        "  const rows = table.getElementsByTagName('tr');",
        "  for (let i = 1; i < rows.length; i++) {",
        "    const ssimCell = rows[i].cells[2];",
        "    if (ssimCell) {",
        "      const ssimValue = parseFloat(ssimCell.textContent);",
        "      rows[i].style.display = (ssimValue >= minValue && ssimValue <= maxValue) ? '' : 'none';",
        "    }",
        "  }",
        "}",
        "</script>",
        "</head><body>",
        "<h1>SSIM图片相似度分析报告</h1>",
        f"<p>图片总数：{len(image_files)}</p>",
        f"<div class='info-box'>",
        f"<h3>SSIM参数设置</h3>",
        f"<p><strong>目标尺寸:</strong> {target_size}</p>",
        f"<p><strong>多通道模式:</strong> {multichannel}</p>",
        f"<p><strong>说明:</strong> SSIM值范围为-1到1，值越接近1表示结构相似度越高</p>",
        f"</div>"
    ]
    
    # 总览表
    similarities = results["similarities"]
    if similarities:
        avg = f"{sum(similarities)/len(similarities):.4f}"
        maxv = f"{max(similarities):.4f}"
        minv = f"{min(similarities):.4f}"
        html.append("<div class='section'><h2>SSIM相似度统计</h2><table>")
        html.append("<tr><th>指标</th><th>值</th></tr>")
        html.append(f"<tr><td>计算耗时(秒)</td><td>{results['time']:.2f}</td></tr>")
        html.append(f"<tr><td>平均SSIM值</td><td>{avg}</td></tr>")
        html.append(f"<tr><td>最大SSIM值</td><td>{maxv}</td></tr>")
        html.append(f"<tr><td>最小SSIM值</td><td>{minv}</td></tr>")
        html.append(f"<tr><td>对比对数</td><td>{len(similarities)}</td></tr>")
        html.append("</table></div>")

    # 详细对比
    html.append("<div class='section'><h2>详细SSIM对比</h2>")
    
    # 添加过滤控件
    html.append("<div class='filter-controls'>")
    html.append("SSIM值范围: ")
    html.append("<input type='number' id='filter-min' min='-1' max='1' step='0.01' placeholder='最小值' value='0.8'>")
    html.append(" - ")
    html.append("<input type='number' id='filter-max' min='-1' max='1' step='0.01' placeholder='最大值' value='1.0'>")
    html.append("<button onclick='filterTable()'>过滤</button>")
    html.append("<span style='margin-left:20px;'>说明: SSIM值越接近1表示结构越相似</span>")
    html.append("</div>")
    
    html.append("<table id='ssim-table'><tr><th>图片1</th><th>图片2</th><th>SSIM值</th></tr>")
    
    # 对SSIM值进行排序（降序，最相似的在前）
    sorted_pairs = sorted(results["pairs"], key=lambda x: x[2], reverse=True)
    
    # 使用rich进度条
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[bold green]{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task("[cyan]生成SSIM报告", total=len(sorted_pairs))
        
        for img1, img2, ssim_value in sorted_pairs:
            img1_path = Path(img1).resolve()
            img2_path = Path(img2).resolve()
            # 显示文件名和相对路径
            img1_name = img1_path.name
            img2_name = img2_path.name
            img1_folder = str(img1_path.parent)
            img2_folder = str(img2_path.parent)
            
            # 根据SSIM值设置行样式
            row_class = ""
            if ssim_value >= 0.9:
                row_class = "high-similarity"
            elif ssim_value >= 0.7:
                row_class = "medium-similarity"
            else:
                row_class = "low-similarity"
            
            html.append(
                f"<tr class='{row_class}'>"
                f"<td><img class='thumb' src='file:///{img1_path}'>"
                f"<div class='filename'>{img1_name}</div>"
                f"<div class='folder'>{img1_folder}</div></td>"
                f"<td><img class='thumb' src='file:///{img2_path}'>"
                f"<div class='filename'>{img2_name}</div>"
                f"<div class='folder'>{img2_folder}</div></td>"
                f"<td>{ssim_value:.4f}</td>"
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
    if similarities:
        table = Table(title="SSIM相似度分析结果")
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green", justify="right")
        
        table.add_row("计算耗时(秒)", f"{results['time']:.2f}")
        table.add_row("平均SSIM值", f"{sum(similarities)/len(similarities):.4f}")
        table.add_row("最大SSIM值", f"{max(similarities):.4f}")
        table.add_row("最小SSIM值", f"{min(similarities):.4f}")
        table.add_row("对比对数", str(len(similarities)))
        table.add_row("高相似度对数(≥0.9)", str(len([s for s in similarities if s >= 0.9])))
        table.add_row("中等相似度对数(0.7-0.9)", str(len([s for s in similarities if 0.7 <= s < 0.9])))
        table.add_row("低相似度对数(<0.7)", str(len([s for s in similarities if s < 0.7])))
        
        console.print(table)

if __name__ == "__main__":
    # 交互式输入路径
    folder = Prompt.ask("请输入图片文件夹路径", default="E:\\2EHV\\test")
    
    # 交互式选择参数
    size_input = Prompt.ask("请输入目标图片尺寸（格式：宽,高）", default="256,256")
    try:
        width, height = map(int, size_input.split(','))
        target_size = (width, height)
    except:
        target_size = (256, 256)
        console.print("[yellow]尺寸格式错误，使用默认值 (256, 256)[/yellow]")
    
    multichannel_input = Prompt.ask("是否使用彩色模式？(y/n，n表示转为灰度)", default="y")
    multichannel = multichannel_input.lower() == 'y'
    
    # 图片数量限制
    max_images = None
    limit_choice = Prompt.ask("是否限制图片数量以加快计算？(y/n)", default="y")
    if limit_choice.lower() == 'y':
        max_images = IntPrompt.ask("请输入最大图片数量", default=50)
    
    # 询问是否保存/加载结果
    save_choice = Prompt.ask("是否保存SSIM结果到文件？(y/n)", default="y")
    results_file = None
    if save_choice.lower() == 'y':
        results_file = Path(folder) / "ssim_results.pkl"
    
    load_choice = Prompt.ask(f"是否从现有文件加载SSIM结果？(如果存在 {results_file}) (y/n)", default="n")
    load_file = None
    if load_choice.lower() == 'y' and results_file and results_file.exists():
        load_file = results_file
      console.print(f"[bold]参数设置:[/bold]")
    console.print(f"  - 目标文件夹: [cyan]{folder}[/cyan]")
    console.print(f"  - 图片尺寸: [cyan]{target_size}[/cyan]")
    console.print(f"  - 彩色模式: [cyan]{multichannel}[/cyan]")
    console.print(f"  - 最大图片数: [cyan]{max_images or '无限制'}[/cyan]")
    if results_file:
        console.print(f"  - 结果文件: [cyan]{results_file}[/cyan]")
    
    results, image_files = benchmark_ssim_similarity(
        folder,
        target_size=target_size,
        multichannel=multichannel,
        save_results_file=results_file,
        load_results_file=load_file,
        max_images=max_images
    )
    
    output_path = Path(folder) / "ssim_similarity_report.html"
    generate_html_report(results, image_files, output_path=output_path)
