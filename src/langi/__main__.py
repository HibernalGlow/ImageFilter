from __future__ import annotations
import json
from pathlib import Path
from typing import List
import typer
from rich.console import Console
from rich.progress import Progress, BarColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn, TextColumn
from rich.table import Table
from rich.panel import Panel

from .client import CommandUmiOCRClient
from .detector import batch_detect, DEFAULT_SUFFIX_MAP, LanguageHeuristics

console = Console()
app = typer.Typer(add_completion=False, help="图片主要语言识别 (调用本地 Umi-OCR 可执行文件)")

def _run(paths: List[Path], output: Path | None, no_rename: bool, interactive: bool, hide: bool, raw: bool,
         mode: str, min_total: int, min_lang: int, min_prop: float, workers: int, utf8: bool):
    LanguageHeuristics.configure(min_total=min_total, min_lang=min_lang, min_prop=min_prop)
    all_files: List[Path] = []
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".jxl"}
    for p in paths:
        if p.is_dir():
            for f in p.rglob('*'):
                if f.suffix.lower() in exts:
                    all_files.append(f)
        else:
            if p.suffix.lower() in exts:
                all_files.append(p)
    if not all_files:
        typer.echo("未找到图片文件")
        raise typer.Exit(code=1)
    client = CommandUmiOCRClient(hide=hide, mode=mode.lower(), enforce_utf8=utf8)

    file_list = [str(p) for p in all_files]
    results = []
    if interactive and not raw:
        console.print(Panel(f"共找到 [bold]{len(file_list)}[/] 张图片，开始识别", title="Langi"))
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            transient=True,
            console=console,
        )
        with progress:
            task_id = progress.add_task("OCR", total=len(file_list))
            def _cb(idx: int, total: int, path: str):  # noqa: D401
                progress.update(task_id, advance=1, description=f"OCR {idx}/{total}")
            results = batch_detect(file_list, client=client, rename=not no_rename,
                                   suffix_map=DEFAULT_SUFFIX_MAP, output_json=None, progress=_cb, workers=workers)
        # 表格展示
        table = Table(title="识别结果", show_lines=False)
        table.add_column("#", justify="right", style="cyan", no_wrap=True)
        table.add_column("文件")
        table.add_column("语言", style="magenta")
        table.add_column("长度", justify="right")
        table.add_column("重命名后")
        lang_color = {"chinese": "green", "english": "yellow", "japanese": "blue", "unknown": "red"}
        for i, info in enumerate(results, 1):
            lang = info.get("language", "unknown")
            lang_disp = f"[{lang_color.get(lang,'white')}]" + lang + "[/]"
            table.add_row(str(i), Path(info["path"]).name, lang_disp, str(info.get("text_length", 0)),
                          Path(info.get("renamed_path", info["path"])).name)
        console.print(table)
    else:
        results = batch_detect(
            file_list,
            client=client,
            rename=not no_rename,
            suffix_map=DEFAULT_SUFFIX_MAP,
            output_json=None,
            workers=workers,
        )

    # 输出 JSON（文件 + 控制台）
    if output:
        try:
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            if interactive and not raw:
                console.print(f"结果已写入: [bold]{output}[/]")
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]写入 JSON 失败: {e}[/]")
    # 最终标准输出 JSON（raw 模式仅这一行）
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2))

@app.callback()
def main_cb():
    """图片主要语言识别工具。使用命令:

    langi detect <图片或文件夹...> [选项]

    通过 'langi detect --help' 查看参数。
    """
    # 不解析位置参数，避免与子命令冲突
    return

@app.command("detect")
def detect_cmd(
    paths: List[Path] = typer.Argument(..., exists=True, readable=True, resolve_path=True, help="图片文件或目录，可多个"),
    output: Path = typer.Option(None, "-o", "--output", help="结果写出 JSON 文件"),
    no_rename: bool = typer.Option(False, "--no-rename", help="不对文件重命名"),
    interactive: bool = typer.Option(True, "--no-interactive", flag_value=False, help="关闭交互式 Rich 输出"),
    hide: bool = typer.Option(False, "--hide", help="调用 Umi-OCR 时附加 --hide"),
    raw: bool = typer.Option(False, "--raw", help="只输出 JSON，不显示表格/额外文字"),
    mode: str = typer.Option("stdout", "--mode", help="调用模式: stdout|file|clip", case_sensitive=False),
    workers: int = typer.Option(1, "--workers", help="并发 worker 数(>1 开启并发)"),
    utf8: bool = typer.Option(True, "--no-utf8", flag_value=False, help="关闭对子进程 UTF-8 强制 (默认开启)"),
    min_total: int = typer.Option(5, "--min-total", help="最少总字符数"),
    min_lang: int = typer.Option(3, "--min-lang", help="某语言最少字符数"),
    min_prop: float = typer.Option(0.5, "--min-prop", help="某语言最少占比(0-1)"),
):
    _run(paths, output, no_rename, interactive, hide, raw, mode, min_total, min_lang, min_prop, workers, utf8)


def main():  # 供入口点
    app()

if __name__ == "__main__":
    main()
