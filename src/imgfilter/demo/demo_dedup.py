import os
import time
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import List, Dict, Tuple, Optional
import mmap
from PIL import Image
import pillow_avif
import pillow_jxl 
import imagehash
import io
import argparse
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.markdown import Markdown
import tkinter as tk
from tkinter import filedialog

# 初始化Rich控制台
console = Console()

def calculate_phash(img_data) -> str:
    """计算感知哈希值，模拟实际哈希计算的CPU消耗"""
    try:
        img = Image.open(io.BytesIO(img_data))
        hash_obj = imagehash.phash(img)
        return str(hash_obj)
    except Exception as e:
        console.print(f"[red]计算哈希值失败: {e}[/red]")
        return None

def process_single_image(img_path: str) -> Tuple[str, Optional[str]]:
    """处理单张图片（用于单线程/多线程/多进程的工作函数）"""
    try:
        # 读取图片数据
        with open(img_path, 'rb') as f:
            img_data = f.read()
        
        # 计算哈希值
        hash_value = calculate_phash(img_data)
        return img_path, hash_value
    except Exception as e:
        # 不在子进程中打印，以避免控制台混乱
        return img_path, None

def single_thread_process(images: List[str], progress=None, task_id=None) -> Dict[str, str]:
    """单线程处理"""
    results = {}
    total = len(images)
    
    for i, img_path in enumerate(images):
        path, hash_value = process_single_image(img_path)
        if hash_value:
            results[path] = hash_value
        
        # 更新进度条（如果存在）
        if progress and task_id is not None:
            progress.update(task_id, completed=i+1, total=total)
    
    return results

def multi_thread_process(images: List[str], max_workers: int, progress=None, task_id=None) -> Dict[str, str]:
    """多线程处理"""
    results = {}
    total = len(images)
    completed = 0
    
    def update_progress(future):
        nonlocal completed
        completed += 1
        if progress and task_id is not None:
            progress.update(task_id, completed=completed, total=total)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交任务并添加回调以更新进度
        futures = []
        for img in images:
            future = executor.submit(process_single_image, img)
            future.add_done_callback(update_progress)
            futures.append(future)
        
        # 收集结果
        for future in futures:
            path, hash_value = future.result()
            if hash_value:
                results[path] = hash_value
    
    return results

def worker_init():
    """工作进程初始化函数"""
    # 禁用在工作进程中的PIL调试输出
    import logging
    logging.getLogger('PIL').setLevel(logging.WARNING)

def multi_process_process(images: List[str], max_workers: int, progress=None, task_id=None) -> Dict[str, str]:
    """多进程处理"""
    results = {}
    total = len(images)
    completed = 0
    
    # 由于多进程中无法直接更新共享进度条，我们使用主进程中的回调函数
    def update_progress(future):
        nonlocal completed
        completed += 1
        if progress and task_id is not None:
            progress.update(task_id, completed=completed, total=total)
    
    with ProcessPoolExecutor(max_workers=max_workers, initializer=worker_init) as executor:
        # 提交任务并添加回调以更新进度
        futures = []
        for img in images:
            future = executor.submit(process_single_image, img)
            future.add_done_callback(update_progress)
            futures.append(future)
        
        # 收集结果
        for future in futures:
            path, hash_value = future.result()
            if hash_value:
                results[path] = hash_value
    
    return results

