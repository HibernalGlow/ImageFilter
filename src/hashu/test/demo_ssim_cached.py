import time
import numpy as np
import pickle
from pathlib import Path
from PIL import Image
import pillow_avif
import pillow_jxl 
from skimage.metrics import structural_similarity as ssim
from skimage import color
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
import hashlib
import json

# 创建控制台
console = Console()

class CachedSSIMCalculator:
    """支持缓存的SSIM计算器"""
    
    def __init__(self, target_size=(128, 128), use_grayscale=False, cache_dir=None):
        self.target_size = target_size
        self.use_grayscale = use_grayscale
        self.cache_dir = Path(cache_dir) if cache_dir else None
        
        # 创建缓存目录
        if self.cache_dir:
            self.cache_dir.mkdir(exist_ok=True)
            self.preprocessed_cache_file = self.cache_dir / "preprocessed_images.pkl"
            self.ssim_cache_file = self.cache_dir / "ssim_results.pkl"
            self.image_info_file = self.cache_dir / "image_info.json"
        
        # 加载已有缓存
        self.preprocessed_images = {}  # {图片路径: numpy数组}
        self.ssim_results = {}  # {(img1, img2): ssim_value}
        self.image_info = {}  # {图片路径: {size, mtime, hash}}
        
        self.load_cache()
        console.print(f"[bold green]缓存SSIM计算器初始化 - 尺寸: {target_size}, 灰度: {use_grayscale}[/bold green]")
        console.print(f"[cyan]已缓存预处理图片: {len(self.preprocessed_images)} 张[/cyan]")
        console.print(f"[cyan]已缓存SSIM结果: {len(self.ssim_results)} 对[/cyan]")
    
    def get_file_hash(self, file_path):
        """计算文件hash值"""
        file_path = Path(file_path)
        stat = file_path.stat()
        # 使用文件路径、大小、修改时间作为简单hash
        hash_str = f"{file_path.name}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(hash_str.encode()).hexdigest()[:16]
    
    def is_image_changed(self, img_path):
        """检查图片是否发生变化"""
        img_path = str(img_path)
        if img_path not in self.image_info:
            return True
        
        file_path = Path(img_path)
        if not file_path.exists():
            return True
            
        current_hash = self.get_file_hash(file_path)
        return self.image_info[img_path].get('hash') != current_hash
    
    def preprocess_image(self, img_path):
        """预处理图片（支持缓存）"""
        img_path = str(img_path)
        
        # 检查缓存
        if img_path in self.preprocessed_images and not self.is_image_changed(img_path):
            return self.preprocessed_images[img_path]
        
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
                
                # 更新缓存
                self.preprocessed_images[img_path] = img_array
                self.image_info[img_path] = {
                    'hash': self.get_file_hash(img_path),
                    'size': self.target_size,
                    'grayscale': self.use_grayscale
                }
                
                return img_array
        except Exception as e:
            console.print(f"[red]预处理失败: {img_path}, 错误: {e}")
            return None
    
    def calculate_ssim(self, img1_path, img2_path):
        """计算SSIM值（支持缓存）"""
        img1_path = str(img1_path)
        img2_path = str(img2_path)
        
        # 标准化顺序（避免重复计算）
        pair_key = tuple(sorted([img1_path, img2_path]))
        
        # 检查SSIM缓存
        if pair_key in self.ssim_results:
            return self.ssim_results[pair_key]
        
        # 预处理图片
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
            
            # 缓存结果
            self.ssim_results[pair_key] = float(ssim_value)
            return float(ssim_value)
        except Exception as e:
            console.print(f"[red]SSIM计算失败: {e}")
            return None
    
    def save_cache(self):
        """保存缓存到文件"""
        if not self.cache_dir:
            return
        
        try:
            # 保存预处理图片
            if self.preprocessed_images:
                with open(self.preprocessed_cache_file, 'wb') as f:
                    pickle.dump(self.preprocessed_images, f)
            
            # 保存SSIM结果
            if self.ssim_results:
                with open(self.ssim_cache_file, 'wb') as f:
                    pickle.dump(self.ssim_results, f)
            
            # 保存图片信息
            if self.image_info:
                with open(self.image_info_file, 'w', encoding='utf-8') as f:
                    json.dump(self.image_info, f, indent=2, ensure_ascii=False)
            
            console.print(f"[bold green]缓存已保存到: {self.cache_dir}[/bold green]")
        except Exception as e:
            console.print(f"[red]保存缓存失败: {e}")
    
    def load_cache(self):
        """从文件加载缓存"""
        if not self.cache_dir:
            return
        
        try:
            # 加载预处理图片
            if self.preprocessed_cache_file.exists():
                with open(self.preprocessed_cache_file, 'rb') as f:
                    self.preprocessed_images = pickle.load(f)
            
            # 加载SSIM结果
            if self.ssim_cache_file.exists():
                with open(self.ssim_cache_file, 'rb') as f:
                    self.ssim_results = pickle.load(f)
            
            # 加载图片信息
            if self.image_info_file.exists():
                with open(self.image_info_file, 'r', encoding='utf-8') as f:
                    self.image_info = json.load(f)
        except Exception as e:
            console.print(f"[yellow]加载缓存失败: {e}[/yellow]")
    
    def clean_invalid_cache(self, valid_image_paths):
        """清理无效的缓存（图片已被删除或移动）"""
        valid_paths = set(str(p) for p in valid_image_paths)
        
        # 清理预处理缓存
        invalid_preprocessed = [k for k in self.preprocessed_images.keys() if k not in valid_paths]
        for k in invalid_preprocessed:
            del self.preprocessed_images[k]
        
        # 清理图片信息
        invalid_info = [k for k in self.image_info.keys() if k not in valid_paths]
        for k in invalid_info:
            del self.image_info[k]
        
        # 清理SSIM结果
        invalid_ssim = [k for k in self.ssim_results.keys() if k[0] not in valid_paths or k[1] not in valid_paths]
        for k in invalid_ssim:
            del self.ssim_results[k]
        
        if invalid_preprocessed or invalid_info or invalid_ssim:
            console.print(f"[yellow]清理了 {len(invalid_preprocessed)} 个预处理缓存, {len(invalid_ssim)} 个SSIM缓存[/yellow]")

