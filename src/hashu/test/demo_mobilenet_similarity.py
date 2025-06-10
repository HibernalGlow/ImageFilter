import time
import numpy as np
import pickle
from pathlib import Path
from itertools import combinations
from PIL import Image
import pillow_avif
import pillow_jxl 
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing import image

# 创建控制台
console = Console()

class MobileNetFeatureExtractor:
    """MobileNet特征提取器"""
    
    def __init__(self):
        # 加载预训练的MobileNetV2模型，去掉顶层分类器
        self.model = MobileNetV2(weights='imagenet', include_top=False, pooling='avg')
        console.print("[bold green]MobileNetV2模型加载完成[/bold green]")
    
    def extract_features(self, img_path):
        """提取单张图片的特征向量"""
        try:
            # 加载和预处理图片
            img = image.load_img(img_path, target_size=(224, 224))
            img_array = image.img_to_array(img)
            img_array = np.expand_dims(img_array, axis=0)
            img_array = preprocess_input(img_array)
            
            # 提取特征
            features = self.model.predict(img_array, verbose=0)
            # 归一化特征向量
            features = normalize(features, norm='l2')
            return features.flatten()
        except Exception as e:
            console.print(f"[red]特征提取失败: {img_path}，原因: {e}")
            return None

def calc_features_for_images(image_files, feature_extractor, progress=None, task_id=None):
    """批量计算图片特征向量"""
    features = {}
    
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
            task = local_progress.add_task("[cyan]提取MobileNet特征", total=len(image_files))
            for img in image_files:
                feature_vector = feature_extractor.extract_features(img)
                if feature_vector is not None:
                    features[str(img)] = feature_vector
                local_progress.update(task, advance=1)
    else:
        # 使用传入的progress实例
        for img in image_files:
            feature_vector = feature_extractor.extract_features(img)
            if feature_vector is not None:
                features[str(img)] = feature_vector
            if task_id is not None:
                progress.update(task_id, advance=1)
    return features

def calc_similarity_pairs(features, progress=None, task_id=None):
    """计算所有图片两两余弦相似度"""
    similarities = []
    pairs = []
    items = list(features.items())
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
            task = local_progress.add_task("[cyan]计算余弦相似度", total=total_pairs)
            for i, (img1, feat1) in enumerate(items):
                for j in range(i + 1, len(items)):
                    img2, feat2 = items[j]
                    # 计算余弦相似度
                    similarity = cosine_similarity([feat1], [feat2])[0][0]
                    similarities.append(similarity)
                    pairs.append((img1, img2, similarity))
                    local_progress.update(task, advance=1)
    else:
        # 使用传入的progress实例
        for i, (img1, feat1) in enumerate(items):
            for j in range(i + 1, len(items)):
                img2, feat2 = items[j]
                # 计算余弦相似度
                similarity = cosine_similarity([feat1], [feat2])[0][0]
                similarities.append(similarity)
                pairs.append((img1, img2, similarity))
                if task_id is not None:
                    progress.update(task_id, advance=1)
    return similarities, pairs

def save_features(features, save_path):
    """保存特征向量到文件"""
    console.print(f"[bold]正在保存特征向量到 [cyan]{save_path}[/cyan]...[/bold]")
    with open(save_path, 'wb') as f:
        pickle.dump(features, f)
    console.print(f"[bold green]特征向量已保存至: {Path(save_path).resolve()}[/bold green]")

def load_features(load_path):
    """从文件加载特征向量"""
    console.print(f"[bold]正在从 [cyan]{load_path}[/cyan] 加载特征向量...[/bold]")
    with open(load_path, 'rb') as f:
        features = pickle.load(f)
    console.print(f"[bold green]成功加载 {len(features)} 个特征向量[/bold green]")
    return features

