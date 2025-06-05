"""
图像相似性算法比较脚本
比较PHash汉明距离、SSIM和LPIPS三种算法的速度和数值差异

功能：
1. GPU加速的SSIM计算（使用PyTorch）
2. 已有的PHash汉明距离计算（CPU/NumPy加速）
3. 已有的LPIPS计算（GPU支持）
4. 性能基准测试（速度比较）
5. 数值差异分析
6. 结果可视化

作者: ImageFilter项目
"""

import os
import time
import torch
import torch.nn.functional as F
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
from dataclasses import dataclass
from PIL import Image
import pillow_avif
import pillow_jxl
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
import argparse
import json
from io import BytesIO

# 导入现有模块
from hashu.core.calculate_hash_custom import ImageHashCalculator
from hashu.utils.hash_accelerator import HashAccelerator
from imgutils.metrics import lpips_difference

# 设置环境变量
os.environ['LPIPS_USE_GPU'] = '1'

console = Console()

@dataclass
class SimilarityResult:
    """相似性算法结果"""
    algorithm: str
    value: float
    computation_time: float
    device: str = "cpu"

@dataclass
class ComparisonMetrics:
    """比较指标"""
    mean_time: float
    std_time: float
    min_time: float
    max_time: float
    median_time: float
    throughput: float  # 图片对/秒

