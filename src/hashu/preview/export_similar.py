# -*- coding: utf-8 -*-
"""
相似图片导出工具演示脚本
使用说明：
1. 运行 size_preview.py 生成哈希对比结果
2. 运行此脚本导出指定阈值下的相似组
3. 检查生成的删除列表并执行删除操作
"""

from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
import sys
import os

# 添加父目录到Python路径
sys.path.append(str(Path(__file__).parent))

from size_preview import export_similar_groups, benchmark_phash_sizes

console = Console()

def main():
    console.print("[bold blue]相似图片导出工具[/bold blue]")
    console.print("此工具可以根据指定的汉明距离阈值导出相似图片组")
    console.print("并生成保留文件列表和删除文件列表\n")
    
    # 选择操作模式
    mode = Prompt.ask(
        "请选择操作模式",
        choices=["1", "2"],
        default="1"
    )
    
    if mode == "1":
        console.print("\n[cyan]模式1: 重新计算并导出[/cyan]")
        run_full_analysis()
    else:
        console.print("\n[cyan]模式2: 从已有结果导出[/cyan]")
        console.print("[yellow]注意：此模式需要先运行过完整分析[/yellow]")
        run_quick_export()

def run_full_analysis():
    """运行完整的哈希分析并导出相似组"""
    # 输入参数
    folder = Prompt.ask("请输入图片文件夹路径", default="E:\\1Hub\\EH\\2EHV\\test")
    hash_size = int(Prompt.ask("请输入哈希尺寸", default="16"))
    threshold = int(Prompt.ask("请输入汉明距离阈值", default="5"))
    
    console.print(f"\n[bold]开始分析...[/bold]")
    console.print(f"文件夹: [cyan]{folder}[/cyan]")
    console.print(f"哈希尺寸: [cyan]{hash_size}[/cyan]")
    console.print(f"阈值: [cyan]{threshold}[/cyan]")
    
    # 运行分析
    results, image_files = benchmark_phash_sizes(folder, hash_sizes=(hash_size,))
    
    # 导出相似组
    export_result = export_similar_groups(
        results, 
        threshold, 
        output_dir=folder,
        hash_size=hash_size
    )
    
    if export_result:
        show_export_summary(export_result)

def run_quick_export():
    """从已有结果快速导出"""
    console.print("[yellow]此功能需要您提供之前分析的结果数据[/yellow]")
    console.print("如果您还没有运行过分析，请选择模式1")

def show_export_summary(export_result):
    """显示导出结果摘要"""
    if not export_result:
        console.print("[red]导出失败[/red]")
        return
    
    keep_files = export_result["keep_files"]
    delete_files = export_result["delete_files"]
    groups = export_result["groups"]
    
    console.print(f"\n[bold green]导出完成！[/bold green]")
    
    # 创建摘要表格
    summary_table = Table(title="导出结果摘要")
    summary_table.add_column("项目", style="cyan")
    summary_table.add_column("数量", style="green", justify="right")
    summary_table.add_column("说明", style="yellow")
    
    summary_table.add_row("相似组", str(len(groups)), "发现的相似图片组数量")
    summary_table.add_row("保留文件", str(len(keep_files)), "每组中保留的文件（按名称排序第一个）")
    summary_table.add_row("删除文件", str(len(delete_files)), "建议删除的重复文件")
    
    console.print(summary_table)
    
    # 显示一些具体的组例子
    console.print(f"\n[bold]前几个相似组示例:[/bold]")
    for i, group in enumerate(groups[:3], 1):
        sorted_files = sorted(list(group), key=lambda x: Path(x).name.lower())
        keep_file = Path(sorted_files[0]).name
        delete_count = len(sorted_files) - 1
        console.print(f"  组 {i}: 保留 [green]{keep_file}[/green], 删除 {delete_count} 个相似文件")
    
    if len(groups) > 3:
        console.print(f"  ... 还有 {len(groups) - 3} 个组")
    
    console.print(f"\n[bold yellow]下一步操作建议:[/bold yellow]")
    console.print("1. 检查生成的文件列表，确认删除的文件确实是重复的")
    console.print("2. 如果确认无误，可以运行生成的 .bat 脚本进行批量删除")
    console.print("3. 或者手动删除 delete_files_*.txt 中列出的文件")
    
    # 显示生成的文件路径
    export_files = export_result["export_files"]
    console.print(f"\n[bold]生成的文件:[/bold]")
    for desc, path in [
        ("详细信息", export_files["json"]),
        ("保留列表", export_files["keep_list"]), 
        ("删除列表", export_files["delete_list"]),
        ("删除脚本", export_files["batch_script"])
    ]:
        console.print(f"  {desc}: [cyan]{path}[/cyan]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]用户取消操作[/yellow]")
    except Exception as e:
        console.print(f"\n[red]发生错误: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")