def browse_directory():
    """使用文件对话框选择目录"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    folder_path = filedialog.askdirectory(title="选择包含图片的目录")
    root.destroy()
    return folder_path if folder_path else None

def run_benchmark(image_dir: str, max_workers: int = None, iterations: int = 3):
    """运行基准测试"""
    # 设置默认工作线程/进程数
    if not max_workers:
        max_workers = multiprocessing.cpu_count()
    
    # 获取图片文件列表
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    ) as progress:
        scan_task = progress.add_task("[yellow]扫描图片文件...", total=None)
        
        image_files = []
        for root, _, files in os.walk(image_dir):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.avif', '.jxl')):
                    image_files.append(os.path.join(root, file))
        
        progress.update(scan_task, completed=1, total=1)
    
    if not image_files:
        console.print(Panel(f"[bold red]目录中没有找到图片文件: {image_dir}[/bold red]", 
                           title="错误", border_style="red"))
        return
    
    console.print(Panel(
        f"[bold green]找到 {len(image_files)} 张图片进行测试\n"
        f"将使用 {max_workers} 个工作线程/进程\n"
        f"每种方法将运行 {iterations} 次迭代[/bold green]", 
        title="测试配置", border_style="green"
    ))
    
    # 运行多次计算平均值
    single_times = []
    thread_times = []
    process_times = []
    
    # 创建带有详细信息的进度条
    for i in range(iterations):
        console.rule(f"[bold]运行迭代 {i+1}/{iterations}[/bold]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            # 单线程测试
            console.print("[yellow]运行单线程测试...[/yellow]")
            single_task = progress.add_task("[green]单线程处理", total=len(image_files))
            start_time = time.time()
            results_single = single_thread_process(image_files, progress, single_task)
            end_time = time.time()
            single_time = end_time - start_time
            single_times.append(single_time)
            console.print(f"[green]单线程完成: {single_time:.2f}秒, 处理了 {len(results_single)}/{len(image_files)} 张图片[/green]")
            
            # 多线程测试
            console.print("[yellow]运行多线程测试...[/yellow]")
            thread_task = progress.add_task("[blue]多线程处理", total=len(image_files))
            start_time = time.time()
            results_thread = multi_thread_process(image_files, max_workers, progress, thread_task)
            end_time = time.time()
            thread_time = end_time - start_time
            thread_times.append(thread_time)
            console.print(f"[blue]多线程完成: {thread_time:.2f}秒, 处理了 {len(results_thread)}/{len(image_files)} 张图片[/blue]")
            
            # 多进程测试
            console.print("[yellow]运行多进程测试...[/yellow]")
            process_task = progress.add_task("[magenta]多进程处理", total=len(image_files))
            start_time = time.time()
            results_process = multi_process_process(image_files, max_workers, progress, process_task)
            end_time = time.time()
            process_time = end_time - start_time
            process_times.append(process_time)
            console.print(f"[magenta]多进程完成: {process_time:.2f}秒, 处理了 {len(results_process)}/{len(image_files)} 张图片[/magenta]")
    
    # 计算平均时间
    avg_single = sum(single_times) / len(single_times)
    avg_thread = sum(thread_times) / len(thread_times)
    avg_process = sum(process_times) / len(process_times)
    
    # 创建结果表格
    table = Table(title="性能测试结果摘要")
    
    table.add_column("方法", style="cyan", no_wrap=True)
    table.add_column("平均时间(秒)", style="magenta")
    table.add_column("加速比", style="green")
    table.add_column("每次迭代时间(秒)", style="blue")
    
    table.add_row(
        "单线程", 
        f"{avg_single:.2f}", 
        "1.00x", 
        ", ".join([f"{t:.2f}" for t in single_times])
    )
    
    table.add_row(
        "多线程", 
        f"{avg_thread:.2f}", 
        f"{avg_single/avg_thread:.2f}x", 
        ", ".join([f"{t:.2f}" for t in thread_times])
    )
    
    table.add_row(
        "多进程", 
        f"{avg_process:.2f}", 
        f"{avg_single/avg_process:.2f}x", 
        ", ".join([f"{t:.2f}" for t in process_times])
    )
    
    console.print(table)
    
    # 确定最快的方法
    fastest = min(avg_single, avg_thread, avg_process)
    conclusion = ""
    
    if fastest == avg_single:
        conclusion = "[bold red]单线程处理最快[/bold red]"
    elif fastest == avg_thread:
        conclusion = "[bold blue]多线程处理最快[/bold blue]"
    else:
        conclusion = "[bold green]多进程处理最快[/bold green]"
    
    # 提供改进建议
    recommendation = ""
    if avg_process < avg_thread:
        recommendation = """
对于图片哈希计算，多进程实现是更好的选择：

- 哈希计算是CPU密集型操作，多进程可以绕过Python的GIL限制
- 多进程能够真正并行利用多核处理器
- 对于这种计算密集型任务，进程间通信开销被计算速度提升所抵消
        """
    else:
        recommendation = """
对于图片哈希计算，多线程实现表现更好：

