#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Rich美化输入处理演示脚本
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.imgfilter.utils.input import InputHandler, console
from rich.panel import Panel
from rich.markdown import Markdown


def demo_clipboard_input():
    """演示剪贴板输入"""
    console.print(Panel(
        "[bold]剪贴板输入演示[/]\n"
        "请先复制一些文本到剪贴板，然后按Enter继续...",
        border_style="green"
    ))
    input()
    
    content = InputHandler.get_clipboard_content()
    if content:
        console.print(Panel(
            f"[bold green]剪贴板内容:[/]\n{content[:200]}{'...' if len(content) > 200 else ''}",
            title="剪贴板内容",
            border_style="blue"
        ))
    else:
        console.print("[yellow]剪贴板为空[/]")


def demo_manual_input():
    """演示手动输入"""
    console.print(Panel(
        "[bold]手动输入演示[/]\n"
        "请输入几行文本，然后按Enter空行结束",
        border_style="green"
    ))
    
    lines = InputHandler.get_manual_input("请输入一些文本（每行一个，输入空行结束）：")
    
    if lines:
        console.print(Panel(
            "\n".join(lines),
            title=f"手动输入内容 ({len(lines)}行)",
            border_style="blue"
        ))


def demo_path_input():
    """演示路径输入"""
    console.print(Panel(
        "[bold]路径输入演示[/]\n"
        "这将演示通过多种方式输入路径",
        border_style="green"
    ))
    
    paths = InputHandler.get_input_paths(
        cli_paths=None,
        use_clipboard=True,
        allow_manual=True
    )
    
    if paths:
        console.print(Panel(
            "\n".join(paths[:10]) + ("\n..." if len(paths) > 10 else ""),
            title=f"输入路径 ({len(paths)}个)",
            border_style="blue"
        ))
        
        # 演示获取所有文件路径
        file_types = {'.jpg', '.png', '.gif', '.jpeg', '.webp'}
        all_files = InputHandler.get_all_file_paths(set(paths), file_types)
        
        # 演示路径分组
        if len(paths) > 1:
            groups = InputHandler.group_input_paths(paths)
            console.print(f"[bold green]路径已分成 {len(groups)} 组[/]")


def main():
    """主函数"""
    console.print(Markdown("""
    # Rich美化输入处理演示
    
    这个脚本演示了使用Rich库美化后的输入处理功能，包括：
    
    * 剪贴板输入
    * 手动输入
    * 多种路径输入方式
    * 文件扫描与统计
    * 路径分组
    """))
    
    options = [
        ("1", "剪贴板输入演示"),
        ("2", "手动输入演示"),
        ("3", "路径输入演示"),
        ("4", "退出")
    ]
    
    while True:
        console.rule("[bold cyan]请选择演示功能[/]", style="cyan")
        for key, desc in options:
            console.print(f"[cyan]{key}[/]. {desc}")
            
        choice = console.input("[bold yellow]请选择 (1-4): [/]")
        
        if choice == "1":
            demo_clipboard_input()
        elif choice == "2":
            demo_manual_input()
        elif choice == "3":
            demo_path_input()
        elif choice == "4":
            console.print("[bold green]演示结束，谢谢使用！[/]")
            break
        else:
            console.print("[bold red]无效选择，请重试[/]")
            
        console.print("\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]演示已中断[/]")
    except Exception as e:
        console.print(f"[bold red]发生错误: {e}[/]") 