class GPUAcceleratedSSIM:
    """GPU加速的SSIM计算器"""
    
    def __init__(self, device: str = None):
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        console.print(f"[green]SSIM使用设备: {self.device}[/green]")
    
    def _prepare_image(self, image_path: str) -> torch.Tensor:
        """准备图像用于SSIM计算"""
        try:
            # 加载图像
            img = Image.open(image_path).convert('RGB')
            
            # 转换为张量 [C, H, W]
            img_array = np.array(img).astype(np.float32) / 255.0
            img_tensor = torch.from_numpy(img_array).permute(2, 0, 1)
            
            # 添加批次维度 [1, C, H, W]
            img_tensor = img_tensor.unsqueeze(0)
            
            # 移到GPU
            img_tensor = img_tensor.to(self.device)
            
            return img_tensor
            
        except Exception as e:
            console.print(f"[red]加载图像失败 {image_path}: {e}[/red]")
            return None
    
    def calculate_ssim(self, img1_path: str, img2_path: str, 
                      window_size: int = 11, sigma: float = 1.5) -> float:
        """计算两图像的SSIM值"""
        try:
            # 准备图像
            img1 = self._prepare_image(img1_path)
            img2 = self._prepare_image(img2_path)
            
            if img1 is None or img2 is None:
                return None
            
            # 调整图像大小到相同尺寸
            if img1.shape != img2.shape:
                h = min(img1.shape[2], img2.shape[2])
                w = min(img1.shape[3], img2.shape[3])
                img1 = F.interpolate(img1, size=(h, w), mode='bilinear', align_corners=False)
                img2 = F.interpolate(img2, size=(h, w), mode='bilinear', align_corners=False)
            
            # 计算SSIM
            ssim_value = self._ssim(img1, img2, window_size, sigma)
            
            return float(ssim_value.item())
            
        except Exception as e:
            console.print(f"[red]SSIM计算失败: {e}[/red]")
            return None
    
    def _ssim(self, img1: torch.Tensor, img2: torch.Tensor, 
              window_size: int = 11, sigma: float = 1.5) -> torch.Tensor:
        """SSIM计算核心函数"""
        # 创建高斯窗口
        window = self._create_window(window_size, img1.size(1), sigma).to(img1.device)
        
        # 计算均值
        mu1 = F.conv2d(img1, window, padding=window_size//2, groups=img1.size(1))
        mu2 = F.conv2d(img2, window, padding=window_size//2, groups=img2.size(1))
        
        mu1_sq = mu1.pow(2)
        mu2_sq = mu2.pow(2)
        mu1_mu2 = mu1 * mu2
        
        # 计算方差和协方差
        sigma1_sq = F.conv2d(img1*img1, window, padding=window_size//2, groups=img1.size(1)) - mu1_sq
        sigma2_sq = F.conv2d(img2*img2, window, padding=window_size//2, groups=img2.size(1)) - mu2_sq
        sigma12 = F.conv2d(img1*img2, window, padding=window_size//2, groups=img1.size(1)) - mu1_mu2
        
        # SSIM常数
        C1 = 0.01**2
        C2 = 0.03**2
        
        # 计算SSIM
        ssim_map = ((2*mu1_mu2 + C1)*(2*sigma12 + C2))/((mu1_sq + mu2_sq + C1)*(sigma1_sq + sigma2_sq + C2))
        
        return ssim_map.mean()
    
    def _create_window(self, window_size: int, channel: int, sigma: float) -> torch.Tensor:
        """创建高斯窗口"""
        gauss = torch.Tensor([np.exp(-(x - window_size//2)**2/float(2*sigma**2)) for x in range(window_size)])
        gauss = gauss/gauss.sum()
        _1D_window = gauss.unsqueeze(1)
        _2D_window = _1D_window.mm(_1D_window.t()).float().unsqueeze(0).unsqueeze(0)
        window = _2D_window.expand(channel, 1, window_size, window_size).contiguous()
        return window

class ImageSimilarityComparator:
    """图像相似性算法比较器"""
    
    def __init__(self, max_workers: int = None, device: str = None):
        self.max_workers = max_workers or multiprocessing.cpu_count()
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        
        # 初始化算法
        self.ssim_calculator = GPUAcceleratedSSIM(self.device)
        
        console.print(Panel(
            f"[bold green]图像相似性算法比较器已初始化[/bold green]\n"
            f"最大工作线程数: {self.max_workers}\n"
            f"计算设备: {self.device}\n"
            f"GPU可用: {'是' if torch.cuda.is_available() else '否'}",
            title="初始化信息"
        ))
    
    def calculate_phash_hamming(self, img1_path: str, img2_path: str) -> Tuple[float, float]:
        """计算PHash汉明距离"""
        start_time = time.time()
        
        try:
            # 计算两个图像的哈希值
            hash1_result = ImageHashCalculator.calculate_phash(img1_path)
            hash2_result = ImageHashCalculator.calculate_phash(img2_path)
            
            if not hash1_result or not hash2_result:
                return None, time.time() - start_time
            
            # 计算汉明距离
            hamming_distance = ImageHashCalculator.calculate_hamming_distance(
                hash1_result['hash'], hash2_result['hash']
            )
            
            # 转换为相似性分数 (距离越小越相似，这里转换为0-1的相似性分数)
            # 假设最大汉明距离为64 (8x8=64位哈希)
            similarity = 1.0 - (hamming_distance / 64.0)
            
            computation_time = time.time() - start_time
            return similarity, computation_time
            
        except Exception as e:
            console.print(f"[red]PHash计算失败: {e}[/red]")
            return None, time.time() - start_time
    
    def calculate_ssim_score(self, img1_path: str, img2_path: str) -> Tuple[float, float]:
        """计算SSIM分数"""
        start_time = time.time()
        
        try:
            ssim_value = self.ssim_calculator.calculate_ssim(img1_path, img2_path)
            computation_time = time.time() - start_time
            return ssim_value, computation_time
            
        except Exception as e:
            console.print(f"[red]SSIM计算失败: {e}[/red]")
            return None, time.time() - start_time
    
    def calculate_lpips_score(self, img1_path: str, img2_path: str) -> Tuple[float, float]:
        """计算LPIPS分数"""
        start_time = time.time()
        
        try:
            # LPIPS返回的是距离，需要转换为相似性分数
            lpips_distance = lpips_difference(img1_path, img2_path)
            
            # 转换为相似性分数 (距离越小越相似)
            # LPIPS通常在0-1范围，我们使用 1-distance 作为相似性
            similarity = 1.0 - min(lpips_distance, 1.0)
            
            computation_time = time.time() - start_time
            return similarity, computation_time
            
        except Exception as e:
            console.print(f"[red]LPIPS计算失败: {e}[/red]")
            return None, time.time() - start_time
    
    def compare_image_pair(self, img1_path: str, img2_path: str) -> Dict[str, SimilarityResult]:
        """比较单对图像的所有算法"""
        results = {}
        
        # PHash汉明距离
        phash_sim, phash_time = self.calculate_phash_hamming(img1_path, img2_path)
        if phash_sim is not None:
            results['PHash_Hamming'] = SimilarityResult(
                algorithm='PHash_Hamming',
                value=phash_sim,
                computation_time=phash_time,
                device='cpu'
            )
        
        # SSIM
        ssim_sim, ssim_time = self.calculate_ssim_score(img1_path, img2_path)
        if ssim_sim is not None:
            results['SSIM'] = SimilarityResult(
                algorithm='SSIM',
                value=ssim_sim,
                computation_time=ssim_time,
                device=self.device
            )
        
        # LPIPS
        lpips_sim, lpips_time = self.calculate_lpips_score(img1_path, img2_path)
        if lpips_sim is not None:
            results['LPIPS'] = SimilarityResult(
                algorithm='LPIPS',
                value=lpips_sim,
                computation_time=lpips_time,
                device='gpu' if torch.cuda.is_available() else 'cpu'
            )
        
        return results
    
    def batch_compare_images(self, image_pairs: List[Tuple[str, str]], 
                           algorithms: List[str] = None) -> pd.DataFrame:
        """批量比较图像对"""
        if algorithms is None:
            algorithms = ['PHash_Hamming', 'SSIM', 'LPIPS']
        
        all_results = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
        ) as progress:
            
            task = progress.add_task(
                f"[green]比较 {len(image_pairs)} 对图像...", 
                total=len(image_pairs)
            )
            
            for i, (img1, img2) in enumerate(image_pairs):
                pair_results = self.compare_image_pair(img1, img2)
                
                # 添加基本信息
                base_info = {
                    'pair_id': i,
                    'image1': Path(img1).name,
                    'image2': Path(img2).name,
                    'image1_path': img1,
                    'image2_path': img2
                }
                
                # 为每个算法添加结果
                for algo in algorithms:
                    if algo in pair_results:
                        result = pair_results[algo]
                        row = base_info.copy()
                        row.update({
                            'algorithm': result.algorithm,
                            'similarity_score': result.value,
                            'computation_time': result.computation_time,
                            'device': result.device
                        })
                        all_results.append(row)
                
                progress.update(task, completed=i+1)
        
        return pd.DataFrame(all_results)
    
    def benchmark_algorithms(self, image_pairs: List[Tuple[str, str]], 
                           iterations: int = 3) -> Dict[str, ComparisonMetrics]:
        """基准测试算法性能"""
        console.print(f"[yellow]开始基准测试，将运行 {iterations} 次迭代...[/yellow]")
        
        algorithms = ['PHash_Hamming', 'SSIM', 'LPIPS']
        benchmark_results = {algo: [] for algo in algorithms}
        
        for iteration in range(iterations):
            console.print(f"[cyan]运行迭代 {iteration + 1}/{iterations}[/cyan]")
            
            results_df = self.batch_compare_images(image_pairs)
            
            # 统计每个算法的性能
            for algo in algorithms:
                algo_data = results_df[results_df['algorithm'] == algo]
                if not algo_data.empty:
                    total_time = algo_data['computation_time'].sum()
                    benchmark_results[algo].append(total_time)
        
        # 计算统计指标
        metrics = {}
        for algo, times in benchmark_results.items():
            if times:
                times = np.array(times)
                metrics[algo] = ComparisonMetrics(
                    mean_time=np.mean(times),
                    std_time=np.std(times),
                    min_time=np.min(times),
                    max_time=np.max(times),
                    median_time=np.median(times),
                    throughput=len(image_pairs) / np.mean(times)
                )
        
        return metrics
    
    def analyze_numerical_differences(self, results_df: pd.DataFrame) -> Dict:
        """分析算法间的数值差异"""
        analysis = {}
        
        # 获取每对图像的所有算法结果
        pair_results = {}
        for _, row in results_df.iterrows():
            pair_id = row['pair_id']
            if pair_id not in pair_results:
                pair_results[pair_id] = {}
            pair_results[pair_id][row['algorithm']] = row['similarity_score']
        
        # 计算算法间的相关性
        algorithms = results_df['algorithm'].unique()
        correlations = {}
        
        for i, algo1 in enumerate(algorithms):
            for algo2 in algorithms[i+1:]:
                scores1 = []
                scores2 = []
                
                for pair_id, scores in pair_results.items():
                    if algo1 in scores and algo2 in scores:
                        scores1.append(scores[algo1])
                        scores2.append(scores[algo2])
                
                if len(scores1) > 1:
                    correlation = np.corrcoef(scores1, scores2)[0, 1]
                    correlations[f"{algo1}_vs_{algo2}"] = correlation
        
        analysis['correlations'] = correlations
        
        # 计算每个算法的统计信息
        algorithm_stats = {}
        for algo in algorithms:
            algo_data = results_df[results_df['algorithm'] == algo]['similarity_score']
            algorithm_stats[algo] = {
                'mean': algo_data.mean(),
                'std': algo_data.std(),
                'min': algo_data.min(),
                'max': algo_data.max(),
                'median': algo_data.median()
            }
        
        analysis['algorithm_stats'] = algorithm_stats
        
        return analysis
    
    def visualize_results(self, results_df: pd.DataFrame, 
                         benchmark_metrics: Dict[str, ComparisonMetrics],
                         numerical_analysis: Dict,
                         output_dir: str = "similarity_comparison_results"):
        """可视化比较结果"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # 设置matplotlib中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 1. 性能比较图
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # 计算时间比较
        algorithms = list(benchmark_metrics.keys())
        mean_times = [benchmark_metrics[algo].mean_time for algo in algorithms]
        throughputs = [benchmark_metrics[algo].throughput for algo in algorithms]
        
        bars1 = ax1.bar(algorithms, mean_times, color=['skyblue', 'lightgreen', 'lightcoral'])
        ax1.set_ylabel('平均计算时间 (秒)')
        ax1.set_title('算法计算时间比较')
        ax1.tick_params(axis='x', rotation=45)
        
        # 添加数值标签
        for bar, time_val in zip(bars1, mean_times):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f'{time_val:.3f}s', ha='center', va='bottom')
        
        # 吞吐量比较
        bars2 = ax2.bar(algorithms, throughputs, color=['skyblue', 'lightgreen', 'lightcoral'])
        ax2.set_ylabel('吞吐量 (图片对/秒)')
        ax2.set_title('算法吞吐量比较')
        ax2.tick_params(axis='x', rotation=45)
        
        for bar, throughput in zip(bars2, throughputs):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                    f'{throughput:.2f}', ha='center', va='bottom')
        
        # 2. 相似性分数分布
        for algo in algorithms:
            algo_data = results_df[results_df['algorithm'] == algo]['similarity_score']
            ax3.hist(algo_data, bins=20, alpha=0.7, label=algo)
        
        ax3.set_xlabel('相似性分数')
        ax3.set_ylabel('频次')
        ax3.set_title('相似性分数分布')
        ax3.legend()
        
        # 3. 算法相关性热力图
        if 'correlations' in numerical_analysis:
            corr_data = numerical_analysis['correlations']
            if corr_data:
                corr_matrix = np.zeros((len(algorithms), len(algorithms)))
                for i, algo1 in enumerate(algorithms):
                    for j, algo2 in enumerate(algorithms):
                        if i == j:
                            corr_matrix[i, j] = 1.0
                        else:
                            key1 = f"{algo1}_vs_{algo2}"
                            key2 = f"{algo2}_vs_{algo1}"
                            if key1 in corr_data:
                                corr_matrix[i, j] = corr_data[key1]
                            elif key2 in corr_data:
                                corr_matrix[i, j] = corr_data[key2]
                
                im = ax4.imshow(corr_matrix, cmap='coolwarm', vmin=-1, vmax=1)
                ax4.set_xticks(range(len(algorithms)))
                ax4.set_yticks(range(len(algorithms)))
                ax4.set_xticklabels(algorithms, rotation=45)
                ax4.set_yticklabels(algorithms)
                ax4.set_title('算法相关性矩阵')
                
                # 添加数值标签
                for i in range(len(algorithms)):
                    for j in range(len(algorithms)):
                        ax4.text(j, i, f'{corr_matrix[i, j]:.2f}',
                               ha='center', va='center')
                
                plt.colorbar(im, ax=ax4)
        
        plt.tight_layout()
        plt.savefig(output_path / 'algorithm_comparison.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 4. 详细的相似性分数比较散点图
        if len(algorithms) >= 2:
            fig, axes = plt.subplots(1, len(algorithms)-1, figsize=(5*(len(algorithms)-1), 5))
            if len(algorithms) == 2:
                axes = [axes]
            
            for i, (algo1, algo2) in enumerate(zip(algorithms[:-1], algorithms[1:])):
                # 获取对应的分数
                scores1 = []
                scores2 = []
                pair_results = {}
                
                for _, row in results_df.iterrows():
                    pair_id = row['pair_id']
                    if pair_id not in pair_results:
                        pair_results[pair_id] = {}
                    pair_results[pair_id][row['algorithm']] = row['similarity_score']
                
                for pair_id, scores in pair_results.items():
                    if algo1 in scores and algo2 in scores:
                        scores1.append(scores[algo1])
                        scores2.append(scores[algo2])
                
                if scores1 and scores2:
                    axes[i].scatter(scores1, scores2, alpha=0.6)
                    axes[i].plot([0, 1], [0, 1], 'r--', alpha=0.8)
                    axes[i].set_xlabel(f'{algo1} 相似性分数')
                    axes[i].set_ylabel(f'{algo2} 相似性分数')
                    axes[i].set_title(f'{algo1} vs {algo2}')
                    axes[i].grid(True, alpha=0.3)
                    
                    # 添加相关系数
                    if len(scores1) > 1:
                        corr = np.corrcoef(scores1, scores2)[0, 1]
                        axes[i].text(0.05, 0.95, f'相关系数: {corr:.3f}',
                                   transform=axes[i].transAxes, va='top',
                                   bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            
            plt.tight_layout()
            plt.savefig(output_path / 'similarity_scatter_plots.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        console.print(f"[green]可视化结果已保存到: {output_path}[/green]")
    
    def save_results(self, results_df: pd.DataFrame, 
                    benchmark_metrics: Dict[str, ComparisonMetrics],
                    numerical_analysis: Dict,
                    output_dir: str = "similarity_comparison_results"):
        """保存比较结果"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # 保存详细结果
        results_df.to_csv(output_path / 'detailed_results.csv', index=False)
        
        # 保存基准测试结果
        benchmark_data = {}
        for algo, metrics in benchmark_metrics.items():
            benchmark_data[algo] = {
                'mean_time': metrics.mean_time,
                'std_time': metrics.std_time,
                'min_time': metrics.min_time,
                'max_time': metrics.max_time,
                'median_time': metrics.median_time,
                'throughput': metrics.throughput
            }
        
        with open(output_path / 'benchmark_results.json', 'w', encoding='utf-8') as f:
            json.dump(benchmark_data, f, indent=2, ensure_ascii=False)
        
        # 保存数值分析结果
        with open(output_path / 'numerical_analysis.json', 'w', encoding='utf-8') as f:
            json.dump(numerical_analysis, f, indent=2, ensure_ascii=False)
        
        console.print(f"[green]所有结果已保存到: {output_path}[/green]")
    
    def print_summary(self, benchmark_metrics: Dict[str, ComparisonMetrics],
                     numerical_analysis: Dict):
        """打印结果摘要"""
        # 性能摘要表
        table = Table(title="算法性能比较摘要")
        table.add_column("算法", style="cyan")
        table.add_column("平均时间(秒)", style="magenta")
        table.add_column("吞吐量(对/秒)", style="green")
        table.add_column("设备", style="yellow")
        
        device_map = {
            'PHash_Hamming': 'CPU',
            'SSIM': f'GPU' if self.device == 'cuda' else 'CPU',
            'LPIPS': 'GPU' if torch.cuda.is_available() else 'CPU'
        }
        
        for algo, metrics in benchmark_metrics.items():
            table.add_row(
                algo,
                f"{metrics.mean_time:.3f}",
                f"{metrics.throughput:.2f}",
                device_map.get(algo, 'Unknown')
            )
        
        console.print(table)
        
        # 相关性摘要
        if 'correlations' in numerical_analysis:
            console.print("\n[bold cyan]算法相关性分析:[/bold cyan]")
            for pair, corr in numerical_analysis['correlations'].items():
                console.print(f"  {pair}: {corr:.3f}")
        
        # 统计摘要
        if 'algorithm_stats' in numerical_analysis:
            console.print("\n[bold cyan]相似性分数统计:[/bold cyan]")
            for algo, stats in numerical_analysis['algorithm_stats'].items():
                console.print(f"  {algo}: 均值={stats['mean']:.3f}, 标准差={stats['std']:.3f}")

def get_image_pairs_from_directory(directory: str, max_pairs: int = 50) -> List[Tuple[str, str]]:
    """从目录中获取图像对进行比较"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.avif', '.jxl'}
    
    image_files = []
    for ext in image_extensions:
        image_files.extend(Path(directory).rglob(f'*{ext}'))
        image_files.extend(Path(directory).rglob(f'*{ext.upper()}'))
    
    image_files = [str(f) for f in image_files]
    
    if len(image_files) < 2:
        console.print(f"[red]目录中找到的图像文件不足2个: {len(image_files)}[/red]")
        return []
    
    # 创建图像对
    pairs = []
    for i in range(len(image_files)):
        for j in range(i + 1, len(image_files)):
            pairs.append((image_files[i], image_files[j]))
            if len(pairs) >= max_pairs:
                break
        if len(pairs) >= max_pairs:
            break
    
    console.print(f"[green]从 {len(image_files)} 个图像文件中创建了 {len(pairs)} 个图像对[/green]")
    return pairs

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='图像相似性算法比较工具')
    parser.add_argument('--directory', '-d', type=str, required=True,
                       help='包含图像的目录路径')
    parser.add_argument('--max-pairs', '-p', type=int, default=50,
                       help='最大比较图像对数量 (默认: 50)')
    parser.add_argument('--iterations', '-i', type=int, default=3,
                       help='基准测试迭代次数 (默认: 3)')
    parser.add_argument('--output', '-o', type=str, default='similarity_comparison_results',
                       help='输出目录 (默认: similarity_comparison_results)')
    parser.add_argument('--max-workers', '-w', type=int, default=None,
                       help='最大工作线程数 (默认: CPU核心数)')
    parser.add_argument('--device', type=str, choices=['cpu', 'cuda'], default=None,
                       help='计算设备 (默认: 自动检测)')
    
    args = parser.parse_args()
    
    # 检查目录是否存在
    if not Path(args.directory).exists():
        console.print(f"[red]目录不存在: {args.directory}[/red]")
        return
    
    # 显示开始信息
    console.print(Panel(
        f"[bold green]图像相似性算法比较测试[/bold green]\n"
        f"输入目录: {args.directory}\n"
        f"最大图像对数: {args.max_pairs}\n"
        f"基准测试迭代: {args.iterations}\n"
        f"输出目录: {args.output}",
        title="测试配置"
    ))
    
    # 获取图像对
    image_pairs = get_image_pairs_from_directory(args.directory, args.max_pairs)
    if not image_pairs:
        return
    
    # 初始化比较器
    comparator = ImageSimilarityComparator(
        max_workers=args.max_workers,
        device=args.device
    )
    
    # 运行比较
    console.print("[yellow]开始算法比较...[/yellow]")
    results_df = comparator.batch_compare_images(image_pairs)
    
    # 运行基准测试
    console.print("[yellow]开始基准测试...[/yellow]")
    benchmark_metrics = comparator.benchmark_algorithms(image_pairs, args.iterations)
    
    # 分析数值差异
    console.print("[yellow]分析数值差异...[/yellow]")
    numerical_analysis = comparator.analyze_numerical_differences(results_df)
    
    # 打印摘要
    comparator.print_summary(benchmark_metrics, numerical_analysis)
    
    # 保存结果
    comparator.save_results(results_df, benchmark_metrics, numerical_analysis, args.output)
    
    # 生成可视化
    console.print("[yellow]生成可视化结果...[/yellow]")
    comparator.visualize_results(results_df, benchmark_metrics, numerical_analysis, args.output)
    
    console.print("[bold green]所有测试完成！[/bold green]")

if __name__ == "__main__":
    main()