- 虽然受到GIL限制，但IO操作(读取图片)占比较高
- 线程间共享内存，没有进程切换和通信开销
- 对于IO密集型任务，线程池通常是更好的选择
        """
    
    console.print(Panel(conclusion, title="结论", border_style="yellow"))
    console.print(Panel(Markdown(recommendation), title="建议", border_style="cyan"))
    
    # 生成性能可视化报告
    console.print("\n[bold yellow]生成比较图表...[/bold yellow]")
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        
        methods = ['单线程', '多线程', '多进程']
        avg_times = [avg_single, avg_thread, avg_process]
        colors = ['#ff9999', '#66b3ff', '#99ff99']
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # 条形图
        ax1.bar(methods, avg_times, color=colors)
        ax1.set_ylabel('平均执行时间(秒)')
        ax1.set_title('执行时间比较')
        
        # 为每个条形添加数值标签
        for i, v in enumerate(avg_times):
            ax1.text(i, v + 0.1, f'{v:.2f}s', ha='center')
        
        # 加速比折线图
        speedups = [1, avg_single/avg_thread, avg_single/avg_process]
        ax2.plot(methods, speedups, 'o-', color='red', linewidth=2)
        ax2.set_ylabel('相对于单线程的加速比')
        ax2.set_title('加速比比较')
        
        # 为每个点添加数值标签
        for i, v in enumerate(speedups):
            ax2.text(i, v + 0.1, f'{v:.2f}x', ha='center')
        
        plt.tight_layout()
        
        # 保存图表
        report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"performance_report_{time.strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(report_path)
        
        console.print(f"[green]图表已保存到: {report_path}[/green]")
        
        # 显示图表（可选）
        if Confirm.ask("是否显示性能比较图表?"):
            plt.show()
        
    except ImportError:
        console.print("[yellow]提示: 安装 matplotlib 可以生成图形化报告: pip install matplotlib[/yellow]")

def interactive_mode():
    """交互式模式启动测试"""
    console.print(Panel.fit(
        "[bold cyan]图片哈希计算性能测试工具[/bold cyan]\n\n"
        "本工具将比较单线程、多线程和多进程三种方式计算图片哈希值的性能差异。\n"
        "测试结果将帮助您选择最适合的并行处理方式。",
        title="欢迎", border_style="blue"
    ))
    
    # 询问图片目录
    console.print("[yellow]请选择包含图片的目录:[/yellow]")
    console.print("1. 使用文件浏览器选择")
    console.print("2. 手动输入路径")
    choice = IntPrompt.ask("请选择", choices=["1", "2"], default=1)
    
    if choice == 1:
        console.print("[yellow]正在打开文件浏览器...[/yellow]")
        image_dir = browse_directory()
        if not image_dir:
            console.print("[bold red]未选择目录，退出程序[/bold red]")
            return
        console.print(f"[green]已选择目录: {image_dir}[/green]")
    else:
        image_dir = Prompt.ask("请输入图片目录路径")
        if not os.path.exists(image_dir):
            console.print(f"[bold red]目录不存在: {image_dir}[/bold red]")
            return
        console.print(f"[green]已确认目录: {image_dir}[/green]")
    cpu_count = os.cpu_count()
    # 显示CPU核心数提示信息
    console.print(f"[blue]推荐值: CPU核心数 ({cpu_count})[/blue]")
    max_workers = IntPrompt.ask(
        f"工作线程/进程数量", 
        default=cpu_count, 
        show_default=True
    )
    
    # 显示迭代次数提示信息
    console.print("[blue]更多迭代可提高结果准确性，但需要更长时间[/blue]")
    iterations = IntPrompt.ask(
        "测试迭代次数", 
        default=3, 
        show_default=True
    )
    
    # 运行测试
    run_benchmark(image_dir, max_workers, iterations)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="比较单线程、多线程和多进程处理图片哈希计算的性能")
    parser.add_argument("--dir", "-d", help="包含图片的目录路径")
    parser.add_argument("--workers", "-w", type=int, default=None, help="工作线程/进程数量")
    parser.add_argument("--iterations", "-i", type=int, default=3, help="每种方法运行的迭代次数")
    parser.add_argument("--interactive", "-int", action="store_true", help="启用交互式模式")
    
    args = parser.parse_args()
    
    # 优先使用交互式模式，其次使用命令行参数
    if args.interactive or not args.dir:
        interactive_mode()
    else:
        run_benchmark(args.dir, args.workers, args.iterations)