def find_most_similar_pairs_cached(image_files, calculator, top_n=10):
    """找出最相似的N对图片（使用缓存）"""
    console.print(f"[bold]开始计算SSIM（使用缓存），寻找最相似的 {top_n} 对图片...[/bold]")
    
    # 清理无效缓存
    calculator.clean_invalid_cache(image_files)
    
    all_pairs = []
    total_pairs = len(image_files) * (len(image_files) - 1) // 2
    
    # 统计缓存命中
    cache_hits = 0
    new_calculations = 0
    
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
                
                # 检查是否已有缓存
                pair_key = tuple(sorted([str(img1), str(img2)]))
                if pair_key in calculator.ssim_results:
                    ssim_value = calculator.ssim_results[pair_key]
                    cache_hits += 1
                else:
                    ssim_value = calculator.calculate_ssim(img1, img2)
                    new_calculations += 1
                
                if ssim_value is not None:
                    all_pairs.append((str(img1), str(img2), ssim_value))
                progress.update(task, advance=1)
    
    console.print(f"[green]缓存命中: {cache_hits}, 新计算: {new_calculations}[/green]")
    
    # 按SSIM值排序，取最相似的top_n对
    all_pairs.sort(key=lambda x: x[2], reverse=True)
    return all_pairs[:top_n], all_pairs

