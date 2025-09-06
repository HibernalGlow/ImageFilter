import time
import numpy as np
from pathlib import Path
from PIL import Image
import pillow_avif
import pillow_jxl 
from skimage.metrics import structural_similarity as ssim
from skimage import color
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
import random

# 创建控制台
console = Console()

class SimpleSSIMCalculator:
    """简化的SSIM计算器"""
    
    def __init__(self, target_size=(128, 128), use_grayscale=False):
        self.target_size = target_size
        self.use_grayscale = use_grayscale
        console.print(f"[bold green]SSIM计算器初始化 - 尺寸: {target_size}, 灰度: {use_grayscale}[/bold green]")
    
    def preprocess_image(self, img_path):
        """预处理图片"""
        try:
            with Image.open(img_path) as img:
                # 转换为RGB
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 调整尺寸
                img = img.resize(self.target_size, Image.Resampling.LANCZOS)
                
                # 转换为numpy数组
                img_array = np.array(img, dtype=np.float64) / 255.0
                
                # 如果需要转为灰度
                if self.use_grayscale:
                    img_array = color.rgb2gray(img_array)
                
                return img_array
        except Exception as e:
            console.print(f"[red]预处理失败: {img_path}, 错误: {e}")
            return None
    def calculate_ssim(self, img1_path, img2_path):
        """计算SSIM值"""
        img1 = self.preprocess_image(img1_path)
        img2 = self.preprocess_image(img2_path)
        
        if img1 is None or img2 is None:
            return None
        
        try:
            if self.use_grayscale:
                # 灰度图像，数据范围0-1
                ssim_value = ssim(img1, img2, data_range=1.0)
            else:
                # 彩色图像，数据范围0-1，使用channel_axis参数
                ssim_value = ssim(img1, img2, data_range=1.0, channel_axis=-1)
            return float(ssim_value)
        except Exception as e:
            console.print(f"[red]SSIM计算失败: {e}")
            return None

def find_most_similar_pairs(image_files, calculator, top_n=10):
    """找出最相似的N对图片"""
    console.print(f"[bold]开始计算SSIM，寻找最相似的 {top_n} 对图片...[/bold]")
    
    all_pairs = []
    total_pairs = len(image_files) * (len(image_files) - 1) // 2
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[bold green]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("[cyan]计算SSIM", total=total_pairs)
        
        for i, img1 in enumerate(image_files):
            for j in range(i + 1, len(image_files)):
                img2 = image_files[j]
                ssim_value = calculator.calculate_ssim(img1, img2)
                if ssim_value is not None:
                    all_pairs.append((str(img1), str(img2), ssim_value))
                progress.update(task, advance=1)
    
    # 按SSIM值排序，取最相似的top_n对
    all_pairs.sort(key=lambda x: x[2], reverse=True)
    return all_pairs[:top_n], all_pairs

def generate_simple_report(top_pairs, all_pairs, output_path):
    """生成简化的HTML报告"""
    console.print("[bold]正在生成HTML报告...[/bold]")
    
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>SSIM相似度报告</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;margin:30px;background:#f8f9fa;}",
        ".container{max-width:1200px;margin:0 auto;background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}",
        "h1{color:#2c3e50;text-align:center;margin-bottom:30px;}",
        ".stats{background:#e8f4fd;padding:15px;border-radius:8px;margin:20px 0;}",
        ".pair-grid{display:grid;gap:20px;margin:20px 0;}",
        ".pair-item{border:1px solid #ddd;border-radius:8px;padding:15px;background:#fff;}",
        ".image-container{display:flex;align-items:center;gap:20px;}",
        ".image-box{text-align:center;flex:1;}",
        "img{max-width:200px;max-height:200px;border-radius:5px;box-shadow:0 2px 5px rgba(0,0,0,0.2);}",
        ".filename{font-size:12px;color:#666;margin-top:5px;word-break:break-all;}",
        ".ssim-value{font-size:24px;font-weight:bold;color:#27ae60;text-align:center;flex:0 0 120px;}",
        ".high{color:#27ae60;} .medium{color:#f39c12;} .low{color:#e74c3c;}",
        "table{width:100%;border-collapse:collapse;margin:20px 0;}",
        "th,td{border:1px solid #ddd;padding:8px;text-align:center;}",
        "th{background:#f2f2f2;}",
        "</style>",
        "</head><body>",
        "<div class='container'>",
        "<h1>🎯 SSIM图片相似度分析报告</h1>",
    ]
    
    # 统计信息
    if all_pairs:
        avg_ssim = sum(p[2] for p in all_pairs) / len(all_pairs)
        max_ssim = max(p[2] for p in all_pairs)
        min_ssim = min(p[2] for p in all_pairs)
        
        html.append("<div class='stats'>")
        html.append("<h3>📊 统计信息</h3>")
        html.append(f"<p><strong>总对比数:</strong> {len(all_pairs)}</p>")
        html.append(f"<p><strong>平均SSIM:</strong> {avg_ssim:.4f}</p>")
        html.append(f"<p><strong>最大SSIM:</strong> {max_ssim:.4f}</p>")
        html.append(f"<p><strong>最小SSIM:</strong> {min_ssim:.4f}</p>")
        html.append("</div>")
    
    # 最相似的图片对
    html.append("<h2>🔥 最相似的图片对</h2>")
    html.append("<div class='pair-grid'>")
    
    for i, (img1, img2, ssim_value) in enumerate(top_pairs, 1):
        img1_path = Path(img1)
        img2_path = Path(img2)
        
        # 根据SSIM值设置颜色
        ssim_class = "high" if ssim_value >= 0.8 else "medium" if ssim_value >= 0.6 else "low"
        
        html.append(f"<div class='pair-item'>")
        html.append(f"<h4>第 {i} 对 (SSIM: {ssim_value:.4f})</h4>")
        html.append(f"<div class='image-container'>")
        html.append(f"<div class='image-box'>")
        html.append(f"<img src='file:///{img1_path.resolve()}' alt='图片1'>")
        html.append(f"<div class='filename'>{img1_path.name}</div>")
        html.append(f"</div>")
        html.append(f"<div class='ssim-value {ssim_class}'>{ssim_value:.4f}</div>")
        html.append(f"<div class='image-box'>")
        html.append(f"<img src='file:///{img2_path.resolve()}' alt='图片2'>")
        html.append(f"<div class='filename'>{img2_path.name}</div>")
        html.append(f"</div>")
        html.append(f"</div>")
        html.append(f"</div>")
    
    html.append("</div>")
    html.append("</div></body></html>")
    
    # 保存文件
    Path(output_path).write_text('\n'.join(html), encoding="utf-8")
    console.print(f"[bold green]报告已保存: {Path(output_path).resolve()}[/bold green]")

