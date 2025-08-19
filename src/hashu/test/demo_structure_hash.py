import time
import numpy as np
import pickle
import json
from pathlib import Path
from PIL import Image
import pillow_avif
import pillow_jxl 
from skimage import filters, feature, measure
from skimage.transform import resize
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
import hashlib
import sqlite3

# 创建控制台
console = Console()

class StructureHashExtractor:
    """结构特征哈希提取器 - 生成可存储到数据库的短特征"""
    
    def __init__(self, target_size=(128, 128), feature_dim=64):
        self.target_size = target_size
        self.feature_dim = feature_dim
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=feature_dim)
        self.is_fitted = False
        
        console.print(f"[bold green]结构哈希提取器初始化 - 尺寸: {target_size}, 特征维度: {feature_dim}[/bold green]")
    
    def extract_basic_features(self, img_array):
        """提取基础统计特征"""
        features = []
        
        # 1. 基础统计特征
        features.extend([
            np.mean(img_array),           # 均值
            np.std(img_array),            # 标准差
            np.median(img_array),         # 中位数
            np.min(img_array),            # 最小值
            np.max(img_array),            # 最大值
        ])
        
        # 2. 边缘特征
        edges = filters.sobel(img_array)
        features.extend([
            np.mean(edges),
            np.std(edges),
            np.sum(edges > 0.1),         # 边缘像素数量
        ])
        
        # 3. 纹理特征（局部二值模式）
        lbp = feature.local_binary_pattern(img_array, P=8, R=1, method='uniform')
        lbp_hist, _ = np.histogram(lbp.ravel(), bins=10, range=(0, 10))
        features.extend(lbp_hist.tolist())
        
        return np.array(features)
    
    def extract_block_features(self, img_array, block_size=16):
        """提取分块特征"""
        h, w = img_array.shape
        features = []
        
        # 将图像分成若干块
        for i in range(0, h, block_size):
            for j in range(0, w, block_size):
                block = img_array[i:i+block_size, j:j+block_size]
                if block.size > 0:
                    features.extend([
                        np.mean(block),
                        np.std(block),
                        np.median(block)
                    ])
        
        return np.array(features)
    
    def extract_gradient_features(self, img_array):
        """提取梯度特征"""
        # 计算梯度
        grad_x = filters.sobel_h(img_array)
        grad_y = filters.sobel_v(img_array)
        
        # 梯度幅值和方向
        magnitude = np.sqrt(grad_x**2 + grad_y**2)
        orientation = np.arctan2(grad_y, grad_x)
        
        features = []
        
        # 梯度统计
        features.extend([
            np.mean(magnitude),
            np.std(magnitude),
            np.percentile(magnitude, 25),
            np.percentile(magnitude, 75),
        ])
        
        # 方向直方图
        orientation_hist, _ = np.histogram(orientation.ravel(), bins=8, range=(-np.pi, np.pi))
        features.extend(orientation_hist.tolist())
        
        return np.array(features)
    
    def extract_all_features(self, img_path):
        """提取完整特征向量"""
        try:
            with Image.open(img_path) as img:
                # 转换为灰度
                if img.mode != 'L':
                    img = img.convert('L')
                
                # 调整尺寸
                img = img.resize(self.target_size, Image.Resampling.LANCZOS)
                img_array = np.array(img, dtype=np.float64) / 255.0
                
                # 提取各种特征
                basic_features = self.extract_basic_features(img_array)
                block_features = self.extract_block_features(img_array)
                gradient_features = self.extract_gradient_features(img_array)
                
                # 合并所有特征
                all_features = np.concatenate([
                    basic_features,
                    block_features,
                    gradient_features
                ])
                
                return all_features
        except Exception as e:
            console.print(f"[red]特征提取失败: {img_path}, 错误: {e}")
            return None
    
    def fit_transform(self, image_files):
        """训练PCA并转换特征"""
        console.print("[bold]开始提取特征并训练降维模型...[/bold]")
        
        all_features = []
        valid_files = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[bold green]{task.completed}/{task.total}"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("[cyan]提取特征", total=len(image_files))
            
            for img_file in image_files:
                features = self.extract_all_features(img_file)
                if features is not None:
                    all_features.append(features)
                    valid_files.append(img_file)
                progress.update(task, advance=1)
        
        if not all_features:
            console.print("[red]没有成功提取任何特征！")
            return {}, []
          # 标准化和降维
        X = np.array(all_features)
        n_samples, n_features = X.shape
        
        # 调整特征维度，不能超过样本数和原始特征数的最小值
        max_components = min(n_samples, n_features)
        actual_feature_dim = min(self.feature_dim, max_components)
        
        console.print(f"[cyan]原始特征维度: {n_features}, 样本数: {n_samples}[/cyan]")
        console.print(f"[cyan]目标维度: {self.feature_dim} -> 实际维度: {actual_feature_dim}[/cyan]")
        
        # 更新PCA组件数
        self.pca = PCA(n_components=actual_feature_dim)
        
        # 标准化
        X_scaled = self.scaler.fit_transform(X)
        
        # PCA降维
        X_reduced = self.pca.fit_transform(X_scaled)
        
        self.is_fitted = True
        
        # 生成结构哈希
        structure_hashes = {}
        for i, img_file in enumerate(valid_files):
            # 将特征向量转换为固定长度的哈希
            hash_vector = X_reduced[i]
            structure_hashes[str(img_file)] = hash_vector
        
        console.print(f"[bold green]成功生成 {len(structure_hashes)} 个结构哈希[/bold green]")
        console.print(f"[cyan]PCA解释方差比: {self.pca.explained_variance_ratio_.sum():.3f}[/cyan]")
        
        return structure_hashes, valid_files
    
    def transform(self, img_path):
        """转换单张图片为结构哈希"""
        if not self.is_fitted:
            console.print("[red]模型未训练，请先调用fit_transform!")
            return None
        
        features = self.extract_all_features(img_path)
        if features is None:
            return None
        
        # 标准化和降维
        features_scaled = self.scaler.transform([features])
        hash_vector = self.pca.transform(features_scaled)[0]
        
        return hash_vector