def benchmark_mobilenet_similarity(image_dir, save_features_file=None, load_features_file=None):
    """MobileNet相似度基准测试"""
    image_dir = Path(image_dir)
    # 修改为递归查找所有子文件夹中的图片
    image_extensions = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".jxl", ".avif"]
    console.print("[bold]开始递归查找所有图片...[/bold]")
    image_files = []
    for ext in image_extensions:
        image_files.extend(list(image_dir.rglob(f"*{ext}")))
        image_files.extend(list(image_dir.rglob(f"*{ext.upper()}")))  # 兼容大写扩展名
    
    console.print(f"[bold green]共找到 {len(image_files)} 张图片[/bold green]")
    
    # 创建单一的Progress实例
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[bold green]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        
        if load_features_file and Path(load_features_file).exists():
            # 从文件加载特征向量
            features = load_features(load_features_file)
            # 过滤掉不存在的图片
            existing_features = {}
            for img_path, feat in features.items():
                if Path(img_path).exists():
                    existing_features[img_path] = feat
            features = existing_features
            console.print(f"[bold yellow]过滤后剩余 {len(features)} 个有效特征向量[/bold yellow]")
            elapsed = 0  # 加载时间忽略不计
        else:
            # 计算特征向量
            console.print(f"\n[bold yellow]=== MobileNet特征提取 ===[/bold yellow]")
            start = time.time()
            
            # 创建特征提取器
            feature_extractor = MobileNetFeatureExtractor()
            
            # 添加计算特征的任务
            feature_task = progress.add_task("[cyan]提取MobileNet特征", total=len(image_files))
            features = calc_features_for_images(image_files, feature_extractor, progress, feature_task)
            elapsed = time.time() - start
            console.print(f"[bold]特征提取耗时: [green]{elapsed:.2f}[/green] 秒[/bold]")
            
            # 保存特征向量
            if save_features_file:
                save_features(features, save_features_file)
        
        console.print("[bold]开始计算余弦相似度...[/bold]")
        # 计算相似度对数
        total_pairs = len(features) * (len(features) - 1) // 2
        similarity_task = progress.add_task("[cyan]计算余弦相似度", total=total_pairs)
        similarities, pairs = calc_similarity_pairs(features, progress, similarity_task)
        
        if similarities:
            avg_sim = sum(similarities) / len(similarities)
            console.print(f"[bold]平均余弦相似度: [green]{avg_sim:.4f}[/green]，最大: [red]{max(similarities):.4f}[/red]，最小: [blue]{min(similarities):.4f}[/blue][/bold]")
        else:
            console.print("[bold red]图片数量过少，无法对比相似度[/bold red]")
        
        results = {
            "features": features,
            "time": elapsed,
            "similarities": similarities,
            "pairs": pairs
        }
    
    return results, image_files