def main():
    console.print("[bold blue]🎯 简化版SSIM相似度分析工具[/bold blue]")
    console.print("[yellow]此版本专为快速测试设计，支持图片数量限制[/yellow]\n")
    
    # 输入参数
    folder = Prompt.ask("📁 请输入图片文件夹路径", default="E:\\1Hub\\EH\\2EHV\\test")
    
    # 图片数量限制
    max_images = IntPrompt.ask("🔢 最大处理图片数量（避免计算时间过长）", default=20)
    
    # 寻找最相似的对数
    top_n = IntPrompt.ask("🏆 显示最相似的前N对", default=10)
    
    # 图片尺寸
    size_choice = Prompt.ask("📐 图片处理尺寸 (1:128x128快速 2:256x256精确)", default="1", choices=["1", "2"])
    target_size = (128, 128) if size_choice == "1" else (256, 256)
    
    # 颜色模式
    grayscale = Prompt.ask("🎨 是否转为灰度模式？(可能更快)", default="n").lower() == 'y'
    
    # 查找图片
    folder_path = Path(folder)
    image_extensions = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".jxl", ".avif"]
    
    console.print("\n[bold]🔍 搜索图片文件...[/bold]")
    image_files = []
    for ext in image_extensions:
        image_files.extend(list(folder_path.rglob(f"*{ext}")))
        image_files.extend(list(folder_path.rglob(f"*{ext.upper()}")))
    
    console.print(f"[green]📷 找到 {len(image_files)} 张图片[/green]")
    
    # 限制图片数量
    if len(image_files) > max_images:
        console.print(f"[yellow]⚡ 随机选择 {max_images} 张图片进行分析[/yellow]")
        image_files = random.sample(image_files, max_images)
    
    if len(image_files) < 2:
        console.print("[red]❌ 图片数量不足，至少需要2张图片[/red]")
        return
    
    # 计算预估时间
    total_pairs = len(image_files) * (len(image_files) - 1) // 2
    estimated_seconds = total_pairs * (0.02 if target_size == (128, 128) else 0.05)
    console.print(f"[cyan]⏱️  需要计算 {total_pairs} 对，预估耗时: {estimated_seconds:.1f} 秒[/cyan]\n")
    
    # 开始计算
    start_time = time.time()
    calculator = SimpleSSIMCalculator(target_size=target_size, use_grayscale=grayscale)
    top_pairs, all_pairs = find_most_similar_pairs(image_files, calculator, top_n)
    
    elapsed_time = time.time() - start_time
    console.print(f"\n[bold green]✅ 计算完成！耗时: {elapsed_time:.2f} 秒[/bold green]")
    
    # 显示结果表格
    if top_pairs:
        table = Table(title="🏆 最相似的图片对")
        table.add_column("排名", style="cyan", justify="center")
        table.add_column("图片1", style="blue")
        table.add_column("图片2", style="blue") 
        table.add_column("SSIM值", style="green", justify="center")
        table.add_column("相似度", style="yellow", justify="center")
        
        for i, (img1, img2, ssim_value) in enumerate(top_pairs, 1):
            img1_name = Path(img1).name
            img2_name = Path(img2).name
            similarity_level = "很高" if ssim_value >= 0.9 else "高" if ssim_value >= 0.8 else "中等" if ssim_value >= 0.6 else "低"
            table.add_row(str(i), img1_name, img2_name, f"{ssim_value:.4f}", similarity_level)
        
        console.print(table)
    
    # 生成报告
    output_path = folder_path / "ssim_simple_report.html"
    generate_simple_report(top_pairs, all_pairs, output_path)
    
    console.print(f"\n[bold blue]🎉 分析完成！[/bold blue]")
    console.print(f"[green]📄 HTML报告: {output_path}[/green]")

if __name__ == "__main__":
    main()
