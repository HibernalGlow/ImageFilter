from __future__ import annotations
from typing import List, Optional
import sys
from pathlib import Path
import subprocess
import typer
from loguru import logger
from .run import process_directory, ReportGenerator
from .core.utils import process_paths, get_paths_from_clipboard

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    help="rawfilter 压缩包重复与版本裁剪工具 (无参数默认尝试启动 lata TUI)"
)

def _resolve_paths(paths: Optional[List[Path]], clipboard: bool) -> List[str]:
    collected: List[str] = []
    if clipboard:
        collected.extend(get_paths_from_clipboard())
    if paths:
        collected.extend(str(p) for p in paths)
    if not collected:
        # 交互式输入
        typer.echo("请输入要处理的路径（每行一个，空行结束）：", err=True)
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    break
                collected.append(line)
        except KeyboardInterrupt:
            typer.echo("用户取消输入", err=True)
    return collected

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    paths: Optional[List[Path]] = typer.Option(None, "--paths", "-p", help="要处理的目录路径，可多次指定"),
    clipboard: bool = typer.Option(False, "--clipboard", "-c", help="从剪贴板读取路径"),
    sample_count: int = typer.Option(3, "--sample-count", "-s", help="每个压缩包抽取的图片样本数量 (当前未直接使用占位)"),
    create_shortcuts: bool = typer.Option(False, "--create-shortcuts", help="创建快捷方式而不是移动文件"),
    enable_multi_main: bool = typer.Option(False, "--enable-multi-main", help="为每个 multi 组创建主文件副本"),
    name_only_mode: bool = typer.Option(False, "--name-only-mode", help="仅名称模式：仅通过文件名判断，不读内部，不添加指标标记"),
    trash_only: bool = typer.Option(False, "--trash-only", help="仅执行裁剪并把其余版本移入 trash，不创建/移动到 multi"),
    report: Optional[str] = typer.Option(None, "--report", help="指定报告文件名 (默认自动生成)"),
) -> None:
    """主命令：执行目录扫描、分组、裁剪与移动。

    invoke_without_command=True: 若无子命令且无参数，则尝试启动 lata。
    """
    # 若用户调用了子命令 (如 tui) 则不执行主逻辑
    if ctx.invoked_subcommand is not None:
        return

    # 无任何额外参数且未指定路径/剪贴板 -> 先尝试启动 lata
    raw_args = [a for a in sys.argv[1:] if a.strip()]
    no_user_args = len(raw_args) == 0 and not paths and not clipboard
    if no_user_args:
        try:
            script_dir = Path(__file__).parent
            result = subprocess.run("lata", cwd=script_dir)
            if result.returncode == 0:
                raise typer.Exit(code=0)
        except FileNotFoundError:
            typer.echo("未找到 'lata'，回退到命令行模式。", err=True)
        # except Exception as e:
        #     typer.echo(f"启动 lata 失败: {e}，回退到命令行模式。", err=True)

    all_paths = _resolve_paths(paths, clipboard)
    if not all_paths:
        logger.info("[#error_log] ❌ 未提供任何路径")
        raise typer.Exit(code=1)
    valid_paths = process_paths(all_paths)
    if not valid_paths:
        logger.info("[#error_log] ❌ 没有有效的路径可处理")
        raise typer.Exit(code=1)
    report_generator = ReportGenerator()
    for p in valid_paths:
        logger.info("[#process] 🚀 开始处理目录: {}", p)
        process_directory(
            p,
            report_generator,
            create_shortcuts=create_shortcuts,
            enable_multi_main=enable_multi_main,
            name_only_mode=name_only_mode,
            trash_only=trash_only,
        )
        logger.info("[#process] ✨ 目录处理完成: {}", p)
        rpt = report_generator.save_report(p, report) if report else report_generator.save_report(p)
        if rpt:
            logger.info("[#process] 📝 报告已保存到: {}", rpt)
        else:
            logger.info("[#error_log] ❌ 保存报告失败")

@app.command(help="启动 Taskfile (lata) TUI 界面")
def tui() -> None:
    try:
        script_dir = Path(__file__).parent
        subprocess.run("lata", cwd=script_dir)
    except FileNotFoundError:
        typer.echo("未找到 'lata' 可执行文件，请确认已安装。", err=True)
    # except Exception as e:
    #     typer.echo(f"启动 lata 失败: {e}", err=True)

def run():  # 供外部调用
    app()

if __name__ == "__main__":  # pragma: no cover
    run()
