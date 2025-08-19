"""输入处理模块"""
import os
import sys
import argparse
import pyperclip
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich import box
from loguru import logger
console = Console()


class InputHandler:
    """输入处理类"""
    
    @staticmethod
    def parse_arguments():
        parser = argparse.ArgumentParser(description='图片文件名清理工具')
        parser.add_argument('--clipboard', '-c', action='store_true', help='从剪贴板读取路径')
        parser.add_argument('--mode', '-m', choices=['image', 'zip'], help='处理模式：image(图片文件) 或 zip(压缩包)')
        parser.add_argument('--verbose', '-v', action='store_true', help='详细日志输出')
        parser.add_argument('--processes', '-p', type=int, default=None, help='进程数量，默认为CPU核心数')
        parser.add_argument('path', nargs='*', help='要处理的文件或目录路径')
        return parser.parse_args()

    @staticmethod
    def get_paths_from_clipboard():
        """从剪贴板读取多行路径"""
        try:
            logger.debug("尝试从剪贴板读取路径")
            clipboard_content = pyperclip.paste()
            if not clipboard_content:
                logger.warning("剪贴板为空")
                console.print('[yellow]⚠️ 剪贴板中没有有效路径[/yellow]')
                return []
            
            paths = [path.strip().strip('"') for path in clipboard_content.splitlines() if path.strip()]
            valid_paths = [path for path in paths if os.path.exists(path)]
            
            if valid_paths:
                logger.info(f"从剪贴板读取到 {len(valid_paths)} 个有效路径")
                console.print(f'[green]✅ 从剪贴板读取到 {len(valid_paths)} 个有效路径[/green]')
            else:
                logger.warning("剪贴板中没有有效路径")
                console.print('[yellow]⚠️ 剪贴板中没有有效路径[/yellow]')
            return valid_paths
        except Exception as e:
            logger.error(f"读取剪贴板时出错: {e}")
            console.print(f'[red]❌ 读取剪贴板时出错: {e}[/red]')
            return []

    @staticmethod
    def get_input_paths(args):
        """获取输入路径"""
        paths = []
        
        # 从命令行参数获取路径
        if args.path:
            paths.extend(args.path)
            logger.info(f"从命令行参数获取到 {len(args.path)} 个路径")
            
        # 从剪贴板获取路径
        if args.clipboard:
            clipboard_paths = InputHandler.get_paths_from_clipboard()
            paths.extend(clipboard_paths)
            
        # 如果没有路径，使用Rich界面提示用户输入
        if not paths:
            paths = InputHandler._interactive_path_input()
                
        valid_paths = [p for p in paths if os.path.exists(p)]
        invalid_count = len(paths) - len(valid_paths)
        
        if invalid_count > 0:
            logger.warning(f"发现 {invalid_count} 个无效路径")
            console.print(f'[yellow]⚠️ 跳过 {invalid_count} 个无效路径[/yellow]')
        
        logger.info(f"最终获得 {len(valid_paths)} 个有效路径")
        return valid_paths

    @staticmethod
    def _interactive_path_input():
        """交互式路径输入"""
        console.print(Panel(
            "[bold blue]请输入要处理的文件夹或压缩包路径[/bold blue]\n"
            "[dim]• 每行一个路径\n"
            "• 支持拖拽文件/文件夹到终端\n"
            "• 输入空行结束[/dim]",
            title="路径输入",
            border_style="blue"
        ))
        
        paths = []
        while True:
            try:
                line = Prompt.ask(f"[cyan]路径 {len(paths)+1}[/cyan]", default="")
                if not line.strip():
                    break
                    
                path = line.strip().strip('"').strip("'")
                if os.path.exists(path):
                    paths.append(path)
                    console.print(f"[green]✅ 已添加: {path}[/green]")
                    logger.debug(f"添加有效路径: {path}")
                else:
                    console.print(f"[red]❌ 路径不存在: {path}[/red]")
                    logger.warning(f"路径不存在: {path}")
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]用户取消输入[/yellow]")
                logger.info("用户取消路径输入")
                break
                
        return paths

    @staticmethod
    def select_processing_mode():
        """选择处理模式"""
        console.print("\n")
        console.print(Panel(
            "[bold green]请选择处理模式[/bold green]",
            title="模式选择",
            border_style="green"
        ))
        
        table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
        table.add_column("选项", style="cyan", width=6)
        table.add_column("模式", style="green", width=15)
        table.add_column("描述", style="white")
        
        table.add_row("1", "图片文件", "处理文件夹中的图片文件，清理文件名")
        table.add_row("2", "压缩包", "处理ZIP压缩包，清理内部图片文件名")
        
        console.print(table)
        
        while True:
            try:
                choice = Prompt.ask(
                    "[bold cyan]请选择处理模式[/bold cyan]",
                    choices=["1", "2"],
                    default="2"
                )
                
                mode = 'image' if choice == '1' else 'zip'
                logger.info(f"用户选择处理模式: {mode}")
                
                # 显示确认信息
                mode_name = "图片文件" if mode == 'image' else "压缩包"
                console.print(f"[green]✅ 已选择: {mode_name} 处理模式[/green]")
                
                return mode
                
            except KeyboardInterrupt:
                console.print("\n[yellow]用户取消选择[/yellow]")
                logger.info("用户取消模式选择")
                sys.exit(0)

    @staticmethod
    def get_retry_input():
        """获取重试输入"""
        console.print("\n")
        console.print(Panel(
            "[yellow]没有有效的输入路径[/yellow]",
            title="提示",
            border_style="yellow"
        ))
        
        if not Confirm.ask("[bold cyan]是否要重新输入路径?[/bold cyan]"):
            console.print("[yellow]退出程序[/yellow]")
            logger.info("用户选择退出程序")
            return None
        
        # 选择输入方式
        method = Prompt.ask(
            "[bold cyan]请选择输入方式[/bold cyan]",
            choices=["manual", "clipboard"],
            default="manual"
        )
        
        if method == "manual":
            return InputHandler._interactive_path_input()
        else:
            return InputHandler.get_paths_from_clipboard()