def generate_cached_report(top_pairs, all_pairs, output_path, cache_stats=None):
    """生成带缓存信息的HTML报告"""
    console.print("[bold]正在生成HTML报告...[/bold]")
    
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>缓存SSIM相似度报告</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;margin:30px;background:#f8f9fa;}",
        ".container{max-width:1200px;margin:0 auto;background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}",
        "h1{color:#2c3e50;text-align:center;margin-bottom:30px;}",
        ".stats{background:#e8f4fd;padding:15px;border-radius:8px;margin:20px 0;}",
        ".cache-stats{background:#fff3cd;padding:15px;border-radius:8px;margin:20px 0;border-left:4px solid #ffc107;}",
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
        "<h1>🚀 缓存SSIM图片相似度分析报告</h1>",
    ]
    
    # 缓存统计信息
    if cache_stats:
        html.append("<div class='cache-stats'>")
        html.append("<h3>⚡ 缓存性能统计</h3>")
        html.append(f"<p><strong>缓存命中:</strong> {cache_stats.get('cache_hits', 0)} 次</p>")
        html.append(f"<p><strong>新计算:</strong> {cache_stats.get('new_calculations', 0)} 次</p>")
        html.append(f"<p><strong>缓存命中率:</strong> {cache_stats.get('hit_rate', 0):.1f}%</p>")
        html.append(f"<p><strong>预处理缓存:</strong> {cache_stats.get('preprocessed_count', 0)} 张图片</p>")
        html.append("</div>")
    
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
    console.print("[bold blue]🚀 缓存版SSIM相似度分析工具[/bold blue]")
    console.print("[yellow]支持预处理缓存和SSIM结果缓存，大幅提升重复计算效率[/yellow]\n")
    
    # 输入参数
    folder = Prompt.ask("📁 请输入图片文件夹路径", default="E:\\1Hub\\EH\\2EHV\\test")
    
    # 是否启用缓存
    use_cache = Confirm.ask("💾 是否启用缓存？(推荐)", default=True)
    cache_dir = None
    if use_cache:
        cache_dir = Path(folder) / ".ssim_cache"
    
    # 图片数量限制
    max_images = IntPrompt.ask("🔢 最大处理图片数量（0表示不限制）", default=50)
    
    # 寻找最相似的对数
    top_n = IntPrompt.ask("🏆 显示最相似的前N对", default=15)
    
    # 图片尺寸
    size_choice = Prompt.ask("📐 图片处理尺寸 (1:128x128快速 2:256x256精确)", default="1", choices=["1", "2"])
    target_size = (128, 128) if size_choice == "1" else (256, 256)
    
    # 颜色模式
    grayscale = Confirm.ask("🎨 是否转为灰度模式？", default=False)
    
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
    if max_images > 0 and len(image_files) > max_images:
        console.print(f"[yellow]⚡ 随机选择 {max_images} 张图片进行分析[/yellow]")
        import random
        image_files = random.sample(image_files, max_images)
    
    if len(image_files) < 2:
        console.print("[red]❌ 图片数量不足，至少需要2张图片[/red]")
        return
    
    # 计算预估时间
    total_pairs = len(image_files) * (len(image_files) - 1) // 2
    estimated_seconds = total_pairs * (0.01 if target_size == (128, 128) else 0.03)
    console.print(f"[cyan]⏱️  需要计算 {total_pairs} 对，预估耗时: {estimated_seconds:.1f} 秒[/cyan]")
    console.print(f"[cyan]💡 使用缓存可以大幅减少重复计算时间[/cyan]\n")
    
    # 开始计算
    start_time = time.time()
    calculator = CachedSSIMCalculator(
        target_size=target_size, 
        use_grayscale=grayscale,
        cache_dir=cache_dir
    )
    
    # 统计缓存信息
    initial_cached_pairs = len(calculator.ssim_results)
    initial_cached_images = len(calculator.preprocessed_images)
    
    top_pairs, all_pairs = find_most_similar_pairs_cached(image_files, calculator, top_n)
    
    elapsed_time = time.time() - start_time
    console.print(f"\n[bold green]✅ 计算完成！耗时: {elapsed_time:.2f} 秒[/bold green]")
    
    # 保存缓存
    if use_cache:
        calculator.save_cache()
    
    # 缓存统计
    final_cached_pairs = len(calculator.ssim_results)
    final_cached_images = len(calculator.preprocessed_images)
    new_calculations = final_cached_pairs - initial_cached_pairs
    cache_hits = total_pairs - new_calculations
    hit_rate = (cache_hits / total_pairs * 100) if total_pairs > 0 else 0
    
    cache_stats = {
        'cache_hits': cache_hits,
        'new_calculations': new_calculations,
        'hit_rate': hit_rate,
        'preprocessed_count': final_cached_images
    }
    
    # 显示缓存统计
    cache_table = Table(title="⚡ 缓存性能统计")
    cache_table.add_column("指标", style="cyan")
    cache_table.add_column("值", style="green", justify="right")
    
    cache_table.add_row("缓存命中", str(cache_hits))
    cache_table.add_row("新计算", str(new_calculations))
    cache_table.add_row("命中率", f"{hit_rate:.1f}%")
    cache_table.add_row("预处理缓存", str(final_cached_images))
    cache_table.add_row("SSIM结果缓存", str(final_cached_pairs))
    
    console.print(cache_table)
    
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
    output_path = folder_path / "ssim_cached_report.html"
    generate_cached_report(top_pairs, all_pairs, output_path, cache_stats)
    
    console.print(f"\n[bold blue]🎉 分析完成！[/bold blue]")
    console.print(f"[green]📄 HTML报告: {output_path}[/green]")
    if use_cache:
        console.print(f"[green]💾 缓存目录: {cache_dir}[/green]")

if __name__ == "__main__":
    main()
