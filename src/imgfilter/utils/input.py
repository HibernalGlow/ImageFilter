import os
from typing import List, Set, Dict, Optional, Tuple
import pyperclip
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any
from loguru import logger
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich import print as rprint
from rich.progress import Progress, SpinnerColumn, TextColumn

# 全局变量定义
SUPPORTED_ARCHIVE_FORMATS = ['.zip', '.rar', '.7z', '.cbz', '.cbr']
# 创建Rich控制台对象
console = Console()

class InputHandler:
    """通用输入处理类，支持Rich美化和快捷输入"""
    
    @staticmethod
    def get_clipboard_content() -> str:
        """
        获取剪贴板内容
        
        Returns:
            str: 剪贴板内容
        """
        try:
            with console.status("[bold green]正在读取剪贴板...", spinner="dots"):
                content = pyperclip.paste()
            return content
        except Exception as e:
            console.print(f"[bold red]从剪贴板读取失败: {e}[/]")
            logger.error(f"[#file_ops]从剪贴板读取失败: {e}")
            return ""
            
    @staticmethod
    def get_manual_input(prompt: str = "请输入内容（输入空行结束）：") -> List[str]:
        """
        获取用户手动输入的多行内容，支持Rich美化
        
        Args:
            prompt: 提示信息
            
        Returns:
            List[str]: 输入的内容列表
        """
        console.print(Panel(prompt, style="bold green"))
        lines = []
        line_number = 1
        
        while True:
            try:
                line = Prompt.ask(f"[cyan]{line_number}[/]").strip()
                if not line:
                    break
                lines.append(line)
                line_number += 1
            except KeyboardInterrupt:
                console.print("\n[yellow]输入已取消[/]")
                break
                
        if lines:
            console.print(f"[green]已输入 {len(lines)} 行内容[/]")
        return lines
        
    @staticmethod
    def path_normalizer(path: str) -> str:
        """
        规范化路径，处理引号和转义字符
        
        Args:
            path: 原始路径
            
        Returns:
            str: 规范化后的路径
        """
        # 移除首尾的引号
        path = path.strip('"\'')
        # 处理转义字符
        path = path.replace('\\\\', '\\')
        # 转换为绝对路径
        return os.path.abspath(path)
    
    @staticmethod
    def get_input_paths(
        cli_paths: Optional[List[str]] = None,
        use_clipboard: bool = True,
        allow_manual: bool = True,
        path_validator: Optional[callable] = os.path.exists,
    ) -> List[str]:
        """
        获取输入路径，支持多种输入方式，使用Rich美化
        
        Args:
            cli_paths: 命令行参数中的路径列表
            use_clipboard: 是否使用剪贴板内容
            allow_manual: 是否允许手动输入
            path_validator: 路径验证函数
            
        Returns:
            List[str]: 有效的路径列表
        """
        paths = []
        
        # 处理命令行参数
        if cli_paths:
            console.print("[bold blue]从命令行参数获取路径...[/]")
            paths.extend(cli_paths)
            
        # 处理剪贴板内容
        if use_clipboard and (not paths or use_clipboard):
            clipboard_content = InputHandler.get_clipboard_content()
            if clipboard_content:
                clipboard_paths = [
                    line.strip()
                    for line in clipboard_content.splitlines()
                    if line.strip()
                ]
                paths.extend(clipboard_paths)
                console.print(f"[bold green]从剪贴板读取了 {len(clipboard_paths)} 个路径[/]")
                logger.info(f"从剪贴板读取了 {len(clipboard_paths)} 个路径")
                
        # 快捷输入选项
        if not paths and allow_manual:
            options = [
                ("1", "手动输入路径"),
                ("2", "选择当前目录"),
                ("3", "浏览选择文件/文件夹")
            ]
            
            table = Table(title="输入选项")
            table.add_column("选项", style="cyan")
            table.add_column("描述", style="green")
            
            for key, desc in options:
                table.add_row(key, desc)
                
            console.print(table)
            choice = Prompt.ask("请选择输入方式", choices=["1", "2", "3"], default="1")
            
            if choice == "1":
                # 手动输入
                manual_paths = InputHandler.get_manual_input("请输入路径（每行一个，输入空行结束）：")
                paths.extend(manual_paths)
            elif choice == "2":
                # 当前目录
                current_dir = os.getcwd()
                console.print(f"[bold green]已选择当前目录: [/][yellow]{current_dir}[/]")
                paths.append(current_dir)
            elif choice == "3":
                # 使用系统文件选择器
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    
                    root = tk.Tk()
                    root.withdraw()
                    
                    console.print("[bold blue]请在弹出窗口中选择文件或文件夹...[/]")
                    
                    if Confirm.ask("是否选择文件夹？", default=True):
                        selected_path = filedialog.askdirectory(title="选择文件夹")
                    else:
                        selected_path = filedialog.askopenfilename(title="选择文件")
                        
                    if selected_path:
                        console.print(f"[bold green]已选择: [/][yellow]{selected_path}[/]")
                        paths.append(selected_path)
                    else:
                        console.print("[yellow]未选择任何文件或文件夹[/]")
                except Exception as e:
                    console.print(f"[bold red]文件选择器出错: {e}[/]")
                    logger.error(f"[#file_ops]文件选择器出错: {e}")
                    # 回退到手动输入
                    manual_paths = InputHandler.get_manual_input("请输入路径（每行一个，输入空行结束）：")
                    paths.extend(manual_paths)
            
        # 规范化路径
        paths = [InputHandler.path_normalizer(p) for p in paths]
            
        # 验证路径
        if path_validator:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]验证路径中..."),
                console=console
            ) as progress:
                task = progress.add_task("验证", total=len(paths))
                
                valid_paths = []
                invalid_paths = []
                
                for p in paths:
                    if path_validator(p):
                        valid_paths.append(p)
                    else:
                        invalid_paths.append(p)
                    progress.update(task, advance=1)
            
            # 显示验证结果
            if invalid_paths:
                console.print(f"[bold yellow]警告: {len(invalid_paths)} 个路径无效[/]")
                for p in invalid_paths:
                    console.print(f"  [red]✗[/] {p}")
                    logger.warning(f"[#file_ops]路径无效: {p}")
                    
            console.print(f"[bold green]有效路径: {len(valid_paths)} 个[/]")
            return valid_paths
            
        return paths

    @staticmethod
    def get_all_file_paths(paths: Set[str], file_types: Optional[Set[str]] = None) -> List[str]:
        """将包含文件夹和文件路径的集合转换为完整的文件路径列表，使用Rich显示进度
        
        Args:
            paths: 包含文件夹和文件路径的集合
            file_types: 要筛选的文件类型集合，如果为None则返回所有文件
            
        Returns:
            List[str]: 完整的文件路径列表
        """
        all_files = []
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]扫描文件中..."),
                console=console
            ) as progress:
                task = progress.add_task("扫描", total=len(paths))
                
                for path in paths:
                    if not os.path.exists(path):
                        console.print(f"[yellow]警告: 路径不存在: [/][red]{path}[/]")
                        logger.warning(f"[#file_ops]路径不存在: {path}")
                        progress.update(task, advance=1)
                        continue
                        
                    if os.path.isfile(path):
                        if file_types is None or any(path.lower().endswith(ext) for ext in file_types):
                            all_files.append(path)
                    elif os.path.isdir(path):
                        dir_files = []
                        for root, _, files in os.walk(path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                if file_types is None or any(file_path.lower().endswith(ext) for ext in file_types):
                                    dir_files.append(file_path)
                        all_files.extend(dir_files)
                        console.print(f"[green]目录 {path} 中找到 {len(dir_files)} 个文件[/]")
                    
                    progress.update(task, advance=1)
                                
        except Exception as e:
            console.print(f"[bold red]获取文件路径时出错: {e}[/]")
            logger.error(f"[#file_ops]获取文件路径时出错: {e}")
            
        # 显示结果摘要
        if all_files:
            console.print(f"[bold green]共找到 {len(all_files)} 个文件[/]")
            if file_types:
                type_counts = {}
                for file in all_files:
                    ext = os.path.splitext(file)[1].lower()
                    type_counts[ext] = type_counts.get(ext, 0) + 1
                
                table = Table(title="文件类型统计")
                table.add_column("类型", style="cyan")
                table.add_column("数量", style="green", justify="right")
                
                for ext, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                    table.add_row(ext, str(count))
                
                console.print(table)
            
        return all_files
        
    @staticmethod
    def group_input_paths(paths: List[str]) -> List[Set[str]]:
        """将输入路径分组，使用Rich显示结果
        
        规则:
        1. 每个目录下的压缩包作为一组(按路径排序)
        2. 连续的压缩包文件会被分到同一组
        3. 不连续的压缩包（中间有非压缩包或目录）会被分成不同组
        
        Args:
            paths: 输入路径列表
            
        Returns:
            List[Set[str]]: 分组后的路径集合列表
        """
        with console.status("[bold green]正在分组路径...", spinner="dots"):
            groups = []
            sorted_paths = sorted(paths)
            
            # 处理目录
            for path in [p for p in sorted_paths if os.path.isdir(p)]:
                archives = []
                for root, _, files in os.walk(Path(path)):
                    archives.extend([os.path.join(root, f) for f in files 
                                if Path(f).suffix.lower() in SUPPORTED_ARCHIVE_FORMATS])
                if archives:
                    groups.append(set(sorted(archives)))
            
            # 处理文件
            file_paths = [p for p in sorted_paths if not os.path.isdir(p)]
            current = []
            is_prev_archive = False
            
            for path in file_paths:
                is_archive = Path(path).suffix.lower() in SUPPORTED_ARCHIVE_FORMATS
                
                # 当前是压缩包但上一个不是，开始新序列
                if is_archive and not is_prev_archive:
                    if current:
                        groups.append(set(current))
                        current = []
                    current.append(path)
                # 当前是压缩包且上一个也是，继续序列
                elif is_archive and is_prev_archive:
                    current.append(path)
                    
                is_prev_archive = is_archive
            
            # 添加最后一个序列
            if current:
                groups.append(set(current))
        
        # 显示分组结果
        console.print(f"[bold green]共分成 {len(groups)} 组[/]")
        for i, group in enumerate(groups, 1):
            console.print(f"[cyan]组 {i}[/]: [yellow]{len(group)}[/] 个文件")
            
        return groups