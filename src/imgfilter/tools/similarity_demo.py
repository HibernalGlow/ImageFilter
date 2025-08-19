"""
简化的图像相似性算法比较演示脚本
适用于快速测试和验证

功能：
- 简化的界面
- 预设的测试配置
- 快速结果展示
"""

import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

from imgfilter.tools.similarity_comparison import ImageSimilarityComparator, get_image_pairs_from_directory

console = Console()

def select_directory():
    """使用GUI选择目录"""
    root = tk.Tk()
    root.withdraw()
    directory = filedialog.askdirectory(title="选择包含图像的目录")
    root.destroy()
    return directory

def quick_demo():
    """快速演示模式"""
    console.print(Panel(
        "[bold cyan]图像相似性算法比较 - 快速演示[/bold cyan]\n"
        "本工具将比较三种图像相似性算法:\n"
        "• PHash + 汉明距离 (CPU)\n"
        "• SSIM (GPU加速)\n"
        "• LPIPS (GPU加速)\n\n"
        "请选择包含图像文件的目录进行测试",
        title="欢迎"
    ))
    
    # 选择目录
    directory = select_directory()
    if not directory:
        console.print("[red]未选择目录，退出程序[/red]")
        return
    
    console.print(f"[green]选择的目录: {directory}[/green]")
    
    # 获取用户配置
    max_pairs = IntPrompt.ask("最大比较图像对数量", default=20)
    iterations = IntPrompt.ask("基准测试迭代次数", default=2)
    
    # 确认开始
    if not Confirm.ask("开始比较测试?"):
        return
    
    # 运行比较
    try:
        # 获取图像对
        image_pairs = get_image_pairs_from_directory(directory, max_pairs)
        if not image_pairs:
            return
        
        # 初始化比较器
        comparator = ImageSimilarityComparator()
        
        # 运行简化测试
        console.print("[yellow]正在运行算法比较...[/yellow]")
        results_df = comparator.batch_compare_images(image_pairs[:min(5, len(image_pairs))])  # 先测试少量图像
        
        if not results_df.empty:
            # 显示快速结果
            console.print("\n[bold green]快速测试结果:[/bold green]")
            
            # 按算法分组显示
            for algo in results_df['algorithm'].unique():
                algo_data = results_df[results_df['algorithm'] == algo]
                avg_time = algo_data['computation_time'].mean()
                avg_score = algo_data['similarity_score'].mean()
                console.print(f"  {algo}: 平均时间={avg_time:.3f}秒, 平均相似度={avg_score:.3f}")
            
            # 询问是否运行完整测试
            if Confirm.ask("运行完整的基准测试和分析?"):
                console.print("[yellow]运行完整测试...[/yellow]")
                
                # 完整比较
                results_df = comparator.batch_compare_images(image_pairs)
                benchmark_metrics = comparator.benchmark_algorithms(image_pairs, iterations)
                numerical_analysis = comparator.analyze_numerical_differences(results_df)
                
                # 打印摘要
                comparator.print_summary(benchmark_metrics, numerical_analysis)
                
                # 保存结果
                output_dir = "demo_results"
                comparator.save_results(results_df, benchmark_metrics, numerical_analysis, output_dir)
                comparator.visualize_results(results_df, benchmark_metrics, numerical_analysis, output_dir)
                
                console.print(f"[bold green]完整测试结果已保存到: {output_dir}[/bold green]")
        
    except Exception as e:
        console.print(f"[red]测试过程中发生错误: {e}[/red]")
        import traceback
        traceback.print_exc()

def interactive_mode():
    """交互模式"""
    console.print(Panel(
        "[bold yellow]交互模式[/bold yellow]\n"
        "您可以自定义所有参数",
        title="高级配置"
    ))
    
    # 获取所有参数
    directory = select_directory()
    if not directory:
        console.print("[red]未选择目录，退出程序[/red]")
        return
    
    max_pairs = IntPrompt.ask("最大比较图像对数量", default=50)
    iterations = IntPrompt.ask("基准测试迭代次数", default=3)
    max_workers = IntPrompt.ask("最大工作线程数 (0=自动)", default=0) or None
    
    device_choice = Prompt.ask(
        "选择计算设备", 
        choices=["auto", "cpu", "cuda"], 
        default="auto"
    )
    device = None if device_choice == "auto" else device_choice
    
    output_dir = Prompt.ask("输出目录", default="similarity_comparison_results")
    
    # 运行完整测试
    try:
        image_pairs = get_image_pairs_from_directory(directory, max_pairs)
        if not image_pairs:
            return
        
        comparator = ImageSimilarityComparator(max_workers=max_workers, device=device)
        
        results_df = comparator.batch_compare_images(image_pairs)
        benchmark_metrics = comparator.benchmark_algorithms(image_pairs, iterations)
        numerical_analysis = comparator.analyze_numerical_differences(results_df)
        
        comparator.print_summary(benchmark_metrics, numerical_analysis)
        comparator.save_results(results_df, benchmark_metrics, numerical_analysis, output_dir)
        comparator.visualize_results(results_df, benchmark_metrics, numerical_analysis, output_dir)
        
        console.print(f"[bold green]测试完成! 结果保存在: {output_dir}[/bold green]")
        
    except Exception as e:
        console.print(f"[red]测试过程中发生错误: {e}[/red]")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    console.print(Panel(
        "[bold blue]图像相似性算法比较工具[/bold blue]\n"
        "比较PHash、SSIM和LPIPS三种算法的性能和精度",
        title="图像相似性算法比较"
    ))
    
    mode = Prompt.ask(
        "选择运行模式",
        choices=["quick", "interactive"],
        default="quick"
    )
    
    if mode == "quick":
        quick_demo()
    else:
        interactive_mode()

if __name__ == "__main__":
    main()