class StructureHashDatabase:
    """结构哈希数据库管理"""
    
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS structure_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                file_mtime REAL,
                hash_vector BLOB NOT NULL,
                feature_dim INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        console.print(f"[bold green]数据库初始化完成: {self.db_path}[/bold green]")
    
    def save_hashes(self, structure_hashes):
        """保存结构哈希到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        saved_count = 0
        for file_path, hash_vector in structure_hashes.items():
            try:
                path_obj = Path(file_path)
                if not path_obj.exists():
                    continue
                
                stat = path_obj.stat()
                
                # 序列化哈希向量
                hash_blob = pickle.dumps(hash_vector.astype(np.float32))
                
                cursor.execute('''
                    INSERT OR REPLACE INTO structure_hashes 
                    (file_path, file_name, file_size, file_mtime, hash_vector, feature_dim)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    str(path_obj),
                    path_obj.name,
                    stat.st_size,
                    stat.st_mtime,
                    hash_blob,
                    len(hash_vector)
                ))
                saved_count += 1
            except Exception as e:
                console.print(f"[red]保存失败: {file_path}, 错误: {e}")
        
        conn.commit()
        conn.close()
        console.print(f"[bold green]成功保存 {saved_count} 个结构哈希到数据库[/bold green]")
    
    def load_hashes(self):
        """从数据库加载结构哈希"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT file_path, hash_vector FROM structure_hashes')
        rows = cursor.fetchall()
        
        structure_hashes = {}
        for file_path, hash_blob in rows:
            try:
                hash_vector = pickle.loads(hash_blob)
                # 检查文件是否仍然存在
                if Path(file_path).exists():
                    structure_hashes[file_path] = hash_vector
            except Exception as e:
                console.print(f"[yellow]加载哈希失败: {file_path}, 错误: {e}")
        
        conn.close()
        console.print(f"[bold green]从数据库加载 {len(structure_hashes)} 个结构哈希[/bold green]")
        return structure_hashes
    
    def get_database_stats(self):
        """获取数据库统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM structure_hashes')
        total_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT AVG(feature_dim) FROM structure_hashes')
        avg_dim = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(LENGTH(hash_vector)) FROM structure_hashes')
        total_size = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_count': total_count,
            'avg_dimension': int(avg_dim),
            'total_size_bytes': total_size,
            'avg_size_per_hash': total_size / total_count if total_count > 0 else 0
        }

def calculate_structure_similarity(hash1, hash2, method='cosine'):
    """计算结构哈希相似度"""
    if method == 'cosine':
        # 余弦相似度 (0-1, 1最相似)
        similarity = cosine_similarity([hash1], [hash2])[0][0]
        return similarity
    elif method == 'euclidean':
        # 欧氏距离 (越小越相似)
        distance = euclidean_distances([hash1], [hash2])[0][0]
        # 转换为相似度 (0-1, 1最相似)
        max_dist = np.sqrt(len(hash1)) * 2  # 估计最大距离
        similarity = max(0, 1 - distance / max_dist)
        return similarity
    else:
        raise ValueError(f"不支持的相似度计算方法: {method}")

def find_similar_pairs_by_hash(structure_hashes, top_n=10, similarity_method='cosine'):
    """基于结构哈希查找相似图片对"""
    console.print(f"[bold]使用结构哈希计算相似度（方法: {similarity_method}）...[/bold]")
    
    items = list(structure_hashes.items())
    all_pairs = []
    total_pairs = len(items) * (len(items) - 1) // 2
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[bold green]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("[cyan]计算结构相似度", total=total_pairs)
        
        for i, (img1, hash1) in enumerate(items):
            for j in range(i + 1, len(items)):
                img2, hash2 = items[j]
                
                similarity = calculate_structure_similarity(hash1, hash2, similarity_method)
                all_pairs.append((img1, img2, similarity))
                progress.update(task, advance=1)
    
    # 按相似度排序
    all_pairs.sort(key=lambda x: x[2], reverse=True)
    return all_pairs[:top_n], all_pairs

def generate_structure_hash_report(top_pairs, all_pairs, output_path, stats=None):
    """生成结构哈希报告"""
    console.print("[bold]正在生成结构哈希HTML报告...[/bold]")
    
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>结构哈希相似度报告</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;margin:30px;background:#f8f9fa;}",
        ".container{max-width:1200px;margin:0 auto;background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}",
        "h1{color:#2c3e50;text-align:center;margin-bottom:30px;}",
        ".stats{background:#e8f4fd;padding:15px;border-radius:8px;margin:20px 0;}",
        ".hash-stats{background:#f0f9ff;padding:15px;border-radius:8px;margin:20px 0;border-left:4px solid #0ea5e9;}",
        ".pair-grid{display:grid;gap:20px;margin:20px 0;}",
        ".pair-item{border:1px solid #ddd;border-radius:8px;padding:15px;background:#fff;}",
        ".image-container{display:flex;align-items:center;gap:20px;}",
        ".image-box{text-align:center;flex:1;}",
        "img{max-width:200px;max-height:200px;border-radius:5px;box-shadow:0 2px 5px rgba(0,0,0,0.2);}",
        ".filename{font-size:12px;color:#666;margin-top:5px;word-break:break-all;}",
        ".similarity-value{font-size:24px;font-weight:bold;text-align:center;flex:0 0 120px;}",
        ".high{color:#27ae60;} .medium{color:#f39c12;} .low{color:#e74c3c;}",
        "</style>",
        "</head><body>",
        "<div class='container'>",
        "<h1>🔗 结构哈希相似度分析报告</h1>",
    ]
    
    # 结构哈希统计
    if stats:
        html.append("<div class='hash-stats'>")
        html.append("<h3>🔢 结构哈希统计</h3>")
        html.append(f"<p><strong>哈希总数:</strong> {stats.get('total_count', 0)}</p>")
        html.append(f"<p><strong>平均维度:</strong> {stats.get('avg_dimension', 0)}</p>")
        html.append(f"<p><strong>存储大小:</strong> {stats.get('total_size_bytes', 0) / 1024:.1f} KB</p>")
        html.append(f"<p><strong>平均每个哈希:</strong> {stats.get('avg_size_per_hash', 0):.1f} 字节</p>")
        html.append("</div>")
    
    # 相似度统计
    if all_pairs:
        similarities = [p[2] for p in all_pairs]
        avg_sim = sum(similarities) / len(similarities)
        max_sim = max(similarities)
        min_sim = min(similarities)
        
        html.append("<div class='stats'>")
        html.append("<h3>📊 相似度统计</h3>")
        html.append(f"<p><strong>对比总数:</strong> {len(all_pairs)}</p>")
        html.append(f"<p><strong>平均相似度:</strong> {avg_sim:.4f}</p>")
        html.append(f"<p><strong>最大相似度:</strong> {max_sim:.4f}</p>")
        html.append(f"<p><strong>最小相似度:</strong> {min_sim:.4f}</p>")
        html.append("</div>")
    
    # 最相似图片对
    html.append("<h2>🏆 最相似的图片对</h2>")
    html.append("<div class='pair-grid'>")
    
    for i, (img1, img2, similarity) in enumerate(top_pairs, 1):
        img1_path = Path(img1)
        img2_path = Path(img2)
        
        # 根据相似度设置颜色
        sim_class = "high" if similarity >= 0.8 else "medium" if similarity >= 0.6 else "low"
        
        html.append(f"<div class='pair-item'>")
        html.append(f"<h4>第 {i} 对 (相似度: {similarity:.4f})</h4>")
        html.append(f"<div class='image-container'>")
        html.append(f"<div class='image-box'>")
        html.append(f"<img src='file:///{img1_path.resolve()}' alt='图片1'>")
        html.append(f"<div class='filename'>{img1_path.name}</div>")
        html.append(f"</div>")
        html.append(f"<div class='similarity-value {sim_class}'>{similarity:.4f}</div>")
        html.append(f"<div class='image-box'>")
        html.append(f"<img src='file:///{img2_path.resolve()}' alt='图片2'>")
        html.append(f"<div class='filename'>{img2_path.name}</div>")
        html.append(f"</div>")
        html.append(f"</div>")
        html.append(f"</div>")
    
    html.append("</div>")
    html.append("</div></body></html>")
    
    Path(output_path).write_text('\n'.join(html), encoding="utf-8")
    console.print(f"[bold green]报告已保存: {Path(output_path).resolve()}[/bold green]")

def main():
    console.print("[bold blue]🔗 结构哈希图片相似度分析工具[/bold blue]")
    console.print("[yellow]基于图像结构特征生成短哈希，支持数据库存储[/yellow]\n")
    
    # 输入参数
    folder = Prompt.ask("📁 请输入图片文件夹路径", default="E:\\2EHV\\test")
    
    # 特征参数
    feature_dim = IntPrompt.ask("🔢 结构哈希维度（推荐32-128）", default=64)
    
    # 数据库选项
    use_database = Confirm.ask("💾 是否使用数据库存储哈希？", default=True)
    db_path = None
    if use_database:
        db_path = Path(folder) / "structure_hashes.db"
    
    # 图片限制
    max_images = IntPrompt.ask("🔢 最大处理图片数量（0表示不限制）", default=50)
    top_n = IntPrompt.ask("🏆 显示最相似的前N对", default=15)
    
    # 相似度计算方法
    similarity_method = Prompt.ask("📏 相似度计算方法", 
                                 choices=["cosine", "euclidean"], 
                                 default="cosine")
    
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
    
    # 初始化数据库
    db_manager = None
    if use_database:
        db_manager = StructureHashDatabase(db_path)
    
    # 尝试加载已有哈希
    existing_hashes = {}
    if db_manager:
        existing_hashes = db_manager.load_hashes()
    
    # 提取特征
    start_time = time.time()
    extractor = StructureHashExtractor(feature_dim=feature_dim)
    
    if existing_hashes:
        console.print(f"[cyan]发现 {len(existing_hashes)} 个已有哈希，将增量处理[/cyan]")
        # TODO: 增量处理逻辑（新图片提取特征，已有图片复用）
        structure_hashes, valid_files = extractor.fit_transform(image_files)
    else:
        structure_hashes, valid_files = extractor.fit_transform(image_files)
    
    elapsed_time = time.time() - start_time
    console.print(f"\n[bold green]✅ 特征提取完成！耗时: {elapsed_time:.2f} 秒[/bold green]")
    
    # 保存到数据库
    if db_manager and structure_hashes:
        db_manager.save_hashes(structure_hashes)
        db_stats = db_manager.get_database_stats()
    else:
        db_stats = None
    
    # 计算相似度
    console.print("\n[bold]🔍 开始计算结构相似度...[/bold]")
    top_pairs, all_pairs = find_similar_pairs_by_hash(
        structure_hashes, top_n, similarity_method
    )
    
    # 显示统计信息
    if db_stats:
        stats_table = Table(title="💾 数据库统计")
        stats_table.add_column("指标", style="cyan")
        stats_table.add_column("值", style="green", justify="right")
        
        stats_table.add_row("哈希总数", str(db_stats['total_count']))
        stats_table.add_row("平均维度", str(db_stats['avg_dimension']))
        stats_table.add_row("存储大小", f"{db_stats['total_size_bytes'] / 1024:.1f} KB")
        stats_table.add_row("每哈希大小", f"{db_stats['avg_size_per_hash']:.1f} 字节")
        
        console.print(stats_table)
    
    # 显示结果
    if top_pairs:
        result_table = Table(title="🏆 最相似的图片对")
        result_table.add_column("排名", style="cyan", justify="center")
        result_table.add_column("图片1", style="blue")
        result_table.add_column("图片2", style="blue")
        result_table.add_column("相似度", style="green", justify="center")
        result_table.add_column("相似程度", style="yellow")
        
        for i, (img1, img2, similarity) in enumerate(top_pairs, 1):
            img1_name = Path(img1).name
            img2_name = Path(img2).name
            level = "很高" if similarity >= 0.9 else "高" if similarity >= 0.8 else "中等" if similarity >= 0.6 else "低"
            result_table.add_row(str(i), img1_name, img2_name, f"{similarity:.4f}", level)
        
        console.print(result_table)
    
    # 生成报告
    output_path = folder_path / "structure_hash_report.html"
    generate_structure_hash_report(top_pairs, all_pairs, output_path, db_stats)
    
    console.print(f"\n[bold blue]🎉 分析完成！[/bold blue]")
    console.print(f"[green]📄 HTML报告: {output_path}[/green]")
    if use_database:
        console.print(f"[green]💾 数据库: {db_path}[/green]")
        console.print(f"[cyan]💡 下次运行可直接使用数据库中的哈希，大幅提升速度[/cyan]")

if __name__ == "__main__":
    main()