def generate_html_report(results, image_files, output_path="mobilenet_similarity_report.html"):
    """生成HTML相似度报告"""
    console.print("[bold]正在生成HTML报告...[/bold]")
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>MobileNet Similarity Report</title>",
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
        ".high-similarity{background-color:#ffe6e6;}",
        ".medium-similarity{background-color:#fff2e6;}",
        ".low-similarity{background-color:#e6f3ff;}",
        "</style>",
        "<script>",
        "function filterTable() {",
        "  const minInput = document.getElementById('filter-min');",
        "  const maxInput = document.getElementById('filter-max');",
        "  const minValue = parseFloat(minInput.value) || 0;",
        "  const maxValue = parseFloat(maxInput.value) || 1;",
        "  const table = document.getElementById('similarity-table');",
        "  const rows = table.getElementsByTagName('tr');",
        "  for (let i = 1; i < rows.length; i++) {",
        "    const similarityCell = rows[i].cells[2];",
        "    if (similarityCell) {",
        "      const similarity = parseFloat(similarityCell.textContent);",
        "      rows[i].style.display = (similarity >= minValue && similarity <= maxValue) ? '' : 'none';",
        "    }",
        "  }",
        "}",
        "</script>",
        "</head><body>",
        "<h1>MobileNet图片相似度分析报告</h1>",
        f"<p>图片总数：{len(image_files)}</p>",
        f"<p>特征向量维度：{len(list(results['features'].values())[0]) if results['features'] else 'N/A'}</p>"
    ]
    
    # 总览表
    similarities = results["similarities"]
    if similarities:
        avg = f"{sum(similarities)/len(similarities):.4f}"
        maxv = f"{max(similarities):.4f}"
        minv = f"{min(similarities):.4f}"
        html.append("<div class='section'><h2>相似度统计</h2><table>")
        html.append("<tr><th>指标</th><th>值</th></tr>")
        html.append(f"<tr><td>计算耗时(秒)</td><td>{results['time']:.2f}</td></tr>")
        html.append(f"<tr><td>平均余弦相似度</td><td>{avg}</td></tr>")
        html.append(f"<tr><td>最大相似度</td><td>{maxv}</td></tr>")
        html.append(f"<tr><td>最小相似度</td><td>{minv}</td></tr>")
        html.append(f"<tr><td>对比对数</td><td>{len(similarities)}</td></tr>")
        html.append("</table></div>")

    # 详细对比
    html.append("<div class='section'><h2>详细相似度对比</h2>")
    
    # 添加过滤控件
    html.append("<div class='filter-controls'>")
    html.append("相似度范围: ")
    html.append("<input type='number' id='filter-min' min='0' max='1' step='0.01' placeholder='最小值' value='0.8'>")
    html.append(" - ")
    html.append("<input type='number' id='filter-max' min='0' max='1' step='0.01' placeholder='最大值' value='1.0'>")
    html.append("<button onclick='filterTable()'>过滤</button>")
    html.append("<span style='margin-left:20px;'>说明: 相似度越接近1表示越相似</span>")
    html.append("</div>")
    
    html.append("<table id='similarity-table'><tr><th>图片1</th><th>图片2</th><th>余弦相似度</th></tr>")
    
    # 对相似度进行排序（降序，最相似的在前）
    sorted_pairs = sorted(results["pairs"], key=lambda x: x[2], reverse=True)
    
    # 使用rich进度条
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[bold green]{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task("[cyan]生成相似度报告", total=len(sorted_pairs))
        
        for img1, img2, similarity in sorted_pairs:
            img1_path = Path(img1).resolve()
            img2_path = Path(img2).resolve()
            # 显示文件名和相对路径
            img1_name = img1_path.name
            img2_name = img2_path.name
            img1_folder = str(img1_path.parent)
            img2_folder = str(img2_path.parent)
            
            # 根据相似度设置行样式
            row_class = ""
            if similarity >= 0.9:
                row_class = "high-similarity"
            elif similarity >= 0.7:
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
                f"<td>{similarity:.4f}</td>"
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
        table = Table(title="MobileNet相似度分析结果")
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green", justify="right")
        
        table.add_row("计算耗时(秒)", f"{results['time']:.2f}")
        table.add_row("平均余弦相似度", f"{sum(similarities)/len(similarities):.4f}")
        table.add_row("最大相似度", f"{max(similarities):.4f}")
        table.add_row("最小相似度", f"{min(similarities):.4f}")
        table.add_row("对比对数", str(len(similarities)))
        table.add_row("高相似度对数(≥0.9)", str(len([s for s in similarities if s >= 0.9])))
        table.add_row("中等相似度对数(0.7-0.9)", str(len([s for s in similarities if 0.7 <= s < 0.9])))
        table.add_row("低相似度对数(<0.7)", str(len([s for s in similarities if s < 0.7])))
        
        console.print(table)

if __name__ == "__main__":
    # 交互式输入路径
    folder = Prompt.ask("请输入图片文件夹路径", default="E:\\2EHV\\test")
    
    # 询问是否保存/加载特征向量
    save_features_choice = Prompt.ask("是否保存特征向量到文件？(y/n)", default="y")
    features_file = None
    if save_features_choice.lower() == 'y':
        features_file = Path(folder) / "mobilenet_features.pkl"
    
    load_features_choice = Prompt.ask(f"是否从现有文件加载特征向量？(如果存在 {features_file}) (y/n)", default="n")
    load_file = None
    if load_features_choice.lower() == 'y' and features_file and features_file.exists():
        load_file = features_file
    
    console.print(f"[bold]目标文件夹: [cyan]{folder}[/cyan][/bold]")
    if features_file:
        console.print(f"[bold]特征文件: [cyan]{features_file}[/cyan][/bold]")
    
    results, image_files = benchmark_mobilenet_similarity(
        folder, 
        save_features_file=features_file,
        load_features_file=load_file
    )
    
    output_path = Path(folder) / "mobilenet_similarity_report.html"
    generate_html_report(results, image_files, output_path=output_path)
